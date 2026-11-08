import argparse
import importlib
import json
import os
from pathlib import Path
import re

from verify_ui_integration import chain, ordinary, sha, verify, wording_contract

B = Path('/home/frappe/frappe-bench')
U = Path('/home/frappe/u030')
PATCHES = U / 'frontend-patches'
STATE = Path('/home/frappe/ui-base-state.json')


def source_manifest():
    manifest = json.loads((U / 'ui-source-manifest.json').read_bytes())
    for name, digest in manifest['files'].items():
        if sha(ordinary(U / name, U).read_bytes()) != digest:
            raise RuntimeError('Exported UI source drift: ' + name)
    contract = wording_contract(U / 'deploy')
    if manifest['wording'] != contract or any(manifest['overlays'].get(path) != entry['after'] for path, entry in contract['targets'].items()):
        raise RuntimeError('Final wording contract differs')
    return manifest


def snapshot():
    source_manifest()
    paths = set()
    for name in ('full951-manifest.json', 'm29-a512-manifest.json', 'final-source-manifest.json', 'print-a174-manifest.json'):
        data = json.loads((Path('/home/frappe') / name).read_bytes())
        paths.update(path for path in data['files'] if path.startswith('apps/'))
    sources = {name: sha(ordinary(B / name, B).read_bytes()) for name in sorted(paths)}
    original = json.loads(Path('/home/frappe/m24-modal-manifest.json').read_bytes())
    assets = {}
    for entry in original['asset_proof'].values():
        name = entry['url'].removeprefix('/assets/')
        assets[name] = sha((B / 'assets' / name).read_bytes())
    manifest = json.loads((B / 'assets/assets.json').read_bytes())
    STATE.write_text(json.dumps(dict(sources=sources, assets=assets, manifest=manifest), sort_keys=True) + '\n')
    verify(B / 'apps/crm', PATCHES, 'l3-scheduling')
    print('PASS: fixed five-app baseline snapshot after original verifier')


def apply_wording():
    manifest = source_manifest()
    changes = []
    for name, entry in manifest['wording']['targets'].items():
        target = ordinary(B / name, B)
        source = ordinary(U / 'wording-overlays' / name, U)
        data = source.read_bytes()
        if sha(target.read_bytes()) != entry['before'] or sha(data) != entry['after']:
            raise RuntimeError('Ordered wording before/after mismatch: ' + name)
        changes.append((target, data))
    pending = []
    try:
        for target, data in changes:
            temporary = target.with_name(target.name + '.wording-tmp')
            with temporary.open('xb') as stream:
                stream.write(data)
            pending.append((temporary, target))
        for temporary, target in pending:
            os.replace(temporary, target)
    finally:
        for temporary, _ in pending:
            if temporary.exists():
                temporary.unlink()
    print('PASS: five exact wording overlays after reviewed dark UI baseline')


def check(assets=False):
    manifest = source_manifest()
    state = json.loads(STATE.read_bytes())
    expected = dict(state['sources'])
    expected.update(manifest['overlays'])
    expected.update({'apps/crm/' + path: value for path, value in chain(PATCHES)['branding'].items()})
    for name, digest in expected.items():
        if sha(ordinary(B / name, B).read_bytes()) != digest:
            raise RuntimeError('Five-app source/guard drift: ' + name)
    canonical = B / 'apps/team_schedule/team_schedule/public/crm-theme.css'
    if canonical.read_bytes() != (PATCHES / 'dark-ui/payload/crm-theme.css').read_bytes():
        raise RuntimeError('Missing or changed canonical shared theme')
    dictionary = B / 'apps/team_schedule/team_schedule/public/crm-zh-cn.js'
    if sha(dictionary.read_bytes()) != manifest['overlays']['apps/team_schedule/team_schedule/public/crm-zh-cn.js']:
        raise RuntimeError('Missing or changed standalone dictionary')
    for name, version in (('frappe', '15.125.0'), ('crm', '1.90.0'), ('resource_import', '0.1.0'), ('team_access', '0.1.0'), ('team_schedule', '0.1.0')):
        if importlib.import_module(name).__version__ != version:
            raise RuntimeError('App version changed: ' + name)
    if (B / 'sites/apps.txt').read_text() != 'frappe\ncrm\nresource_import\nteam_access\nteam_schedule\n':
        raise RuntimeError('App registry changed')
    verify(B / 'apps/crm', PATCHES)
    if assets:
        root_manifest = json.loads((B / 'assets/assets.json').read_bytes())
        site_manifest = json.loads((B / 'sites/assets/assets.json').read_bytes())
        if root_manifest != site_manifest or any(root_manifest.get(key) != value for key, value in state['manifest'].items()):
            raise RuntimeError('Original Framework asset mappings were lost')
        for directory in ('assets', 'sites/assets'):
            root = B / directory
            for value in root_manifest.values():
                if not isinstance(value, str) or not value.startswith('/assets/') or not (root / value.removeprefix('/assets/')).is_file():
                    raise RuntimeError('Mapped static asset missing')
            for name, digest in state['assets'].items():
                app, filename = name.split('/', 1)
                source = f'apps/{app}/{app}/public/{filename}'
                expected_digest = manifest['overlays'].get(source, digest)
                if sha((root / name).read_bytes()) != expected_digest:
                    raise RuntimeError('Original static asset changed unexpectedly: ' + name)
            for app, names in {'team_schedule': ('crm-theme.css', 'crm-zh-cn.js', 'team-schedule.css', 'team-schedule.js'), 'team_access': ('access.js', 'page.js'), 'crm': ('css/login-theme.css',)}.items():
                for name in names:
                    source = B / 'apps' / app / app / 'public' / name
                    if not source.is_file() or (root / app / name).read_bytes() != source.read_bytes():
                        raise RuntimeError('New static asset missing or differs: ' + app + '/' + name)
        html = (B / 'apps/crm/crm/www/crm.html').read_text()
        if '<title>哲人石CRM</title>' not in html or 'boot.philosopher_language' not in html:
            raise RuntimeError('Built CRM HTML branding/locale missing')
        references = re.findall(r'(?:src|href)=[\"\'](/assets/crm/[^\"\']+)', html)
        if not references:
            raise RuntimeError('Built CRM HTML has no asset references')
        for value in references:
            if not (B / 'assets' / value.removeprefix('/assets/')).is_file():
                raise RuntimeError('Built CRM HTML references a missing asset: ' + value)
        pwa = json.loads((B / 'assets/crm/frontend/manifest.webmanifest').read_bytes())
        if pwa.get('name') != '哲人石CRM' or pwa.get('short_name') != '哲人石CRM':
            raise RuntimeError('Built PWA install branding missing')
    print('PASS: fixed five-app sources, ordered hashes, five wording targets, canonical theme/dictionary' + (' and complete static assets' if assets else ''))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=('snapshot', 'wording', 'source', 'assets'))
    args = parser.parse_args()
    if args.phase == 'snapshot':
        snapshot()
    elif args.phase == 'wording':
        apply_wording()
    else:
        check(args.phase == 'assets')

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

B = Path('/home/frappe/frappe-bench')
U = Path('/home/frappe/common-ui')
PARENT = Path('/home/frappe/u030')
CATALOG = 'frontend/src/philosopher-zh-cn.json'
CATALOG_BEFORE = 'ea598fe9e1b8c7a10ddd57e8c35950c30bc8462fe1e12ae3f3b2cbe6a8f6b551'
TARGETS = frozenset({
    'frontend/src/components/Notifications.vue',
    'frontend/src/components/Activities/DataFields.vue',
    'frontend/src/components/Filter.vue',
    'frontend/src/components/IconPicker.vue',
})


def sha(data):
    return hashlib.sha256(data).hexdigest()


def entries(root):
    items = json.loads((root / 'frontend-patches/common-ui-localization/manifest.json').read_bytes())
    if not isinstance(items, list) or len(items) != 4 or {item.get('target') for item in items} != TARGETS:
        raise RuntimeError('Common UI target whitelist differs')
    for item in items:
        if set(item) != {'target', 'before', 'after'} or any(not isinstance(item[key], str) or len(item[key]) != 64 or any(c not in '0123456789abcdef' for c in item[key]) for key in ('before', 'after')):
            raise RuntimeError('Common UI target schema differs')
    return items


def catalog_contract(root):
    items = json.loads((root / 'frontend-patches/localization/manifest.json').read_bytes())
    expected = {
        'crm/www/crm.py': ('6a908a9c7b05151bd7760e2bf329230ccabf9d25a804376df8a24f990ac98020', '5eda918e55a72ca318fd6800d302a6545f4181c7c8fa2e33816b585a099e79d3'),
        'frontend/src/translation.js': ('2732096397614d78764b18128ad6999b1fc577d35bd548b726a17606dbc5e619', '1b1ef1412b20df6071a1ee3f6058a17d8d4d0071a135ca6a62195cbdeb0e135c'),
    }
    if len(items) != 3 or {item.get('target') for item in items} != set(expected) | {CATALOG}:
        raise RuntimeError('Localization manifest target set differs')
    for item in items:
        if set(item) != {'target', 'before', 'after'}:
            raise RuntimeError('Localization manifest schema differs')
        if item['target'] in expected and (item['before'], item['after']) != expected[item['target']]:
            raise RuntimeError('Common UI must not change existing locale implementation')
    item = next(item for item in items if item['target'] == CATALOG)
    data = (root / 'frontend-patches/localization/zh-CN.json').read_bytes()
    if item['before'] is not None or item['after'] != sha(data):
        raise RuntimeError('Common UI catalog differs from its exact manifest')
    return dict(target=CATALOG, before=CATALOG_BEFORE, after=item['after'])


def ordinary(path, root):
    if not path.parent.resolve(strict=True).is_relative_to(root.resolve(strict=True)):
        raise RuntimeError('Common UI source escapes root')
    for item in (path, *path.parents):
        if item.is_symlink() or (item.exists() and getattr(item.lstat(), 'st_file_attributes', 0) & 0x400):
            raise RuntimeError('Linked common UI source refused')
    if not path.is_file() or path.stat().st_nlink != 1:
        raise RuntimeError('Common UI source must be an ordinary file')
    return path


def apply_catalog(bench, source, mode):
    entry = catalog_contract(source)
    target = ordinary(bench / 'apps/crm' / CATALOG, bench)
    current = target.read_bytes()
    if sha(current) != entry['after' if mode == 'verify' else 'before']:
        raise RuntimeError('Common UI catalog predecessor differs')
    updated = (source / 'frontend-patches/localization/zh-CN.json').read_bytes()
    if mode != 'verify':
        old, new = json.loads(current), json.loads(updated)
        if any(new.get(key) != value for key, value in old.items()):
            raise RuntimeError('Common UI catalog overwrites an existing reviewed key')
    temporary = target.with_name(target.name + '.common-ui-catalog-tmp')
    if os.path.lexists(temporary):
        raise RuntimeError('Common UI catalog temporary already exists')
    if mode == 'apply':
        owned = False
        try:
            with temporary.open('xb') as stream:
                owned = True
                stream.write(updated)
            os.replace(temporary, target)
        finally:
            if owned:
                temporary.unlink(missing_ok=True)
    print('PASS exact existing catalog -> common UI catalog (' + mode + ')')


def expected_sources(bench, source, parent):
    sys.path.insert(0, str(parent / 'deploy'))
    from verify_ui_integration import chain, framework_entries
    baseline = json.loads(Path('/home/frappe/ui-base-state.json').read_bytes())
    manifest = json.loads((parent / 'ui-source-manifest.json').read_bytes())
    expected = dict(baseline['sources'])
    expected.update(manifest['overlays'])
    expected.update({'apps/crm/' + path: value for path, value in chain(parent / 'frontend-patches')['branding'].items()})
    expected[manifest['access_version']['target']] = manifest['access_version']['after']
    expected.update({'apps/frappe/' + entry['target']: entry['after'] for entry in framework_entries(parent / 'frontend-patches')})
    expected.update({'apps/crm/' + entry['target']: entry['after'] for entry in entries(source)})
    expected['apps/crm/' + CATALOG] = catalog_contract(source)['after']
    return expected


def verify_sources(bench, source, parent):
    manifest = json.loads((source / 'common-ui-source-manifest.json').read_bytes())
    for name, digest in manifest['files'].items():
        if sha(ordinary(source / name, source).read_bytes()) != digest:
            raise RuntimeError('Exported common UI input changed: ' + name)
    if manifest['targets'] != entries(source) or manifest['catalog'] != catalog_contract(source):
        raise RuntimeError('Common UI source manifest contract changed')
    if subprocess.check_output(['git', '-C', str(bench / 'apps/crm'), 'rev-parse', 'HEAD'], text=True).strip() != '36bd8859f2a6345a620477bc708d0546e8c3f08a':
        raise RuntimeError('Common UI CRM HEAD differs')
    for name, digest in expected_sources(bench, source, parent).items():
        if sha(ordinary(bench / name, bench).read_bytes()) != digest:
            raise RuntimeError('Existing deployed source or common UI source drift: ' + name)
    print('PASS inherited deployed five-app/CRM/Framework/brand/request guards with four explicit common UI changes and catalog')


def snapshot():
    state = {'manifest': json.loads((B / 'assets/assets.json').read_bytes()), 'assets': {}}
    for root in (B / 'assets/team_access', B / 'assets/team_schedule'):
        for path in root.rglob('*'):
            if path.is_file():
                state['assets'][path.relative_to(B / 'assets').as_posix()] = sha(path.read_bytes())
    (U / 'asset-baseline.json').write_text(json.dumps(state, sort_keys=True) + '\n')
    print('PASS deployed asset mapping and standalone asset baseline')


def verify_assets():
    verify_sources(B, U, PARENT)
    baseline = json.loads((U / 'asset-baseline.json').read_bytes())
    manifests = [json.loads((B / name / 'assets.json').read_bytes()) for name in ('assets', 'sites/assets')]
    if manifests[0] != manifests[1] or any(manifests[0].get(key) != value for key, value in baseline['manifest'].items()):
        raise RuntimeError('Common UI build lost inherited Framework mappings')
    for directory in ('assets', 'sites/assets'):
        root = B / directory
        for url in manifests[0].values():
            if not isinstance(url, str) or not url.startswith('/assets/') or not (root / url.removeprefix('/assets/')).is_file():
                raise RuntimeError('Common UI mapped asset missing')
        for name, digest in baseline['assets'].items():
            if sha((root / name).read_bytes()) != digest:
                raise RuntimeError('Unchanged standalone asset drift: ' + name)
    print('PASS common UI final assets and unchanged standalone mappings/assets')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=('catalog-check', 'catalog-apply', 'catalog-verify', 'snapshot', 'sources', 'assets'))
    args = parser.parse_args()
    if args.phase.startswith('catalog-'):
        apply_catalog(B, U, args.phase.removeprefix('catalog-'))
    elif args.phase == 'snapshot':
        snapshot()
    elif args.phase == 'sources':
        verify_sources(B, U, PARENT)
    else:
        verify_assets()

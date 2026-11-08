import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

CRM_COMMIT = '36bd8859f2a6345a620477bc708d0546e8c3f08a'
ORDER = ('c011000', 'l3-scheduling', 'dark-ui', 'localization', 'branding')
TARGETS = {
    'dark-ui': frozenset({'frontend/src/App.vue', 'frontend/src/index.css', 'frontend/src/components/UserDropdown.vue', 'frontend/src/crm-theme.css'}),
    'localization': frozenset({'crm/www/crm.py', 'frontend/src/translation.js', 'frontend/src/philosopher-zh-cn.json'}),
    'branding': frozenset({'frontend/index.html', 'crm/hooks.py', 'crm/ui_branding.py', 'crm/public/css/login-theme.css'}),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def ordinary(path, root):
    if not path.parent.resolve(strict=True).is_relative_to(root.resolve(strict=True)):
        raise RuntimeError('Source parent escapes root')
    for item in (path, *path.parents):
        if item.is_symlink() or (item.exists() and getattr(item.lstat(), 'st_file_attributes', 0) & 0x400):
            raise RuntimeError('Linked source refused')
    if path.exists() and (not path.is_file() or path.stat().st_nlink != 1):
        raise RuntimeError('Source must be an ordinary non-hardlinked file')
    return path


def relative(value):
    if not isinstance(value, str):
        raise RuntimeError('Source path must be text')
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or '..' in path.parts or '\\' in value or ':' in value:
        raise RuntimeError('Unsafe source path')
    return value


def digest(value, nullable=False):
    if nullable and value is None:
        return
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise RuntimeError('Invalid SHA256')


def entries(patches):
    result = {}
    cache_raw = (patches / 'c011000/manifest.json').read_bytes()
    if sha(cache_raw) != '2060a0f99a778797e8c2b2f97527ccc6bbf96288b7a23362d9319096fde177a3':
        raise RuntimeError('U030 requires the exact M24 production manifest')
    cache = json.loads(cache_raw)
    if len(cache) != 43 or len({e['target'] for e in cache}) != 43:
        raise RuntimeError('U030 requires all 43 M24 entries, never the legacy patch')
    result['c011000'] = cache
    nav_raw = (patches / 'l3-scheduling/manifest.json').read_bytes()
    if sha(nav_raw) != '74787afa31373457e9b91fa8ea6f53e4e3317854670656558579df0762b75670':
        raise RuntimeError('U030 requires the exact M30 navigation manifest')
    nav = json.loads(nav_raw)
    if nav['crm_commit'] != CRM_COMMIT or len(nav['targets']) != 1:
        raise RuntimeError('Unexpected navigation patch')
    item = nav['targets'][0]
    if item['target'] != 'frontend/src/components/Layouts/AppSidebar.vue':
        raise RuntimeError('Unexpected navigation target')
    baseline = next(b for b in item['baselines'] if b['name'] == 'c011000-resume')
    result['l3-scheduling'] = [dict(target=item['target'], before=baseline['before'], after=baseline['after'])]
    for name in ORDER[2:]:
        manifest = json.loads((patches / name / 'manifest.json').read_text(encoding='utf-8'))
        if name == 'localization':
            if not isinstance(manifest, list) or any(set(entry) != {'target', 'before', 'after'} for entry in manifest):
                raise RuntimeError('Unexpected localization manifest schema')
            items = manifest
            catalog = ordinary(patches / name / 'zh-CN.json', patches / name)
            catalog_entry = next(entry for entry in items if entry['target'] == 'frontend/src/philosopher-zh-cn.json')
            if sha(catalog.read_bytes()) != catalog_entry['after']:
                raise RuntimeError('Localization catalog SHA mismatch')
        else:
            if manifest['crm_commit'] != CRM_COMMIT or manifest['patch'] != name:
                raise RuntimeError('Unexpected patch identity')
            items = manifest['targets']
        actual = {e['target'] for e in items}
        if len(items) != len(actual) or actual != TARGETS[name]:
            raise RuntimeError('Unexpected ' + name + ' target whitelist')
        result[name] = items
    return result


def chain(patches):
    state = {}
    snapshots = {}
    for name, items in entries(patches).items():
        for entry in items:
            target = relative(entry['target'])
            digest(entry['before'], nullable=True)
            after = entry.get('after', entry['before'])
            digest(after)
            if target in state and state[target] != entry['before']:
                raise RuntimeError('Ordered overlap SHA mismatch: ' + name + ':' + target)
            state[target] = after
            if entry.get('payload'):
                payload = ordinary(patches / name / 'payload' / relative(entry['payload']), patches / name)
                if sha(payload.read_bytes()) != after:
                    raise RuntimeError('Payload SHA mismatch: ' + name + ':' + target)
        snapshots[name] = dict(state)
    return snapshots


def verify(root, patches, stage='branding'):
    if subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip() != CRM_COMMIT:
        raise RuntimeError('CRM HEAD differs from fixed upstream')
    expected = chain(patches)[stage]
    for target, value in expected.items():
        path = ordinary(root / target, root)
        if sha(path.read_bytes()) != value:
            raise RuntimeError('Integrated source mismatch: ' + target)
    print(f'PASS: ordered {stage} state, {len(expected)} exact sources and guards')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('crm_root', type=Path)
    parser.add_argument('patch_root', type=Path)
    parser.add_argument('--stage', choices=ORDER, default='branding')
    args = parser.parse_args()
    verify(args.crm_root, args.patch_root, args.stage)

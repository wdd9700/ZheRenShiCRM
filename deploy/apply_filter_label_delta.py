import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess

CRM_HEAD = '36bd8859f2a6345a620477bc708d0546e8c3f08a'
FILTER = 'frontend/src/components/Filter.vue'
CATALOG = 'frontend/src/philosopher-zh-cn.json'
BEFORE = {
    FILTER: '4a502a48935ab5312cdd9e5bfe6af000b92c7b25f0abb171aa4c8e21dc33fc1a',
    CATALOG: 'f07c9e466f23dbe2847c9549a4e35f7c645e2ae9d01e1b9a66761aef9fabdbc5',
}
AFTER = {
    FILTER: '82da91b378239ccc20b57a3f23292cbba856b02aed54a28b3c9e4f3709247fe6',
    CATALOG: '7f305884bed9519ef3f069fccbac7d69a0f163cd2a5a6a55fb3cba8c70fe033d',
}
UNCHANGED = {
    'frontend/src/components/Notifications.vue': 'f133d72297b14794e1740e280a56ff0f2bf2d453c7ce8c8eff5377e2dabcfecf',
    'frontend/src/components/Activities/DataFields.vue': '3c86c21bec986b13d87ae0c637acfc0ba2d25c5204a1acd591155128a29cfe08',
    'frontend/src/components/IconPicker.vue': '1ac702a3433270031ff50c4f58a792e5b962d55c29536e3e7fb7f1bc1cff688a',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def ordinary(root, relative):
    path = root / relative
    if not path.parent.resolve(strict=True).is_relative_to(root):
        raise RuntimeError('Filter delta source escapes root')
    for item in (path, *path.parents):
        if item.is_symlink() or (item.exists() and getattr(item.lstat(), 'st_file_attributes', 0) & 0x400):
            raise RuntimeError('Linked filter delta source refused')
    if not path.is_file() or path.stat().st_nlink != 1:
        raise RuntimeError('Filter delta source must be an ordinary file')
    return path


def inputs(patches):
    manifest = json.loads((patches / 'common-ui-localization/manifest.json').read_bytes())
    if len(manifest) != 4 or {entry.get('target') for entry in manifest} != set(UNCHANGED) | {FILTER}:
        raise RuntimeError('Unexpected common UI target set')
    for entry in manifest:
        expected = AFTER[FILTER] if entry['target'] == FILTER else UNCHANGED[entry['target']]
        if set(entry) != {'target', 'before', 'after'} or entry['after'] != expected:
            raise RuntimeError('Unexpected reviewed common UI after contract')
    catalog = (patches / 'localization/zh-CN.json').read_bytes()
    if sha(catalog) != AFTER[CATALOG]:
        raise RuntimeError('Reviewed filter catalog differs')
    spec = importlib.util.spec_from_file_location('focused_filter_common_transform', patches / 'common-ui-localization/apply.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, catalog, next(entry['before'] for entry in manifest if entry['target'] == FILTER)


def replacements(root, patches):
    transformer, catalog, original_digest = inputs(patches)
    current = ordinary(root, FILTER).read_bytes()
    if sha(current) != BEFORE[FILTER]:
        raise RuntimeError('Deployed Filter predecessor differs; do not replay original patch')
    patched_check = b"        label: fieldtype == 'Check' ? __(o) : o,\n        value: o,"
    original_check = b'        label: o,\n        value: o,'
    if current.count(patched_check) != 1:
        raise RuntimeError('Deployed Filter Check anchor differs')
    original = current.replace(patched_check, original_check, 1)
    if sha(original) != original_digest:
        raise RuntimeError('Reconstructed fixed upstream Filter differs')
    updated = transformer.transform(FILTER, original)
    if sha(updated) != AFTER[FILTER]:
        raise RuntimeError('Filter label after differs')
    old_catalog = ordinary(root, CATALOG).read_bytes()
    if sha(old_catalog) != BEFORE[CATALOG]:
        raise RuntimeError('Deployed filter catalog predecessor differs')
    old, new = json.loads(old_catalog), json.loads(catalog)
    if any(new.get(key) != value for key, value in old.items()):
        raise RuntimeError('Filter label catalog overwrites an existing key')
    return {FILTER: updated, CATALOG: catalog}


def apply(root, patches, mode='apply'):
    root, patches = root.resolve(strict=True), patches.resolve(strict=True)
    if subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip() != CRM_HEAD:
        raise RuntimeError('Filter delta CRM HEAD differs')
    inputs(patches)
    for name, digest in UNCHANGED.items():
        if sha(ordinary(root, name).read_bytes()) != digest:
            raise RuntimeError('Unchanged deployed common UI source drift: ' + name)
    if mode == 'verify':
        for name, digest in AFTER.items():
            if sha(ordinary(root, name).read_bytes()) != digest:
                raise RuntimeError('Filter delta final source differs: ' + name)
        return
    changes = replacements(root, patches)
    paths = []
    for name in changes:
        target = ordinary(root, name)
        temporary = target.with_name(target.name + '.filter-label-tmp')
        backup = target.with_name(target.name + '.filter-label-backup')
        if os.path.lexists(temporary) or os.path.lexists(backup):
            raise RuntimeError('Filter delta temporary path already exists')
        paths.append((target, temporary, backup, target.read_bytes(), changes[name]))
    if mode == 'check':
        return
    owned, committed, preserve = set(), [], set()
    try:
        for target, temporary, backup, original, updated in paths:
            for path, content in ((temporary, updated), (backup, original)):
                with path.open('xb') as stream:
                    owned.add(path)
                    stream.write(content)
        for target, temporary, backup, _, _ in paths:
            os.replace(temporary, target)
            owned.remove(temporary)
            committed.append((target, backup))
    except BaseException as error:
        failures = []
        for target, backup in reversed(committed):
            try:
                os.replace(backup, target)
                owned.remove(backup)
            except OSError as rollback_error:
                preserve.add(backup)
                failures.append(str(rollback_error))
        if failures:
            raise RuntimeError('Filter rollback incomplete; originals retained') from error
        raise
    finally:
        for path in owned - preserve:
            path.unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('crm_root', type=Path)
    parser.add_argument('patch_root', type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--check', action='store_true')
    modes.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    apply(args.crm_root, args.patch_root, 'check' if args.check else 'verify' if args.verify else 'apply')
    print('PASS exact deployed35d0 Filter/catalog delta; unchanged common UI guards retained')

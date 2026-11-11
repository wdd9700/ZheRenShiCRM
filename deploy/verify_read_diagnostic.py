import argparse
import hashlib
import json
import os
from pathlib import Path

DIAGNOSTIC_TARGETS = frozenset({
    'frontend/node_modules/frappe-ui/src/resources/accountBoundary.js',
    'frontend/node_modules/frappe-ui/src/resources/resources.js',
    'frontend/node_modules/frappe-ui/src/utils/request.ts',
    'frontend/node_modules/frappe-ui/src/utils/frappeRequest.ts',
})


def sha(data):
    return hashlib.sha256(data).hexdigest()


def ordinary(root, relative):
    path = root / relative
    if not path.parent.resolve(strict=True).is_relative_to(root):
        raise RuntimeError('Diagnostic target escapes CRM')
    for item in (path, *path.parents):
        if item.is_symlink() or (item.exists() and getattr(item.lstat(), 'st_file_attributes', 0) & 0x400):
            raise RuntimeError('Linked diagnostic target refused')
    if not path.is_file() or path.stat().st_nlink != 1:
        raise RuntimeError('Diagnostic target must be an ordinary existing file')
    return path


def contract(source):
    data = json.loads((source / 'read-diagnostic-delta.json').read_bytes())
    if set(data) != {'source_revision', 'targets', 'temporary', 'default_enabled'} or data['temporary'] is not True or data['default_enabled'] is not False:
        raise RuntimeError('Diagnostic contract must remain temporary and default disabled')
    if not isinstance(data['source_revision'], str) or len(data['source_revision']) != 40 or any(c not in '0123456789abcdef' for c in data['source_revision']):
        raise RuntimeError('Diagnostic source must be an exact commit')
    entries = data['targets']
    if not isinstance(entries, list) or len(entries) != len(DIAGNOSTIC_TARGETS) or {entry.get('target') for entry in entries} != DIAGNOSTIC_TARGETS:
        raise RuntimeError('Diagnostic target whitelist differs')
    for entry in entries:
        if set(entry) != {'target', 'before', 'after', 'payload'} or entry['payload'] != entry['target'].replace('/', '__'):
            raise RuntimeError('Diagnostic entry schema differs')
        for key in ('before', 'after'):
            value = entry[key]
            if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
                raise RuntimeError('Diagnostic SHA is invalid')
        if sha((source / 'diagnostic-payloads' / entry['payload']).read_bytes()) != entry['after']:
            raise RuntimeError('Diagnostic payload differs')
    return data


def apply(root, source, mode='apply'):
    root = root.resolve(strict=True)
    data = contract(source)
    changes = []
    for entry in data['targets']:
        target = ordinary(root, entry['target'])
        current = target.read_bytes()
        if sha(current) != entry['after' if mode == 'verify' else 'before']:
            raise RuntimeError('Diagnostic predecessor/final source differs: ' + entry['target'])
        temporary = target.with_name(target.name + '.read-diagnostic-tmp')
        backup = target.with_name(target.name + '.read-diagnostic-backup')
        if os.path.lexists(temporary) or os.path.lexists(backup):
            raise RuntimeError('Existing diagnostic temporary path refused')
        changes.append((target, temporary, backup, current, (source / 'diagnostic-payloads' / entry['payload']).read_bytes()))
    if mode in ('check', 'verify'):
        return
    owned, committed, preserve = set(), [], set()
    try:
        for _, temporary, backup, original, updated in changes:
            for path, content in ((temporary, updated), (backup, original)):
                with path.open('xb') as stream:
                    owned.add(path)
                    stream.write(content)
        for target, temporary, backup, _, _ in changes:
            os.replace(temporary, target)
            owned.remove(temporary)
            committed.append((target, backup))
    except BaseException as error:
        failed = False
        for target, backup in reversed(committed):
            try:
                os.replace(backup, target)
                owned.remove(backup)
            except OSError:
                preserve.add(backup)
                failed = True
        if failed:
            raise RuntimeError('Diagnostic rollback incomplete; original backups retained') from error
        raise
    finally:
        for path in owned - preserve:
            path.unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('crm_root', type=Path)
    parser.add_argument('source_root', type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    apply(args.crm_root, args.source_root, 'check' if args.check else 'verify' if args.verify else 'apply')
    print('PASS exact four-source temporary default-off diagnostic delta; no runtime activation')

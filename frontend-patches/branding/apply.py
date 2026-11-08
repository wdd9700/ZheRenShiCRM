import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
COMMIT = '36bd8859f2a6345a620477bc708d0546e8c3f08a'
TARGETS = {'frontend/index.html', 'crm/hooks.py', 'crm/ui_branding.py', 'crm/public/css/login-theme.css'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def transform(current, entry):
    if entry.get('payload'):
        updated = (HERE / 'payload' / entry['payload']).read_bytes()
    else:
        updated = current
        for edit in entry['edits']:
            anchor = edit['anchor'].encode('utf-8')
            if updated.count(anchor) != 1:
                raise ValueError('Ambiguous or missing anchor: ' + entry['target'])
            updated = updated.replace(anchor, edit['replacement'].encode('utf-8'), 1)
    if sha(updated) != entry['after']:
        raise ValueError('Branding result SHA mismatch: ' + entry['target'])
    return updated


def apply(root, check=False, verify_after=False):
    root = root.resolve(strict=True)
    if subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip() != COMMIT:
        raise ValueError('CRM HEAD mismatch')
    manifest = json.loads((HERE / 'manifest.json').read_text(encoding='utf-8'))
    entries = manifest['targets']
    if manifest['crm_commit'] != COMMIT or len(entries) != len(TARGETS) or {e['target'] for e in entries} != TARGETS:
        raise ValueError('Branding target whitelist mismatch')
    changes = []
    for entry in entries:
        target = root / entry['target']
        parent = target.parent.resolve(strict=True)
        if not parent.is_relative_to(root):
            raise ValueError('Parent escapes CRM')
        for item in (target, *target.parents):
            if item.is_symlink() or (item.exists() and getattr(item.lstat(), 'st_file_attributes', 0) & 0x400):
                raise ValueError('Linked branding source refused')
        if target.exists() and (not target.is_file() or target.stat().st_nlink != 1):
            raise ValueError('Branding target must be an ordinary file')
        current = target.read_bytes() if target.exists() else None
        if (sha(current) if current is not None else None) != entry['after' if verify_after else 'before']:
            raise ValueError('Branding baseline mismatch: ' + entry['target'])
        if not verify_after:
            changes.append((target, transform(current, entry)))
        elif entry.get('payload'):
            transform(None, entry)
    if not check and not verify_after:
        pending = []
        try:
            for target, data in changes:
                temporary = target.with_name(target.name + '.branding-tmp')
                with temporary.open('xb') as stream:
                    stream.write(data)
                pending.append((temporary, target))
            for temporary, target in pending:
                os.replace(temporary, target)
        finally:
            for temporary, _ in pending:
                if temporary.exists():
                    temporary.unlink()
    return len(entries)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('crm_root', type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--verify-after', action='store_true')
    args = parser.parse_args()
    print('PASS: %d exact branding targets' % apply(args.crm_root, args.check, args.verify_after))

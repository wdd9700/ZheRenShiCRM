import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
COMMIT = '36bd8859f2a6345a620477bc708d0546e8c3f08a'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def apply(root, check=False):
    root = root.resolve(strict=True)
    if not (root / 'frontend').is_dir():
        raise ValueError('CRM root/frontend required')
    head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    if head != COMMIT:
        raise ValueError('CRM HEAD mismatch')
    manifest = json.loads((HERE / 'manifest.json').read_text(encoding='utf-8'))
    changes = []
    for entry in manifest:
        target = root / entry['target']
        parent = target.parent.resolve(strict=True)
        if not parent.is_relative_to(root) or target.is_symlink():
            raise ValueError('Target escapes CRM root or is a symlink: ' + entry['target'])
        if target.exists() and target.stat().st_nlink > 1:
            raise ValueError('Hard-linked target refused: ' + entry['target'])
        current = target.read_bytes() if target.exists() else None
        expected = entry['before']
        if (sha(current) if current is not None else None) != expected:
            raise ValueError('Baseline mismatch: ' + entry['target'])
        if entry.get('payload'):
            replacement = (HERE / 'payload' / entry['payload']).read_bytes()
            if sha(replacement) != entry['after']:
                raise ValueError('Patch payload mismatch: ' + entry['payload'])
            changes.append((target, replacement))
    if not check:
        for target, data in changes:
            temporary = target.with_name(target.name + '.c011000-tmp')
            with temporary.open('xb') as stream:
                stream.write(data)
            os.replace(temporary, target)
    return len(changes)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('crm_root', type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        count = apply(args.crm_root, args.check)
        print(('Baseline verified' if args.check else 'Patch applied') + f': {count} files')
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print('C011000 REFUSED: ' + str(error), file=sys.stderr)
        sys.exit(1)

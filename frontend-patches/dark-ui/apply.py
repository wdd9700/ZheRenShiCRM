import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
COMMIT = '36bd8859f2a6345a620477bc708d0546e8c3f08a'
TARGETS = {
    'frontend/src/App.vue',
    'frontend/src/index.css',
    'frontend/src/components/UserDropdown.vue',
    'frontend/src/crm-theme.css',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def target_path(root, relative):
    candidate = root / relative
    if not candidate.parent.resolve(strict=True).is_relative_to(root):
        raise ValueError('Parent escapes CRM root: ' + relative)
    if candidate.is_symlink() or (candidate.exists() and candidate.stat().st_nlink > 1):
        raise ValueError('Linked target refused: ' + relative)
    return candidate


def transform(data, entry):
    if entry.get('payload'):
        replacement = (HERE / 'payload' / entry['payload']).read_bytes()
    else:
        replacement = data
        for edit in entry['edits']:
            anchor = edit['anchor'].encode('utf-8')
            if replacement.count(anchor) != 1:
                raise ValueError('Ambiguous or missing anchor: ' + entry['target'])
            replacement = replacement.replace(anchor, edit['replacement'].encode('utf-8'), 1)
    if sha(replacement) != entry['after']:
        raise ValueError('After SHA mismatch: ' + entry['target'])
    return replacement


def verify_theme():
    payload = (HERE / 'payload' / 'crm-theme.css').read_bytes()
    canonical = HERE.parents[1] / 'apps/team_schedule/team_schedule/public/crm-theme.css'
    if canonical.exists() and canonical.read_bytes() != payload:
        raise ValueError('Canonical theme differs from CRM payload')


def apply(root, check=False, verify_after=False):
    root = root.resolve(strict=True)
    if not (root / 'frontend').is_dir():
        raise ValueError('CRM root/frontend required')
    if subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip() != COMMIT:
        raise ValueError('CRM HEAD mismatch')
    manifest = json.loads((HERE / 'manifest.json').read_text(encoding='utf-8'))
    if len(manifest['targets']) != 4 or {entry['target'] for entry in manifest['targets']} != TARGETS:
        raise ValueError('Unexpected dark-ui target set')
    verify_theme()
    guards = json.loads((HERE / 'prerequisites.json').read_text(encoding='utf-8'))
    if len(guards['targets']) != 43:
        raise ValueError('M24 production prerequisite set must contain 43 entries')
    for entry in guards['targets']:
        target = target_path(root, entry['target'])
        if not target.is_file() or sha(target.read_bytes()) != entry['sha256']:
            raise ValueError('M24/M30 prerequisite mismatch: ' + entry['target'])
    changes = []
    for entry in manifest['targets']:
        target = target_path(root, entry['target'])
        current = target.read_bytes() if target.exists() else None
        expected = entry['after'] if verify_after else entry['before']
        if (sha(current) if current is not None else None) != expected:
            raise ValueError('Baseline mismatch: ' + entry['target'])
        if not verify_after:
            changes.append((target, transform(current, entry)))
        elif entry.get('payload'):
            transform(None, entry)
    if not check and not verify_after:
        temporary = []
        try:
            for target, data in changes:
                path = target.with_name(target.name + '.dark-ui-tmp')
                with path.open('xb') as stream:
                    stream.write(data)
                temporary.append((path, target))
            for path, target in temporary:
                os.replace(path, target)
        finally:
            for path, _ in temporary:
                if path.exists():
                    path.unlink()
    return len(manifest['targets'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('crm_root', type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--verify-after', action='store_true')
    args = parser.parse_args()
    try:
        count = apply(args.crm_root, args.check, args.verify_after)
        print(('Verified' if args.check or args.verify_after else 'Applied') + f': {count} dark-ui targets; M24/M30 guards intact')
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        print('DARK-UI REFUSED: ' + str(error), file=sys.stderr)
        sys.exit(1)

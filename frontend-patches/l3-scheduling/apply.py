import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / 'manifest.json'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_manifest():
    return json.loads(MANIFEST.read_text(encoding='utf-8'))


def apply_edits(target, data):
    text = data.decode('utf-8')
    for edit in target['edits']:
        count = text.count(edit['anchor'])
        if count != 1:
            raise ValueError(
                'Edit anchor must appear exactly once (%d) in %s: %r'
                % (count, target['target'], edit['anchor'][:60])
            )
        text = text.replace(edit['anchor'], edit['replacement'])
    return text.encode('utf-8')


def plan(root, manifest):
    root = root.resolve(strict=True)
    if not (root / 'frontend').is_dir():
        raise ValueError('CRM root/frontend required')
    head = subprocess.check_output(
        ['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True
    ).strip()
    if head != manifest['crm_commit']:
        raise ValueError('CRM HEAD mismatch: ' + head)
    changes = []
    for target in manifest['targets']:
        path = root / target['target']
        parent = path.parent.resolve(strict=True)
        if not parent.is_relative_to(root) or path.is_symlink():
            raise ValueError(
                'Target escapes CRM root or is a symlink: ' + target['target']
            )
        if path.exists() and path.stat().st_nlink > 1:
            raise ValueError('Hard-linked target refused: ' + target['target'])
        if not path.exists():
            raise ValueError('Missing target: ' + target['target'])
        current = path.read_bytes()
        digest = sha(current)
        baseline = next(
            (item for item in target['baselines'] if item['before'] == digest),
            None,
        )
        if baseline is None:
            applied = [
                item['name']
                for item in target['baselines']
                if item['after'] == digest
            ]
            if applied:
                raise ValueError(
                    'Already applied (%s): %s' % (applied[0], target['target'])
                )
            raise ValueError(
                'Baseline mismatch: %s; accepted %s; got %s'
                % (
                    target['target'],
                    [item['before'] for item in target['baselines']],
                    digest,
                )
            )
        updated = apply_edits(target, current)
        if sha(updated) != baseline['after']:
            raise ValueError(
                'Result hash mismatch on baseline %s: %s'
                % (baseline['name'], target['target'])
            )
        changes.append((path, updated))
    return changes


def apply(root, check=False):
    changes = plan(root, load_manifest())
    if not check:
        for target, data in changes:
            temporary = target.with_name(target.name + '.l3-scheduling-tmp')
            with temporary.open('xb') as stream:
                stream.write(data)
            os.replace(temporary, target)
    return len(changes)


def derive(path, manifest):
    data = path.read_bytes()
    digest = sha(data)
    for target in manifest['targets']:
        for baseline in target['baselines']:
            if baseline['before'] == digest:
                updated = apply_edits(target, data)
                print(
                    json.dumps(
                        {
                            'target': target['target'],
                            'baseline': baseline['name'],
                            'before': digest,
                            'after': sha(updated),
                            'declared_after': baseline['after'],
                            'matches_declared': sha(updated) == baseline['after'],
                        },
                        indent=2,
                    )
                )
                return 0
    print(
        'DERIVE REFUSED: %s is not a declared baseline (%s)'
        % (path, [item['before'] for target in manifest['targets'] for item in target['baselines']]),
        file=sys.stderr,
    )
    return 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('crm_root', nargs='?', type=Path)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--derive', type=Path)
    args = parser.parse_args()
    manifest = load_manifest()
    if args.derive is not None:
        sys.exit(derive(args.derive, manifest))
    if args.crm_root is None:
        parser.error('crm_root is required unless --derive is used')
    try:
        count = apply(args.crm_root, args.check)
        print(
            ('Baseline verified' if args.check else 'Patch applied')
            + ': %d files' % count
        )
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print('L3-SCHEDULING NAVIGATION REFUSED: ' + str(error), file=sys.stderr)
        sys.exit(1)

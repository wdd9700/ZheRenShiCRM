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


def checked_root(root, manifest):
    root = root.resolve(strict=True)
    if not (root / 'frontend').is_dir():
        raise ValueError('CRM root/frontend required')
    head = subprocess.check_output(
        ['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True
    ).strip()
    if head != manifest['crm_commit']:
        raise ValueError('CRM HEAD mismatch: ' + head)
    return root


def checked_target(root, target):
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
    return path


def plan(root, manifest):
    root = checked_root(root, manifest)
    changes = []
    for target in manifest['targets']:
        path = checked_target(root, target)
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


def verify(root, manifest):
    """Read-only post-application check: current bytes must equal a declared after."""
    root = checked_root(root, manifest)
    states = []
    for target in manifest['targets']:
        path = checked_target(root, target)
        digest = sha(path.read_bytes())
        applied = [
            item for item in target['baselines'] if item['after'] == digest
        ]
        if applied:
            states.append((target['target'], applied[0]['name'], digest))
            continue
        pending = [
            item['name'] for item in target['baselines'] if item['before'] == digest
        ]
        if pending:
            raise ValueError(
                'Not applied yet (baseline %s): %s'
                % (pending[0], target['target'])
            )
        raise ValueError(
            'Unknown state: %s; expected one of the declared after hashes %s; got %s'
            % (
                target['target'],
                [item['after'] for item in target['baselines']],
                digest,
            )
        )
    return states


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
    """Read-only candidate generator. Writes nothing and authorizes nothing.

    Registered baselines and unknown bytes are both accepted; the anchors must
    still be unique, and the output is only a candidate for human review.
    """
    data = path.read_bytes()
    digest = sha(data)
    target = manifest['targets'][0]
    registered = next(
        (item for item in target['baselines'] if item['before'] == digest), None
    )
    if any(item['after'] == digest for item in target['baselines']):
        print(
            'DERIVE REFUSED: %s already equals a declared after hash; no candidate'
            % path,
            file=sys.stderr,
        )
        return 1
    try:
        updated = apply_edits(target, data)
    except ValueError as error:
        print('DERIVE REFUSED: ' + str(error), file=sys.stderr)
        return 1
    result = sha(updated)
    print(
        json.dumps(
            {
                'mode': 'read-only candidate; writes nothing and does not authorize apply',
                'target': target['target'],
                'before': digest,
                'after_candidate': result,
                'declared_baseline': registered['name'] if registered else None,
                'matches_declared_after': bool(
                    registered and registered['after'] == result
                ),
                'anchors_verified_unique': True,
                'writes': False,
                'apply_authorized': False,
                'next_step': (
                    'review the candidate diff, add a fixture plus a baseline entry to '
                    'manifest.json, re-run check_apply.py, then commit a new tip; '
                    'apply.py keeps refusing unregistered bytes'
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('crm_root', nargs='?', type=Path)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--derive', type=Path)
    args = parser.parse_args()
    if sum(bool(flag) for flag in (args.check, args.verify, args.derive)) > 1:
        parser.error('choose only one of --check, --verify, --derive')
    manifest = load_manifest()
    if args.derive is not None:
        sys.exit(derive(args.derive, manifest))
    if args.crm_root is None:
        parser.error('crm_root is required unless --derive is used')
    try:
        if args.verify:
            states = verify(args.crm_root, manifest)
        else:
            count = apply(args.crm_root, args.check)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print('L3-SCHEDULING NAVIGATION REFUSED: ' + str(error), file=sys.stderr)
        sys.exit(1)
    if args.verify:
        for target, baseline, digest in states:
            print('Verified applied state: %s = %s after %s' % (target, baseline, digest))
    else:
        print(
            ('Baseline verified (pre-application)' if args.check else 'Patch applied')
            + ': %d files' % count
        )

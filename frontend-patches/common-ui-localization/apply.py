import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
COMMIT = '36bd8859f2a6345a620477bc708d0546e8c3f08a'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def transform(target, data):
    replacements = {
        'frontend/src/components/Notifications.vue': [
            ('title="No New Notifications"', ':title="__(\'No New Notifications\')"'),
            ('description="You have no new notifications"', ':description="__(\'You have no new notifications\')"'),
        ],
        'frontend/src/components/Activities/DataFields.vue': [
            ('label="Save"', ':label="__(\'Save\')"'),
        ],
        'frontend/src/components/Filter.vue': [
            ('        label: o,\n        value: o,', "        label: fieldtype == 'Check' ? __(o) : o,\n        value: o,"),
        ],
        'frontend/src/components/IconPicker.vue': [
            ('placeholder="Search by keyword"', ':placeholder="__(\'Search by keyword\')"'),
            ('<Button @click="setRandom">Random</Button>', '<Button @click="setRandom">{{ __(\'Random\') }}</Button>'),
            ('{{ group }}', "{{ group === 'No results' ? __('No results') : group }}"),
        ],
    }
    if target not in replacements:
        raise ValueError('Unexpected target: ' + target)
    for old, new in replacements[target]:
        old, new = old.encode('utf-8'), new.encode('utf-8')
        if data.count(old) != 1:
            raise ValueError('Expected source anchor absent or ambiguous: ' + old.decode('utf-8'))
        data = data.replace(old, new, 1)
    return data


def apply(root, mode='apply'):
    root = root.resolve(strict=True)
    head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    if head != COMMIT:
        raise ValueError('CRM HEAD mismatch')
    entries = json.loads((HERE / 'manifest.json').read_text(encoding='utf-8'))
    changes = []
    for entry in entries:
        target = root / entry['target']
        if not target.parent.resolve(strict=True).is_relative_to(root) or target.is_symlink():
            raise ValueError('Target escapes CRM root or is a symlink: ' + entry['target'])
        if target.stat().st_nlink != 1:
            raise ValueError('Hard-linked target refused: ' + entry['target'])
        source = target.read_bytes()
        if digest(source) != entry['after' if mode == 'verify' else 'before']:
            raise ValueError('Source mismatch: ' + entry['target'])
        if mode != 'verify':
            output = transform(entry['target'], source)
            if digest(output) != entry['after']:
                raise ValueError('Replacement mismatch: ' + entry['target'])
            temporary = target.with_name(target.name + '.common-ui-localization-tmp')
            backup = target.with_name(target.name + '.common-ui-localization-backup')
            changes.append((target, source, output, temporary, backup))
    for _, _, _, temporary, backup in changes:
        if os.path.lexists(temporary) or os.path.lexists(backup):
            raise ValueError('Temporary path already exists')
    if mode == 'apply':
        owned, committed, preserve = set(), [], set()
        try:
            for _, source, output, temporary, backup in changes:
                for path, content in ((temporary, output), (backup, source)):
                    with path.open('xb') as stream:
                        owned.add(path)
                        stream.write(content)
            for target, _, _, temporary, backup in changes:
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
                    failures.append(f'{target}: {rollback_error}')
            if failures:
                raise RuntimeError('Rollback incomplete; originals retained: ' + '; '.join(failures)) from error
            raise
        finally:
            for path in owned - preserve:
                path.unlink(missing_ok=True)
    return len(entries)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('crm_root', type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--check', action='store_true')
    modes.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    try:
        mode = 'check' if args.check else 'verify' if args.verify else 'apply'
        print(f'Common UI localization {mode}: {apply(args.crm_root, mode)} files verified')
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print('COMMON UI LOCALIZATION REFUSED: ' + str(error), file=sys.stderr)
        sys.exit(1)

import argparse
import json
import os
from pathlib import Path

from apply_filter_label_delta import ordinary, sha

TARGET = 'apps/team_access/team_access/request.py'
BRANDED_BEFORE = 'bd6ba3cad3290549b8d028ea868cd72e2cc3543a4b3978145ffd509deb30d3bf'
UPSTREAM_BEFORE = '0a654aaeba6e9145bc0bf35b9ccd1f07033038df9fc3926e6cda53e34522331f'
UPSTREAM_AFTER = '3c7fa425ff150ba3abf2d252244dc471124778f6057126f8355e5e8077fdc8af'
OLD = b'crm.api.doc.get_sort_options'
NEW = b'crm.api.doc.sort_options'


def generate(branded, upstream_before, upstream_after):
    if sha(branded) != BRANDED_BEFORE or sha(upstream_before) != UPSTREAM_BEFORE or sha(upstream_after) != UPSTREAM_AFTER:
        raise RuntimeError('Sort endpoint source contract differs')
    if upstream_before.count(OLD) != 1 or upstream_before.replace(OLD, NEW, 1) != upstream_after or branded.count(OLD) != 1:
        raise RuntimeError('Sort endpoint delta must be one exact reviewed string change')
    updated = branded.replace(OLD, NEW, 1)
    if updated.replace(NEW, OLD, 1) != branded:
        raise RuntimeError('Unexpected non-endpoint source delta')
    query = b'/assets/team_access/access.js?v=7d26cdb3a226da9094e9e2f7ed5b1aadef2790de46fc0c3d47fea244bee043d6'
    if branded.count(query) != 1 or updated.count(query) != 1:
        raise RuntimeError('Sort endpoint patch must preserve branded access digest URL')
    return dict(target=TARGET, before=BRANDED_BEFORE, after=sha(updated)), updated


def contract(source):
    receipt = json.loads((source / 'sort-endpoint-delta.json').read_bytes())
    expected, updated = generate((source / 'sort-inputs/request.branded.py').read_bytes(), (source / 'sort-inputs/request.upstream-before.py').read_bytes(), (source / 'sort-inputs/request.upstream-after.py').read_bytes())
    if receipt != expected:
        raise RuntimeError('Sort endpoint receipt differs')
    return receipt, updated


def apply(root, source, mode='apply'):
    root = root.resolve(strict=True)
    receipt, updated = contract(source)
    target = ordinary(root, TARGET)
    if sha(target.read_bytes()) != receipt['after' if mode == 'verify' else 'before']:
        raise RuntimeError('Branded sort endpoint predecessor/final source differs')
    temporary = target.with_name(target.name + '.sort-endpoint-tmp')
    if os.path.lexists(temporary):
        raise RuntimeError('Sort endpoint temporary already exists')
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
    print('PASS one exact sort_options name fix on branded request source; all other bytes retained')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('bench_root', type=Path)
    parser.add_argument('source_root', type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--check', action='store_true')
    modes.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    apply(args.bench_root, args.source_root, 'check' if args.check else 'verify' if args.verify else 'apply')

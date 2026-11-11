import argparse
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
TARGET = 'apps/team_access/team_access/request.py'
ASSET = 'apps/team_access/team_access/public/access.js'
BEFORE = '0a654aaeba6e9145bc0bf35b9ccd1f07033038df9fc3926e6cda53e34522331f'
ANCHOR = b'<script defer src="/assets/team_access/access.js"></script>'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def generate(asset):
    original = (HERE / 'fixtures/team_access__request.py').read_bytes()
    if sha(original) != BEFORE or original.count(ANCHOR) != 1:
        raise ValueError('Access request fixture differs from its fixed baseline')
    digest = sha(asset)
    url = '/assets/team_access/access.js?v=' + digest
    updated = original.replace(ANCHOR, ('<script defer src="' + url + '"></script>').encode('ascii'), 1)
    receipt = dict(target=TARGET, before=BEFORE, after=sha(updated), asset=ASSET, asset_sha256=digest, script_url=url)
    return receipt, updated


def ordinary(root, relative):
    path = root / relative
    if not path.parent.resolve(strict=True).is_relative_to(root):
        raise ValueError('Access version path escapes bench')
    for item in (path, *path.parents):
        if item.is_symlink() or (item.exists() and getattr(item.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('Linked access version source refused')
    if not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError('Access version source must be an ordinary file')
    return path


def apply(root, receipt, mode='apply'):
    root = root.resolve(strict=True)
    asset = ordinary(root, ASSET)
    expected, updated = generate(asset.read_bytes())
    if receipt != expected:
        raise ValueError('Access injection receipt differs from final script bytes')
    target = ordinary(root, TARGET)
    if sha(target.read_bytes()) != receipt['after' if mode == 'verify' else 'before']:
        raise ValueError('Access injection source SHA mismatch')
    temporary = target.with_name(target.name + '.access-version-tmp')
    if os.path.lexists(temporary):
        raise ValueError('Access injection temporary path already exists')
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
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('bench_root', type=Path)
    parser.add_argument('source_manifest', type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--check', action='store_true')
    modes.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    manifest = json.loads(args.source_manifest.read_bytes())
    result = apply(args.bench_root, manifest['access_version'], 'check' if args.check else 'verify' if args.verify else 'apply')
    print('PASS exact access injection URL: ' + result['script_url'])

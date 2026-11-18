#!/usr/bin/env python3
"""Offline, pinned S023 inventory. Never extracts files or emits an active include."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
import tarfile

BENCH = 'home/frappe/frappe-bench/'
ASSETS = BENCH + 'sites/assets'
FRONT = '/assets/crm/frontend/'
CRM_HTML = BENCH + 'apps/crm/crm/www/crm.html'
LEGACY_HTML = BENCH + 'apps/team_schedule/team_schedule/www/team-schedule.html'
ARTIFACT = 'home/frappe/native-schedule/native-artifact-proof.json'
HEADERS = 'etc/nginx/snippets/security_headers.conf'
INNER = 'templates/nginx/frappe.conf.template'
ROOTS = {a: BENCH + 'apps/{0}/{0}/public'.format(a)
         for a in ('crm', 'frappe', 'team_access', 'team_schedule')}
TRACKED = (ASSETS, BENCH + 'assets', *ROOTS.values())
KEEP = {CRM_HTML, LEGACY_HTML, ARTIFACT, HEADERS, INNER}
PINS = (
    ('0a91cbcc298ef599de35f46b0ab09ab696bc389fc0697c6d1feedaf163441679',
     'e14b6cce43cf861f92ffaf4f55935434897ed156efea04f8eacc56311e39a4dd',
     '732034ffab2cb7b8d6aed7a65c32e79d3fb2cb2baea252a8a30d6cd3832435a8',
     'c2601699d018675f1e2fc87a13c7fa4963090182eccfc70a8e51ed5ccdfbe062'),
    ('6edfc7a901e71e9038a540b4b8becf7a3c61d2bdc89770caf8382721c4b9bf79',
     '1703e3da28022573f94d7c3374c76d214016c7c39a07f843c8c96a4f6b219b97',
     '9121a22690c2d2a9f7f1077ef670065287340b56fda99e0d94e143e158717c48',
     '7ec179f1c0635f735aa6d59e6075f695f61e5a72739a1ea866c4e604e5bcf58a'),
)


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def digest(stream):
    result = sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b''):
        result.update(block)
    return result.hexdigest()


def layer_list(archive, pins):
    _, index, manifest, config = ('sha256:' + h for h in pins)
    outer = json.load(archive.extractfile('index.json'))['manifests']
    require([x['digest'] for x in outer] == [index], 'index drift')
    inner = json.load(blob(archive, index))['manifests']
    def linux_amd64(descriptor):
        platform = descriptor.get('platform', {})
        return (platform.get('os'), platform.get('architecture')) == ('linux', 'amd64')

    require([x['digest'] for x in inner if linux_amd64(x)] == [manifest], 'platform manifest drift')
    model = json.load(blob(archive, manifest))
    require(model['config']['digest'] == config, 'config drift')
    return model['layers']


def blob(archive, identity):
    return archive.extractfile('blobs/sha256/' + identity.split(':')[1])


def under(path, root):
    return path == root or path.startswith(root + '/')


def relevant(path):
    return any(under(path, root) or under(root, path) for root in (*TRACKED, *KEEP))


def apply(archive, layers, tree, *, candidate=False):
    for desc in layers:
        delta, removes = {}, []
        with tarfile.open(fileobj=blob(archive, desc['digest']), mode='r|gz') as layer:
            for member in layer:
                path = member.name.removeprefix('./').rstrip('/')
                parent, _, name = path.rpartition('/')
                if candidate and not member.isdir():
                    require(not any(under(path, BENCH + 'apps/' + app + '/node_modules')
                                    for app in ('crm', 'frappe')), 'public node_modules target changed')
                if name.startswith('.wh.'):
                    opaque = name == '.wh..wh..opq'
                    delete = parent if opaque else '/'.join(filter(None, (parent, name[4:])))
                    if relevant(delete):
                        removes.append((delete, opaque))
                    continue
                if not path or not relevant(path):
                    continue
                require(path not in delta, 'duplicate tar path: ' + path)
                if member.isfile():
                    with layer.extractfile(member) as payload:
                        raw = payload.read() if path in KEEP else None
                        h = sha256(raw).hexdigest() if raw is not None else digest(payload)
                    node = ('file', member.size, h, raw)
                elif member.isdir():
                    node = ('dir',)
                elif member.issym():
                    node = ('link', member.linkname)
                else:
                    node = ('special', member.type, member.linkname)
                delta[path] = node
        for path, children_only in removes:
            for recorded in list(tree):
                if (under(recorded, path) and (recorded != path or not children_only)) or not path:
                    del tree[recorded]
        for path, node in delta.items():
            if tree.get(path, ('dir',))[0] == 'dir' and node[0] != 'dir':
                for child in [p for p in tree if p.startswith(path + '/')]:
                    del tree[child]
            tree[path] = node


def public(tree):
    def index(directory, url_base, skip):
        require(all(tree.get(d, ('dir',))[0] == 'dir' for d in parents(directory) | {directory}),
                'asset directory redirected: ' + directory)
        result = {}
        for path, node in tree.items():
            if not path.startswith(directory + '/') or path in skip or node[0] == 'dir':
                continue
            require(node[0] == 'file', 'unreviewed public link or special file: ' + path)
            result[url_base + path[len(directory) + 1:]] = node[1:3]
        return result

    aliases = {ASSETS + '/' + a for a in ROOTS}
    result = index(ASSETS, '/assets/', aliases)
    for app, path in ROOTS.items():
        require(tree.get(ASSETS + '/' + app) == ('link', '/' + path), 'asset alias drift: ' + app)
        modules = path + '/node_modules'
        if modules in tree:
            require(app in ('crm', 'frappe') and tree[modules] == ('link', '/' + BENCH + 'apps/' + app + '/node_modules'),
                    'public node_modules link drift: ' + app)
        result.update(index(path, '/assets/' + app + '/', {modules}))
    return result


def parents(path):
    parts = path.split('/')
    return {'/'.join(parts[:i]) for i in range(1, len(parts))}


def inventory(base_path, next_path):
    with base_path.open('rb') as base, next_path.open('rb') as new:
        for stream, pins in zip((base, new), PINS):
            require(digest(stream) == pins[0], 'not the frozen archive: ' + stream.name)
            stream.seek(0)
        with tarfile.open(fileobj=base, mode='r:') as a, tarfile.open(fileobj=new, mode='r:') as b:
            before, after = layer_list(a, PINS[0]), layer_list(b, PINS[1])
            require(len(before) == 16 and len(after) == 18 and after[:16] == before, 'base layer inheritance drift')
            tree = {}
            apply(a, before, tree)
            old = public(tree)
            original = {path: tree[path] for path in (HEADERS, INNER, BENCH + 'assets/assets.json')}
            apply(b, after[16:], tree, candidate=True)
            require(all(tree[path] == node for path, node in original.items()), 'non-static server input drift')
            return old, public(tree), tree


def classify(old, new, tree):
    proof = json.loads(tree[ARTIFACT][3])
    files = {FRONT + name: h for name, h in proof['assets'].items()}
    require(len(files) == 158 and all(new[url][1] == h for url, h in files.items()), 'archive proof graph drift')
    require(tree[LEGACY_HTML][2] == 'cdb9e49ae2832574c231d4d9b4b0ee0b41abf6f8ed1e3b3e1c63a82f953a8f9f',
            'candidate fallback is not the reviewed M48 template')
    require(proof['entry'].encode() in tree[CRM_HTML][3], 'CRM entry missing from rendered template source')
    rows = []
    for url in sorted(old.keys() | new.keys()):
        a, b = old.get(url), new.get(url)
        if a == b:
            continue
        if b is None:
            action = 'retain-old'
        elif a is not None:
            action = 'block-same-url'
        elif re.fullmatch(re.escape(FRONT) + r'assets/[A-Za-z0-9_-]+-[A-Za-z0-9_-]{8}\.(js|css)', url) and url in files:
            action = 'coexist-exact'
        elif url.startswith(FRONT + 'assets/') and url.endswith('.map'):
            action = 'exclude-sourcemap'
        else:
            action = 'block-unreviewed-new'
        rows.append((action, url, *(a or ('-', '-')), *(b or ('-', '-'))))
    return rows


def nginx_review(rows):
    yield '# S023 REVIEW ONLY — HOLD. Do not uncomment or install. Verify live MIME, cache and headers before a new release.'
    for action, url, _, _, size, digest_value in rows:
        if action == 'coexist-exact':
            yield '# {} B sha256:{}'.format(size, digest_value)
            yield '# location = ' + url + ' {'
            yield '#     root /var/lib/crm-native-cutover/REVIEWED_RELEASE;'
            yield '#     try_files $uri =404;'
            yield '#     limit_except GET { deny all; }'
            yield '# }'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('e14b6_archive', type=Path)
    parser.add_argument('s021_archive', type=Path)
    parser.add_argument('--format', choices=('ledger', 'nginx-review', 'gate'), default='ledger')
    args = parser.parse_args()
    old, new, tree = inventory(args.e14b6_archive, args.s021_archive)
    rows = classify(old, new, tree)
    blockers = [url for action, url, *_ in rows if action.startswith('block-')]
    print('S023 HOLD: ' + ', '.join(blockers or ['no activation in this pinned review kit']), file=sys.stderr)
    if args.format == 'gate':
        return 3
    if args.format == 'nginx-review':
        lines = nginx_review(rows)
    else:
        lines = iter(['action\turl\told_bytes\told_sha256\tnew_bytes\tnew_sha256',
                      *('\t'.join(map(str, row)) for row in rows)])
    sys.stdout.buffer.write(('\n'.join(lines) + '\n').encode('utf-8'))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (KeyError, ValueError, OSError, tarfile.TarError) as error:
        sys.exit('S023 refused: {}'.format(error))

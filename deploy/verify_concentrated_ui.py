import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from apply_filter_label_delta import AFTER as FILTER_AFTER, ordinary, sha
from verify_read_diagnostic import contract as diagnostic_contract

B = Path('/home/frappe/frappe-bench')
U = Path('/home/frappe/concentrated-ui')
STATE = U / 'deployed-source-state.json'


def source_manifest():
    manifest = json.loads((U / 'concentrated-source-manifest.json').read_bytes())
    for name, digest in manifest['files'].items():
        if sha(ordinary(U, name).read_bytes()) != digest:
            raise RuntimeError('Concentrated input source drift: ' + name)
    if manifest['filter_targets'] != FILTER_AFTER or manifest['diagnostic'] != diagnostic_contract(U):
        raise RuntimeError('Concentrated delta contract differs')
    return manifest


def snapshot():
    source_manifest()
    source = Path('/home/frappe/common-ui')
    spec = importlib.util.spec_from_file_location('deployed_common_ui_guard', source / 'deploy/verify_common_ui.py')
    previous = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(previous)
    previous.verify_assets()
    expected = previous.expected_sources(B, source, Path('/home/frappe/u030'))
    state = dict(sources=expected, asset_manifest=json.loads((B / 'assets/assets.json').read_bytes()), assets={})
    for root in (B / 'assets/team_access', B / 'assets/team_schedule'):
        for path in root.rglob('*'):
            if path.is_file():
                state['assets'][path.relative_to(B / 'assets').as_posix()] = sha(path.read_bytes())
    login = B / 'assets/crm/css/login-theme.css'
    state['assets']['crm/css/login-theme.css'] = sha(login.read_bytes())
    with STATE.open('x', encoding='utf-8') as stream:
        json.dump(state, stream, sort_keys=True)
        stream.write('\n')
    print('PASS exact deployed35d0 source/asset state recorded after original guard')


def verify(assets=False):
    manifest = source_manifest()
    if subprocess.check_output(['git', '-C', str(B / 'apps/crm'), 'rev-parse', 'HEAD'], text=True).strip() != '36bd8859f2a6345a620477bc708d0546e8c3f08a':
        raise RuntimeError('Concentrated CRM HEAD differs')
    state = json.loads(STATE.read_bytes())
    expected = dict(state['sources'])
    expected.update({'apps/crm/' + name: digest for name, digest in FILTER_AFTER.items()})
    expected.update({'apps/crm/' + entry['target']: entry['after'] for entry in manifest['diagnostic']['targets']})
    for name, digest in expected.items():
        if sha(ordinary(B, name).read_bytes()) != digest:
            raise RuntimeError('Inherited guard or explicit concentrated source differs: ' + name)
    if assets:
        mappings = [json.loads((B / root / 'assets.json').read_bytes()) for root in ('assets', 'sites/assets')]
        if mappings[0] != mappings[1] or any(mappings[0].get(key) != value for key, value in state['asset_manifest'].items()):
            raise RuntimeError('Concentrated build lost original Framework mapping')
        for directory in ('assets', 'sites/assets'):
            root = B / directory
            for url in mappings[0].values():
                if not isinstance(url, str) or not url.startswith('/assets/') or not (root / url.removeprefix('/assets/')).is_file():
                    raise RuntimeError('Concentrated mapped asset missing')
            for name, digest in state['assets'].items():
                if sha((root / name).read_bytes()) != digest:
                    raise RuntimeError('Unchanged standalone/login/access asset changed: ' + name)
    print('PASS inherited deployed source guards plus bounded Filter/catalog/four diagnostic sources' + (' and original static assets' if assets else ''))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=('snapshot', 'sources', 'assets'))
    args = parser.parse_args()
    if args.phase == 'snapshot':
        snapshot()
    else:
        verify(args.phase == 'assets')

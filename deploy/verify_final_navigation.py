import argparse
import importlib.util
import json
from pathlib import Path
import subprocess

from apply_filter_label_delta import AFTER as FILTER_AFTER, ordinary, sha

B = Path('/home/frappe/frappe-bench')
U = Path('/home/frappe/final-navigation')
STATE = U / 'deployed-source-state.json'
CLEAN_SOURCES = {
    'frontend/node_modules/frappe-ui/src/resources/accountBoundary.js': 'a899121b944a1ceb96ca13e258bc819ffd339418c018b3accd17714b7f4af421',
    'frontend/node_modules/frappe-ui/src/resources/resources.js': '5c38ca06466ee52fc21625300fb15e6107e788cf849d3b797e8eb39e35458f80',
    'frontend/node_modules/frappe-ui/src/utils/request.ts': '752fdeb0996e63fb65829e5eedb7942a4ebbbdfe15a4db6312c92d2869b9db1b',
    'frontend/node_modules/frappe-ui/src/utils/frappeRequest.ts': '83e4b44deed36b3bad35f9539b052f2e53b9e64a2f96eb6e98e4236b7a473ef9',
}
FORBIDDEN = ('VITE_CRM_READ_FAILURE_DIAGNOSTICS', 'D020102', 'markReadFailurePhase', 'recordReadFailure', 'readFailureCode')


def clean_diagnostics(bench):
    for name, digest in CLEAN_SOURCES.items():
        data = ordinary(bench / 'apps/crm', name).read_bytes()
        if sha(data) != digest or any(token.encode() in data for token in FORBIDDEN):
            raise RuntimeError('Temporary diagnostic code not removed: ' + name)


def source_manifest():
    manifest = json.loads((U / 'final-navigation-source-manifest.json').read_bytes())
    for name, digest in manifest['files'].items():
        if sha(ordinary(U, name).read_bytes()) != digest:
            raise RuntimeError('Final navigation exported input changed: ' + name)
    if manifest['filter_targets'] != FILTER_AFTER or manifest['diagnostics_present'] is not False:
        raise RuntimeError('Final navigation source contract differs')
    return manifest


def snapshot():
    source_manifest()
    previous_root = Path('/home/frappe/common-ui')
    spec = importlib.util.spec_from_file_location('final_deployed_common_guard', previous_root / 'deploy/verify_common_ui.py')
    previous = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(previous)
    previous.verify_assets()
    clean_diagnostics(B)
    state = dict(sources=previous.expected_sources(B, previous_root, Path('/home/frappe/u030')), asset_manifest=json.loads((B / 'assets/assets.json').read_bytes()), assets={})
    for root in (B / 'assets/team_access', B / 'assets/team_schedule'):
        for path in root.rglob('*'):
            if path.is_file():
                state['assets'][path.relative_to(B / 'assets').as_posix()] = sha(path.read_bytes())
    state['assets']['crm/css/login-theme.css'] = sha((B / 'assets/crm/css/login-theme.css').read_bytes())
    with STATE.open('x', encoding='utf-8') as stream:
        json.dump(state, stream, sort_keys=True)
        stream.write('\n')
    print('PASS exact deployed35d0 source/asset baseline and original four non-diagnostic sources')


def verify(assets=False):
    manifest = source_manifest()
    clean_diagnostics(B)
    if subprocess.check_output(['git', '-C', str(B / 'apps/crm'), 'rev-parse', 'HEAD'], text=True).strip() != '36bd8859f2a6345a620477bc708d0546e8c3f08a':
        raise RuntimeError('Final navigation CRM HEAD differs')
    state = json.loads(STATE.read_bytes())
    expected = dict(state['sources'])
    expected.update({'apps/crm/' + name: digest for name, digest in FILTER_AFTER.items()})
    expected[manifest['sort_endpoint']['target']] = manifest['sort_endpoint']['after']
    for name, digest in expected.items():
        if sha(ordinary(B, name).read_bytes()) != digest:
            raise RuntimeError('Final inherited or explicit source guard differs: ' + name)
    if assets:
        maps = [json.loads((B / directory / 'assets.json').read_bytes()) for directory in ('assets', 'sites/assets')]
        if maps[0] != maps[1] or any(maps[0].get(key) != value for key, value in state['asset_manifest'].items()):
            raise RuntimeError('Final navigation lost Framework mappings')
        for directory in ('assets', 'sites/assets'):
            root = B / directory
            for url in maps[0].values():
                if not isinstance(url, str) or not url.startswith('/assets/') or not (root / url.removeprefix('/assets/')).is_file():
                    raise RuntimeError('Final mapped asset is missing')
            for name, digest in state['assets'].items():
                if sha((root / name).read_bytes()) != digest:
                    raise RuntimeError('Unchanged final static asset differs: ' + name)
        for path in (B / 'assets/crm/frontend').rglob('*.js'):
            data = path.read_bytes()
            if b'D020102' in data or b'readFailureCode' in data:
                raise RuntimeError('Temporary diagnostic marker remains in final built JavaScript')
    print('PASS final Filter/catalog plus bounded sort endpoint, inherited guards and diagnostic code removal' + (' / static assets' if assets else ''))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=('snapshot', 'sources', 'assets'))
    args = parser.parse_args()
    if args.phase == 'snapshot':
        snapshot()
    else:
        verify(args.phase == 'assets')

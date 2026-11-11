import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import uuid

from prepare_integration import ROOT, committed_files, ordinary_path, write_sources
from verify_common_ui import catalog_contract, entries

BASE_TAG = 'crm-local:ui-ebc790fba433470789113948e69f50fd'
BASE_IMAGE = 'sha256:2f92c460d47948bf6f030e23b24687b82ca3a92c4af4b8a200da7de7ac97db1b'
BASE_CONFIG = 'sha256:50a654164666adafc4f35c7a14b950b13cfba43363ce977aaa315461a0fd7987'
PATCH_FILES = frozenset({'frontend-patches/common-ui-localization/apply.py', 'frontend-patches/common-ui-localization/manifest.json', 'frontend-patches/localization/manifest.json', 'frontend-patches/localization/zh-CN.json'})
DEPLOY_FILES = frozenset({'deploy/Dockerfile.common-ui', 'deploy/Dockerfile.common-ui.dockerignore', 'deploy/verify_common_ui.py'})


def sha(data):
    return hashlib.sha256(data).hexdigest()


def select(commit, prefix, expected):
    files = committed_files(commit, prefix)
    if not expected <= set(files):
        raise RuntimeError('Missing required common UI source')
    return {path: files[path] for path in expected}


def prepare(common_commit, integration_commit):
    exported = select(common_commit, 'frontend-patches/', PATCH_FILES)
    exported.update(select(integration_commit, 'deploy/', DEPLOY_FILES))
    runtime = ROOT / '.runtime'
    ordinary_path(runtime)
    runtime.mkdir(exist_ok=True)
    if subprocess.run(['git', '-C', str(ROOT.parent), 'check-ignore', '--quiet', '--no-index', '--', 'deploy/.runtime/common-ui-probe']).returncode:
        raise RuntimeError('Common UI context must be ignored')
    context = runtime / ('common-ui-' + uuid.uuid4().hex)
    context.mkdir()
    files = write_sources(exported, context)
    targets = entries(context)
    catalog = catalog_contract(context)
    manifest = dict(schema='common-ui-v1', base_image=BASE_IMAGE, base_config=BASE_CONFIG, common_revision=common_commit, integration_revision=integration_commit, files=files, targets=targets, catalog=catalog)
    (context / 'common-ui-source-manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    receipt = sha((context / 'common-ui-source-manifest.json').read_bytes())
    load(context, receipt)
    print('Common UI context:', context)
    print('Common UI receipt:', receipt)
    return context, manifest, receipt


def load(value, receipt):
    context = Path(value)
    ordinary_path(context)
    if not context.is_absolute() or context.parent.resolve() != (ROOT / '.runtime').resolve() or not re.fullmatch('common-ui-[0-9a-f]{32}', context.name):
        raise RuntimeError('Common UI context location differs')
    raw = (context / 'common-ui-source-manifest.json').read_bytes()
    if not re.fullmatch('[0-9a-f]{64}', receipt) or sha(raw) != receipt:
        raise RuntimeError('Common UI receipt differs')
    manifest = json.loads(raw)
    if set(manifest) != {'schema', 'base_image', 'base_config', 'common_revision', 'integration_revision', 'files', 'targets', 'catalog'} or manifest['schema'] != 'common-ui-v1' or (manifest['base_image'], manifest['base_config']) != (BASE_IMAGE, BASE_CONFIG):
        raise RuntimeError('Common UI manifest schema/base differs')
    if any(not isinstance(manifest[key], str) or not re.fullmatch('[0-9a-f]{40}', manifest[key]) for key in ('common_revision', 'integration_revision')):
        raise RuntimeError('Common UI exact commits required')
    if set(manifest['files']) != PATCH_FILES | DEPLOY_FILES:
        raise RuntimeError('Common UI file whitelist differs')
    actual = set()
    for path in context.rglob('*'):
        ordinary_path(path)
        if path.is_file():
            if path.stat().st_nlink != 1:
                raise RuntimeError('Hardlinked common UI context refused')
            actual.add(path.relative_to(context).as_posix())
    if actual != PATCH_FILES | DEPLOY_FILES | {'common-ui-source-manifest.json'}:
        raise RuntimeError('Unexpected or missing common UI context file')
    for name, digest in manifest['files'].items():
        if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest) or sha((context / name).read_bytes()) != digest:
            raise RuntimeError('Common UI exported source drift: ' + name)
    if manifest['targets'] != entries(context) or manifest['catalog'] != catalog_contract(context):
        raise RuntimeError('Common UI target/catalog contract drift')
    return context, manifest


def build(context, receipt):
    context, manifest = load(context, receipt)
    parent = json.loads(subprocess.check_output(['docker', 'image', 'inspect', BASE_TAG], text=True))[0]
    if parent['Id'] != BASE_IMAGE or len(parent['RootFS']['Layers']) != 7:
        raise RuntimeError('Exact deployed common UI parent identity/layers differ')
    tag = 'crm-local:' + context.name
    command = ['docker', 'build', '--network=none', '--pull=false', '--progress=plain', '--build-arg', 'COMMON_UI_REVISION=' + manifest['common_revision'], '--build-arg', 'COMMON_UI_INTEGRATION_REVISION=' + manifest['integration_revision'], '-t', tag, '-f', str(context / 'deploy/Dockerfile.common-ui'), str(context)]
    subprocess.run(command, check=True)
    image = json.loads(subprocess.check_output(['docker', 'image', 'inspect', tag], text=True))[0]
    labels = {'crm.common-ui.revision': manifest['common_revision'], 'crm.common-ui.integration.revision': manifest['integration_revision'], 'crm.common-ui.base': BASE_IMAGE}
    expected = dict(parent['Config'], Labels=dict(parent['Config']['Labels'], **labels))
    if image['Config'] != expected or not re.fullmatch('sha256:[0-9a-f]{64}', image['Id']) or not 7 < len(image['RootFS']['Layers']) <= 16 or image['RootFS']['Layers'][:7] != parent['RootFS']['Layers']:
        raise RuntimeError('Common UI Config/layer inheritance differs')
    destination = ROOT / '.runtime' / (context.name + '-build-result.json')
    with destination.open('x', encoding='utf-8') as stream:
        json.dump(dict(source_receipt=receipt, source=manifest, image=image, candidate_tag=tag), stream, indent=2, sort_keys=True)
        stream.write('\n')
    print('Candidate only, no site activation:', tag, image['Id'])
    return image


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--common-commit')
    parser.add_argument('--integration-commit')
    parser.add_argument('--context', type=Path)
    parser.add_argument('--receipt')
    parser.add_argument('--build', action='store_true')
    args = parser.parse_args()
    if args.context:
        if args.common_commit or args.integration_commit or not args.receipt:
            parser.error('Context reuse requires its receipt only')
        context, manifest = load(args.context, args.receipt)
        receipt = args.receipt
    else:
        if not args.common_commit or not args.integration_commit or args.receipt:
            parser.error('Two exact reviewed source commits required')
        context, manifest, receipt = prepare(args.common_commit, args.integration_commit)
    if args.build:
        build(context, receipt)

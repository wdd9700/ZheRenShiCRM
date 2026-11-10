import argparse
import json
from pathlib import Path
import re
import subprocess
import uuid

from prepare_integration import ROOT, committed_files, ordinary_path, write_sources
from apply_filter_label_delta import AFTER as FILTER_AFTER, inputs as filter_inputs, sha
from apply_sort_endpoint_delta import generate as sort_generate, contract as sort_contract

BASE_TAG = 'crm-local:common-ui-3c8a0ee657aa461d8d4f617807a5bf10'
BASE_IMAGE = 'sha256:35d0b0bd36ae08fa9d434b4275cb50bc4e202607c5f8ad95a34e6441c4922101'
BASE_CONFIG = 'sha256:310b0d22992ac555ea577f2fdc770f9adc0e21191d9d7e1855c6edd2d230649d'
FILTER_REVISION = '3bcad3233cf674a145d47cbe3c927ff9eb432743'
SORT_REVISION = '83d1cd4bc8311e7dda49c1df518169be9d4556a9'
CLEANUP_REVISION = '5c2470ef451d9c0d19905fe41ef4ccb2dd28c799'
ORIGINAL_REVISION = '9403d5a7ee4eb2d50eee3faf844d679a6aee5c80'
PATCH_FILES = frozenset({'frontend-patches/common-ui-localization/apply.py', 'frontend-patches/common-ui-localization/manifest.json', 'frontend-patches/localization/manifest.json', 'frontend-patches/localization/zh-CN.json'})
DEPLOY_FILES = frozenset({'deploy/Dockerfile.final-navigation', 'deploy/Dockerfile.final-navigation.dockerignore', 'deploy/apply_filter_label_delta.py', 'deploy/apply_sort_endpoint_delta.py', 'deploy/verify_final_navigation.py'})
SORT_FILES = frozenset({'sort-inputs/request.branded.py', 'sort-inputs/request.upstream-before.py', 'sort-inputs/request.upstream-after.py', 'sort-endpoint-delta.json'})


def selected(commit, prefix, names):
    files = committed_files(commit, prefix)
    if not names <= set(files):
        raise RuntimeError('Missing final navigation source')
    return {name: files[name] for name in names}


def cleanup_proof():
    prefix = 'frontend-patches/c011000/'
    original = committed_files(ORIGINAL_REVISION, prefix)
    clean = committed_files(CLEANUP_REVISION, prefix)
    production = {name for name in original if name.startswith(prefix + 'payload/') or name in {prefix + 'apply.py', prefix + 'manifest.json', prefix + 'source_edits.py'}}
    if any(clean.get(name) != original[name] for name in production):
        raise RuntimeError('Cleanup production differs from original reviewed source')
    forbidden = (b'VITE_CRM_READ_FAILURE_DIAGNOSTICS', b'D020102', b'markReadFailurePhase', b'recordReadFailure', b'readFailureCode')
    if any(token in data for _, data in clean.values() for token in forbidden):
        raise RuntimeError('Cleanup patch still contains temporary diagnostic markers')
    return {name: sha(original[name][1]) for name in sorted(production)}


def prepare(integration_revision):
    exported = selected(FILTER_REVISION, 'frontend-patches/', PATCH_FILES)
    exported.update(selected(integration_revision, 'deploy/', DEPLOY_FILES))
    before = committed_files('f7c25dc93ed06a82295cf5630bd079321d125b62', 'apps/team_access/')['apps/team_access/team_access/request.py']
    after = committed_files(SORT_REVISION, 'apps/team_access/')['apps/team_access/team_access/request.py']
    branded = committed_files(integration_revision, 'frontend-patches/branding/')['frontend-patches/branding/fixtures/team_access__request.py'][1]
    old_tag = b'<script defer src="/assets/team_access/access.js"></script>'
    new_tag = b'<script defer src="/assets/team_access/access.js?v=7d26cdb3a226da9094e9e2f7ed5b1aadef2790de46fc0c3d47fea244bee043d6"></script>'
    if branded.count(old_tag) != 1:
        raise RuntimeError('Branded request fixture tag differs')
    branded = branded.replace(old_tag, new_tag, 1)
    sort_entry, _ = sort_generate(branded, before[1], after[1])
    exported.update({'sort-inputs/request.branded.py': ('100644', branded), 'sort-inputs/request.upstream-before.py': before, 'sort-inputs/request.upstream-after.py': after, 'sort-endpoint-delta.json': ('100644', (json.dumps(sort_entry, indent=2, sort_keys=True) + '\n').encode())})
    proof = cleanup_proof()
    runtime = ROOT / '.runtime'
    ordinary_path(runtime)
    runtime.mkdir(exist_ok=True)
    if subprocess.run(['git', '-C', str(ROOT.parent), 'check-ignore', '--quiet', '--no-index', '--', 'deploy/.runtime/final-navigation-probe']).returncode:
        raise RuntimeError('Final navigation context must be ignored')
    context = runtime / ('final-navigation-' + uuid.uuid4().hex)
    context.mkdir()
    hashes = write_sources(exported, context)
    filter_inputs(context / 'frontend-patches')
    manifest = dict(schema='final-navigation-v1', base_image=BASE_IMAGE, base_config=BASE_CONFIG, filter_revision=FILTER_REVISION, sort_revision=SORT_REVISION, cleanup_revision=CLEANUP_REVISION, integration_revision=integration_revision, diagnostics_present=False, cleanup_production=proof, filter_targets=FILTER_AFTER, sort_endpoint=sort_entry, files=hashes)
    (context / 'final-navigation-source-manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    receipt = sha((context / 'final-navigation-source-manifest.json').read_bytes())
    load(context, receipt)
    print('Final navigation context:', context)
    print('Final navigation receipt:', receipt)
    return context, manifest, receipt


def load(value, receipt):
    context = Path(value)
    ordinary_path(context)
    if not context.is_absolute() or context.parent.resolve() != (ROOT / '.runtime').resolve() or not re.fullmatch('final-navigation-[0-9a-f]{32}', context.name):
        raise RuntimeError('Final navigation context location differs')
    raw = (context / 'final-navigation-source-manifest.json').read_bytes()
    if not re.fullmatch('[0-9a-f]{64}', receipt) or sha(raw) != receipt:
        raise RuntimeError('Final navigation receipt differs')
    manifest = json.loads(raw)
    if set(manifest) != {'schema', 'base_image', 'base_config', 'filter_revision', 'sort_revision', 'cleanup_revision', 'integration_revision', 'diagnostics_present', 'cleanup_production', 'filter_targets', 'sort_endpoint', 'files'} or manifest['schema'] != 'final-navigation-v1' or (manifest['base_image'], manifest['base_config']) != (BASE_IMAGE, BASE_CONFIG) or (manifest['filter_revision'], manifest['sort_revision'], manifest['cleanup_revision']) != (FILTER_REVISION, SORT_REVISION, CLEANUP_REVISION) or manifest['diagnostics_present'] is not False or not re.fullmatch('[0-9a-f]{40}', manifest['integration_revision']):
        raise RuntimeError('Final navigation source schema/revisions differ')
    expected = PATCH_FILES | DEPLOY_FILES | SORT_FILES
    if set(manifest['files']) != expected:
        raise RuntimeError('Final navigation file whitelist differs')
    actual = set()
    for path in context.rglob('*'):
        ordinary_path(path)
        if path.is_file():
            if path.stat().st_nlink != 1:
                raise RuntimeError('Hardlinked final navigation input refused')
            actual.add(path.relative_to(context).as_posix())
    if actual != expected | {'final-navigation-source-manifest.json'}:
        raise RuntimeError('Missing/unmanifested final navigation input')
    for name, digest in manifest['files'].items():
        if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest) or sha((context / name).read_bytes()) != digest:
            raise RuntimeError('Final navigation exported source drift: ' + name)
    filter_inputs(context / 'frontend-patches')
    sort_entry, _ = sort_contract(context)
    if manifest['sort_endpoint'] != sort_entry or manifest['filter_targets'] != FILTER_AFTER or not isinstance(manifest['cleanup_production'], dict) or not manifest['cleanup_production']:
        raise RuntimeError('Final navigation source contract drift')
    return context, manifest


def build(context, receipt):
    context, manifest = load(context, receipt)
    parent = json.loads(subprocess.check_output(['docker', 'image', 'inspect', BASE_TAG], text=True))[0]
    if parent['Id'] != BASE_IMAGE or len(parent['RootFS']['Layers']) != 13:
        raise RuntimeError('Final navigation parent differs')
    arguments = {'FILTER_LABEL_REVISION': FILTER_REVISION, 'SORT_ENDPOINT_REVISION': SORT_REVISION, 'DIAGNOSTIC_CLEANUP_REVISION': CLEANUP_REVISION, 'FINAL_NAVIGATION_REVISION': manifest['integration_revision']}
    labels = {'crm.navigation.filter-label.revision': FILTER_REVISION, 'crm.navigation.sort-endpoint.revision': SORT_REVISION, 'crm.navigation.diagnostic-cleanup.revision': CLEANUP_REVISION, 'crm.navigation.integration.revision': manifest['integration_revision'], 'crm.navigation.base': BASE_IMAGE}
    tag = 'crm-local:' + context.name
    command = ['docker', 'build', '--network=none', '--pull=false', '--progress=plain']
    for name, val in arguments.items():
        command += ['--build-arg', name + '=' + val]
    command += ['-t', tag, '-f', str(context / 'deploy/Dockerfile.final-navigation'), str(context)]
    subprocess.run(command, check=True)
    image = json.loads(subprocess.check_output(['docker', 'image', 'inspect', tag], text=True))[0]
    expected = dict(parent['Config'], Labels=dict(parent['Config']['Labels'], **labels))
    if image['Config'] != expected or not re.fullmatch('sha256:[0-9a-f]{64}', image['Id']) or not 13 < len(image['RootFS']['Layers']) <= 16 or image['RootFS']['Layers'][:13] != parent['RootFS']['Layers']:
        raise RuntimeError('Final navigation Config/layer inheritance differs')
    if any('diagnostic.enabled' in key for key in image['Config']['Labels']) or any('VITE_CRM_READ_FAILURE_DIAGNOSTICS' in value for value in image['Config'].get('Env', [])):
        raise RuntimeError('Temporary diagnostic configuration remains in final image')
    out = ROOT / '.runtime' / (context.name + '-build-result.json')
    with out.open('x', encoding='utf-8') as stream:
        json.dump(dict(source_receipt=receipt, source=manifest, image=image, candidate_tag=tag), stream, indent=2, sort_keys=True)
        stream.write('\n')
    print('Final navigation candidate; no site activation:', tag, image['Id'])
    return image


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--integration-commit')
    parser.add_argument('--context', type=Path)
    parser.add_argument('--receipt')
    parser.add_argument('--build', action='store_true')
    args = parser.parse_args()
    if args.context:
        if args.integration_commit or not args.receipt:
            parser.error('Context reuse requires receipt only')
        context, manifest = load(args.context, args.receipt)
        receipt = args.receipt
    else:
        if not args.integration_commit or args.receipt:
            parser.error('Exact integration commit required')
        context, manifest, receipt = prepare(args.integration_commit)
    if args.build:
        build(context, receipt)

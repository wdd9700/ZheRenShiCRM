import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import uuid

from prepare_integration import ROOT, committed_files, ordinary_path, write_sources
from apply_filter_label_delta import AFTER as FILTER_AFTER, inputs as filter_inputs
from verify_read_diagnostic import DIAGNOSTIC_TARGETS, contract as diagnostic_contract

BASE_TAG = 'crm-local:common-ui-3c8a0ee657aa461d8d4f617807a5bf10'
BASE_IMAGE = 'sha256:35d0b0bd36ae08fa9d434b4275cb50bc4e202607c5f8ad95a34e6441c4922101'
BASE_CONFIG = 'sha256:310b0d22992ac555ea577f2fdc770f9adc0e21191d9d7e1855c6edd2d230649d'
FILTER_REVISION = '3bcad3233cf674a145d47cbe3c927ff9eb432743'
BASE_DIAGNOSTIC_REVISION = '9403d5a7ee4eb2d50eee3faf844d679a6aee5c80'
FILTER_FILES = frozenset({'frontend-patches/common-ui-localization/apply.py', 'frontend-patches/common-ui-localization/manifest.json', 'frontend-patches/localization/manifest.json', 'frontend-patches/localization/zh-CN.json'})
DIAGNOSTIC_FILES = frozenset({'frontend-patches/c011000/manifest.json', 'frontend-patches/c011000/source_edits.py', 'frontend-patches/c011000/payload/resources/accountBoundary.js', 'frontend-patches/c011000/payload/resources/resources.js'})
DEPLOY_FILES = frozenset({'deploy/Dockerfile.concentrated-ui', 'deploy/Dockerfile.concentrated-ui.dockerignore', 'deploy/apply_filter_label_delta.py', 'deploy/verify_read_diagnostic.py', 'deploy/verify_concentrated_ui.py'})


def sha(data):
    return hashlib.sha256(data).hexdigest()


def selected(commit, prefix, expected):
    files = committed_files(commit, prefix)
    if not expected <= set(files):
        raise RuntimeError('Missing concentrated committed source')
    return {name: files[name] for name in expected}


def diagnostic_outputs(context, revision):
    base = json.loads((context / 'diagnostic-base-manifest.json').read_bytes())
    updated = json.loads((context / 'frontend-patches/c011000/manifest.json').read_bytes())
    if len(base) != 43 or len(updated) != 43 or {entry['target'] for entry in base} != {entry['target'] for entry in updated}:
        raise RuntimeError('Diagnostic must preserve the exact original43 target set')
    old = {entry['target']: entry for entry in base}
    new = {entry['target']: entry for entry in updated}
    changed = {name for name in old if old[name] != new[name]}
    if changed != DIAGNOSTIC_TARGETS:
        raise RuntimeError('Diagnostic modified targets differ from the bounded four-source contract')
    path = context / 'frontend-patches/c011000/source_edits.py'
    spec = importlib.util.spec_from_file_location('concentrated_diagnostic_source_edits', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    entries, payloads = [], {}
    for name in sorted(DIAGNOSTIC_TARGETS):
        entry = new[name]
        before = old[name].get('after', old[name]['before'])
        if entry['before'] != old[name]['before']:
            raise RuntimeError('Diagnostic upstream before contract changed')
        if entry.get('payload'):
            if entry['payload'] != old[name].get('payload') or name not in {'frontend/node_modules/frappe-ui/src/resources/accountBoundary.js', 'frontend/node_modules/frappe-ui/src/resources/resources.js'}:
                raise RuntimeError('Unexpected diagnostic payload target')
            data = (context / 'frontend-patches/c011000/payload' / entry['payload']).read_bytes()
        else:
            original = (context / 'diagnostic-upstream' / Path(name).name).read_bytes()
            if sha(original) != entry['before'] or old[name]['before'] != entry['before']:
                raise RuntimeError('Diagnostic upstream utils input differs')
            data = module.transform(name, original)
        if sha(data) != entry['after']:
            raise RuntimeError('Diagnostic generated after differs: ' + name)
        payload = name.replace('/', '__')
        entries.append(dict(target=name, before=before, after=entry['after'], payload=payload))
        payloads['diagnostic-payloads/' + payload] = ('100644', data)
    return dict(source_revision=revision, targets=entries, temporary=True, default_enabled=False), payloads


def prepare(diagnostic_revision, integration_revision, upstream, enabled=False):
    files = selected(FILTER_REVISION, 'frontend-patches/', FILTER_FILES)
    files.update(selected(diagnostic_revision, 'frontend-patches/c011000/', DIAGNOSTIC_FILES))
    files.update(selected(integration_revision, 'deploy/', DEPLOY_FILES))
    base_files = committed_files(BASE_DIAGNOSTIC_REVISION, 'frontend-patches/c011000/')
    base = base_files['frontend-patches/c011000/manifest.json']
    if sha(base[1]) != '2060a0f99a778797e8c2b2f97527ccc6bbf96288b7a23362d9319096fde177a3':
        raise RuntimeError('Original diagnostic predecessor manifest differs')
    files['diagnostic-base-manifest.json'] = base
    for name in ('request.ts', 'frappeRequest.ts'):
        original = upstream / 'frontend/node_modules/frappe-ui/src/utils' / name
        ordinary_path(original)
        if not original.is_file() or original.stat().st_nlink != 1:
            raise RuntimeError('Diagnostic upstream source must be ordinary')
        files['diagnostic-upstream/' + name] = ('100644', original.read_bytes())
    runtime = ROOT / '.runtime'
    ordinary_path(runtime)
    runtime.mkdir(exist_ok=True)
    if subprocess.run(['git', '-C', str(ROOT.parent), 'check-ignore', '--quiet', '--no-index', '--', 'deploy/.runtime/concentrated-probe']).returncode:
        raise RuntimeError('Concentrated context must be ignored')
    context = runtime / ('concentrated-ui-' + uuid.uuid4().hex)
    context.mkdir()
    hashes = write_sources(files, context)
    diagnostic, generated = diagnostic_outputs(context, diagnostic_revision)
    hashes.update(write_sources(generated, context))
    data = (json.dumps(diagnostic, indent=2, sort_keys=True) + '\n').encode()
    hashes.update(write_sources({'read-diagnostic-delta.json': ('100644', data)}, context))
    filter_inputs(context / 'frontend-patches')
    manifest = dict(schema='concentrated-ui-v1', base_image=BASE_IMAGE, base_config=BASE_CONFIG, filter_revision=FILTER_REVISION, diagnostic_revision=diagnostic_revision, integration_revision=integration_revision, diagnostics_enabled=bool(enabled), files=hashes, filter_targets=FILTER_AFTER, diagnostic=diagnostic)
    (context / 'concentrated-source-manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    receipt = sha((context / 'concentrated-source-manifest.json').read_bytes())
    load(context, receipt)
    print('Concentrated context:', context)
    print('Concentrated receipt:', receipt)
    print('Temporary read diagnostics explicitly enabled:', enabled)
    return context, manifest, receipt


def load(value, receipt):
    context = Path(value)
    ordinary_path(context)
    if not context.is_absolute() or context.parent.resolve() != (ROOT / '.runtime').resolve() or not re.fullmatch('concentrated-ui-[0-9a-f]{32}', context.name):
        raise RuntimeError('Concentrated context location differs')
    raw = (context / 'concentrated-source-manifest.json').read_bytes()
    if not re.fullmatch('[0-9a-f]{64}', receipt) or sha(raw) != receipt:
        raise RuntimeError('Concentrated receipt differs')
    manifest = json.loads(raw)
    if set(manifest) != {'schema', 'base_image', 'base_config', 'filter_revision', 'diagnostic_revision', 'integration_revision', 'diagnostics_enabled', 'files', 'filter_targets', 'diagnostic'} or manifest['schema'] != 'concentrated-ui-v1' or (manifest['base_image'], manifest['base_config']) != (BASE_IMAGE, BASE_CONFIG) or manifest['filter_revision'] != FILTER_REVISION or type(manifest['diagnostics_enabled']) is not bool:
        raise RuntimeError('Concentrated source schema differs')
    for key in ('diagnostic_revision', 'integration_revision'):
        if not isinstance(manifest[key], str) or not re.fullmatch('[0-9a-f]{40}', manifest[key]):
            raise RuntimeError('Exact concentrated source revisions required')
    expected = FILTER_FILES | DIAGNOSTIC_FILES | DEPLOY_FILES | {'diagnostic-base-manifest.json', 'diagnostic-upstream/request.ts', 'diagnostic-upstream/frappeRequest.ts', 'read-diagnostic-delta.json'}
    expected |= {'diagnostic-payloads/' + name.replace('/', '__') for name in DIAGNOSTIC_TARGETS}
    if not isinstance(manifest['files'], dict) or set(manifest['files']) != expected:
        raise RuntimeError('Concentrated source whitelist differs')
    actual = set()
    for path in context.rglob('*'):
        ordinary_path(path)
        if path.is_file():
            if path.stat().st_nlink != 1:
                raise RuntimeError('Hardlinked concentrated source refused')
            actual.add(path.relative_to(context).as_posix())
    if actual != expected | {'concentrated-source-manifest.json'}:
        raise RuntimeError('Unexpected or missing concentrated context source')
    for name, digest in manifest['files'].items():
        if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest) or sha((context / name).read_bytes()) != digest:
            raise RuntimeError('Concentrated source drift: ' + name)
    generated, payloads = diagnostic_outputs(context, manifest['diagnostic_revision'])
    if manifest['diagnostic'] != generated or diagnostic_contract(context) != generated or manifest['filter_targets'] != FILTER_AFTER:
        raise RuntimeError('Concentrated diagnostic/filter contract differs')
    for name, (_, data) in payloads.items():
        if data != (context / name).read_bytes():
            raise RuntimeError('Diagnostic generated payload changed')
    filter_inputs(context / 'frontend-patches')
    return context, manifest


def build(context, receipt):
    context, manifest = load(context, receipt)
    parent = json.loads(subprocess.check_output(['docker', 'image', 'inspect', BASE_TAG], text=True))[0]
    if parent['Id'] != BASE_IMAGE or len(parent['RootFS']['Layers']) != 13:
        raise RuntimeError('Concentrated deployed35d0 identity/layers differ')
    enabled = '1' if manifest['diagnostics_enabled'] else '0'
    labels = {'crm.focused.filter-label.revision': FILTER_REVISION, 'crm.focused.read-diagnostic.revision': manifest['diagnostic_revision'], 'crm.focused.integration.revision': manifest['integration_revision'], 'crm.focused.read-diagnostic.enabled': enabled, 'crm.focused.base': BASE_IMAGE}
    tag = 'crm-local:' + context.name
    command = ['docker', 'build', '--network=none', '--pull=false', '--progress=plain']
    for argument, value in (('FILTER_LABEL_REVISION', FILTER_REVISION), ('READ_DIAGNOSTIC_REVISION', manifest['diagnostic_revision']), ('CONCENTRATED_INTEGRATION_REVISION', manifest['integration_revision']), ('VITE_CRM_READ_FAILURE_DIAGNOSTICS', enabled)):
        command += ['--build-arg', argument + '=' + value]
    command += ['-t', tag, '-f', str(context / 'deploy/Dockerfile.concentrated-ui'), str(context)]
    subprocess.run(command, check=True)
    image = json.loads(subprocess.check_output(['docker', 'image', 'inspect', tag], text=True))[0]
    expected = dict(parent['Config'], Labels=dict(parent['Config']['Labels'], **labels))
    if image['Config'] != expected or not re.fullmatch('sha256:[0-9a-f]{64}', image['Id']) or not 13 < len(image['RootFS']['Layers']) <= 24 or image['RootFS']['Layers'][:13] != parent['RootFS']['Layers']:
        raise RuntimeError('Concentrated runtime Config or inherited layers differ')
    destination = ROOT / '.runtime' / (context.name + '-build-result.json')
    with destination.open('x', encoding='utf-8') as stream:
        json.dump(dict(source_receipt=receipt, source=manifest, image=image, candidate_tag=tag, temporary_diagnostic=True), stream, indent=2, sort_keys=True)
        stream.write('\n')
    print('Temporary diagnostic candidate only; no deployment:', tag, image['Id'])
    return image


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Prepare one bounded Filter plus temporary default-off diagnostic increment; never deploys')
    parser.add_argument('--diagnostic-commit')
    parser.add_argument('--integration-commit')
    parser.add_argument('--diagnostic-upstream-root', type=Path)
    parser.add_argument('--enable-read-failure-diagnostics', action='store_true')
    parser.add_argument('--context', type=Path)
    parser.add_argument('--receipt')
    parser.add_argument('--build', action='store_true')
    args = parser.parse_args()
    if args.context:
        if any((args.diagnostic_commit, args.integration_commit, args.diagnostic_upstream_root, args.enable_read_failure_diagnostics)) or not args.receipt:
            parser.error('Context reuse requires receipt only')
        context, manifest = load(args.context, args.receipt)
        receipt = args.receipt
    else:
        if not all((args.diagnostic_commit, args.integration_commit, args.diagnostic_upstream_root)) or args.receipt:
            parser.error('Exact diagnostic/integration commits and fixed public upstream root required')
        context, manifest, receipt = prepare(args.diagnostic_commit, args.integration_commit, args.diagnostic_upstream_root, args.enable_read_failure_diagnostics)
    if args.build:
        build(context, receipt)

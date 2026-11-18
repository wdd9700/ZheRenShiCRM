import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid

from contract import (APP, BASE_CONFIG, BASE_INDEX, BASE_LAYERS_SHA, BASE_TAG, BUILD_FILES,
                      CONTROLLER, FALLBACK_REVISION, FALLBACK_SHA, HTML, NATIVE_INPUTS, PATCH,
                      RECEIPT, SCHEMA, labels, patch_contract, sha, valid_sha)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prepare_integration import ROOT, committed_files, git, ordinary_path, write_sources

RUNTIME = ROOT / '.runtime'


def sources(schedule, integration):
    patch = committed_files(schedule, PATCH)
    names = {PATCH + name for name in ('apply.py', 'manifest.json', 'payload/TeamSchedule.vue', 'payload/native-controls.css')}
    if not names <= patch.keys() or {name for name in patch if name.startswith(PATCH + 'payload/')} != names - {PATCH + 'apply.py', PATCH + 'manifest.json'}:
        raise RuntimeError('Native patch runtime source whitelist differs')
    files = {name: patch[name] for name in names}
    app = committed_files(schedule, APP)
    files.update({'app-source/team_schedule/' + name: app[APP + name] for name in NATIVE_INPUTS})
    files['legacy/target/' + CONTROLLER] = app[APP + CONTROLLER]
    fallback = committed_files(FALLBACK_REVISION, APP + 'www/')[APP + HTML]
    if sha(fallback[1]) != FALLBACK_SHA:
        raise RuntimeError('M48-compatible fallback template differs')
    files['legacy/target/' + HTML] = fallback
    deploy = committed_files(integration, 'deploy/native-schedule/')
    files.update({name: deploy[name] for name in BUILD_FILES})
    return files


def source_manifest(schedule, integration, files):
    return dict(schema=SCHEMA, base_index=BASE_INDEX, base_config=BASE_CONFIG,
                fallback_revision=FALLBACK_REVISION, schedule_revision=schedule,
                integration_revision=integration, files=files)


def prepare(schedule, integration):
    exported = sources(schedule, integration)
    ordinary_path(RUNTIME)
    git('check-ignore', '--quiet', '--no-index', '--', 'deploy/.runtime/native-schedule-probe')
    RUNTIME.mkdir(exist_ok=True)
    context = RUNTIME / ('native-schedule-' + uuid.uuid4().hex)
    context.mkdir()
    files = write_sources(exported, context)
    patch_contract(context, files)
    manifest = source_manifest(schedule, integration, files)
    raw = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()
    (context / RECEIPT).write_bytes(raw)
    digest = sha(raw)
    load(context, digest)
    print('S021 context:', context)
    print('S021 source receipt SHA256:', digest)
    return context, digest


def load(context, receipt):
    ordinary_path(context)
    if not context.is_absolute() or context.parent.resolve() != RUNTIME.resolve() or not re.fullmatch('native-schedule-[0-9a-f]{32}', context.name):
        raise RuntimeError('Not a context beneath this checkout’s ignored deploy/.runtime')
    path = context / RECEIPT
    ordinary_path(path)
    if not path.is_file() or path.stat().st_nlink != 1:
        raise RuntimeError('Not an ordinary S021 receipt')
    raw = path.read_bytes()
    if not valid_sha(receipt) or sha(raw) != receipt:
        raise RuntimeError('S021 context receipt mismatch')
    manifest = json.loads(raw)
    schedule, integration = manifest['schedule_revision'], manifest['integration_revision']
    expected = {name: sha(source[1]) for name, source in sources(schedule, integration).items()}
    if manifest != source_manifest(schedule, integration, expected):
        raise RuntimeError('S021 manifest differs from exact Git source identity')
    actual = set()
    for node in context.rglob('*'):
        ordinary_path(node)
        relative = node.relative_to(context).as_posix()
        if node.is_file() and node.stat().st_nlink == 1:
            actual.add(relative)
        elif not node.is_dir():
            raise RuntimeError('Not an ordinary S021 build context path: ' + relative)
    if actual != set(expected) | {RECEIPT}:
        raise RuntimeError('Missing/unmanifested native build source')
    for name, digest in expected.items():
        if sha((context / name).read_bytes()) != digest:
            raise RuntimeError('Changed native build source: ' + name)
    patch_contract(context, expected)
    return manifest


def inspect(image):
    results = json.loads(subprocess.check_output(['docker', 'image', 'inspect', image]))
    if len(results) != 1:
        raise RuntimeError('Expected exactly one image: ' + image)
    return results[0]


def verify_base(image):
    layers = image['RootFS']['Layers']
    if (image['Id'] not in (BASE_CONFIG, BASE_INDEX) or image['Os'] != 'linux' or image['Architecture'] != 'amd64'
            or len(layers) != 16 or sha(('\n'.join(layers) + '\n').encode()) != BASE_LAYERS_SHA):
        raise RuntimeError('Exact e14b6/c260 linux/amd64 release and all 16 diff_ids required; no substitute/base upgrade')
    return layers


def build(context, receipt):
    manifest = load(context, receipt)
    parent = inspect(BASE_TAG)
    layers = verify_base(parent)
    tag = 'crm-local:' + context.name
    command = ['docker', 'build', '--network=none', '--pull=false', '--progress=plain',
               '--build-arg', 'SCHEDULE_REVISION=' + manifest['schedule_revision'],
               '--build-arg', 'INTEGRATION_REVISION=' + manifest['integration_revision'],
               '-f', str(context / 'deploy/native-schedule/Dockerfile'), '-t', tag, str(context)]
    subprocess.run(command, check=True)
    image = inspect(tag)
    child_layers = image['RootFS']['Layers']
    expected = dict(parent['Config'], Labels=dict(parent['Config']['Labels'], **labels(manifest)))
    if image['Config'] != expected or child_layers[:len(layers)] != layers or not len(layers) < len(child_layers) <= 20:
        raise RuntimeError('S021 runtime Config or e14b6 layer inheritance differs')
    out = RUNTIME / (context.name + '-build-result.json')
    with out.open('x', encoding='utf-8') as stream:
        json.dump(dict(candidate_tag=tag, candidate_inspect=image, source_receipt=receipt, manifest=manifest),
                  stream, indent=2, sort_keys=True)
        stream.write('\n')
    print('Built offline candidate only:', tag, image['Id'])
    print('S021 build receipt:', out)


def main():
    parser = argparse.ArgumentParser(description='Compose S020 on the exact e14b6 release; no service activation')
    parser.add_argument('--schedule-commit')
    parser.add_argument('--integration-commit')
    parser.add_argument('--context', type=Path)
    parser.add_argument('--receipt')
    parser.add_argument('--build', action='store_true')
    args = parser.parse_args()
    if args.context:
        if not args.receipt or args.schedule_commit or args.integration_commit:
            parser.error('Context reuse requires only --context and --receipt, optionally --build')
        context, receipt = args.context, args.receipt
        if not args.build:
            load(context, receipt)
    else:
        if not args.integration_commit or not args.schedule_commit or args.receipt:
            parser.error('Preparing a context requires both full Git commit IDs')
        context, receipt = prepare(args.schedule_commit, args.integration_commit)
    if args.build:
        build(context, receipt)


if __name__ == '__main__':
    main()

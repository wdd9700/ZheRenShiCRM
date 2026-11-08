import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import uuid

from prepare_integration import ROOT, committed_files, ordinary_path, write_sources
from verify_ui_integration import ORDER, chain

BASE_TAG = 'crm-local:m9-lowdepth-ld2-195e623cfeb7458587597600e8e1e3e7'
BASE_IMAGE = 'sha256:e17300da434bd0c251adf618c86db26c718511fec6ab6bfe2a99e7fd91bebe41'
BASE_CONFIG = 'sha256:caf102a5716f4be0fc16ac9590038867bbe34c8e5419ff9fa92753ed6f1bf6d9'
CACHE = '9403d5a7ee4eb2d50eee3faf844d679a6aee5c80'
NAVIGATION = '76f23be38dd993f32724c34d5184d8cf75c77146'
PATCH_FILES = {
    'c011000': frozenset('apply.py check_apply.py consumer-fixtures/router.js consumer-fixtures/users.js consumer-fixtures/views.js controlled.test.mjs initialization.test.mjs manifest.json payload/main.js payload/resources/accountBoundary.js payload/resources/documentResource.js payload/resources/listResource.js payload/resources/local.ts payload/resources/resources.js payload/resumeRuntime.js payload/safeResume.js payload/session.js real-runtime.test.mjs resume.test.mjs runtime-evidence/l3-scheduling-4ff499e.json runtime_sources.py sfc-request-diagnostics.mjs sfc-resume-diagnostic.test.mjs sfc-resume.test.mjs source_edits.py vitest-bridge.test.js vitest.sfc.config.mjs'.split()),
    'l3-scheduling': frozenset('README.md apply.py check_apply.py expected/AppSidebar.fixed-crm.diff fixtures/AppSidebar.c011000-resume.vue fixtures/AppSidebar.fixed-crm.vue manifest.json sfc_check.mjs'.split()),
    'dark-ui': frozenset('apply.py check_apply.py fixtures/App.vue fixtures/UserDropdown.vue fixtures/index.css manifest.json payload/crm-theme.css prerequisites.json'.split()),
    'localization': frozenset('README.md apply.py manifest.json runtime.test.cjs test_localization.py zh-CN.json'.split()),
    'branding': frozenset('.gitattributes apply.py check_apply.py fixtures/crm__hooks.py fixtures/frontend__index.html manifest.json payload/login-theme.css payload/ui_branding.py'.split()),
}
DARK_OVERLAYS = frozenset({
    'apps/resource_import/resource_import/www/resource-import.html',
    'apps/team_access/team_access/www/team-activities.html',
    'apps/team_schedule/team_schedule/public/crm-theme.css',
    'apps/team_schedule/team_schedule/public/team-schedule.css',
    'apps/team_schedule/team_schedule/public/team-schedule.js',
    'apps/team_schedule/team_schedule/www/team-schedule.html',
})
LOCAL_OVERLAYS = frozenset({'apps/team_schedule/team_schedule/public/crm-zh-cn.js'})
DEPLOY_FILES = frozenset({'deploy/Dockerfile.ui', 'deploy/Dockerfile.ui.dockerignore', 'deploy/verify_ui_integration.py', 'deploy/ui_build_guard.py'})


def selected(commit, prefix, expected):
    source = committed_files(commit, prefix)
    if not expected <= set(source):
        raise RuntimeError('Missing required committed UI source: ' + str(sorted(expected - set(source))))
    return {path: source[path] for path in expected}


def sources(revisions):
    if set(revisions) != set(ORDER):
        raise RuntimeError('UI revision set differs from the ordered contract')
    if revisions['c011000'] != CACHE or revisions['l3-scheduling'] != NAVIGATION:
        raise RuntimeError('M24/M30 revisions are fixed to the already-online production inputs')
    result = {}
    for name in ORDER:
        prefix = f'frontend-patches/{name}/'
        found = committed_files(revisions[name], prefix)
        if set(found) != {prefix + path for path in PATCH_FILES[name]}:
            raise RuntimeError('Unexpected committed patch file whitelist: ' + name)
        result.update(found)
    result.update(selected(revisions['dark-ui'], 'apps/', DARK_OVERLAYS))
    result.update(selected(revisions['localization'], 'apps/', LOCAL_OVERLAYS))
    result.update(selected(revisions['branding'], 'deploy/', DEPLOY_FILES))
    return result


def prepare(dark, localization, integration):
    revisions = dict(zip(ORDER, (CACHE, NAVIGATION, dark, localization, integration)))
    exported = sources(revisions)
    runtime = ROOT / '.runtime'
    ordinary_path(runtime)
    runtime.mkdir(exist_ok=True)
    if subprocess.run(['git', '-C', str(ROOT.parent), 'check-ignore', '--quiet', '--no-index', '--', 'deploy/.runtime/context-probe']).returncode:
        raise RuntimeError('UI context must be Git-ignored')
    context = runtime / ('ui-' + uuid.uuid4().hex)
    context.mkdir()
    files = write_sources(exported, context)
    chain(context / 'frontend-patches')
    overlays = {path: files[path] for path in DARK_OVERLAYS | LOCAL_OVERLAYS}
    manifest = dict(schema='u030-v1', base_tag=BASE_TAG, base_image=BASE_IMAGE, base_config=BASE_CONFIG, revisions=revisions, files=files, overlays=overlays)
    (context / 'ui-source-manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    receipt = hashlib.sha256((context / 'ui-source-manifest.json').read_bytes()).hexdigest()
    load(context, receipt)
    print('UI context:', context)
    print('UI source manifest SHA256:', receipt)
    return context, manifest, receipt


def load(value, receipt):
    context = Path(value)
    ordinary_path(context)
    if not context.is_absolute() or context.parent.resolve() != (ROOT / '.runtime').resolve() or not re.fullmatch('ui-[0-9a-f]{32}', context.name):
        raise RuntimeError('UI context must be this checkout prepared directory')
    ordinary_path(context / 'ui-source-manifest.json')
    raw = (context / 'ui-source-manifest.json').read_bytes()
    if not re.fullmatch('[0-9a-f]{64}', receipt) or hashlib.sha256(raw).hexdigest() != receipt:
        raise RuntimeError('UI context receipt mismatch')
    manifest = json.loads(raw)
    if set(manifest) != {'schema', 'base_tag', 'base_image', 'base_config', 'revisions', 'files', 'overlays'} or manifest['schema'] != 'u030-v1':
        raise RuntimeError('UI context schema mismatch')
    if (manifest['base_tag'], manifest['base_image'], manifest['base_config']) != (BASE_TAG, BASE_IMAGE, BASE_CONFIG):
        raise RuntimeError('UI base identity mismatch')
    revisions = manifest['revisions']
    if set(revisions) != set(ORDER) or revisions['c011000'] != CACHE or revisions['l3-scheduling'] != NAVIGATION:
        raise RuntimeError('UI revision contract mismatch')
    if any(not isinstance(value, str) or not re.fullmatch('[0-9a-f]{40}', value) for value in revisions.values()):
        raise RuntimeError('Exact UI source commits required')
    paths = {f'frontend-patches/{name}/{path}' for name in ORDER for path in PATCH_FILES[name]}
    paths |= DARK_OVERLAYS | LOCAL_OVERLAYS | DEPLOY_FILES
    hashes = manifest['files']
    if not isinstance(hashes, dict) or set(hashes) != paths or any(not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value) for value in hashes.values()):
        raise RuntimeError('UI context differs from its exact source whitelist')
    if manifest['overlays'] != {path: hashes[path] for path in DARK_OVERLAYS | LOCAL_OVERLAYS}:
        raise RuntimeError('UI context overlay whitelist mismatch')
    actual = set()
    for path in context.rglob('*'):
        ordinary_path(path)
        if path.is_file():
            if path.stat().st_nlink != 1:
                raise RuntimeError('Hardlinked context refused')
            actual.add(path.relative_to(context).as_posix())
    if actual != set(hashes) | {'ui-source-manifest.json'}:
        raise RuntimeError('Unmanifested or missing UI context source')
    for path, digest in hashes.items():
        if hashlib.sha256((context / path).read_bytes()).hexdigest() != digest:
            raise RuntimeError('Prepared UI source drift: ' + path)
    chain(context / 'frontend-patches')
    return context, manifest


def build(context, receipt):
    context, manifest = load(context, receipt)
    source = json.loads(subprocess.check_output(['docker', 'image', 'inspect', BASE_TAG], text=True))[0]
    if source['Id'] != BASE_IMAGE or len(source['RootFS']['Layers']) != 2:
        raise RuntimeError('Local lowdepth base identity/layer count differs')
    tag = 'crm-local:' + context.name
    subprocess.run(['docker', 'build', '--network=none', '--pull=false', '--progress=plain', '-t', tag, '-f', str(context / 'deploy/Dockerfile.ui'), str(context)], check=True)
    image = json.loads(subprocess.check_output(['docker', 'image', 'inspect', tag], text=True))[0]
    if len(image['RootFS']['Layers']) > 16:
        raise RuntimeError('UI image unexpectedly exceeds lowdepth layer budget')
    print('Candidate only; no runtime activation:', tag, image['Id'])
    return image


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Exact reviewed U030 inputs on the fixed lowdepth five-app base; never activates a site')
    parser.add_argument('--dark-commit')
    parser.add_argument('--localization-commit')
    parser.add_argument('--integration-commit')
    parser.add_argument('--context', type=Path)
    parser.add_argument('--context-sha256')
    parser.add_argument('--build', action='store_true')
    args = parser.parse_args()
    if args.context:
        if any((args.dark_commit, args.localization_commit, args.integration_commit)) or not args.context_sha256:
            parser.error('Context reuse requires only --context and its --context-sha256 receipt')
        context, manifest = load(args.context, args.context_sha256)
        receipt = args.context_sha256
    else:
        if args.context_sha256 or not all((args.dark_commit, args.localization_commit, args.integration_commit)):
            parser.error('Three exact reviewed UI revisions are required')
        context, manifest, receipt = prepare(args.dark_commit, args.localization_commit, args.integration_commit)
    if args.build:
        build(context, receipt)

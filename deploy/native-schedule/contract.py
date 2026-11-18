import hashlib
import re
from pathlib import PurePosixPath

BASE_TAG = 'crm-local:final-navigation-9043bb5dc09a4abc9d562c7bcf2ef4d2'
BASE_INDEX = 'sha256:e14b6cce43cf861f92ffaf4f55935434897ed156efea04f8eacc56311e39a4dd'
BASE_CONFIG = 'sha256:c2601699d018675f1e2fc87a13c7fa4963090182eccfc70a8e51ed5ccdfbe062'
BASE_LAYERS_SHA = 'fb75287484298a947b53d7d2f3b8822fdeae478e8607ac6da3a4e317a2fda083'
BASE_ARCHIVE_SHA = '0a91cbcc298ef599de35f46b0ab09ab696bc389fc0697c6d1feedaf163441679'
CRM_HEAD = '36bd8859f2a6345a620477bc708d0546e8c3f08a'
SCHEMA = 'native-schedule-s021-v1'
RECEIPT = 'native-schedule-source-manifest.json'
PATCH = 'frontend-patches/l3-scheduling/native/'
DEPLOY = 'deploy/native-schedule/'
APP = 'apps/team_schedule/team_schedule/'
HTML = 'www/team-schedule.html'
CONTROLLER = 'www/team_schedule.py'
FALLBACK_REVISION = 'd4330d3c0baeb2fa75ccdd2dd993aab60f90babe'
FALLBACK_SHA = 'cdb9e49ae2832574c231d4d9b4b0ee0b41abf6f8ed1e3b3e1c63a82f953a8f9f'
BASE_HTML_SHA = '0bd3175203476a7c75fbf71e63a855e53adecf656900bb089660d8b710b496b5'
BASE_CONTROLLER_SHA = '2743ce92d01712f98f9014da78b12405a1c1c15480462f9c4945f39b6835edea'
NATIVE_INPUTS = frozenset({HTML, 'public/team-schedule.js', 'public/team-schedule.css', 'public/crm-zh-cn.js'})
BUILD_FILES = frozenset({DEPLOY + name for name in ('Dockerfile', 'contract.py', 'verify.py')})
EXISTING_CRM_TARGETS = frozenset({
    'frontend/src/components/Layouts/AppSidebar.vue', 'frontend/src/router.js',
    'frontend/src/resumeRuntime.js', 'frontend/node_modules/frappe-ui/src/resources/accountBoundary.js',
    'crm/www/crm.py',
})


def sha(data):
    return hashlib.sha256(data).hexdigest()


def valid_sha(value, size=64):
    return isinstance(value, str) and re.fullmatch(f'[0-9a-f]{{{size}}}', value) is not None


def safe_relative(value):
    path = PurePosixPath(value)
    if not path.parts or path.is_absolute() or path.as_posix() != value or '..' in path.parts or '\\' in value or ':' in value:
        raise RuntimeError('Unsafe relative source path: ' + value)
    return value


NEW_CRM_TARGETS = frozenset('frontend/src/pages/' + name for name in (
    'TeamSchedule.vue', 'teamScheduleController.mjs', 'teamScheduleCatalog.mjs', 'teamSchedule.css',
))


def patch_contract(root, files):
    import json

    value = json.loads((root / (PATCH + 'manifest.json')).read_bytes())
    if set(value) != {'crm_commit', 'app_sources', 'targets'} or value['crm_commit'] != CRM_HEAD:
        raise RuntimeError('Unexpected native patch manifest identity')
    expected_inputs = {p: files['app-source/team_schedule/' + p] for p in NATIVE_INPUTS}
    if value['app_sources'] != expected_inputs:
        raise RuntimeError('Native patch package source hashes differ')
    targets = {}
    for entry in value['targets']:
        name = entry['target']
        if set(entry) != {'target', 'before', 'after'} or name in targets or not valid_sha(entry['after']):
            raise RuntimeError('Unexpected native patch target entry')
        if (name in EXISTING_CRM_TARGETS and not valid_sha(entry['before'])) or (name in NEW_CRM_TARGETS and entry['before'] is not None):
            raise RuntimeError('Invalid native predecessor: ' + name)
        targets[name] = entry
    if set(targets) != EXISTING_CRM_TARGETS | NEW_CRM_TARGETS:
        raise RuntimeError('Native patch target whitelist differs')
    return targets


def labels(manifest):
    return {
        'crm.native-schedule.integration': SCHEMA,
        'crm.native-schedule.base': BASE_CONFIG,
        'crm.native-schedule.revision': manifest['schedule_revision'],
        'crm.native-schedule.integration.revision': manifest['integration_revision'],
    }

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('l3_scheduling_apply', HERE / 'apply.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

manifest = json.loads((HERE / 'manifest.json').read_text(encoding='utf-8'))
target = manifest['targets'][0]


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def refused(root, check=False):
    before = snapshot(root)
    try:
        module.apply(root, check)
    except ValueError:
        assert snapshot(root) == before, 'Refusal modified fixture'
    else:
        raise AssertionError('Expected refusal')


def fixture_root(directory, fixture):
    root = Path(directory)
    (root / 'frontend').mkdir()
    destination = root / target['target']
    destination.parent.mkdir(parents=True)
    shutil.copyfile(HERE / fixture, destination)
    return root


# The patch must stay inside the navigation row of one non-identity file.
assert len(manifest['targets']) == 1
assert target['target'] == 'frontend/src/components/Layouts/AppSidebar.vue'
c011000 = json.loads((HERE.parent / 'c011000' / 'manifest.json').read_text(encoding='utf-8'))
assert target['target'] not in {entry['target'] for entry in c011000}
assert 'main.js' not in target['target']

for baseline in target['baselines']:
    data = (HERE / baseline['fixture']).read_bytes()
    assert hashlib.sha256(data).hexdigest() == baseline['before'], (
        'Fixture hash differs from declared baseline: ' + baseline['fixture']
    )
    assert baseline['before'] != baseline['after']

for baseline in target['baselines']:
    with tempfile.TemporaryDirectory(prefix='l3-scheduling-') as directory:
        root = fixture_root(directory, baseline['fixture'])
        destination = root / target['target']
        with patch.object(
            module.subprocess, 'check_output', return_value=manifest['crm_commit'] + '\n'
        ):
            original = snapshot(root)
            assert module.apply(root, True) == 1
            assert snapshot(root) == original, 'Dry run wrote files'

            drift = destination
            saved = drift.read_bytes()
            drift.write_bytes(saved + b'\nDRIFT')
            refused(root, True)
            refused(root)
            drift.write_bytes(saved)

            missing = root / target['target']
            missing.unlink()
            refused(root)
            missing.write_bytes(saved)

            assert module.apply(root) == 1
            patched = destination.read_bytes()
            assert hashlib.sha256(patched).hexdigest() == baseline['after']
            assert not list(destination.parent.glob('*.l3-scheduling-tmp'))

            refused(root)
            refused(root, True)

            if baseline['name'] == 'c011000-resume':
                text = patched.decode('utf-8')
                assert "import { accountBoundary } from '../../../node_modules/frappe-ui/src/resources/accountBoundary'" in text
                assert "if (props.mobile || accountBoundary.state === 'HYDRATING') return" in text
            else:
                assert 'accountBoundary' not in patched.decode('utf-8')

            assert patched.decode('utf-8').count('href="/team-schedule"') == 1
            assert patched.decode('utf-8').count('v-if="isCrmUser()"') == 1

        with patch.object(module.subprocess, 'check_output', return_value='wrong-head\n'):
            refused(root)

print(
    'PASS: two declared baselines (fixed-crm, c011000-resume) replay to their exact after hashes; '
    'dry-run is zero-write; drift/missing/wrong-HEAD/reapply are refused without writes; '
    'M24 identity/resume lines survive; single nav row only'
)

import argparse
import hashlib
import importlib.util
import io
import json
from contextlib import redirect_stderr, redirect_stdout
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
baselines = {item['name']: item for item in target['baselines']}


def sha(data):
    return hashlib.sha256(data).hexdigest()


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


def verify_refused(root):
    before = snapshot(root)
    try:
        module.verify(root, manifest)
    except ValueError:
        assert snapshot(root) == before, 'Verify refusal modified fixture'
    else:
        raise AssertionError('Expected verify refusal')


def fixture_root(directory, fixture):
    root = Path(directory)
    (root / 'frontend').mkdir(parents=True)
    destination = root / target['target']
    destination.parent.mkdir(parents=True)
    shutil.copyfile(HERE / fixture, destination)
    return root


# The patch stays inside one non-identity file, but that file IS an c011000
# target in the M24 variant: the two patches touch the same upstream file in a
# declared order. "Does not modify c011000" is not "no shared upstream target".
assert len(manifest['targets']) == 1
assert target['target'] == 'frontend/src/components/Layouts/AppSidebar.vue'
assert 'main.js' not in target['target']

for baseline in target['baselines']:
    data = (HERE / baseline['fixture']).read_bytes()
    assert sha(data) == baseline['before'], (
        'Fixture hash differs from declared baseline: ' + baseline['fixture']
    )
    assert baseline['before'] != baseline['after']

overlap = manifest['upstream_overlap']
assert overlap['target'] == target['target']
assert overlap['c011000_before'] == baselines['fixed-crm']['before'], (
    'declared upstream overlap before differs from the fixed-crm baseline'
)
assert overlap['c011000_after'] == baselines['c011000-resume']['before'], (
    'declared upstream overlap after differs from the c011000-resume baseline'
)
assert sha((HERE / baselines['c011000-resume']['fixture']).read_bytes()) == overlap['c011000_after']

parser = argparse.ArgumentParser()
parser.add_argument('--c011000', type=Path)
args = parser.parse_args()
c011000_path = args.c011000 or (HERE.parent / 'c011000' / 'manifest.json')
entry = None
if c011000_path.exists():
    entries = json.loads(c011000_path.read_text(encoding='utf-8'))
    if isinstance(entries, dict):
        entries = entries.get('targets') or entries.get('files') or []
    entry = next((item for item in entries if item.get('target') == target['target']), None)
if entry is None:
    print(
        'note: %s does not target %s; only the fixed-crm baseline is declared in that chain'
        % (c011000_path, target['target'])
    )
else:
    fixed, resume = baselines['fixed-crm'], baselines['c011000-resume']
    assert entry.get('before') == fixed['before'], (
        'c011000 order overlap mismatch: declared before %s != fixed-crm before %s'
        % (entry.get('before'), fixed['before'])
    )
    assert entry.get('after') == resume['before'], (
        'c011000 order overlap mismatch: declared after %s != c011000-resume before %s; '
        're-derive the candidate and re-pin the manifest with review'
        % (entry.get('after'), resume['before'])
    )
    assert sha((HERE / resume['fixture']).read_bytes()) == entry['after'], (
        'resume fixture differs from the c011000 declared after'
    )
    print(
        'PASS declared c011000 order overlap: %s before %s then this patch applies on %s'
        % (target['target'], entry.get('before'), entry.get('after'))
    )

manifest_digest = sha((HERE / 'manifest.json').read_bytes())

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
            verify_refused(root)

            saved = destination.read_bytes()
            destination.write_bytes(saved + b'\nDRIFT')
            refused(root, True)
            refused(root)
            verify_refused(root)
            destination.write_bytes(saved)

            destination.unlink()
            refused(root)
            refused(root, True)
            destination.write_bytes(saved)

            assert module.apply(root) == 1
            patched = destination.read_bytes()
            assert sha(patched) == baseline['after']
            assert not list(destination.parent.glob('*.l3-scheduling-tmp'))

            verified = snapshot(root)
            assert module.verify(root, manifest) == [
                (target['target'], baseline['name'], baseline['after'])
            ]
            assert snapshot(root) == verified, 'Verify wrote files'

            refused(root)
            refused(root, True)
            destination.write_bytes(patched)

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
            verify_refused(root)

# Derive is a read-only candidate generator: registered or unknown bytes.
with tempfile.TemporaryDirectory(prefix='l3-scheduling-derive-') as directory:
    known = Path(directory) / 'known.vue'
    known.write_bytes((HERE / baselines['fixed-crm']['fixture']).read_bytes())
    output = io.StringIO()
    with redirect_stdout(output):
        assert module.derive(known, manifest) == 0
    candidate = json.loads(output.getvalue())
    assert candidate['declared_baseline'] == 'fixed-crm'
    assert candidate['matches_declared_after'] is True
    assert candidate['after_candidate'] == baselines['fixed-crm']['after']
    assert candidate['writes'] is False and candidate['apply_authorized'] is False

    unknown = Path(directory) / 'unknown.vue'
    unknown.write_bytes((HERE / baselines['fixed-crm']['fixture']).read_bytes() + b'\n')
    output = io.StringIO()
    with redirect_stdout(output):
        assert module.derive(unknown, manifest) == 0
    candidate = json.loads(output.getvalue())
    assert candidate['declared_baseline'] is None
    assert candidate['matches_declared_after'] is False
    assert candidate['anchors_verified_unique'] is True
    assert candidate['before'] != baselines['fixed-crm']['before']
    assert candidate['apply_authorized'] is False

    blocked = fixture_root(Path(directory) / 'blocked', baselines['fixed-crm']['fixture'])
    (blocked / target['target']).write_bytes(unknown.read_bytes())
    with patch.object(
        module.subprocess, 'check_output', return_value=manifest['crm_commit'] + '\n'
    ):
        refused(blocked)

    broken = Path(directory) / 'broken.vue'
    broken.write_bytes(
        (HERE / baselines['fixed-crm']['fixture'])
        .read_bytes()
        .replace(
            b"const { users, isManager } = usersStore()",
            b"const { users } = usersStore()",
        )
    )
    with redirect_stderr(io.StringIO()):
        assert module.derive(broken, manifest) == 1

    applied_state = Path(directory) / 'applied.vue'
    text = (HERE / baselines['fixed-crm']['fixture']).read_text(encoding='utf-8')
    for edit in target['edits']:
        text = text.replace(edit['anchor'], edit['replacement'])
    applied_state.write_text(text, encoding='utf-8', newline='')
    with redirect_stderr(io.StringIO()):
        assert module.derive(applied_state, manifest) == 1

assert sha((HERE / 'manifest.json').read_bytes()) == manifest_digest, 'Derive wrote the manifest'

print(
    'PASS: c011000 order overlap is declared and verified (not "no intersection"); '
    'two baselines replay to their exact after hashes; pre-application --check is zero-write; '
    'post-application --verify accepts only the declared after and refuses unapplied/unknown/drift; '
    'reapply and post-apply --check are still refused; derive is read-only for registered and '
    'unknown bytes, never authorizes apply, and unknown bytes stay refused by apply; '
    'M24 identity/resume lines survive; single nav row only'
)

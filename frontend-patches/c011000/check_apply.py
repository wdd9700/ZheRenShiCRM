import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('c011000_apply', HERE / 'apply.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
manifest = json.loads((HERE / 'manifest.json').read_text())
baseline = Path(sys.argv[1]).resolve(strict=True)
runtime = Path(sys.argv[2]).resolve(strict=True)
supplemental = Path(sys.argv[3]).resolve(strict=True) if len(sys.argv) > 3 else baseline
expected_count = sum(bool(entry.get('payload') or entry.get('edits')) for entry in manifest)


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


with tempfile.TemporaryDirectory(prefix='c011000-', dir=runtime) as directory:
    root = Path(directory)
    for entry in manifest:
        if entry['before'] is not None:
            candidates = [source / entry['target'] for source in [baseline, supplemental]]
            source = next((candidate for candidate in candidates if candidate.is_file()
                           and module.sha(candidate.read_bytes()) == entry['before']), None)
            assert source, 'No exact source evidence for ' + entry['target']
            target = root / entry['target']
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    with patch.object(module.subprocess, 'check_output', return_value=module.COMMIT + '\n'):
        original = snapshot(root)
        assert module.apply(root, True) == expected_count
        assert snapshot(root) == original
        for name in ['frontend/src/main.js', 'frontend/src/data/document.js']:
            drift = root / name
            old = drift.read_bytes()
            drift.write_bytes(old + b'\nDRIFT')
            refused(root)
            drift.write_bytes(old)
        missing = root / 'frontend/yarn.lock'
        saved = missing.read_bytes()
        missing.unlink()
        refused(root)
        missing.write_bytes(saved)
        with patch.object(module.subprocess, 'check_output', return_value='wrong-head\n'):
            refused(root)
        target = root / 'frontend/src/main.js'
        linked = root / 'hard-link-evidence'
        os.link(target, linked)
        refused(root)
        linked.unlink()
        temporary = target.with_name(target.name + '.c011000-tmp')
        temporary.write_bytes(b'existing-user-file')
        refused(root)
        temporary.unlink()
        assert module.apply(root) == expected_count
        for entry in manifest:
            if entry.get('payload') or entry.get('edits'):
                assert module.sha((root / entry['target']).read_bytes()) == entry['after']
        refused(root)
print(f'PASS: {expected_count} exact source edits/payloads; dry-run, drift/missing/HEAD/hardlink/temp/reapply refusals write nothing')
print('Evidence replay uses a mocked Git HEAD only inside this disposable fixture, not a real checkout/build.')

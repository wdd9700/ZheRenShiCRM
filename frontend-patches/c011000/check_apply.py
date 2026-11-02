import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('c011000_apply', HERE / 'apply.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
manifest = json.loads((HERE / 'manifest.json').read_text())
baseline = Path(sys.argv[1]).resolve(strict=True)
runtime = Path(sys.argv[2]).resolve(strict=True)


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
            target = root / entry['target']
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(baseline / entry['target'], target)
    with patch.object(module.subprocess, 'check_output', return_value=module.COMMIT + '\n'):
        original = snapshot(root)
        assert module.apply(root, True) == 7
        assert snapshot(root) == original
        drift = root / 'frontend/src/main.js'
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
        assert module.apply(root) == 7
        for entry in manifest:
            if entry.get('payload'):
                assert module.sha((root / entry['target']).read_bytes()) == entry['after']
        refused(root)
print('PASS: exact source replay, dry-run no writes, drift/missing/HEAD/reapply rejection with no refusal writes')

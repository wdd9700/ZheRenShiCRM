import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('dark_ui_patch', HERE / 'apply.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
MANIFEST = json.loads((HERE / 'manifest.json').read_text(encoding='utf-8'))
GUARDS = json.loads((HERE / 'prerequisites.json').read_text(encoding='utf-8'))


class PatchTests(unittest.TestCase):
    def test_fixed_public_fixtures_and_theme_match_every_fingerprint(self):
        module.verify_theme()
        for entry in MANIFEST['targets']:
            data = (HERE / entry['fixture']).read_bytes() if entry.get('fixture') else None
            self.assertEqual(module.sha(data) if data is not None else None, entry['before'])
            self.assertEqual(module.sha(module.transform(data, entry)), entry['after'])

    def test_production_prerequisites_preserve_exact_m24_and_ordered_m30(self):
        root = HERE.parents[1]
        baseline = json.loads(subprocess.check_output(['git', '-C', str(root), 'show', '9403d5a:frontend-patches/c011000/manifest.json']))
        expected = {entry['target']: entry.get('after', entry['before']) for entry in baseline}
        expected['frontend/src/components/Layouts/AppSidebar.vue'] = 'e169f9d13cec9245390a8854b1dba8026227945abcaac03fb097473fca29a852'
        self.assertEqual(len(expected), 43)
        self.assertEqual({entry['target']: entry['sha256'] for entry in GUARDS['targets']}, expected)
        self.assertFalse(set(expected) & module.TARGETS)

    def test_real_file_check_apply_after_and_fail_before_write(self):
        with tempfile.TemporaryDirectory(prefix='check-', dir=HERE) as directory:
            base = Path(directory)
            package = base / 'frontend-patches/dark-ui'
            package.mkdir(parents=True)
            shutil.copytree(HERE / 'payload', package / 'payload')
            (package / 'manifest.json').write_bytes((HERE / 'manifest.json').read_bytes())
            root = base / 'crm'
            synthetic_guards = []
            for index, entry in enumerate(GUARDS['targets']):
                target = root / entry['target']
                target.parent.mkdir(parents=True, exist_ok=True)
                data = ('synthetic production guard ' + str(index)).encode()
                target.write_bytes(data)
                synthetic_guards.append({'target': entry['target'], 'sha256': module.sha(data)})
            (package / 'prerequisites.json').write_text(json.dumps({'targets': synthetic_guards}), encoding='utf-8')
            for entry in MANIFEST['targets']:
                target = root / entry['target']
                target.parent.mkdir(parents=True, exist_ok=True)
                if entry.get('fixture'):
                    target.write_bytes((HERE / entry['fixture']).read_bytes())
            with patch.object(module, 'HERE', package), patch.object(module.subprocess, 'check_output', return_value=module.COMMIT):
                before = {entry['target']: (root / entry['target']).read_bytes() for entry in MANIFEST['targets'] if entry.get('fixture')}
                self.assertEqual(module.apply(root, check=True), 4)
                self.assertFalse((root / 'frontend/src/crm-theme.css').exists())
                drift = root / 'frontend/src/components/UserDropdown.vue'
                drift.write_bytes(drift.read_bytes() + b'\n')
                with self.assertRaisesRegex(ValueError, 'Baseline mismatch'):
                    module.apply(root)
                self.assertEqual((root / 'frontend/src/App.vue').read_bytes(), before['frontend/src/App.vue'])
                drift.write_bytes(before['frontend/src/components/UserDropdown.vue'])
                guard = root / GUARDS['targets'][0]['target']
                data = guard.read_bytes()
                guard.write_bytes(b'old master 12-entry guard is not production')
                with self.assertRaisesRegex(ValueError, 'prerequisite mismatch'):
                    module.apply(root)
                guard.write_bytes(data)
                self.assertEqual(module.apply(root), 4)
                self.assertEqual(module.apply(root, verify_after=True), 4)
                with self.assertRaisesRegex(ValueError, 'Baseline mismatch'):
                    module.apply(root)
                for entry in MANIFEST['targets']:
                    self.assertEqual(module.sha((root / entry['target']).read_bytes()), entry['after'])

    def test_anchor_and_payload_tampering_are_refused(self):
        entry = MANIFEST['targets'][0]
        with self.assertRaisesRegex(ValueError, 'anchor'):
            module.transform(b'no matching anchor', entry)
        altered = dict(MANIFEST['targets'][-1], after='0' * 64)
        with self.assertRaisesRegex(ValueError, 'After SHA mismatch'):
            module.transform(None, altered)


if __name__ == '__main__':
    unittest.main()

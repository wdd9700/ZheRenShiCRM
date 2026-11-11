import argparse
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import apply_filter_label_delta as filter_delta
import prepare_concentrated_ui as preparation
import verify_read_diagnostic as diagnostic_delta

CONTEXT = RECEIPT = FILTER_BASELINE = DIAGNOSTIC_BASELINE = None


class ConcentratedTests(unittest.TestCase):
    def test_real_deployed_sources_apply_both_deltas_without_replay(self):
        context, manifest = preparation.load(CONTEXT, RECEIPT)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'crm'
            shutil.copytree(FILTER_BASELINE, root)
            shutil.copytree(DIAGNOSTIC_BASELINE, root, dirs_exist_ok=True)
            before = {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob('*') if path.is_file()}
            with patch.object(filter_delta.subprocess, 'check_output', return_value=filter_delta.CRM_HEAD + '\n'):
                filter_delta.apply(root, context / 'frontend-patches', 'check')
                diagnostic_delta.apply(root, context, 'check')
                self.assertEqual(before, {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob('*') if path.is_file()})
                filter_delta.apply(root, context / 'frontend-patches')
                diagnostic_delta.apply(root, context)
                filter_delta.apply(root, context / 'frontend-patches', 'verify')
                diagnostic_delta.apply(root, context, 'verify')
            for entry in manifest['diagnostic']['targets']:
                self.assertEqual(diagnostic_delta.sha(before[entry['target']]), entry['before'])
                self.assertEqual(diagnostic_delta.sha((root / entry['target']).read_bytes()), entry['after'])
            for name, digest in filter_delta.AFTER.items():
                self.assertEqual(filter_delta.sha((root / name).read_bytes()), digest)
            for name in filter_delta.UNCHANGED:
                self.assertEqual(before[name], (root / name).read_bytes())
            with self.assertRaises(RuntimeError):
                diagnostic_delta.apply(root, context)
            self.assertTrue(manifest['diagnostic']['temporary'])
            self.assertFalse(manifest['diagnostic']['default_enabled'])

    def test_diagnostic_drift_refuses_all_writes_and_payloads_are_exact(self):
        context, manifest = preparation.load(CONTEXT, RECEIPT)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'crm'
            shutil.copytree(DIAGNOSTIC_BASELINE, root)
            target = root / sorted(diagnostic_delta.DIAGNOSTIC_TARGETS)[-1]
            target.write_bytes(target.read_bytes() + b'\n')
            before = {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob('*') if path.is_file()}
            with self.assertRaises(RuntimeError):
                diagnostic_delta.apply(root, context)
            self.assertEqual(before, {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob('*') if path.is_file()})
        self.assertEqual({entry['target'] for entry in manifest['diagnostic']['targets']}, diagnostic_delta.DIAGNOSTIC_TARGETS)
        recipe = (context / 'deploy/Dockerfile.concentrated-ui').read_text()
        self.assertIn('ARG VITE_CRM_READ_FAILURE_DIAGNOSTICS=0', recipe)
        self.assertIn('VITE_CRM_READ_FAILURE_DIAGNOSTICS="${VITE_CRM_READ_FAILURE_DIAGNOSTICS}" bench build --app crm', recipe)
        self.assertEqual(set(manifest['filter_targets']), set(filter_delta.AFTER))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--context', type=Path, required=True)
    parser.add_argument('--receipt', required=True)
    parser.add_argument('--filter-baseline', type=Path, required=True)
    parser.add_argument('--diagnostic-baseline', type=Path, required=True)
    args = parser.parse_args()
    CONTEXT, RECEIPT, FILTER_BASELINE, DIAGNOSTIC_BASELINE = args.context, args.receipt, args.filter_baseline, args.diagnostic_baseline
    unittest.main(argv=['check_concentrated_ui.py'])

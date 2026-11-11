import argparse
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import apply_filter_label_delta as delta

BASELINE = PATCHES = None


class FilterDeltaTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / 'crm'
        shutil.copytree(BASELINE, self.root)
        self.head = patch.object(delta.subprocess, 'check_output', return_value=delta.CRM_HEAD + '\n')
        self.head.start()
        self.addCleanup(self.head.stop)

    def snapshot(self):
        return {name: (self.root / name).read_bytes() for name in set(delta.BEFORE) | set(delta.UNCHANGED)}

    def test_actual_deployed_after_delta_check_apply_verify(self):
        before = self.snapshot()
        for name, digest in delta.BEFORE.items():
            self.assertEqual(delta.sha(before[name]), digest)
        delta.apply(self.root, PATCHES, 'check')
        self.assertEqual(self.snapshot(), before)
        delta.apply(self.root, PATCHES)
        delta.apply(self.root, PATCHES, 'verify')
        after = self.snapshot()
        for name, digest in delta.AFTER.items():
            self.assertEqual(delta.sha(after[name]), digest)
        for name in delta.UNCHANGED:
            self.assertEqual(before[name], after[name])
        with self.assertRaises(RuntimeError):
            delta.apply(self.root, PATCHES)
        source = after[delta.FILTER].decode()
        self.assertIn("systemLabels[field.fieldname] && field.label === systemLabels[field.fieldname]", source)
        self.assertIn("label: fieldtype == 'Check' ? __(o) : o,\n        value: o,", source)
        self.assertIn('!field.is_custom_field && !field.custom', source)

    def test_drift_and_temporary_conflict_refuse_before_write(self):
        path = self.root / delta.FILTER
        path.write_bytes(path.read_bytes() + b'\n')
        before = self.snapshot()
        with self.assertRaises(RuntimeError):
            delta.apply(self.root, PATCHES)
        self.assertEqual(before, self.snapshot())
        path.write_bytes(before[delta.FILTER][:-1])
        temporary = path.with_name(path.name + '.filter-label-tmp')
        temporary.write_bytes(b'preserve')
        before = self.snapshot()
        with self.assertRaises(RuntimeError):
            delta.apply(self.root, PATCHES, 'check')
        self.assertEqual(temporary.read_bytes(), b'preserve')
        self.assertEqual(before, self.snapshot())

    def test_second_replace_failure_restores_originals(self):
        before = self.snapshot()
        replace = delta.os.replace
        calls = 0
        def fail_once(source, destination):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('controlled second replace failure')
            return replace(source, destination)
        with patch.object(delta.os, 'replace', side_effect=fail_once):
            with self.assertRaises(OSError):
                delta.apply(self.root, PATCHES)
        self.assertEqual(before, self.snapshot())
        self.assertFalse(list(self.root.rglob('*.filter-label-*')))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--patch-root', type=Path, required=True)
    args = parser.parse_args()
    BASELINE, PATCHES = args.baseline, args.patch_root
    unittest.main(argv=['check_filter_label_delta.py'])

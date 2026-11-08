import collections
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('common_ui_apply', HERE / 'apply.py')
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)


class CommonUITest(unittest.TestCase):
    def test_catalog_placeholders_and_unique_keys(self):
        catalog = HERE.parent / 'localization' / 'zh-CN.json'
        pairs = json.loads(catalog.read_text(encoding='utf-8'), object_pairs_hook=list)
        self.assertEqual(len(pairs), len(dict(pairs)))
        for key, value in pairs:
            self.assertEqual(collections.Counter(re.findall(r'\{\d+\}', key)),
                             collections.Counter(re.findall(r'\{\d+\}', value)), key)
        messages = dict(pairs)
        self.assertEqual(messages['No New Notifications'], '暂无新通知')
        self.assertEqual(messages['You have no new notifications'], '你目前没有新通知')

    def test_fixed_sources_check_apply_verify(self):
        baseline = Path(os.environ['CRM_SOURCE_BASELINE'])
        entries = json.loads((HERE / 'manifest.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for entry in entries:
                target = root / entry['target']
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(baseline / entry['target'], target)
            with patch.object(common.subprocess, 'check_output', return_value=common.COMMIT + '\n'):
                self.assertEqual(common.apply(root, 'check'), 4)
                target = root / entries[0]['target']
                original = target.read_bytes()
                target.write_bytes(original + b'\n')
                with self.assertRaisesRegex(ValueError, 'Source mismatch'):
                    common.apply(root)
                target.write_bytes(original)
                conflict = target.with_name(target.name + '.common-ui-localization-tmp')
                conflict.write_bytes(b'keep')
                with self.assertRaisesRegex(ValueError, 'Temporary path already exists'):
                    common.apply(root)
                self.assertEqual(conflict.read_bytes(), b'keep')
                self.assertEqual(target.read_bytes(), original)
                conflict.unlink()
                self.assertEqual(common.apply(root), 4)
                self.assertEqual(common.apply(root, 'verify'), 4)
                filter_source = (root / 'frontend/src/components/Filter.vue').read_text(encoding='utf-8')
                self.assertIn("label: fieldtype == 'Check' ? __(o) : o,\n        value: o,", filter_source)
                result = target.read_text(encoding='utf-8')
                self.assertIn(':title="__(\'No New Notifications\')"', result)
                self.assertIn(':description="__(\'You have no new notifications\')"', result)
                self.assertIn('sanitizeHTML(n.notification_text)', result)
                target.write_bytes(b'tampered')
                with self.assertRaisesRegex(ValueError, 'Source mismatch'):
                    common.apply(root, 'verify')
            with patch.object(common.subprocess, 'check_output', return_value='wrong\n'):
                with self.assertRaisesRegex(ValueError, 'HEAD mismatch'):
                    common.apply(root, 'check')


if __name__ == '__main__':
    unittest.main()

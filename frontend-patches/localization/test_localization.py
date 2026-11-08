import ast
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
spec = importlib.util.spec_from_file_location('localization_apply', HERE / 'apply.py')
localization = importlib.util.module_from_spec(spec)
spec.loader.exec_module(localization)


class LocalizationTest(unittest.TestCase):
    def test_fixed_sources_and_runtime(self):
        crm_py = Path(os.environ['CRM_PY_BASELINE'])
        translation = Path(os.environ['CRM_TRANSLATION_BASELINE'])
        runtime = HERE / '.runtime'
        runtime.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=runtime) as directory:
            root = Path(directory)
            (root / 'crm/www').mkdir(parents=True)
            (root / 'frontend/src').mkdir(parents=True)
            shutil.copyfile(crm_py, root / 'crm/www/crm.py')
            shutil.copyfile(translation, root / 'frontend/src/translation.js')
            with patch.object(localization.subprocess, 'check_output', return_value=localization.COMMIT + '\n'):
                target = root / 'frontend/src/translation.js'
                original = target.read_bytes()
                target.write_bytes(original + b'\n')
                with self.assertRaisesRegex(ValueError, 'Source mismatch'):
                    localization.apply(root)
                self.assertEqual((root / 'crm/www/crm.py').read_bytes(), crm_py.read_bytes())
                self.assertFalse((root / 'frontend/src/philosopher-zh-cn.json').exists())
                target.write_bytes(original)
                crm_target = root / 'crm/www/crm.py'
                new_target = root / 'frontend/src/philosopher-zh-cn.json'
                conflict = target.with_name(target.name + '.localization-tmp')
                conflict.write_bytes(b'pre-existing file')
                for mode in ('check', 'apply'):
                    with self.assertRaisesRegex(ValueError, 'Temporary path already exists'):
                        localization.apply(root, mode)
                    self.assertEqual(crm_target.read_bytes(), crm_py.read_bytes())
                    self.assertEqual(target.read_bytes(), original)
                    self.assertFalse(new_target.exists())
                    self.assertEqual(conflict.read_bytes(), b'pre-existing file')
                conflict.unlink()
                real_replace = os.replace
                for fail_at in (2, 3):
                    count = 0

                    def fail_once(source, destination):
                        nonlocal count
                        count += 1
                        if count == fail_at:
                            raise OSError('injected replace failure')
                        return real_replace(source, destination)

                    with patch.object(localization.os, 'replace', side_effect=fail_once):
                        with self.assertRaisesRegex(OSError, 'injected replace failure'):
                            localization.apply(root)
                    self.assertEqual(crm_target.read_bytes(), crm_py.read_bytes())
                    self.assertEqual(target.read_bytes(), original)
                    self.assertFalse(new_target.exists())
                    self.assertEqual(list(root.rglob('*.localization-tmp')), [])
                    self.assertEqual(list(root.rglob('*.localization-backup')), [])
                self.assertEqual(localization.apply(root, 'check'), 3)
                self.assertFalse((root / 'frontend/src/philosopher-zh-cn.json').exists())
                self.assertEqual(localization.apply(root), 3)
                self.assertEqual(localization.apply(root, 'verify'), 3)
                with self.assertRaisesRegex(ValueError, 'Source mismatch'):
                    localization.apply(root, 'check')
                source = (root / 'crm/www/crm.py').read_text(encoding='utf-8')
                parsed = ast.parse(source)
                fn = next(node for node in parsed.body if isinstance(node, ast.FunctionDef) and node.name == 'get_boot')
                frappe = MagicMock()
                frappe.__version__ = 'test'
                frappe._dict.side_effect = lambda value: value
                frappe.local.lang = 'zh-CN'
                messages = {'Lead': '来自服务端'}
                namespace = {'frappe': frappe, '__builtins__': __builtins__}
                for name in ('get_default_route', 'cint', 'is_fc_site', 'get_translated_doctypes',
                             'get_system_timezone', 'get_state_options'):
                    namespace[name] = MagicMock()
                namespace['get_messages_for_boot'] = lambda: messages
                namespace['HAS_AUTOMATION_ENGINE'] = False
                exec(compile(ast.Module(body=[fn], type_ignores=[]), str(crm_py), 'exec'), namespace)
                boot = namespace['get_boot']()
                self.assertEqual(boot['philosopher_language'], 'zh-CN')
                self.assertIs(boot['translated_messages'], messages)
                subprocess.run(['node', str(HERE / 'runtime.test.cjs'),
                                str(root / 'frontend/src/translation.js'),
                                str(root / 'frontend/src/philosopher-zh-cn.json'),
                                str(ROOT / 'apps/team_schedule/team_schedule/public/crm-zh-cn.js')], check=True)
                (root / 'frontend/src/translation.js').write_text('tampered', encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'Source mismatch'):
                    localization.apply(root, 'verify')

    def test_wrong_commit_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'frontend').mkdir()
            with patch.object(localization.subprocess, 'check_output', return_value='wrong\n'):
                with self.assertRaisesRegex(ValueError, 'HEAD mismatch'):
                    localization.apply(root, 'check')


if __name__ == '__main__':
    unittest.main()

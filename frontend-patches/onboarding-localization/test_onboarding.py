import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('onboarding_patch', HERE / 'apply.py')
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)


class OnboardingTest(unittest.TestCase):
    def test_fixed_sources_and_runtime(self):
        original_root = Path(os.environ['FRAMEWORK_BASELINE'])
        runtime = HERE / '.runtime'
        runtime.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=runtime) as directory:
            root = Path(directory)
            names = ['GettingStartedBanner.vue', 'HelpModal.vue', 'OnboardingSteps.vue']
            paths = [root / patcher.PREFIX / name for name in names]
            paths[0].parent.mkdir(parents=True)
            shutil.copyfile(original_root / patcher.PREFIX / 'types.ts', paths[0].parent / 'types.ts')
            for path in paths:
                shutil.copyfile(original_root / patcher.PREFIX / path.name, path)
            originals = [path.read_bytes() for path in paths]
            paths[1].write_bytes(originals[1] + b'\n')
            with self.assertRaisesRegex(ValueError, 'Source mismatch'):
                patcher.apply(root)
            self.assertEqual(paths[0].read_bytes(), originals[0])
            paths[1].write_bytes(originals[1])
            conflict = paths[0].with_name(paths[0].name + '.onboarding-localization-tmp')
            conflict.write_bytes(b'untouched')
            with self.assertRaisesRegex(ValueError, 'Temporary path'):
                patcher.apply(root, 'check')
            self.assertEqual(conflict.read_bytes(), b'untouched')
            conflict.unlink()
            real_replace = os.replace
            for fail_at in (2, 3):
                count = 0
                def fail_once(source, destination):
                    nonlocal count
                    count += 1
                    if count == fail_at:
                        raise OSError('injected failure')
                    return real_replace(source, destination)
                with patch.object(patcher.os, 'replace', side_effect=fail_once):
                    with self.assertRaisesRegex(OSError, 'injected failure'):
                        patcher.apply(root)
                self.assertEqual([path.read_bytes() for path in paths], originals)
                self.assertEqual(list(root.rglob('*.onboarding-localization-*')), [])
            self.assertEqual(patcher.apply(root, 'check'), 3)
            self.assertEqual(patcher.apply(root), 3)
            self.assertEqual(patcher.apply(root, 'verify'), 3)
            localization_path = HERE.parent / 'localization' / 'apply.py'
            localization_spec = importlib.util.spec_from_file_location('localization_patch', localization_path)
            localization = importlib.util.module_from_spec(localization_spec)
            localization_spec.loader.exec_module(localization)
            translation = root / 'translation.js'
            translation.write_bytes(localization.transform('frontend/src/translation.js',
                                    Path(os.environ['CRM_TRANSLATION_BASELINE']).read_bytes()))
            subprocess.run(['node', str(HERE / 'runtime.test.cjs'), str(root),
                            os.environ['CRM_FRONTEND_NODE_MODULES'],
                            str(HERE.parent / 'localization/zh-CN.json'), str(translation)], check=True)
            paths[2].write_text('tampered', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Source mismatch'):
                patcher.apply(root, 'verify')


if __name__ == '__main__':
    unittest.main()

import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import uuid

import prepare_common_ui as preparation
import verify_common_ui as verification

CONTEXT = RECEIPT = BASELINE = OLD_CATALOG = None


class CommonIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.context = preparation.ROOT / '.runtime' / ('common-ui-' + uuid.uuid4().hex)
        shutil.copytree(CONTEXT, self.context)
        self.addCleanup(shutil.rmtree, self.context)

    def test_exact_deployed_before_and_patch_catalog_order(self):
        _, manifest = preparation.load(self.context, RECEIPT)
        with tempfile.TemporaryDirectory() as temporary:
            bench = Path(temporary)
            crm = bench / 'apps/crm'
            shutil.copytree(BASELINE, crm)
            catalog = crm / verification.CATALOG
            catalog.write_bytes(OLD_CATALOG.read_bytes())
            spec = importlib.util.spec_from_file_location('actual_common_ui_apply', self.context / 'frontend-patches/common-ui-localization/apply.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            with patch.object(module.subprocess, 'check_output', return_value='36bd8859f2a6345a620477bc708d0546e8c3f08a\n'):
                module.apply(crm, 'check')
                module.apply(crm)
                module.apply(crm, 'verify')
                with self.assertRaises(ValueError):
                    module.apply(crm)
            verification.apply_catalog(bench, self.context, 'check')
            self.assertEqual(catalog.read_bytes(), OLD_CATALOG.read_bytes())
            verification.apply_catalog(bench, self.context, 'apply')
            verification.apply_catalog(bench, self.context, 'verify')
            self.assertEqual(verification.sha(catalog.read_bytes()), manifest['catalog']['after'])
            with self.assertRaises(RuntimeError):
                verification.apply_catalog(bench, self.context, 'apply')
            for entry in manifest['targets']:
                self.assertEqual(verification.sha((crm / entry['target']).read_bytes()), entry['after'])

    def test_context_missing_extra_drift_and_unknown_target_refused(self):
        with self.assertRaises(RuntimeError):
            preparation.load(self.context, '0' * 64)
        path = self.context / 'extra.js'
        path.write_bytes(b'extra')
        with self.assertRaises(RuntimeError):
            preparation.load(self.context, RECEIPT)
        path.unlink()
        catalog = self.context / 'frontend-patches/localization/zh-CN.json'
        catalog.unlink()
        with self.assertRaises(RuntimeError):
            preparation.load(self.context, RECEIPT)
        target_manifest = self.context / 'frontend-patches/common-ui-localization/manifest.json'
        entries = json.loads(target_manifest.read_bytes())
        entries[0]['target'] = 'frontend/src/stores/session.js'
        target_manifest.write_text(json.dumps(entries))
        with self.assertRaises(RuntimeError):
            verification.entries(self.context)

    def test_existing_catalog_keys_must_remain(self):
        source = self.context
        with tempfile.TemporaryDirectory() as temporary:
            bench = Path(temporary)
            catalog = bench / 'apps/crm' / verification.CATALOG
            catalog.parent.mkdir(parents=True)
            old = OLD_CATALOG.read_bytes()
            catalog.write_bytes(old)
            changed = json.loads((source / 'frontend-patches/localization/zh-CN.json').read_bytes())
            first_key = next(iter(json.loads(old)))
            changed[first_key] = 'unreviewed overwrite'
            changed_bytes = json.dumps(changed).encode()
            (source / 'frontend-patches/localization/zh-CN.json').write_bytes(changed_bytes)
            contract = json.loads((source / 'frontend-patches/localization/manifest.json').read_bytes())
            next(entry for entry in contract if entry['target'] == verification.CATALOG)['after'] = verification.sha(changed_bytes)
            (source / 'frontend-patches/localization/manifest.json').write_text(json.dumps(contract))
            with self.assertRaises(RuntimeError):
                verification.apply_catalog(bench, source, 'apply')
            self.assertEqual(catalog.read_bytes(), old)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--context', type=Path, required=True)
    parser.add_argument('--receipt', required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--old-catalog', type=Path, required=True)
    args = parser.parse_args()
    CONTEXT, RECEIPT, BASELINE, OLD_CATALOG = args.context, args.receipt, args.baseline, args.old_catalog
    unittest.main(argv=['check_common_ui.py'])

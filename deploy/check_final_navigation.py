import argparse
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import apply_filter_label_delta as filter_delta
import apply_sort_endpoint_delta as sort_delta
import prepare_final_navigation as preparation

CONTEXT = RECEIPT = FILTER_BASELINE = None


class FinalNavigationTests(unittest.TestCase):
    def test_branded_request_single_endpoint_delta_preserves_every_other_byte(self):
        context, manifest = preparation.load(CONTEXT, RECEIPT)
        entry, updated = sort_delta.contract(context)
        original = (context / 'sort-inputs/request.branded.py').read_bytes()
        self.assertEqual(updated.replace(sort_delta.NEW, sort_delta.OLD, 1), original)
        self.assertEqual(entry, manifest['sort_endpoint'])
        self.assertIn(b'/assets/team_access/access.js?v=7d26', updated)
        self.assertNotIn(sort_delta.OLD, updated)
        with tempfile.TemporaryDirectory() as temporary:
            bench = Path(temporary)
            target = bench / sort_delta.TARGET
            target.parent.mkdir(parents=True)
            target.write_bytes(original)
            sort_delta.apply(bench, context, 'check')
            self.assertEqual(target.read_bytes(), original)
            sort_delta.apply(bench, context)
            sort_delta.apply(bench, context, 'verify')
            self.assertEqual(target.read_bytes(), updated)
            with self.assertRaises(RuntimeError):
                sort_delta.apply(bench, context)
            target.write_bytes(original + b'\n')
            with self.assertRaises(RuntimeError):
                sort_delta.apply(bench, context)

    def test_filter_overlay_and_no_diagnostic_copy_or_env(self):
        context, manifest = preparation.load(CONTEXT, RECEIPT)
        with tempfile.TemporaryDirectory() as temporary:
            crm = Path(temporary) / 'crm'
            shutil.copytree(FILTER_BASELINE, crm)
            with patch.object(filter_delta.subprocess, 'check_output', return_value=filter_delta.CRM_HEAD + '\n'):
                filter_delta.apply(crm, context / 'frontend-patches', 'check')
                filter_delta.apply(crm, context / 'frontend-patches')
                filter_delta.apply(crm, context / 'frontend-patches', 'verify')
        self.assertFalse(manifest['diagnostics_present'])
        recipe = (context / 'deploy/Dockerfile.final-navigation').read_text()
        self.assertNotIn('VITE_CRM_READ_FAILURE_DIAGNOSTICS', recipe)
        self.assertNotIn('diagnostic-payloads', recipe)
        self.assertNotIn('crm.focused', recipe)
        self.assertNotIn('c011000', recipe)
        self.assertEqual(manifest['filter_targets'], filter_delta.AFTER)
        self.assertEqual(manifest['base_image'], preparation.BASE_IMAGE)
        self.assertTrue(manifest['cleanup_production'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--context', type=Path, required=True)
    parser.add_argument('--receipt', required=True)
    parser.add_argument('--filter-baseline', type=Path, required=True)
    args = parser.parse_args()
    CONTEXT, RECEIPT, FILTER_BASELINE = args.context, args.receipt, args.filter_baseline
    unittest.main(argv=['check_final_navigation.py'])

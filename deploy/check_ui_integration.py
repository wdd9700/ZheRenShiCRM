import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import uuid

import prepare_ui_integration as preparation
import verify_ui_integration as verification

CONTEXT = None
RECEIPT = None
BASELINE = None


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.context = preparation.ROOT / '.runtime' / ('ui-' + uuid.uuid4().hex)
        shutil.copytree(CONTEXT, self.context)
        self.addCleanup(shutil.rmtree, self.context)

    def test_exact_context_and_ordered_real_source_composition(self):
        preparation.load(self.context, RECEIPT)
        patches = self.context / 'frontend-patches'
        states = verification.chain(patches)
        self.assertEqual(len(states['c011000']), 43)
        self.assertEqual(len(states['l3-scheduling']), 43)
        self.assertEqual(len(states['branding']), 55)
        with tempfile.TemporaryDirectory() as temporary:
            bench = Path(temporary)
            shutil.copytree(BASELINE / 'apps', bench / 'apps')
            crm = bench / 'apps/crm'
            self.assertTrue((crm / 'crm/public').is_dir())
            self.assertFalse((crm / 'crm/public/css').exists())
            self.seed_overlays(bench)
            with patch('subprocess.check_output', return_value=verification.CRM_COMMIT + '\n'):
                verification.verify(crm, patches, 'l3-scheduling')
                for name in ('dark-ui', 'localization', 'branding'):
                    module = load_module('ui_test_' + name.replace('-', '_'), patches / name / 'apply.py')
                    if name == 'localization':
                        module.apply(crm, 'check')
                        module.apply(crm)
                        module.apply(crm, 'verify')
                    else:
                        module.apply(crm, check=True)
                        module.apply(crm)
                        module.apply(crm, verify_after=True)
                    verification.verify(crm, patches, name)
                for name in ('dark-ui', 'localization', 'branding'):
                    module = load_module('ui_replay_' + name.replace('-', '_'), patches / name / 'apply.py')
                    with self.assertRaises(ValueError):
                        module.apply(crm)
                framework = bench / 'apps/frappe'
                verification.verify_framework(framework, patches, applied=False)
                onboarding = load_module('u030_onboarding', patches / 'onboarding-localization/apply.py')
                onboarding.apply(framework, 'check')
                onboarding.apply(framework)
                onboarding.apply(framework, 'verify')
                verification.verify_framework(framework, patches)
                with self.assertRaises(ValueError):
                    onboarding.apply(framework)
                protected_framework = framework / 'ui/src/components/Onboarding/HelpModal.vue'
                framework_bytes = protected_framework.read_bytes()
                protected_framework.write_bytes(framework_bytes + b'\n')
                with self.assertRaises(RuntimeError):
                    verification.verify_framework(framework, patches)
                protected_framework.write_bytes(framework_bytes)
                guard = load_module('u030_wording_guard', self.context / 'deploy/ui_build_guard.py')
                guard.B, guard.U = bench, self.context
                guard.apply_wording()
                manifest = json.loads((self.context / 'ui-source-manifest.json').read_bytes())
                self.assertEqual(len(manifest['overlays']), 9)
                for name, digest in manifest['overlays'].items():
                    self.assertEqual(verification.sha((bench / name).read_bytes()), digest)
                with self.assertRaises(RuntimeError):
                    guard.apply_wording()
                protected = crm / 'frontend/src/main.js'
                protected.write_bytes(protected.read_bytes() + b'\n')
                with self.assertRaises(RuntimeError):
                    verification.verify(crm, patches)

    def seed_overlays(self, bench):
        for name in preparation.DARK_OVERLAYS | preparation.LOCAL_OVERLAYS:
            target = bench / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((self.context / name).read_bytes())

    def test_wording_unknown_before_refuses_all_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            bench = Path(temporary)
            shutil.copytree(BASELINE / 'apps/team_access', bench / 'apps/team_access')
            self.seed_overlays(bench)
            target = bench / 'apps/team_access/team_access/public/page.js'
            target.write_bytes(target.read_bytes() + b'\n')
            before = {path.relative_to(bench).as_posix(): path.read_bytes() for path in bench.rglob('*') if path.is_file()}
            guard = load_module('u030_wording_negative', self.context / 'deploy/ui_build_guard.py')
            guard.B, guard.U = bench, self.context
            with self.assertRaises(RuntimeError):
                guard.apply_wording()
            after = {path.relative_to(bench).as_posix(): path.read_bytes() for path in bench.rglob('*') if path.is_file()}
            self.assertEqual(before, after)

    def test_receipt_drift_extra_and_missing_dictionary_refused(self):
        with self.assertRaises(RuntimeError):
            preparation.load(self.context, '0' * 64)
        extra = self.context / 'extra.txt'
        extra.write_bytes(b'unmanifested')
        with self.assertRaises(RuntimeError):
            preparation.load(self.context, RECEIPT)
        extra.unlink()
        target = self.context / 'apps/team_schedule/team_schedule/public/crm-zh-cn.js'
        original = target.read_bytes()
        target.write_bytes(original + b'\n')
        with self.assertRaises(RuntimeError):
            preparation.load(self.context, RECEIPT)
        target.unlink()
        with self.assertRaises(RuntimeError):
            preparation.load(self.context, RECEIPT)

    def test_legacy_manifest_and_unknown_localization_target_refused(self):
        patches = self.context / 'frontend-patches'
        cache = patches / 'c011000/manifest.json'
        original = cache.read_bytes()
        cache.write_text('[]')
        with self.assertRaises(RuntimeError):
            verification.chain(patches)
        cache.write_bytes(original)
        locale = patches / 'localization/manifest.json'
        entries = json.loads(locale.read_bytes())
        entries[0]['target'] = 'crm/permissions.py'
        locale.write_text(json.dumps(entries))
        with self.assertRaises(RuntimeError):
            verification.chain(patches)

    def test_ordered_overlap_requires_previous_after(self):
        entries = {
            'one': [dict(target='frontend/src/example.js', before='a' * 64, after='b' * 64)],
            'two': [dict(target='frontend/src/example.js', before='b' * 64, after='c' * 64)],
        }
        with patch.object(verification, 'entries', return_value=entries):
            self.assertEqual(verification.chain(self.context)['two']['frontend/src/example.js'], 'c' * 64)
            entries['two'][0]['before'] = 'a' * 64
            with self.assertRaises(RuntimeError):
                verification.chain(self.context)

    def test_build_contract_labels_runtime_config_and_lowdepth(self):
        _, manifest = preparation.load(self.context, RECEIPT)
        source = dict(Id=preparation.BASE_IMAGE, RootFS={'Layers': ['base-one', 'base-two']}, Config={'User': 'frappe', 'Labels': {'inherited': 'unchanged'}})
        labels = {
            'inherited': 'unchanged', 'crm.ui.integration': 'u030-v3',
            'crm.ui.base': preparation.BASE_CONFIG, 'crm.ui.order': ','.join(preparation.UI_ORDER),
            'crm.ui.dark.revision': manifest['revisions']['dark-ui'],
            'crm.ui.localization.revision': manifest['revisions']['localization'],
            'crm.ui.branding.revision': manifest['revisions']['branding'],
            'crm.ui.wording.revision': manifest['revisions']['wording'],
            'crm.ui.onboarding.revision': manifest['revisions']['onboarding-localization'],
        }
        candidate = dict(Id='sha256:' + 'a' * 64, RootFS={'Layers': ['one'] * 6}, Config={'User': 'frappe', 'Labels': labels})
        result = preparation.ROOT / '.runtime' / (self.context.name + '-build-result.json')
        self.addCleanup(result.unlink, missing_ok=True)
        with patch.object(preparation.subprocess, 'check_output', side_effect=[json.dumps([source]), json.dumps([candidate])]), patch.object(preparation.subprocess, 'run') as runner:
            preparation.build(self.context, RECEIPT)
            command = runner.call_args.args[0]
            self.assertIn('--network=none', command)
            self.assertIn('--pull=false', command)
            self.assertEqual(command[:2], ['docker', 'build'])
            self.assertIn('DARK_UI_REVISION=' + manifest['revisions']['dark-ui'], command)
            self.assertEqual(json.loads(result.read_bytes())['candidate_inspect'], candidate)
        for field, value in (('RootFS', {'Layers': ['one'] * 140}), ('Config', {'User': 'root', 'Labels': labels})):
            bad = dict(candidate, **{field: value})
            with patch.object(preparation.subprocess, 'check_output', side_effect=[json.dumps([source]), json.dumps([bad])]), patch.object(preparation.subprocess, 'run'):
                with self.assertRaises(RuntimeError):
                    preparation.build(self.context, RECEIPT)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--context', type=Path, required=True)
    parser.add_argument('--context-sha256', required=True)
    parser.add_argument('--baseline', type=Path, required=True, help='Selected public-source extraction from exact caf102 archive; no sites or credentials')
    args = parser.parse_args()
    CONTEXT, RECEIPT, BASELINE = args.context, args.context_sha256, args.baseline
    unittest.main(argv=['check_ui_integration.py'])

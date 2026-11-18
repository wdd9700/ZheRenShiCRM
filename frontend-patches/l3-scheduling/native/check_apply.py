import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import apply as native

HERE = Path(__file__).resolve().parent
PATCHES = HERE.parents[1]


def baselines():
    spec = importlib.util.spec_from_file_location('brand', PATCHES / 'branding/apply.py')
    branding = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(branding)
    entries = json.loads((PATCHES / 'branding/manifest.json').read_bytes())['targets']
    entry = next(entry for entry in entries if entry['target'] == native.SIDEBAR)
    return {
        native.ROUTER: (PATCHES / 'c011000/consumer-fixtures/router.js').read_bytes(),
        native.SIDEBAR: branding.transform((PATCHES / 'branding/fixtures/frontend__AppSidebar.m24-m30.vue').read_bytes(), entry),
        native.RESUME: (PATCHES / 'c011000/payload/resumeRuntime.js').read_bytes(),
        native.BOUNDARY: (PATCHES / 'c011000/payload/resources/accountBoundary.js').read_bytes(),
        native.WEBSITE: (HERE / 'fixtures/crm.localized.py').read_bytes(),
    }


class NativePatchTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(dir=HERE)
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.baselines = baselines()
        for relative in native.TARGETS:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if relative in self.baselines:
                path.write_bytes(self.baselines[relative])

    def apply(self, mode='apply', *, head=native.COMMIT, source=native.DEFAULT_APP):
        with patch.object(native.subprocess, 'check_output', return_value=head):
            return native.apply(self.root, source, mode)

    def assertUnchanged(self):
        for name in native.TARGETS:
            path = self.root / name
            self.assertEqual(path.read_bytes() if path.exists() else None, self.baselines.get(name), name)

    def test_check_apply_verify_with_normalized_source(self):
        with self.assertRaisesRegex(ValueError, 'after mismatch'):
            self.apply('verify')
        self.assertEqual(self.apply('check'), 9)
        self.assertUnchanged()
        self.assertEqual(self.apply(), 9)
        self.assertEqual(self.apply('verify'), 9)
        with self.assertRaisesRegex(ValueError, 'before mismatch'):
            self.apply()
        with (self.root / native.CONTROLLER).open('ab') as out:
            out.write(b'\n')
        with self.assertRaisesRegex(ValueError, 'after mismatch'):
            self.apply('verify')

    def test_wrong_head_and_new_collision_fail_before_writes(self):
        with self.assertRaisesRegex(ValueError, 'HEAD mismatch'):
            self.apply(head='different')
        self.assertUnchanged()
        path = self.root / native.PAGE
        path.write_bytes(b'already present')
        with self.assertRaisesRegex(ValueError, 'before mismatch'):
            self.apply()
        self.assertEqual(path.read_bytes(), b'already present')
        path.unlink()
        self.assertUnchanged()

    def test_app_source_drift_fails_before_writes(self):
        source = self.root / 'input'
        for name in native.SOURCES:
            path = source / name
            path.parent.mkdir(exist_ok=True, parents=True)
            path.write_bytes((native.DEFAULT_APP / name).read_bytes())
        path = source / native.JS_SOURCE
        path.write_bytes(path.read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'app source SHA mismatch'):
            self.apply(source=source)
        self.assertUnchanged()

    def test_canonical_guest_uses_only_fixed_local_return_without_bypassing_crm_gate(self):
        self.apply()
        import ast
        module = ast.parse((self.root / native.WEBSITE).read_bytes())
        context = next(fn for fn in module.body if isinstance(fn, ast.FunctionDef) and fn.name == 'get_context')
        class Redirect(Exception):
            pass
        class ExistingPermissionGate(Exception):
            pass
        def check_app_permission():
            raise ExistingPermissionGate
        frappe = types.SimpleNamespace(session=types.SimpleNamespace(user='Guest'),
                                       local=types.SimpleNamespace(flags=types.SimpleNamespace()),
                                       request=types.SimpleNamespace(path='/crm/team-schedule'), Redirect=Redirect)
        bindings = {'frappe': frappe}
        with patch.dict(sys.modules, {'crm.api': types.SimpleNamespace(check_app_permission=check_app_permission)}):
            exec(compile(ast.Module(body=[context], type_ignores=[]), '<get_context>', 'exec'), bindings)
            for path in ('/crm/team-schedule', '/crm/team-schedule/'):
                frappe.request.path = path
                with self.assertRaises(Redirect) as error:
                    bindings['get_context']()
                self.assertEqual(error.exception.http_status_code, 302)
                self.assertEqual(frappe.local.flags.redirect_location, '/login?redirect-to=%2Fcrm%2Fteam-schedule')
            for user, path in [('Guest', '/crm/leads'), ('person@example.test', '/crm/team-schedule')]:
                frappe.session.user, frappe.request.path = user, path
                with self.assertRaises(ExistingPermissionGate):
                    bindings['get_context']()

    @unittest.skipUnless(shutil.which('node'), 'Node.js is required')
    def test_generated_native_route_controller_and_resume(self):
        self.apply()
        env = {**os.environ, 'S020_APPLIED_ROOT': str(self.root)}
        subprocess.run(['node', '--test', str(HERE / 'native.test.mjs')], env=env, check=True)

    @unittest.skipUnless(os.getenv('CRM_FRONTEND_COMPILER_ROOT') and shutil.which('node'), 'Set CRM_FRONTEND_COMPILER_ROOT to the fixed CRM frontend containing vue/compiler-sfc')
    def test_native_sfc_with_fixed_vue_compiler(self):
        self.apply()
        subprocess.run(['node', str(HERE / 'sfc_check.mjs'), str(self.root), os.environ['CRM_FRONTEND_COMPILER_ROOT']], check=True)


if __name__ == '__main__':
    unittest.main()

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('branding_apply', HERE / 'apply.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BrandingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / 'crm/public').mkdir(parents=True)
        (self.root / 'frontend/src/components/Icons').mkdir(parents=True)
        self.entries = json.loads((HERE / 'manifest.json').read_text(encoding='utf-8'))['targets']
        for entry in self.entries:
            target = self.root / entry['target']
            if entry.get('fixture'):
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((HERE / entry['fixture']).read_bytes())
        self.head = patch.object(module.subprocess, 'check_output', return_value=module.COMMIT + '\n')
        self.head.start()
        self.addCleanup(self.head.stop)

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def test_check_apply_verify_and_replay_refusal(self):
        before = self.snapshot()
        css_directory = self.root / 'crm/public/css'
        self.assertFalse(css_directory.exists())
        self.assertEqual(module.apply(self.root, check=True), 7)
        self.assertEqual(before, self.snapshot())
        self.assertFalse(css_directory.exists())
        module.apply(self.root)
        self.assertTrue(css_directory.is_dir())
        module.apply(self.root, verify_after=True)
        with self.assertRaises(ValueError):
            module.apply(self.root)
        html = (self.root / 'frontend/index.html').read_text(encoding='utf-8')
        self.assertIn("lang=\"{{ boot.philosopher_language | default('zh') | e }}\"", html)
        self.assertIn('<title>哲人石CRM</title>', html)
        self.assertIn('apple-mobile-web-app-title" content="哲人石CRM"', html)
        hooks = (self.root / 'crm/hooks.py').read_text(encoding='utf-8')
        self.assertIn('app_publisher = "Frappe Technologies Pvt. Ltd."', hooks)
        self.assertIn('app_license = "AGPLv3"', hooks)
        pwa = (self.root / 'frontend/vite.config.js').read_text(encoding='utf-8')
        self.assertIn("name: '哲人石CRM'", pwa)
        self.assertIn("short_name: '哲人石CRM'", pwa)
        self.assertEqual(pwa.replace('哲人石CRM', 'Frappe CRM'), (HERE / 'fixtures/frontend__vite.config.js').read_text(encoding='utf-8'))

    def test_help_modal_explicit_brand_preserves_ordered_sidebar(self):
        module.apply(self.root)
        entry = next(entry for entry in self.entries if entry['target'].endswith('/Layouts/AppSidebar.vue'))
        sidebar = (self.root / entry['target']).read_text(encoding='utf-8')
        self.assertIn(':logo="PhilosopherLogo"\n      title="哲人石CRM"', sidebar)
        self.assertNotIn(':logo="CRMLogo"', sidebar)
        for edit in reversed(entry['edits']):
            self.assertEqual(sidebar.count(edit['replacement']), 1)
            sidebar = sidebar.replace(edit['replacement'], edit['anchor'], 1)
        self.assertEqual(sidebar.encode('utf-8'), (HERE / entry['fixture']).read_bytes())
        self.assertEqual(entry['before'], 'e169f9d13cec9245390a8854b1dba8026227945abcaac03fb097473fca29a852')
        self.assertIn('href="/team-schedule"', sidebar)
        self.assertIn("accountBoundary.state === 'HYDRATING'", sidebar)
        logo = (self.root / 'frontend/src/components/Icons/PhilosopherLogo.vue').read_text()
        self.assertNotIn('#EF0BF5', logo)
        self.assertNotIn('CRMLogo', logo)

    def test_drift_and_missing_target_fail_before_writes(self):
        target = self.root / 'frontend/index.html'
        target.write_bytes(target.read_bytes() + b'\n')
        before = self.snapshot()
        with self.assertRaises(ValueError):
            module.apply(self.root)
        self.assertEqual(before, self.snapshot())
        target.unlink()
        with self.assertRaises(ValueError):
            module.apply(self.root)

    def test_unknown_head_and_existing_new_file_refused(self):
        self.head.stop()
        with patch.object(module.subprocess, 'check_output', return_value='0' * 40 + '\n'):
            with self.assertRaises(ValueError):
                module.apply(self.root)
        self.head.start()
        (self.root / 'crm/ui_branding.py').write_bytes(b'unknown')
        before = self.snapshot()
        with self.assertRaises(ValueError):
            module.apply(self.root)
        self.assertEqual(before, self.snapshot())

    def test_missing_parent_whitelist_and_non_directory_refusal(self):
        with self.assertRaises(ValueError):
            module.checked_target(self.root, 'crm/public/unlisted/login-theme.css')
        with self.assertRaises(ValueError):
            module.checked_target(self.root, '../outside-file')
        (self.root / 'crm/public/css').write_bytes(b'not a directory')
        before = self.snapshot()
        with self.assertRaises(ValueError):
            module.apply(self.root, check=True)
        self.assertEqual(before, self.snapshot())

    def test_staging_failure_removes_only_new_empty_directory(self):
        before = self.snapshot()
        original_open = Path.open
        def failing_open(path, *args, **kwargs):
            if path.name == 'login-theme.css.branding-tmp':
                raise OSError('controlled staging failure')
            return original_open(path, *args, **kwargs)
        with patch.object(Path, 'open', failing_open):
            with self.assertRaises(OSError):
                module.apply(self.root)
        self.assertFalse((self.root / 'crm/public/css').exists())
        self.assertEqual(before, self.snapshot())
        self.assertFalse(list(self.root.rglob('*.branding-tmp')))

    def test_context_hook_is_display_only_and_locale_native(self):
        fake = types.ModuleType('frappe')
        fake._ = lambda value: value
        path = HERE / 'payload/ui_branding.py'
        branding_spec = importlib.util.spec_from_file_location('ui_branding', path)
        branding = importlib.util.module_from_spec(branding_spec)
        with patch.dict(sys.modules, {'frappe': fake}):
            branding_spec.loader.exec_module(branding)
        untouched = {'path': 'crm', 'title': 'Existing', 'boot': {'lang': 'en'}}
        branding.update_website_context(untouched)
        self.assertEqual(untouched, {'path': 'crm', 'title': 'Existing', 'boot': {'lang': 'en'}})
        for locale in ('en', 'zh', 'de'):
            context = {'path': 'login', 'head_html': '<meta name="existing">', 'body_class': 'existing', 'boot': {'lang': locale}}
            branding.update_website_context(context)
            self.assertEqual(context['boot']['lang'], locale)
            self.assertEqual(context['app_name'], '哲人石CRM')
            self.assertEqual(context['body_class'], 'existing crm-login-brand')
            self.assertTrue(context['head_html'].startswith('<meta name="existing">'))
            self.assertIn('/assets/team_schedule/crm-theme.css', context['head_html'])
            self.assertNotIn('password', context)


if __name__ == '__main__':
    unittest.main()

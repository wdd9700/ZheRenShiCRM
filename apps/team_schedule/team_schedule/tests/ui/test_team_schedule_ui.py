import shutil
import subprocess
import unittest
from pathlib import Path


TEST_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = TEST_DIR.parent.parent
WWW_DIR = PACKAGE_DIR / "www"
PUBLIC_DIR = PACKAGE_DIR / "public"


class TeamScheduleStaticContractTests(unittest.TestCase):
    def test_page_controller_uses_standard_login_csrf_and_no_cache(self):
        source = (WWW_DIR / "team_schedule.py").read_text(encoding="utf-8")
        self.assertIn("no_cache = 1", source)
        self.assertIn('frappe.session.user == "Guest"', source)
        self.assertIn("/login?redirect-to=%2Fteam-schedule", source)
        self.assertIn("frappe.sessions.get_csrf_token()", source)
        self.assertIn("context.no_cache = 1", source)

    def test_page_has_minute_forms_and_real_asset_entry_points(self):
        source = (WWW_DIR / "team-schedule.html").read_text(encoding="utf-8")
        self.assertIn('meta name="csrf-token"', source)
        self.assertIn("/assets/team_schedule/team-schedule.js", source)
        self.assertIn("/assets/team_schedule/team-schedule.css", source)
        self.assertGreaterEqual(source.count('type="datetime-local" step="60"'), 6)
        for element_id in (
            "schedule-form", "list-form", "detail-panel", "member-panel",
            "participation-panel", "grant-form", "availability-form",
            "source-form", "existing-source-form", "existing-source-id",
            "ics-file", "ics-preview", "ics-confirm", "ics-apply",
        ):
            self.assertIn(f'id="{element_id}"', source)
        self.assertNotIn("30/60", source)

    def test_script_has_no_html_execution_or_persistent_business_cache(self):
        source = (PUBLIC_DIR / "team-schedule.js").read_text(encoding="utf-8")
        for forbidden in ("innerHTML", "outerHTML", "document.write", "eval(", "localStorage", "sessionStorage", "indexedDB", "serviceWorker"):
            self.assertNotIn(forbidden, source)
        self.assertIn("credentials: 'same-origin'", source)
        self.assertIn("'X-Frappe-CSRF-Token'", source)
        self.assertIn("resetMemoryState", source)
        self.assertIn("confirm: true", source)
        self.assertIn("team_schedule.availability.api", source)
        self.assertIn("team_schedule.ics.api", source)

    def test_shared_theme_catalog_and_raw_option_values(self):
        root = PACKAGE_DIR.parents[2]
        theme = (PUBLIC_DIR / "crm-theme.css").read_bytes()
        self.assertEqual(theme, (root / "frontend-patches/dark-ui/payload/crm-theme.css").read_bytes())
        page = (WWW_DIR / "team-schedule.html").read_text(encoding="utf-8")
        self.assertLess(page.index("crm-zh-cn.js"), page.index("team-schedule.js"))
        self.assertIn('id="day-form"', page)
        self.assertIn('id="day-date" type="date"', page)
        for filename in (
            root / "apps/team_access/team_access/www/team-activities.html",
            root / "apps/resource_import/resource_import/www/resource-import.html",
        ):
            self.assertIn("/assets/team_schedule/crm-theme.css", filename.read_text(encoding="utf-8"))
        access = (root / "apps/team_access/team_access/www/team-activities.html").read_text(encoding="utf-8")
        for value in ("FCRM Note", "CRM Task", "CRM Lead", "CRM Deal", "Private", "Shared"):
            self.assertIn(f'<option value="{value}">', access)

    def test_primary_timeline_precedes_collapsed_options_and_editor_without_shrinking_body(self):
        import re
        from html.parser import HTMLParser

        source = (WWW_DIR / "team-schedule.html").read_text(encoding="utf-8")
        previous = subprocess.check_output([
            "git", "show", "9f284b0:apps/team_schedule/team_schedule/www/team-schedule.html"
        ], cwd=PACKAGE_DIR, text=True, encoding="utf-8")
        old_ids = re.findall(r'\bid="([^"]+)"', previous)
        new_ids = re.findall(r'\bid="([^"]+)"', source)
        self.assertEqual(len(new_ids), len(set(new_ids)))
        self.assertTrue(set(old_ids).issubset(new_ids))
        self.assertLess(source.index('id="day-form"'), source.index('id="schedule-list"'))
        self.assertLess(source.index('id="schedule-list"'), source.index('id="timeline-options"'))
        self.assertLess(source.index('id="timeline-options"'), source.index('id="editor-section"'))

        class DetailsParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.details = {}
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == "details" and attrs.get("id"):
                    self.details[attrs["id"]] = attrs

        parser = DetailsParser()
        parser.feed(source)
        self.assertNotIn("open", parser.details["timeline-options"])
        self.assertNotIn("open", parser.details["editor-section"])
        css = (PUBLIC_DIR / "team-schedule.css").read_text(encoding="utf-8")
        self.assertIn('height: clamp(320px, calc(100dvh - 280px), 680px)', css)
        self.assertIn('.day-toolbar > div { display: flex; align-items: center;', css)
        self.assertIn('.crm-standalone .schedule-header h1 { flex: 1; margin: 0; }', css)
        self.assertNotRegex(css, r'(?:\{|;)\s*order\s*:')
        self.assertIn('font: 16px/1.5', (PUBLIC_DIR / "crm-theme.css").read_text(encoding="utf-8"))
        self.assertIn('.timeline-day-viewport { display: grid;', css)
        self.assertIn('grid-template-columns: minmax(340px, 1fr) 320px', css)
        self.assertIn('.timeline-scroll, .timeline-label-rail { height: clamp(', css)
        self.assertIn('font-size: 16px; line-height: 22px;', css)
        self.assertIn('.timeline-connector::before', css)
        self.assertIn('min-height: 0;', css)

    def test_framework_activity_theme_scopes_navigation_and_explicit_heading_foreground(self):
        import re

        css = (PUBLIC_DIR / "crm-theme.css").read_text(encoding="utf-8")
        rules = {selector.strip(): declarations for selector, declarations in re.findall(r'([^{}]+)\{([^{}]*)\}', css)}
        palette = rules[':root,\nbody[data-path="team-activities"]']
        self.assertIn('--crm-text: #E8EAED;', palette)
        self.assertIn('--crm-raised: #292D34;', palette)
        body = rules['body[data-path="team-activities"]']
        for declaration in ('color-scheme: dark;', '--bg-color: var(--crm-bg);', '--navbar-bg: var(--crm-surface);', '--icon-stroke: var(--crm-secondary);'):
            self.assertIn(declaration, body)
        for heading in ('h1', 'h2', 'h3'):
            self.assertIn('color: var(--crm-text);', rules[f'.crm-standalone {heading}'])
        for selector, declarations in rules.items():
            if '.navbar' in selector or '.dropdown' in selector:
                self.assertTrue(all(part.strip().startswith('body[data-path="team-activities"]') for part in selector.split(',\n')))
                self.assertNotIn('!important', declarations)
                self.assertNotIn('display: none', declarations)
        self.assertIn('background: var(--crm-surface);', rules['body[data-path="team-activities"] .navbar'])
        self.assertIn('background: var(--crm-raised);', rules['body[data-path="team-activities"] .navbar .dropdown-menu'])
        self.assertIn(':hover, :focus-visible, .active', css)
        self.assertIn('body[data-path="team-activities"] :focus-visible { outline: 2px solid var(--crm-jade);', css)
        self.assertNotIn('crm-login-brand', css)
        self.assertNotIn('!important', body)
        root = PACKAGE_DIR.parents[2]
        access_page = (root / 'apps/team_access/team_access/www/team-activities.html').read_text(encoding='utf-8')
        import_page = (root / 'apps/resource_import/resource_import/www/resource-import.html').read_text(encoding='utf-8')
        self.assertIn('{% extends "templates/web.html" %}', access_page)
        self.assertIn('class="crm-standalone crm-workspace"', access_page)
        self.assertIn('<body class="crm-standalone">', import_page)
        access_script = (root / 'apps/team_access/team_access/public/access.js').read_text(encoding='utf-8')
        self.assertIn('color:var(--crm-text,#E8EAED)', access_script)
        self.assertIn('background:var(--crm-raised,#292D34)', access_script)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for UI interaction tests")
    def test_node_interaction_and_request_contracts(self):
        result = subprocess.run(
            [
                "node", "--test",
                str(TEST_DIR / "team-schedule.test.cjs"),
                str(TEST_DIR / "team-schedule-dom.test.cjs"),
            ],
            cwd=TEST_DIR,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()

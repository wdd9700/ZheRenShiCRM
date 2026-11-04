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
            "source-form", "ics-file", "ics-preview", "ics-confirm", "ics-apply",
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

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for UI interaction tests")
    def test_node_interaction_and_request_contracts(self):
        result = subprocess.run(
            ["node", "--test", str(TEST_DIR / "team-schedule.test.cjs")],
            cwd=TEST_DIR,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()

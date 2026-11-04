from contextlib import contextmanager
from uuid import uuid4

import frappe
from frappe.tests.utils import FrappeTestCase

from team_schedule import api, permissions, service
from team_schedule.tests.test_model_service import ScheduleCase, payload


@contextmanager
def print_request(path, values):
    previous_request = getattr(frappe.local, "request", None)
    previous_form = frappe.local.form_dict
    frappe.local.request = frappe._dict(path=path)
    frappe.local.form_dict = frappe._dict(values)
    try:
        yield
    finally:
        frappe.local.request = previous_request
        frappe.local.form_dict = previous_form


class TestPrintRequestBoundary(FrappeTestCase):
    def test_print_routes_targets_and_unrelated_requests(self):
        self.assertIn("team_schedule.permissions.reject_print_request", frappe.get_hooks("before_request"))
        targets = (
            {"doctype": "Team Schedule", "name": "synthetic"},
            {"doctype": "Team Schedule", "name": ["synthetic"]},
            {"doctype": "User", "doc": {"doctype": "Team Schedule", "name": "synthetic"}},
            {"doctype": {"User": ["synthetic"], "team schedule": ["synthetic"]}},
            {"doc": frappe.as_json({"doctype": "Team Schedule", "name": "synthetic"})},
            {"doc": {"doctype": "Team Schedule", "name": "synthetic"}},
            {"doc": "Team Schedule", "name": "synthetic"},
            {"doctype": {"User": ["synthetic"], "Team Schedule": ["synthetic"]}},
            {"doctype": frappe.as_json({"User": ["synthetic"], "Team Schedule": ["synthetic"]})},
            {"doctype": "team schedule"},
        )
        for path in ("/printview", "/printview/", "/printview.html"):
            for target in targets:
                with self.subTest(path=path, target=target), print_request(path, target):
                    with self.assertRaises(frappe.PermissionError):
                        permissions.reject_print_request()
        for command in permissions.PRINT_METHODS:
            for prefix in ("/api/method/", "/api/v1/method/", "/api/v2/method/"):
                for target in targets:
                    with self.subTest(command=command, prefix=prefix, target=target), print_request(prefix + command, target):
                        with self.assertRaises(frappe.PermissionError):
                            permissions.reject_print_request()
            with print_request("/", {"cmd": command, "doctype": "Team Schedule"}):
                with self.assertRaises(frappe.PermissionError):
                    permissions.reject_print_request()
        for doctype in permissions.DOCTYPES:
            with print_request("/printview", {"doctype": doctype}):
                with self.assertRaises(frappe.PermissionError):
                    permissions.reject_print_request()
        for values in ({"doctype": "User"}, {"doctype": "CRM Lead"}, {"doc": {"doctype": "User", "title": "Team Schedule"}}, {"doctype": "not Team Schedule"}, {"doc": "{bad"}, {"doctype": ["Team Schedule"]}):
            with print_request("/printview", values):
                permissions.reject_print_request()
        for command in ("frappe.client.get", "team_schedule.api.get", "team_schedule.api.export_owned", "frappe.utils.print_format.report_to_pdf"):
            with print_request("/api/method/" + command, {"doctype": "Team Schedule"}):
                permissions.reject_print_request()


class TestPrintRendererBoundary(ScheduleCase):
    def test_real_standard_renderers_deny_owner_peer_and_maintenance(self):
        document = service.create_schedule(payload([{"user": self.users[1], "access": "Read"}]), str(uuid4()))
        from frappe.utils.print_format import download_pdf
        from frappe.www.printview import get_html_and_style, get_rendered_template

        counts = {doctype: frappe.db.count(doctype) for doctype in ("File", "Communication", "Email Queue")}
        for user in (*self.users, "Administrator"):
            frappe.set_user(user)
            self.assertTrue(permissions.can_read(document))
            for render in (
                lambda: get_rendered_template(document),
                lambda: frappe.get_print("Team Schedule", document.name),
                lambda: get_html_and_style("Team Schedule", name=document.name),
                lambda: get_html_and_style(frappe.as_json(document.as_dict())),
                lambda: download_pdf("Team Schedule", document.name),
            ):
                with self.subTest(user=user, render=render):
                    with self.assertRaises(frappe.PermissionError):
                        render()
            with permissions.internal_write():
                with self.assertRaises(frappe.PermissionError):
                    document.check_permission("print")
            with self.assertRaises(frappe.PermissionError):
                document.run_method("before_print", frappe._dict())
        self.assertEqual(counts, {doctype: frappe.db.count(doctype) for doctype in counts})
        frappe.set_user(self.users[0])
        self.assertEqual(api.get(name=document.name).status_code, 200)
        self.assertEqual(api.export_owned(start_utc="2026-11-04T00:00:00Z", end_utc="2026-11-05T00:00:00Z").status_code, 200)

    def test_non_app_real_html_rendering_is_unchanged(self):
        html = frappe.get_print("User", self.users[0])
        self.assertIsInstance(html, str)
        self.assertIn("Synthetic Schedule", html)

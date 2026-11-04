from uuid import uuid4

import frappe
from frappe import client
from frappe.core.doctype.data_export.exporter import DataExporter
from frappe.tests.utils import FrappeTestCase

from team_schedule import api, permissions, service
from team_schedule.tests.test_model_service import ScheduleCase, payload


class TestPermissionsCore(ScheduleCase):
    def test_standard_read_query_child_and_revoke(self):
        actor, peer = self.users
        private = service.create_schedule({**payload(), "description": "synthetic-private-canary"}, str(uuid4()))
        shared = service.create_schedule(payload([{"user": peer, "access": "Read"}]), str(uuid4()))
        frappe.set_user(peer)
        self.assertFalse(frappe.has_permission("Team Schedule", "read", private))
        self.assertTrue(frappe.has_permission("Team Schedule", "read", shared))
        rows = frappe.get_list("Team Schedule", fields=["name", "description"], filters={"name": ["in", [private.name, shared.name]]})
        self.assertEqual([row.name for row in rows], [shared.name])
        self.assertNotIn("synthetic-private-canary", str(rows))
        self.assertTrue(frappe.has_permission("Team Schedule Member", "read", shared.members[0]))
        frappe.set_user(actor)
        service.set_members(shared.name, 1, [])
        frappe.set_user(peer)
        self.assertFalse(frappe.has_permission("Team Schedule", "read", frappe.get_doc("Team Schedule", shared.name)))
        self.assertEqual(frappe.get_list("Team Schedule", filters={"name": shared.name}), [])

    def test_standard_mutations_flags_and_delete_are_rejected(self):
        doc = service.create_schedule(payload(), str(uuid4()))
        for flags in ({}, {"ignore_permissions": True, "ignore_validate": True}):
            value = frappe.get_doc("Team Schedule", doc.name)
            value.title = "standard write denied"
            value.flags.update(flags)
            with self.subTest(flags=flags), self.assertRaises(frappe.PermissionError):
                value.save()
        with self.assertRaises(frappe.PermissionError):
            client.set_value("Team Schedule", doc.name, "title", "client write denied")
        with self.assertRaises(frappe.PermissionError):
            frappe.get_doc({"doctype": "Team Schedule", **payload(), "revision": 1, "status": "Active", "flags": {"ignore_permissions": True}}).insert()
        with self.assertRaises(frappe.PermissionError):
            frappe.delete_doc("Team Schedule", doc.name)
        self.assertEqual(frappe.db.get_value("Team Schedule", doc.name, "revision"), 1)

    def test_share_denied_for_admin_and_migration_fail_closed(self):
        from team_schedule.patches.v1_constraints import check_shares

        owner, peer = self.users
        request_id = str(uuid4())
        doc = service.create_schedule(payload([{"user": peer, "access": "Read"}]), request_id)
        source = service.create_source("synthetic share target")
        item = service.save_source_item(source.name, "synthetic-share-UID", {"source_sequence": 1, "source_digest": "a" * 64, "tombstone": True})
        service.set_busy_grant(peer, True)
        targets = {
            "Team Schedule": doc.name,
            "Team Schedule Member": doc.members[0].name,
            "Team Schedule Busy Grant": frappe.db.get_value("Team Schedule Busy Grant", {"subject_user": owner, "viewer_user": peer}, "name"),
            "Team Schedule Source": source.name,
            "Team Schedule Source Item": item.name,
            "Team Schedule Request": frappe.db.get_value("Team Schedule Request", {"owner": owner, "request_id": request_id}, "name"),
            "Team Schedule Audit": frappe.db.get_value("Team Schedule Audit", {"target_name": doc.name}, "name"),
        }
        self.assertEqual(set(targets), set(permissions.DOCTYPES))
        frappe.set_user("Administrator")
        for doctype, name in targets.items():
            with self.subTest(doctype=doctype):
                self.assertTrue(name)
                self.assertTrue(frappe.db.exists(doctype, name))
                share = {"doctype": "DocShare", "share_doctype": doctype, "share_name": name, "user": peer, "read": 1}
                with self.assertRaises(frappe.PermissionError):
                    frappe.get_doc({**share, "flags": {"ignore_validate": True}}).insert()
                self.assertFalse(frappe.db.exists("DocShare", {"share_doctype": doctype, "share_name": name}))
                frappe.db.savepoint("synthetic_anomalous_share")
                try:
                    anomalous = frappe.get_doc({**share, "name": uuid4().hex, "owner": "Administrator"})
                    anomalous.db_insert()
                    self.assert_code("FORBIDDEN", check_shares)
                    self.assert_code("FORBIDDEN", permissions.current_user)
                    self.assert_code("FORBIDDEN", permissions.query_conditions, peer)
                    self.assertTrue(frappe.db.exists("DocShare", anomalous.name))
                finally:
                    frappe.db.rollback(save_point="synthetic_anomalous_share")
                self.assertFalse(frappe.db.exists("DocShare", {"share_doctype": doctype, "share_name": name}))
        check_shares()
        self.assertFalse(frappe.db.exists("DocShare", {"share_doctype": ["in", permissions.DOCTYPES]}))

    def test_export_print_version_and_sidecars_denied(self):
        doc = service.create_schedule(payload(), str(uuid4()))
        for permission in ("export", "print", "email", "report", "import", "share"):
            with self.subTest(permission=permission):
                self.assertFalse(frappe.has_permission("Team Schedule", permission, doc))
        with self.assertRaises(frappe.PermissionError):
            DataExporter(doctype="Team Schedule", with_data=True).build_response()
        self.assertFalse(frappe.db.exists("Version", {"ref_doctype": "Team Schedule", "docname": doc.name}))
        with self.assertRaises(frappe.PermissionError):
            frappe.get_doc({"doctype": "Comment", "comment_type": "Comment", "reference_doctype": "Team Schedule", "reference_name": doc.name, "content": "synthetic body"}).insert()
        with self.assertRaises(frappe.PermissionError):
            frappe.get_doc({"doctype": "File", "file_name": "synthetic.txt", "attached_to_doctype": "Team Schedule", "attached_to_name": doc.name, "content": "synthetic body", "is_private": 1}).insert()

    def test_request_is_internal_and_api_unknown_parameters_no_store(self):
        request_id = str(uuid4())
        doc = service.create_schedule(payload(), request_id)
        request = frappe.get_doc("Team Schedule Request", {"owner": self.users[0], "request_id": request_id})
        self.assertFalse(frappe.has_permission("Team Schedule Request", "read", request))
        self.assertEqual(frappe.get_list("Team Schedule Request"), [])
        audit = frappe.get_doc("Team Schedule Audit", {"target_name": doc.name})
        self.assertFalse(frappe.has_permission("Team Schedule Audit", "read", audit))
        self.assertEqual(frappe.get_list("Team Schedule Audit"), [])
        response = frappe.call(api.get, name=doc.name, unexpected="must-not-be-filtered")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.get_json(), {"message": {"error": {"code": "INVALID_INPUT"}}})

    def test_api_responses_and_private_export(self):
        result = api.create(**payload(), request_id=str(uuid4()))
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.headers["Cache-Control"], "no-store")
        doc = result.get_json()["message"]["schedule"]
        self.assertEqual(set(doc), set(service.DETAIL_FIELDS) | {"members"})
        exported = api.export_owned(start_utc="2026-11-04T00:00:00Z", end_utc="2026-11-05T00:00:00Z")
        self.assertEqual(exported.status_code, 200)
        self.assertEqual(exported.headers["Cache-Control"], "no-store")
        self.assertIn("attachment", exported.headers["Content-Disposition"])
        self.assertEqual(exported.get_json()["schedules"][0]["name"], doc["name"])
        frappe.set_user(self.users[1])
        denied = api.get(name=doc["name"])
        self.assertEqual(denied.status_code, 404)
        self.assertNotIn("synthetic body", denied.get_data(as_text=True))

from uuid import uuid4

import frappe
from frappe import client

from team_schedule import api, permissions, service
from team_schedule.tests.test_model_service import ScheduleCase, payload


WINDOW = {"start_utc": "2026-11-04T00:00:00Z", "end_utc": "2026-11-05T00:00:00Z"}


class TestPermissionsIdentity(ScheduleCase):
    def assert_business_denied(self, owned, shared):
        calls = (
            (api.create, {**payload(), "request_id": str(uuid4())}),
            (api.get, {"name": owned}),
            (api.get, {"name": shared}),
            (api.list, WINDOW),
            (api.update, {"name": owned, "expected_revision": 1, "changes": {"title": "denied"}}),
            (api.update, {"name": shared, "expected_revision": 1, "changes": {"title": "denied"}}),
            (api.cancel, {"name": owned, "expected_revision": 1}),
            (api.cancel, {"name": shared, "expected_revision": 1}),
            (api.set_participation, {"name": shared, "expected_revision": 1, "occupies": True}),
            (api.export_owned, WINDOW),
        )
        for function, values in calls:
            with self.subTest(endpoint=function.__name__, values=values):
                response = function(**values)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.get_json(), {"message": {"error": {"code": "FORBIDDEN"}}})
                self.assertEqual(response.headers["Cache-Control"], "no-store")
                self.assertNotIn("synthetic body", response.get_data(as_text=True))

    def assert_standard_denied(self, docs):
        for doc in docs:
            with self.subTest(name=doc.name):
                self.assertFalse(permissions.can_read(doc))
                self.assertFalse(permissions.can_edit(doc))
                self.assertFalse(frappe.has_permission("Team Schedule", "read", doc))
                with self.assertRaises(frappe.PermissionError):
                    client.get("Team Schedule", name=doc.name)
                self.assertEqual(frappe.get_list("Team Schedule", filters={"name": doc.name}), [])
                self.assertEqual(permissions.member_query(), "1=0")
                self.assertEqual(client.get_list("Team Schedule Member", parent="Team Schedule", filters={"parent": doc.name}), [])
                for child in doc.members:
                    self.assertFalse(permissions.can_read(child))
                    self.assertFalse(frappe.has_permission("Team Schedule Member", "read", child))
                    with self.assertRaises(frappe.PermissionError):
                        child.check_permission("read")
                    with self.assertRaises(frappe.PermissionError):
                        client.get("Team Schedule Member", name=child.name, parent="Team Schedule")

    def save_identity(self, user, user_type):
        frappe.set_user("Administrator")
        document = frappe.get_doc("User", user)
        document.set("roles", [{"role": "Sales User"}] if user_type == "System User" else [])
        document.user_type = user_type
        document.save()
        document.reload()
        self.assertEqual((document.enabled, document.user_type), (1, user_type))
        frappe.db.commit()
        self.assertEqual(frappe.db.get_value("User", user, ["enabled", "user_type"]), (1, user_type))
        frappe.set_user(user)

    def test_new_website_user_cannot_enter_business_or_standard_reads(self):
        owner, peer = self.users
        doc = service.create_schedule(payload([{"user": peer, "access": "Edit"}]), str(uuid4()))
        frappe.set_user("Administrator")
        website = f"schedule-website-{uuid4().hex}@example.invalid"
        document = frappe.get_doc({"doctype": "User", "email": website, "first_name": "Synthetic Website", "enabled": 1, "user_type": "Website User", "send_welcome_email": 0}).insert()
        document.reload()
        self.assertEqual((document.enabled, document.user_type), (1, "Website User"))
        frappe.db.commit()
        frappe.set_user(website)
        self.assert_business_denied(doc.name, doc.name)
        self.assert_standard_denied([doc])
        self.assert_code("FORBIDDEN", permissions.current_user)
        self.assert_code("FORBIDDEN", permissions.current_user, lock_mode="shared")

    def test_normal_downgrade_preserves_owner_acl_and_restore_reenables_access(self):
        owner, peer = self.users
        shared = service.create_schedule(payload([{"user": peer, "access": "Edit"}]), str(uuid4()))
        frappe.set_user(peer)
        owned = service.create_schedule(payload([{"user": owner, "access": "Read"}]), str(uuid4()))
        frappe.db.commit()
        original_members = [(row.name, row.user, row.access, row.occupies) for row in shared.members]
        self.save_identity(peer, "Website User")
        self.assert_business_denied(owned.name, shared.name)
        self.assert_standard_denied([owned, shared])
        self.assertEqual(frappe.db.get_value("Team Schedule", owned.name, "owner"), peer)
        shared.reload()
        self.assertEqual([(row.name, row.user, row.access, row.occupies) for row in shared.members], original_members)
        self.assertEqual((shared.revision, shared.status), (1, "Active"))
        self.assertEqual(frappe.db.get_value("Team Schedule", owned.name, "revision"), 1)
        self.save_identity(peer, "System User")
        for doc in (owned, shared):
            self.assertEqual(api.get(name=doc.name).status_code, 200)
            self.assertEqual(client.get("Team Schedule", name=doc.name)["name"], doc.name)
            self.assertEqual(len(frappe.get_list("Team Schedule", filters={"name": doc.name})), 1)
            self.assertTrue(permissions.can_read(doc.members[0]))
        self.assertEqual(api.list(**WINDOW).status_code, 200)
        exported = api.export_owned(**WINDOW)
        self.assertEqual(exported.status_code, 200)
        self.assertIn(owned.name, [row["name"] for row in exported.get_json()["schedules"]])
        self.assertEqual(api.update(name=shared.name, expected_revision=1, changes={"title": "restored edit"}).status_code, 200)
        self.assertEqual(api.set_participation(name=shared.name, expected_revision=2, occupies=True).status_code, 200)
        self.assertEqual(api.cancel(name=shared.name, expected_revision=3).status_code, 200)
        self.assertEqual(api.create(**payload(), request_id=str(uuid4())).status_code, 200)
        shared.reload()
        self.assertEqual((shared.revision, shared.status, shared.members[0].occupies), (4, "Cancelled", 1))

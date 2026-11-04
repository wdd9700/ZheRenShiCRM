from uuid import uuid4

import frappe
from frappe.tests.utils import FrappeTestCase

from team_schedule import service
from team_schedule.timeutils import ScheduleError


def payload(members=None):
    return {"title": "synthetic private schedule", "description": "synthetic body", "start_utc": "2026-11-04T09:07:00Z", "end_utc": "2026-11-04T09:42:00Z", "source_timezone": "UTC", "availability": "Busy", "members": members or []}


class ScheduleCase(FrappeTestCase):
    def setUp(self):
        self.previous_user = frappe.session.user
        frappe.set_user("Administrator")
        self.users = []
        for suffix in ("owner", "peer"):
            email = f"schedule-{suffix}-{uuid4().hex}@example.invalid"
            frappe.get_doc({"doctype": "User", "email": email, "first_name": "Synthetic Schedule", "enabled": 1, "user_type": "System User", "send_welcome_email": 0, "roles": [{"role": "Sales User"}]}).insert()
            self.users.append(email)
        frappe.set_user(self.users[0])

    def tearDown(self):
        frappe.set_user(self.previous_user)
        frappe.db.rollback()

    def assert_code(self, code, function, *args, **kwargs):
        with self.assertRaises(ScheduleError) as error:
            function(*args, **kwargs)
        self.assertEqual(error.exception.code, code)


class TestModelService(ScheduleCase):
    def test_audit_rolls_back_with_item_and_duplicate_does_not_audit(self):
        before = frappe.db.count("Team Schedule Audit", {"actor": self.users[0]})
        frappe.db.savepoint("synthetic_item")
        failed = service.create_schedule(payload(), str(uuid4()))
        self.assertGreater(frappe.db.count("Team Schedule Audit", {"actor": self.users[0]}), before)
        frappe.db.rollback(save_point="synthetic_item")
        self.assertEqual(frappe.db.count("Team Schedule Audit", {"actor": self.users[0]}), before)
        self.assertFalse(frappe.db.exists("Team Schedule", failed.name))
        request_id = str(uuid4())
        doc = service.create_schedule(payload(), request_id)
        committed_count = frappe.db.count("Team Schedule Audit", {"actor": self.users[0]})
        service.create_schedule(payload(), request_id)
        self.assertEqual(frappe.db.count("Team Schedule Audit", {"actor": self.users[0]}), committed_count)
        entry = frappe.get_doc("Team Schedule Audit", {"target_name": doc.name})
        self.assertEqual((entry.actor, entry.action, entry.revision), (self.users[0], "create", 1))
        self.assertFalse(entry.get("title"))
        self.assertFalse(entry.get("description"))

    def test_create_idempotency_and_conflict(self):
        request_id = str(uuid4())
        doc = service.create_schedule(payload(), request_id)
        self.assertEqual(doc.revision, 1)
        service.mutate_schedule(doc.name, 1, {"title": "changed locally"})
        retry = service.create_schedule(payload(), request_id)
        self.assertEqual((retry.name, retry.revision, retry.title), (doc.name, 2, "changed locally"))
        self.assertEqual(frappe.db.count("Team Schedule Request", {"owner": self.users[0], "request_id": request_id}), 1)
        self.assert_code("IDEMPOTENCY_CONFLICT", service.create_schedule, {**payload(), "title": "different payload"}, request_id)
        self.assert_code("REVISION_CONFLICT", service.mutate_schedule, doc.name, 1, {"title": "stale"})
        self.assert_code("INVALID_INPUT", service.mutate_schedule, doc.name, 2, {"start_utc": "2026-11-04T09:08:00Z"})
        self.assert_code("INVALID_INPUT", service.mutate_schedule, doc.name, 2, {"owner": self.users[1]})

    def test_member_acceptance_acl_revision_and_cancel(self):
        peer = self.users[1]
        doc = service.create_schedule(payload([{"user": peer, "access": "Read"}]), str(uuid4()))
        self.assertFalse(doc.members[0].occupies)
        frappe.set_user(peer)
        self.assert_code("FORBIDDEN", service.mutate_schedule, doc.name, 1, {"title": "denied"})
        accepted = service.set_participation(doc.name, 1, True)
        self.assertTrue(accepted.members[0].occupies)
        frappe.set_user(self.users[0])
        edited = service.set_members(doc.name, 2, [{"user": peer, "access": "Edit"}])
        self.assertTrue(edited.members[0].occupies)
        frappe.set_user(peer)
        self.assert_code("FORBIDDEN", service.set_members, doc.name, 3, [])
        service.mutate_schedule(doc.name, 3, {"availability": "Free"})
        frappe.set_user(self.users[0])
        service.set_members(doc.name, 4, [])
        frappe.set_user(peer)
        self.assert_code("NOT_FOUND", service.locked_schedule, doc.name)
        frappe.set_user(self.users[0])
        cancelled = service.cancel(doc.name, 5)
        self.assertEqual((cancelled.status, cancelled.revision), ("Cancelled", 6))
        self.assertEqual(service.cancel(doc.name, 6).revision, 6)
        self.assert_code("FORBIDDEN", service.mutate_schedule, doc.name, 6, {"title": "denied"})

    def test_disabled_member_does_not_block_owner_cancel(self):
        doc = service.create_schedule(payload([{"user": self.users[1], "access": "Read"}]), str(uuid4()))
        frappe.set_user("Administrator")
        frappe.db.set_value("User", self.users[1], "enabled", 0)
        frappe.set_user(self.users[0])
        self.assertEqual(service.cancel(doc.name, 1).status, "Cancelled")
        service.set_busy_grant(self.users[1], False)
        frappe.set_user(self.users[1])
        self.assert_code("FORBIDDEN", service.locked_schedule, doc.name)

    def test_source_uid_case_and_tombstone(self):
        source = service.create_source("synthetic local source")
        for uid in ("CaseUID", "caseuid"):
            service.save_source_item(source.name, uid, {"source_sequence": 1, "source_digest": "a" * 64, "tombstone": True})
        first = service.lock_source_item(source.name, "CaseUID")
        second = service.lock_source_item(source.name, "caseuid")
        self.assertNotEqual(first.name, second.name)
        self.assertEqual(first.uid, "CaseUID")
        frappe.set_user(self.users[1])
        self.assert_code("NOT_FOUND", service.get_source, source.name)

    def test_busy_grant_and_pagination(self):
        actor, peer = self.users
        service.set_busy_grant(peer, True)
        frappe.set_user(peer)
        self.assertEqual(service.assert_busy_access([peer, actor]), peer)
        frappe.set_user(actor)
        service.set_busy_grant(peer, False)
        frappe.set_user(peer)
        self.assert_code("FORBIDDEN", service.assert_busy_access, [peer, actor])
        frappe.set_user(actor)
        for _ in range(2):
            service.create_schedule(payload(), str(uuid4()))
        page = service.list_schedules("2026-11-04T00:00:00Z", "2026-11-05T00:00:00Z", limit=1)
        self.assertEqual(len(page["items"]), 1)
        self.assertIsNotNone(page["next_cursor"])
        next_page = service.list_schedules("2026-11-04T00:00:00Z", "2026-11-05T00:00:00Z", cursor=page["next_cursor"], limit=1)
        self.assertNotEqual(page["items"][0]["name"], next_page["items"][0]["name"])
        frappe.set_user(peer)
        self.assert_code("INVALID_INPUT", service.list_schedules, "2026-11-04T00:00:00Z", "2026-11-05T00:00:00Z", cursor=page["next_cursor"])

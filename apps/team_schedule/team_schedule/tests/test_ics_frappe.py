import base64
import importlib.util
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

try:
    import frappe
    from team_schedule import service as core
    from team_schedule.ics import service
    from team_schedule.tests.test_model_service import ScheduleCase
except ModuleNotFoundError:
    frappe = None
    ScheduleCase = unittest.TestCase


def encoded(*rows):
    text = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Synthetic Real Database Tests//EN\r\n"
    text += "".join("BEGIN:VEVENT\r\n" + row + "END:VEVENT\r\n" for row in rows)
    return base64.b64encode((text + "END:VCALENDAR\r\n").encode()).decode()


def event(uid, sequence=0, title="Synthetic ICS database test"):
    return (f"UID:{uid}\r\nSEQUENCE:{sequence}\r\nSUMMARY:{title}\r\n"
            "DTSTART:20261104T090700Z\r\nDTEND:20261104T094200Z\r\n")


@unittest.skipUnless(frappe is not None and importlib.util.find_spec("vobject"), "Requires real Frappe site and vobject; no dependency is installed by tests")
class TestICSFrappe(ScheduleCase):
    def setUp(self):
        super().setUp()
        self.previous_sid = frappe.session.sid
        self.sid = "synthetic-ics-" + uuid4().hex
        frappe.session.sid = self.sid
        self.source = service.create_source("Synthetic ICS database source")["source_id"]

    def tearDown(self):
        frappe.session.sid = self.previous_sid
        super().tearDown()

    def plan(self, *rows):
        content = encoded(*rows)
        return service.preview(self.source, content), content

    def apply(self, plan, content, resolutions=None):
        return service.apply(plan["receipt"], self.source, content, True, resolutions or [])["items"]

    def audit_count(self):
        return frappe.db.count("Team Schedule Audit", {"actor": self.users[0]})

    def snapshot(self, name, uid):
        return (frappe.get_doc("Team Schedule", name).as_dict(),
                core.lock_source_item(self.source, uid).as_dict(), self.audit_count())

    def test_partial_failure_same_receipt_committed_retry_and_local_edit_zero_write(self):
        plan, content = self.plan(event("A"), event("B"))
        original_save = core.save_source_item

        def fail_b(source, uid, values):
            if uid == "B":
                raise RuntimeError("synthetic item failure")
            return original_save(source, uid, values)

        with patch.object(core, "save_source_item", side_effect=fail_b):
            first = self.apply(plan, content)
        self.assertEqual([row["result"] for row in first], ["create", "error"])
        self.assertEqual(frappe.db.count("Team Schedule", {"owner": self.users[0]}), 1)
        self.assertIsNone(core.lock_source_item(self.source, "B"))
        frappe.db.commit()
        a = first[0]["schedule_name"]
        before = self.snapshot(a, "A")
        retry = self.apply(plan, content)
        self.assertEqual([row["result"] for row in retry], ["duplicate", "create"])
        after = self.snapshot(a, "A")
        self.assertEqual(before[:2], after[:2])
        self.assertEqual(after[2] - before[2], 2)
        self.assertEqual(frappe.db.count("Team Schedule", {"owner": self.users[0]}), 2)
        core.mutate_schedule(a, 1, {"title": "synthetic local edit"})
        core.set_members(a, 2, [{"user": self.users[1], "access": "Read"}])
        before = self.snapshot(a, "A")
        repeated = self.apply(plan, content)
        self.assertEqual([row["result"] for row in repeated], ["duplicate", "duplicate"])
        self.assertEqual(self.snapshot(a, "A"), before)

    def test_absent_state_higher_committed_version_and_other_safe_item(self):
        old, old_file = self.plan(event("A", 0), event("B", 0))
        new, new_file = self.plan(event("A", 5))
        committed = self.apply(new, new_file)[0]
        frappe.db.commit()
        before = self.snapshot(committed["schedule_name"], "A")
        result = self.apply(old, old_file)
        self.assertEqual([row["result"] for row in result], ["revision_conflict", "create"])
        self.assertEqual(self.snapshot(committed["schedule_name"], "A")[:2], before[:2])
        refreshed, _ = self.plan(event("A", 0))
        self.assertEqual(refreshed["items"][0]["action"], "stale")

    def test_local_conflict_resolution_validation_and_acl_preserved(self):
        plan, content = self.plan(event("A"), event("B"))
        first = self.apply(plan, content)
        name = first[0]["schedule_name"]
        core.set_members(name, 1, [{"user": self.users[1], "access": "Edit"}])
        changed, changed_file = self.plan(event("A", 1, "new source title"), event("B"))
        self.assertEqual(changed["items"][0]["allowed_resolutions"], ["replace_from_source"])
        self.assertEqual(changed["items"][0]["expected_revision"], 2)
        before = self.snapshot(name, "A")
        self.assertEqual(self.apply(changed, changed_file)[0]["result"], "local_conflict")
        self.assertEqual(self.snapshot(name, "A"), before)
        valid = {"index": 0, "action": "replace_from_source", "expected_revision": 2}
        for resolutions in ([valid, valid], [{**valid, "index": True}], [{**valid, "index": 1}],
                            [{**valid, "index": 99}], [{**valid, "action": "force"}],
                            [{**valid, "expected_revision": 3}], [{**valid, "extra": 1}]):
            self.assert_code("INVALID_INPUT", service.apply, changed["receipt"], self.source, changed_file, True, resolutions)
            self.assertEqual(self.snapshot(name, "A"), before)
        result = self.apply(changed, changed_file, [valid])
        self.assertEqual(result[0]["result"], "update")
        doc = core.locked_schedule(name)
        self.assertEqual((doc.title, doc.revision), ("new source title", 3))
        self.assertEqual([(row.user, row.access) for row in doc.members], [(self.users[1], "Edit")])
        later, later_file = self.plan(event("A", 2))
        core.mutate_schedule(name, 3, {"title": "another local edit"})
        self.assertEqual(self.apply(later, later_file)[0]["result"], "revision_conflict")

    def test_unknown_cancel_tombstone_and_case_sensitive_uid(self):
        plan, content = self.plan("UID:CaseUID\r\nSEQUENCE:3\r\nSTATUS:CANCELLED\r\n", event("caseuid"))
        result = self.apply(plan, content)
        self.assertEqual([row["result"] for row in result], ["unknown_cancelled", "create"])
        self.assertTrue(core.lock_source_item(self.source, "CaseUID").tombstone)
        self.assertFalse(core.lock_source_item(self.source, "CaseUID").schedule)
        self.assertFalse(core.lock_source_item(self.source, "caseuid").tombstone)
        high, high_file = self.plan(event("CaseUID", 10))
        self.assertEqual(self.apply(high, high_file)[0]["result"], "cancelled_source")

    def test_source_literal_text_roundtrips_without_silent_cleaning(self):
        title = "<script>SYNTHETIC-ICS-TITLE-CANARY</script>"
        description = '<img src="https://example.invalid/not-fetched">& literal text'
        plan, content = self.plan(event("literal-text", title=title) + "DESCRIPTION:" + description + "\r\n")
        result = self.apply(plan, content)[0]
        self.assertEqual(result["result"], "create")
        doc = frappe.get_doc("Team Schedule", result["schedule_name"])
        self.assertEqual(doc.title, title)
        self.assertEqual(doc.description, description)

    def test_two_real_database_connections_same_receipt_create_once(self):
        plan, content = self.plan(event("parallel"))
        owner, sid, source = self.users[0], self.sid, self.source
        site, sites_path = frappe.local.site, frappe.local.sites_path
        frappe.db.commit()
        barrier = Barrier(2)

        def worker():
            frappe.init(site=site, sites_path=sites_path)
            frappe.connect(set_admin_as_user=False)
            try:
                frappe.set_user(owner)
                frappe.session.sid = sid
                barrier.wait(timeout=20)
                result = service.apply(plan["receipt"], source, content, True, [])["items"][0]
                frappe.db.commit()
                return result
            finally:
                frappe.db.rollback()
                frappe.destroy()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(worker) for _ in range(2)]
            results = [future.result(timeout=60) for future in futures]
        frappe.db.rollback()
        self.assertEqual(sorted(row["result"] for row in results), ["create", "duplicate"])
        self.assertEqual(len({row["schedule_name"] for row in results}), 1)
        self.assertEqual(frappe.db.count("Team Schedule", {"owner": owner}), 1)
        self.assertEqual(frappe.db.count("Team Schedule Source Item", {"source": source}), 1)

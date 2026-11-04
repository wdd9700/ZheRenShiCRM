import base64
import copy
import hashlib
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import team_schedule
from team_schedule.ics import parser


def calendar(*rows):
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Synthetic//EN\r\n" + "".join(
        "BEGIN:VEVENT\r\n" + row + "END:VEVENT\r\n" for row in rows) + "END:VCALENDAR\r\n").encode()


def event(uid, sequence=0, title="Synthetic"):
    return (f"UID:{uid}\r\nSEQUENCE:{sequence}\r\nSUMMARY:{title}\r\n"
            "DTSTART:20261104T090700Z\r\nDTEND:20261104T094200Z\r\n")


def cancelled(uid, sequence):
    return f"UID:{uid}\r\nSEQUENCE:{sequence}\r\nSTATUS:CANCELLED\r\n"


class SafeError(ValueError):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code, self.status = code, status


class Doc(dict):
    def __getattr__(self, name):
        return self.get(name)


class MemoryEnvironment:
    def __init__(self):
        self.store = {"sources": {}, "schedules": {}, "mappings": {}, "audit": []}
        self.cache = {}
        self.points = {}
        self.failure_uid = None
        self.disabled = False
        self.frappe = types.SimpleNamespace(session=types.SimpleNamespace(user="owner-a", sid="session-a"),
                                            local=types.SimpleNamespace(message_log=[]))
        self.frappe.cache = types.SimpleNamespace(set_value=self.cache_set, get_value=self.cache.get)
        self.frappe.db = types.SimpleNamespace(savepoint=self.savepoint, rollback=self.rollback)
        self.permissions = types.SimpleNamespace(current_user=self.current_user)
        self.core = types.SimpleNamespace(fields=self.fields, uid_key=lambda uid: hashlib.sha256(uid.encode()).hexdigest(),
                                          create_source=self.create_source, get_source=self.get_source,
                                          lock_source_item=self.lock_source_item, locked_schedule=self.locked_schedule,
                                          save_import_schedule=self.save_import_schedule, save_source_item=self.save_source_item)

    def invalid(self):
        raise SafeError("INVALID_INPUT")

    def current_user(self):
        if self.frappe.session.user == "Guest":
            raise SafeError("AUTH_REQUIRED", 401)
        if self.disabled:
            raise SafeError("FORBIDDEN", 403)
        return self.frappe.session.user

    def fields(self, value, allowed, required=()):
        if not isinstance(value, dict) or set(value) - set(allowed) or not set(required) <= set(value):
            self.invalid()

    def cache_set(self, key, value, expires_in_sec):
        self.cache[key] = copy.deepcopy(value)

    def savepoint(self, point):
        self.points[point] = copy.deepcopy(self.store)

    def rollback(self, save_point):
        self.store = copy.deepcopy(self.points[save_point])

    def create_source(self, label):
        if not isinstance(label, str) or not label.strip() or len(label) > 140:
            self.invalid()
        name = "source-" + str(len(self.store["sources"]))
        doc = Doc(name=name, label=label, owner=self.current_user())
        self.store["sources"][name] = doc
        self.store["audit"].append(("source", name))
        return doc

    def get_source(self, source_id, lock=False):
        doc = self.store["sources"].get(source_id)
        if not doc:
            raise SafeError("NOT_FOUND", 404)
        return copy.deepcopy(doc)

    def lock_source_item(self, source_id, uid):
        return copy.deepcopy(self.store["mappings"].get((source_id, uid)))

    def locked_schedule(self, name, mode="owner"):
        doc = self.store["schedules"].get(name)
        if not doc:
            raise SafeError("NOT_FOUND", 404)
        return copy.deepcopy(doc)

    def save_import_schedule(self, source_id, payload, schedule_name=None, expected_revision=None):
        if schedule_name is None:
            schedule_name = "schedule-" + str(len(self.store["schedules"]))
            doc = Doc(name=schedule_name, owner=self.current_user(), members=[], revision=1, **payload)
        else:
            doc = copy.deepcopy(self.store["schedules"][schedule_name])
            if doc.revision != expected_revision:
                raise SafeError("REVISION_CONFLICT", 409)
            doc.update(payload)
            doc["revision"] += 1
        self.store["schedules"][schedule_name] = doc
        self.store["audit"].append(("schedule", schedule_name, doc.revision))
        return copy.deepcopy(doc)

    def save_source_item(self, source_id, uid, values):
        if self.failure_uid == uid:
            raise RuntimeError("synthetic private failure detail must never be returned")
        self.store["mappings"][(source_id, uid)] = Doc(**values)
        self.store["audit"].append(("mapping", source_id, uid))

    def local_edit(self, name, **changes):
        self.store["schedules"][name].update(changes)
        self.store["schedules"][name]["revision"] += 1


class ICSInMemoryProtocolTests(unittest.TestCase):
    def setUp(self):
        self.env = MemoryEnvironment()
        errors = types.ModuleType("team_schedule.timeutils")
        errors.ScheduleError, errors.invalid = SafeError, self.env.invalid
        bindings = {"frappe": self.env.frappe, "team_schedule.permissions": self.env.permissions,
                    "team_schedule.service": self.env.core, "team_schedule.timeutils": errors}
        path = Path(__file__).parents[1] / "ics" / "service.py"
        spec = importlib.util.spec_from_file_location("ics_memory_service", path)
        self.service = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, bindings), patch.object(team_schedule, "permissions", self.env.permissions, create=True), patch.object(team_schedule, "service", self.env.core, create=True):
            spec.loader.exec_module(self.service)
        parsing = patch.object(parser, "parse_file", lambda raw: parser._parse_file(raw, lambda *args, **kwargs: object()))
        parsing.start()
        self.addCleanup(parsing.stop)
        self.source = self.service.create_source("Synthetic local source")["source_id"]

    def preview(self, *rows, source=None):
        content = base64.b64encode(calendar(*rows)).decode()
        plan = self.service.preview(source or self.source, content)
        return plan, content

    def apply(self, plan, content, source=None, confirm=True, resolutions=None):
        return self.service.apply(plan["receipt"], source or self.source, content, confirm, [] if resolutions is None else resolutions)["items"]

    def imported(self, uid="A", sequence=0):
        plan, content = self.preview(event(uid, sequence))
        result = self.apply(plan, content)[0]
        return result["schedule_name"]

    def assert_invalid_zero_write(self, plan, content, **kwargs):
        before = copy.deepcopy(self.env.store)
        with self.assertRaises(SafeError) as error:
            self.apply(plan, content, **kwargs)
        self.assertEqual(error.exception.code, "INVALID_INPUT")
        self.assertEqual(self.env.store, before)

    def test_preview_zero_business_writes_receipt_no_body_or_uid(self):
        before = copy.deepcopy(self.env.store)
        plan, content = self.preview(event("private-uid-canary", title="private-title-canary"))
        self.assertEqual(self.env.store, before)
        state = next(iter(self.env.cache.values()))
        self.assertNotIn("private-uid-canary", json.dumps(state))
        self.assertNotIn("private-title-canary", json.dumps(state))
        self.assertNotIn(content, json.dumps(state))
        self.assertEqual(state["plans"][0]["state"], {"mapping": {"exists": False}, "target": {"exists": False}})
        self.assertEqual(plan["expires_in"], 900)
        self.assertEqual(plan["items"][0]["expected_revision"], None)
        self.assertEqual(plan["items"][0]["allowed_resolutions"], [])

    def test_first_apply_and_duplicate_after_local_content_or_acl_edit_zero_write(self):
        plan, content = self.preview(event("A"))
        first = self.apply(plan, content)[0]
        self.assertEqual(first["result"], "create")
        self.env.local_edit(first["schedule_name"], title="local text", members=[{"user": "B", "access": "Edit"}])
        before = copy.deepcopy(self.env.store)
        retry = self.apply(plan, content)[0]
        self.assertEqual(retry["result"], "duplicate")
        self.assertEqual(retry["revision"], 2)
        self.assertEqual(self.env.store, before)

    def test_partial_failure_rolls_back_schedule_mapping_audit_then_same_receipt_retry(self):
        plan, content = self.preview(event("A"), event("B"))
        self.env.failure_uid = "B"
        first = self.apply(plan, content)
        self.assertEqual([item["result"] for item in first], ["create", "error"])
        self.assertEqual(first[1]["code"], "WRITE_FAILED")
        self.assertEqual(len(self.env.store["schedules"]), 1)
        self.assertEqual(len(self.env.store["mappings"]), 1)
        a = copy.deepcopy(self.env.store["schedules"][first[0]["schedule_name"]])
        a_mapping = copy.deepcopy(self.env.store["mappings"][(self.source, "A")])
        prior_a_audit = [row for row in self.env.store["audit"] if "B" not in row]
        self.env.failure_uid = None
        retry = self.apply(plan, content)
        self.assertEqual([item["result"] for item in retry], ["duplicate", "create"])
        self.assertEqual(len(self.env.store["schedules"]), 2)
        self.assertEqual(len(self.env.store["mappings"]), 2)
        self.assertEqual(self.env.store["schedules"][first[0]["schedule_name"]], a)
        self.assertEqual(self.env.store["mappings"][(self.source, "A")], a_mapping)
        self.assertEqual(self.env.store["audit"][:len(prior_a_audit)], prior_a_audit)

    def test_absent_preview_concurrent_higher_version_does_not_rebind_other_item_continues(self):
        old_plan, old_content = self.preview(event("A", 0), event("B"))
        new_plan, new_content = self.preview(event("A", 5))
        self.apply(new_plan, new_content)
        before = copy.deepcopy(self.env.store["mappings"][(self.source, "A")])
        result = self.apply(old_plan, old_content)
        self.assertEqual([row["result"] for row in result], ["revision_conflict", "create"])
        self.assertEqual(self.env.store["mappings"][(self.source, "A")], before)
        repreview, _ = self.preview(event("A", 0))
        self.assertEqual(repreview["items"][0]["action"], "stale")

    def test_existing_preview_concurrent_higher_version_is_revision_conflict(self):
        self.imported()
        old, old_file = self.preview(event("A", 1))
        high, high_file = self.preview(event("A", 2))
        self.apply(high, high_file)
        before = copy.deepcopy(self.env.store)
        self.assertEqual(self.apply(old, old_file)[0]["result"], "revision_conflict")
        self.assertEqual(self.env.store, before)

    def test_local_conflict_only_explicit_bound_resolution_overwrites_and_keeps_members(self):
        name = self.imported()
        members = [{"user": "B", "access": "Read", "occupies": True}]
        self.env.local_edit(name, title="local", members=members)
        plan, content = self.preview(event("A", 1, "source new"))
        item = plan["items"][0]
        self.assertEqual((item["action"], item["allowed_resolutions"], item["expected_revision"]), ("local_conflict", ["replace_from_source"], 2))
        before = copy.deepcopy(self.env.store)
        self.assertEqual(self.apply(plan, content)[0]["result"], "local_conflict")
        self.assertEqual(self.env.store, before)
        result = self.apply(plan, content, resolutions=[{"index": 0, "action": "replace_from_source", "expected_revision": 2}])[0]
        self.assertEqual(result["result"], "update")
        doc = self.env.store["schedules"][name]
        self.assertEqual((doc.title, doc.revision, doc.members), ("source new", 3, members))

    def test_old_legal_resolution_after_local_revision_change_cannot_rebind(self):
        name = self.imported()
        self.env.local_edit(name, title="first local")
        plan, content = self.preview(event("A", 1))
        self.env.local_edit(name, title="second local")
        before = copy.deepcopy(self.env.store)
        resolution = {"index": 0, "action": "replace_from_source", "expected_revision": 2}
        self.assertEqual(self.apply(plan, content, resolutions=[resolution])[0]["result"], "revision_conflict")
        self.assertEqual(self.env.store, before)
        self.assert_invalid_zero_write(plan, content, resolutions=[{**resolution, "expected_revision": 3}])

    def test_all_bad_resolutions_rejected_before_duplicate_or_any_safe_write(self):
        name = self.imported("A")
        self.imported("B")
        self.env.local_edit(name, title="local")
        plan, content = self.preview(event("A", 1), event("B"), event("C"))
        valid = {"index": 0, "action": "replace_from_source", "expected_revision": 2}
        invalids = [None, {}, "[]", [valid, valid], [{**valid, "index": -1}], [{**valid, "index": 99}],
                    [{**valid, "index": True}], [{**valid, "index": 0.0}], [{**valid, "index": "0"}],
                    [{**valid, "index": 1}], [{**valid, "index": 2}], [{**valid, "action": "force"}],
                    [{**valid, "expected_revision": True}], [{**valid, "expected_revision": 99}],
                    [{**valid, "extra": "private"}], [{"index": 0, "action": "replace_from_source"}], [None]]
        for resolutions in invalids:
            with self.subTest(resolutions=resolutions):
                if resolutions is None:
                    before = copy.deepcopy(self.env.store)
                    with self.assertRaises(SafeError):
                        self.service.apply(plan["receipt"], self.source, content, True, None)
                    self.assertEqual(self.env.store, before)
                else:
                    self.assert_invalid_zero_write(plan, content, resolutions=resolutions)
        for confirm in (False, 1, 0, "true", None):
            self.assert_invalid_zero_write(plan, content, confirm=confirm)

    def test_receipt_file_session_source_expiry_and_revocation_fail_closed(self):
        plan, content = self.preview(event("A"))
        changed = base64.b64encode(calendar(event("A", title="changed"))).decode()
        self.assert_invalid_zero_write(plan, changed)
        self.env.frappe.session.sid = "another-session"
        self.assert_invalid_zero_write(plan, content)
        self.env.frappe.session.sid = "session-a"
        other_source = self.service.create_source("Another")["source_id"]
        self.assert_invalid_zero_write(plan, content, source=other_source)
        self.env.disabled = True
        with self.assertRaises(SafeError) as error:
            self.apply(plan, content)
        self.assertEqual(error.exception.code, "FORBIDDEN")
        self.env.disabled = False
        state = self.env.cache[self.service.CACHE_PREFIX + plan["receipt"]]
        state["expires_at"] = 0
        self.assert_invalid_zero_write(plan, content)

    def test_duplicate_does_not_bypass_disabled_or_source_ownership(self):
        plan, content = self.preview(event("A"))
        self.apply(plan, content)
        before = copy.deepcopy(self.env.store)
        self.env.disabled = True
        with self.assertRaises(SafeError):
            self.apply(plan, content)
        self.env.disabled = False
        self.env.frappe.session.user = "owner-b"
        with self.assertRaises(SafeError) as error:
            self.apply(plan, content)
        self.assertEqual((error.exception.code, error.exception.status), ("NOT_FOUND", 404))
        self.assertEqual(self.env.store, before)

    def test_version_sequence_matrix(self):
        name = self.imported(sequence=2)
        for seq, title, expected in ((2, "Synthetic", "duplicate"), (1, "lower", "stale"), (2, "different", "version_conflict"), (3, "higher", "update")):
            plan, content = self.preview(event("A", seq, title))
            self.assertEqual(plan["items"][0]["action"], expected)
            result = self.apply(plan, content)[0]
            self.assertEqual(result["result"], expected)
        self.assertEqual(self.env.store["schedules"][name].revision, 2)

    def test_cancel_duplicate_tombstone_and_never_restore(self):
        name = self.imported()
        plan, content = self.preview(cancelled("A", 1))
        self.assertEqual(self.apply(plan, content)[0]["result"], "cancel")
        self.assertEqual(self.env.store["schedules"][name].status, "Cancelled")
        before = copy.deepcopy(self.env.store)
        self.assertEqual(self.apply(plan, content)[0]["result"], "duplicate")
        self.assertEqual(self.env.store, before)
        high, high_file = self.preview(event("A", 9))
        self.assertEqual(self.apply(high, high_file)[0]["result"], "cancelled_source")
        self.assertEqual(self.env.store, before)

    def test_unknown_cancel_mapping_only_and_concurrent_absent_tombstone(self):
        old, old_file = self.preview(cancelled("unknown", 1))
        high, high_file = self.preview(cancelled("unknown", 2))
        self.assertEqual(self.apply(high, high_file)[0]["result"], "unknown_cancelled")
        before = copy.deepcopy(self.env.store)
        self.assertEqual(self.apply(old, old_file)[0]["result"], "revision_conflict")
        self.assertEqual(self.env.store, before)
        self.assertFalse(self.env.store["schedules"])
        active, active_file = self.preview(event("unknown", 3))
        self.assertEqual(self.apply(active, active_file)[0]["result"], "cancelled_source")
        again, again_file = self.preview(cancelled("unknown", 3))
        self.assertEqual(self.apply(again, again_file)[0]["result"], "unknown_cancelled")
        self.assertFalse(self.env.store["schedules"])

    def test_different_sources_users_and_uid_case_are_isolated(self):
        first = self.imported("Same")
        second = self.imported("same")
        other_source = self.service.create_source("Other")["source_id"]
        plan, content = self.preview(event("Same"), source=other_source)
        third = self.apply(plan, content, source=other_source)[0]["schedule_name"]
        self.env.frappe.session.user = "owner-b"
        user_source = self.service.create_source("User B")["source_id"]
        plan, content = self.preview(event("Same"), source=user_source)
        fourth = self.apply(plan, content, source=user_source)[0]["schedule_name"]
        self.assertEqual(len({first, second, third, fourth}), 4)
        with self.assertRaises(SafeError) as error:
            self.preview(event("Same"), source=self.source)
        self.assertEqual(error.exception.code, "NOT_FOUND")

    def test_text_changed_by_normal_core_save_rolls_back_item_not_success(self):
        plan, content = self.preview(event("A", title="<script>private canary</script>"), event("B"))
        original = self.env.core.save_import_schedule

        def sanitizing_save(source, payload, name=None, revision=None):
            doc = original(source, payload, name, revision)
            if "<script>" in doc.title:
                doc["title"] = ""
                self.env.store["schedules"][doc.name]["title"] = ""
            return doc

        with patch.object(self.env.core, "save_import_schedule", side_effect=sanitizing_save):
            result = self.apply(plan, content)
        self.assertEqual([row["result"] for row in result], ["error", "create"])
        self.assertEqual(result[0]["code"], "UNSUPPORTED_TEXT")
        self.assertEqual(len(self.env.store["schedules"]), 1)
        self.assertNotIn((self.source, "A"), self.env.store["mappings"])
        self.assertNotIn("private", json.dumps(result))
        self.assertEqual(len(self.env.store["audit"]), 3)

    def test_unsupported_event_is_safe_and_other_items_continue(self):
        plan, content = self.preview(event("A"), event("B") + "URL:https://example.invalid/private\r\n", event("C"))
        result = self.apply(plan, content)
        self.assertEqual([row["result"] for row in result], ["create", "error", "create"])
        self.assertNotIn("private", json.dumps(result))
        self.assertEqual(len(self.env.store["schedules"]), 2)

from uuid import uuid4

import frappe

from team_schedule import service
from team_schedule.tests.test_model_service import ScheduleCase, payload


class TestModelTransactions(ScheduleCase):
    def test_revision_and_request_reads_ignore_old_snapshot(self):
        request_id = str(uuid4())
        doc = service.create_schedule(payload(), request_id)
        frappe.db.commit()
        primary = frappe.local.db
        frappe.connect()
        secondary = frappe.local.db
        try:
            secondary.sql("SELECT revision FROM `tabTeam Schedule` WHERE name=%s", (doc.name,))
            secondary.sql("SELECT name FROM `tabTeam Schedule Request` WHERE owner=%s AND request_id=%s", (self.users[0], request_id))
            frappe.local.db = primary
            service.mutate_schedule(doc.name, 1, {"title": "committed new revision"})
            primary.commit()
            frappe.local.db = secondary
            self.assert_code("REVISION_CONFLICT", service.mutate_schedule, doc.name, 1, {"title": "stale snapshot write"})
            current = service.create_schedule(payload(), request_id)
            self.assertEqual((current.name, current.revision, current.title), (doc.name, 2, "committed new revision"))
        finally:
            secondary.rollback()
            secondary.close()
            frappe.local.db = primary

    def test_request_lookup_ignores_preexisting_absent_snapshot(self):
        request_id = str(uuid4())
        frappe.db.commit()
        primary = frappe.local.db
        frappe.connect()
        secondary = frappe.local.db
        try:
            secondary.sql("SELECT name FROM `tabTeam Schedule Request` WHERE owner=%s AND request_id=%s", (self.users[0], request_id))
            frappe.local.db = primary
            doc = service.create_schedule(payload(), request_id)
            primary.commit()
            frappe.local.db = secondary
            retry = service.create_schedule(payload(), request_id)
            self.assertEqual(retry.name, doc.name)
            current_requests = secondary.sql("SELECT name FROM `tabTeam Schedule Request` WHERE owner=%s AND request_id=%s FOR UPDATE", (self.users[0], request_id))
            self.assertEqual(len(current_requests), 1)
        finally:
            secondary.rollback()
            secondary.close()
            frappe.local.db = primary

    def test_source_item_lookup_ignores_preexisting_absent_snapshot(self):
        source = service.create_source("synthetic transaction source")
        frappe.db.commit()
        primary = frappe.local.db
        frappe.connect()
        secondary = frappe.local.db
        try:
            secondary.sql("SELECT name FROM `tabTeam Schedule Source Item` WHERE source=%s", (source.name,))
            frappe.local.db = primary
            service.save_source_item(source.name, "synthetic-UID", {"source_sequence": 2, "source_digest": "b" * 64, "tombstone": True})
            primary.commit()
            frappe.local.db = secondary
            mapped = service.lock_source_item(source.name, "synthetic-UID")
            self.assertIsNotNone(mapped)
            self.assertEqual(mapped.source_sequence, 2)
        finally:
            secondary.rollback()
            secondary.close()
            frappe.local.db = primary

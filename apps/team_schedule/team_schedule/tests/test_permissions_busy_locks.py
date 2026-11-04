from contextlib import contextmanager

import frappe

from team_schedule import api, permissions, service
from team_schedule.tests.test_model_service import ScheduleCase


@api.parameters(identity_lock="shared")
def shared_probe():
    return {"ok": True}


@api.parameters()
def exclusive_probe():
    return {"ok": True}


class TestPermissionsBusyLocks(ScheduleCase):
    def prepare_grants(self):
        actor, peer = self.users
        service.set_busy_grant(peer, True)
        frappe.set_user(peer)
        service.set_busy_grant(actor, True)
        frappe.db.commit()
        frappe.set_user(actor)

    @contextmanager
    def second_connection(self):
        primary = frappe.local.db
        actor = frappe.session.user
        primary_timeout = primary.sql("SELECT @@SESSION.innodb_lock_wait_timeout")[0][0]
        primary.sql("SET SESSION innodb_lock_wait_timeout=1")
        frappe.connect(set_admin_as_user=False)
        secondary = frappe.local.db
        self.assertIsNot(primary, secondary)
        self.assertEqual(frappe.session.user, actor)
        secondary.sql("SET SESSION innodb_lock_wait_timeout=1")
        frappe.local.db = primary
        try:
            yield primary, secondary
        finally:
            secondary.rollback()
            secondary.close()
            frappe.local.db = primary
            primary.rollback()
            primary.sql("SET SESSION innodb_lock_wait_timeout=%s", (primary_timeout,))
            frappe.set_user(actor)

    def test_internal_modes_and_http_fields_cannot_change_lock_mode(self):
        self.prepare_grants()
        with self.assertRaises(ValueError):
            permissions.current_user(lock_mode="invalid")
        with self.assertRaises(ValueError):
            api.parameters(identity_lock="invalid")
        with self.assertRaises(ValueError):
            api.endpoint(lambda: None, identity_lock="invalid")
        for field in ("identity_lock", "lock_mode"):
            response = shared_probe(**{field: "exclusive"})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.get_json(), {"message": {"error": {"code": "INVALID_INPUT"}}})
            self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_confirm_rejects_invalid_internal_calls_with_only_forbidden(self):
        actor, peer = self.users
        for identity, subjects in ((peer, [actor, peer]), (actor, []), (actor, [peer]), (actor, [actor, None]), (actor, (actor,))):
            self.assert_code("FORBIDDEN", service.confirm_busy_access, identity, subjects)

    def test_reverse_subject_queries_share_actor_and_subject_locks(self):
        self.prepare_grants()
        actor, peer = self.users
        with self.second_connection() as (primary, secondary):
            self.assertEqual(shared_probe().status_code, 200)
            self.assertEqual(service.assert_busy_access([actor, peer]), actor)
            frappe.local.db = secondary
            frappe.set_user(peer)
            self.assertEqual(shared_probe().status_code, 200)
            self.assertEqual(service.assert_busy_access([peer, actor]), peer)
            self.assertIsNone(service.confirm_busy_access(peer, [peer, actor]))
            frappe.local.db = primary
            frappe.set_user(actor)
            self.assertIsNone(service.confirm_busy_access(actor, [actor, peer]))

    def test_default_endpoint_keeps_exclusive_identity_and_timeout_fails_closed(self):
        self.prepare_grants()
        with self.second_connection() as (primary, secondary):
            self.assertEqual(exclusive_probe().status_code, 200)
            frappe.local.db = secondary
            response = shared_probe()
            self.assertEqual(response.status_code, 500)
            self.assertEqual(response.get_json(), {"message": {"error": {"code": "INTERNAL_ERROR"}}})
            self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_confirm_current_reads_subject_identity_after_old_snapshot(self):
        self.prepare_grants()
        actor, peer = self.users
        for field, value in (("enabled", 0), ("user_type", "Website User")):
            with self.subTest(field=field):
                with self.second_connection() as (primary, secondary):
                    try:
                        self.assertEqual(service.assert_busy_access([actor, peer]), actor)
                        frappe.local.db = secondary
                        frappe.set_user("Administrator")
                        frappe.db.set_value("User", peer, field, value)
                        secondary.commit()
                        frappe.local.db = primary
                        frappe.set_user(actor)
                        self.assert_code("FORBIDDEN", service.confirm_busy_access, actor, [actor, peer])
                    finally:
                        primary.rollback()
                        frappe.local.db = secondary
                        frappe.set_user("Administrator")
                        frappe.db.set_value("User", peer, field, 1 if field == "enabled" else "System User")
                        secondary.commit()

    def test_confirm_current_reads_revoked_grant_after_old_snapshot(self):
        self.prepare_grants()
        actor, peer = self.users
        with self.second_connection() as (primary, secondary):
            self.assertEqual(service.assert_busy_access([actor, peer]), actor)
            frappe.local.db = secondary
            frappe.set_user(peer)
            service.set_busy_grant(actor, False)
            secondary.commit()
            frappe.local.db = primary
            frappe.set_user(actor)
            self.assert_code("FORBIDDEN", service.confirm_busy_access, actor, [actor, peer])

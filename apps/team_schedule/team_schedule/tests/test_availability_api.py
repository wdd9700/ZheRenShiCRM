"""Real-site checks for team_schedule.availability.api.query (D010300 §4, §7.3).

Requires a Frappe site::

    bench --site <isolated-site> run-tests --module team_schedule.tests.test_availability_api

M26 never executed this module: the worker environment has no Frappe install.
It is written for the M9 isolated run and must not be reported as passing
until that run exists.

Isolation: accounts are created per run and per test under a random namespace,
so repeated runs never collide and never reuse another run's identities.
Fixtures are committed so they survive direct bench calls and the endpoint's
error-path rollback. A successful call returns its Response without touching
the transaction: in a real HTTP request Framework commits after the Response
is built (sync_database), and only error paths roll back. Tests calling the
endpoint directly therefore do not reproduce HTTP transaction end by itself.
Nothing is deleted afterwards; no test cleans up users or schedules.

Accounts need a stored desk role: Framework `User.set_system_user()` calls
`has_desk_access()`, which is false without roles, and would silently demote
`user_type="System User"` to "Website User". "Desk User" is automatic, not
assignable, so the fixture uses the deployment's real ordinary role.
"""

import json
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from redis.exceptions import RedisError

from team_schedule import service
from team_schedule.availability import api
from team_schedule.timeutils import ScheduleError

START = "2026-11-04T09:00:00Z"
END = "2026-11-04T14:00:00Z"
WEEK = "2026-11-11T09:00:00Z"
TZ = "Asia/Shanghai"
RUN = uuid.uuid4().hex[:10]
CANARY = "m26-%s-canary" % RUN
ROLE = "Sales User"
FIXED_NOW = 4000000000.0


def keys_of(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key
            yield from keys_of(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from keys_of(nested)


class BusyFreeQueryTest(FrappeTestCase):
    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        self.namespace = "m26-%s-%s" % (RUN, self._testMethodName)
        self.accounts = {}

    def user(self, role):
        if role not in self.accounts:
            email = "%s-%s@m26.example.invalid" % (self.namespace, role)
            frappe.set_user("Administrator")
            self.assertEqual(
                frappe.db.get_value("Role", ROLE, "desk_access"), 1,
                "fixture role %r must exist with desk access" % ROLE,
            )
            frappe.get_doc({
                "doctype": "User",
                "email": email,
                "first_name": "%s-%s" % (RUN, role),
                "user_type": "System User",
                "enabled": 1,
                "send_welcome_email": 0,
                "roles": [{"role": ROLE}],
            }).insert()
            frappe.db.commit()
            stored = frappe.db.get_value("User", email, ["enabled", "user_type"], as_dict=True)
            self.assertEqual(stored.enabled, 1, "fixture user must stay enabled")
            self.assertEqual(stored.user_type, "System User", "fixture user must stay a system user")
            self.accounts[role] = email
        return self.accounts[role]

    def schedule(self, owner, start, end, availability="Busy", members=(), title=CANARY):
        frappe.set_user(owner)
        doc = service.create_schedule({
            "title": title,
            "description": CANARY + "-body",
            "start_utc": start,
            "end_utc": end,
            "source_timezone": "UTC",
            "availability": availability,
            "members": list(members),
        })
        frappe.db.commit()
        return doc

    def grant(self, subject, viewer, allow=True):
        frappe.set_user(subject)
        service.set_busy_grant(viewer, allow)
        frappe.db.commit()

    def participate(self, user, name, occupies=True):
        frappe.set_user(user)
        revision = frappe.get_doc("Team Schedule", name).revision
        service.set_participation(name, revision, occupies)
        frappe.db.commit()

    def ask(self, users, **overrides):
        params = {
            "users": users,
            "start_utc": START,
            "end_utc": END,
            "min_minutes": 20,
            "display_timezone": TZ,
        }
        params.update(overrides)
        response = api.query(**params)
        return response, json.loads(response.get_data())

    def test_contract_window_yields_the_frozen_answer(self):
        alice, bob = self.user("alice"), self.user("bob")
        self.schedule(alice, "2026-11-04T09:07:00Z", "2026-11-04T09:42:00Z")
        self.schedule(alice, "2026-11-04T13:03:00Z", "2026-11-04T13:18:00Z")
        self.schedule(bob, "2026-11-04T09:30:00Z", "2026-11-04T10:05:00Z")
        self.schedule(bob, "2026-11-04T13:18:00Z", "2026-11-04T13:31:00Z")
        self.grant(bob, alice)
        frappe.set_user(alice)

        response, body = self.ask([alice, bob])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["message"]["busy"], [
            {"user": alice, "intervals": [
                {"start_utc": "2026-11-04T09:07:00Z", "end_utc": "2026-11-04T09:42:00Z"},
                {"start_utc": "2026-11-04T13:03:00Z", "end_utc": "2026-11-04T13:18:00Z"},
            ]},
            {"user": bob, "intervals": [
                {"start_utc": "2026-11-04T09:30:00Z", "end_utc": "2026-11-04T10:05:00Z"},
                {"start_utc": "2026-11-04T13:18:00Z", "end_utc": "2026-11-04T13:31:00Z"},
            ]},
        ])
        self.assertEqual(body["message"]["common_free"], [
            {"start_utc": "2026-11-04T10:05:00Z", "end_utc": "2026-11-04T13:03:00Z"},
            {"start_utc": "2026-11-04T13:31:00Z", "end_utc": "2026-11-04T14:00:00Z"},
        ])
        self.assertEqual(body["message"]["display_timezone"], TZ)

    def test_free_and_cancelled_schedules_do_not_occupy(self):
        alice = self.user("alice")
        busy = self.schedule(alice, "2026-11-04T10:00:00Z", "2026-11-04T11:00:00Z")
        self.schedule(alice, "2026-11-04T12:00:00Z", "2026-11-04T13:00:00Z", availability="Free")
        frappe.set_user(alice)
        response, body = self.ask([alice], min_minutes=1)
        self.assertEqual(response.status_code, 200, body)
        self.assertEqual(body["message"]["busy"][0]["intervals"], [
            {"start_utc": "2026-11-04T10:00:00Z", "end_utc": "2026-11-04T11:00:00Z"},
        ])
        self.assertEqual(body["message"]["common_free"], [
            {"start_utc": START, "end_utc": "2026-11-04T10:00:00Z"},
            {"start_utc": "2026-11-04T11:00:00Z", "end_utc": END},
        ])

        frappe.set_user(alice)
        service.cancel(busy.name, frappe.get_doc("Team Schedule", busy.name).revision)
        frappe.db.commit()
        response, body = self.ask([alice], min_minutes=1)
        self.assertEqual(response.status_code, 200, body)
        self.assertEqual(body["message"]["busy"][0]["intervals"], [])
        self.assertEqual(body["message"]["common_free"], [{"start_utc": START, "end_utc": END}])

    def test_member_occupies_only_after_accepting(self):
        alice, bob = self.user("alice"), self.user("bob")
        doc = self.schedule(
            alice,
            "2026-11-04T10:00:00Z",
            "2026-11-04T11:00:00Z",
            members=[{"user": bob, "access": "Read"}],
        )
        frappe.set_user(bob)
        _, body = self.ask([bob])
        self.assertEqual(body["message"]["busy"][0]["intervals"], [])

        self.participate(bob, doc.name, True)
        _, body = self.ask([bob])
        self.assertEqual(body["message"]["busy"][0]["intervals"], [
            {"start_utc": "2026-11-04T10:00:00Z", "end_utc": "2026-11-04T11:00:00Z"},
        ])

        self.participate(bob, doc.name, False)
        _, body = self.ask([bob])
        self.assertEqual(body["message"]["busy"][0]["intervals"], [])

    def test_unreadable_people_are_refused_uniformly(self):
        alice, bob = self.user("alice"), self.user("bob")
        frappe.set_user(alice)
        response, body = self.ask([alice, bob])
        self.assertEqual(response.status_code, 403)
        self.assertEqual(body["message"]["error"]["code"], "FORBIDDEN")

        response, body = self.ask([alice, "m26-%s-absent@m26.example.invalid" % RUN])
        self.assertEqual(response.status_code, 403)
        self.assertEqual(body, {"message": {"error": {"code": "FORBIDDEN"}}})

    def test_revoked_grant_is_refused_on_the_next_request(self):
        alice, bob = self.user("alice"), self.user("bob")
        self.grant(bob, alice)
        frappe.set_user(alice)
        self.assertEqual(self.ask([alice, bob])[0].status_code, 200)

        self.grant(bob, alice, allow=False)
        frappe.set_user(alice)
        self.assertEqual(self.ask([alice, bob])[0].status_code, 403)

    def test_revocation_during_the_scan_denies_through_the_post_check(self):
        alice, bob = self.user("alice"), self.user("bob")
        frappe.set_user(alice)
        with patch.object(api.service, "assert_busy_access", return_value=alice):
            response, body = self.ask([alice, bob])
        self.assertEqual(response.status_code, 403)
        self.assertEqual(body["message"]["error"]["code"], "FORBIDDEN")

        self.grant(bob, alice)
        frappe.set_user(alice)
        with patch.object(api.service, "assert_busy_access", return_value=alice):
            self.assertEqual(self.ask([alice, bob])[0].status_code, 200)

    def in_new_connection(self, user, action):
        """Run ``action`` on a real second Frappe connection as ``user``."""
        site, sites_path = frappe.local.site, frappe.local.sites_path
        outcome = {}

        def worker():
            try:
                frappe.init(site=site, sites_path=sites_path)
                frappe.connect()
                frappe.set_user(user)
                outcome["value"] = action()
            except Exception as error:
                outcome["error"] = "%s: %s" % (type(error).__name__, error)
            finally:
                if getattr(frappe.local, "db", None):
                    frappe.db.rollback()
                frappe.destroy()

        thread = threading.Thread(target=worker, name="m26-second-connection", daemon=True)
        thread.start()
        return thread, outcome

    def finish(self, thread, outcome, timeout=60):
        thread.join(timeout=timeout)
        self.assertFalse(thread.is_alive(), "second connection did not finish")
        self.assertNotIn("error", outcome, outcome)
        return outcome.get("value")

    def revoke_on_new_connection(self, subject, viewer):
        """Revoke through the standard service on a real second connection."""
        def revoke():
            service.set_busy_grant(viewer, False)
            frappe.db.commit()
            return not frappe.db.exists(
                "Team Schedule Busy Grant", {"subject_user": subject, "viewer_user": viewer})

        self.assertTrue(self.finish(*self.in_new_connection(subject, revoke)))

    def stop_at_post_check(self, hook):
        """Pause the running request at its post-scan authorization boundary."""
        code = api._still_granted.__code__

        def pause(frame, event, arg):
            if event == "call" and frame.f_code is code:
                hook()
            return pause

        return pause

    def test_revocation_committed_mid_request_is_seen_by_the_post_check(self):
        """M9 two-connection failure: the post-check must not read the old snapshot."""
        alice, bob = self.user("alice"), self.user("bob")
        self.grant(bob, alice)
        frappe.set_user(alice)
        service.assert_busy_access([alice, bob])
        self.assertTrue(
            frappe.db.exists("Team Schedule Busy Grant", {"subject_user": bob, "viewer_user": alice}),
            "snapshot must be opened while the grant still exists",
        )

        self.revoke_on_new_connection(bob, alice)

        with self.assertRaises(ScheduleError) as caught:
            api._still_granted(alice, [alice, bob])
        self.assertEqual(caught.exception.status, 403)
        self.assertEqual(caught.exception.code, "FORBIDDEN")

    def assert_denied_after_admin_change(self, field, value):
        """Commit a User change from an admin connection between the scan and the check."""
        alice, bob = self.user("alice"), self.user("bob")
        self.grant(bob, alice)
        frappe.set_user(alice)
        reached, changed = threading.Event(), threading.Event()
        site, sites_path = frappe.local.site, frappe.local.sites_path
        outcome = {}

        def admin():
            try:
                frappe.init(site=site, sites_path=sites_path)
                frappe.connect()
                frappe.set_user("Administrator")
                if not reached.wait(30):
                    raise AssertionError("request never reached the post-scan check")
                frappe.db.set_value("User", bob, field, value)
                frappe.db.commit()
                outcome["value"] = frappe.db.get_value("User", bob, field)
            except Exception as error:
                outcome["error"] = "%s: %s" % (type(error).__name__, error)
            finally:
                if getattr(frappe.local, "db", None):
                    frappe.db.rollback()
                frappe.destroy()
                changed.set()

        thread = threading.Thread(target=admin, name="m26-admin", daemon=True)
        thread.start()
        try:
            sys.settrace(self.stop_at_post_check(lambda: (reached.set(), changed.wait(30))))
            response, body = self.ask([alice, bob])
        finally:
            sys.settrace(None)
            thread.join(timeout=60)

        self.assertFalse(thread.is_alive(), "admin connection did not finish")
        self.assertNotIn("error", outcome, outcome)
        self.assertEqual(outcome.get("value"), value)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(body, {"message": {"error": {"code": "FORBIDDEN"}}})
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertNotIn("busy", body["message"])

    def test_disabled_subject_committed_mid_request_is_rejected(self):
        self.assert_denied_after_admin_change("enabled", 0)

    def test_type_invalid_subject_committed_mid_request_is_rejected(self):
        self.assert_denied_after_admin_change("user_type", "Website User")

    def query_on_new_connection(self, user, users, barrier):
        """Run the real endpoint on a real second connection, pausing at the post-check."""
        site, sites_path = frappe.local.site, frappe.local.sites_path
        outcome = {}

        def worker():
            try:
                frappe.init(site=site, sites_path=sites_path)
                frappe.connect()
                frappe.set_user(user)

                def pause(frame, event, arg):
                    if event == "call" and frame.f_code is api._still_granted.__code__:
                        barrier.wait()
                    return pause

                sys.settrace(pause)
                try:
                    response = api.query(users=users, start_utc=START, end_utc=END,
                                         min_minutes=20, display_timezone=TZ)
                    outcome["status"] = response.status_code
                    outcome["body"] = json.loads(response.get_data())
                    outcome["no_store"] = response.headers.get("Cache-Control")
                finally:
                    sys.settrace(None)
            except Exception as error:
                outcome["error"] = "%s: %s" % (type(error).__name__, error)
            finally:
                if getattr(frappe.local, "db", None):
                    frappe.db.rollback()
                frappe.destroy()

        thread = threading.Thread(target=worker, name="m26-concurrent-query", daemon=True)
        thread.start()
        return thread, outcome

    def test_opposite_viewers_query_concurrently_without_deadlock(self):
        alice, bob = self.user("alice"), self.user("bob")
        self.grant(bob, alice)
        self.grant(alice, bob)
        barrier = threading.Barrier(2, timeout=30)
        attempts = [
            self.query_on_new_connection(alice, [alice, bob], barrier),
            self.query_on_new_connection(bob, [bob, alice], barrier),
        ]
        for thread, outcome in attempts:
            thread.join(timeout=60)
            self.assertFalse(thread.is_alive(), "concurrent query did not finish")
            self.assertNotIn("error", outcome, outcome)
            self.assertEqual(outcome.get("status"), 200, outcome)
            self.assertEqual(outcome.get("no_store"), "no-store")

    def test_response_carries_no_schedule_content(self):
        alice, bob = self.user("alice"), self.user("bob")
        doc = self.schedule(alice, "2026-11-04T10:00:00Z", "2026-11-04T11:00:00Z")
        self.grant(alice, bob)
        frappe.set_user(bob)
        response, body = self.ask([bob, alice])

        raw = response.get_data(as_text=True)
        self.assertNotIn(CANARY, raw)
        self.assertNotIn(doc.name, raw)
        self.assertEqual(set(keys_of(body["message"])), {
            "busy", "user", "intervals", "start_utc", "end_utc", "common_free", "display_timezone",
        })

    def test_window_minutes_and_timezone_bounds(self):
        alice = self.user("alice")
        frappe.set_user(alice)
        self.assertEqual(self.ask([alice], end_utc=WEEK)[0].status_code, 200)
        for overrides in (
            {"end_utc": "2026-11-11T09:01:00Z"},
            {"min_minutes": 0},
            {"min_minutes": 10081},
            {"min_minutes": True},
            {"min_minutes": "20"},
            {"min_minutes": 20.0},
            {"display_timezone": "Mars/Olympus"},
            {"display_timezone": None},
        ):
            response, body = self.ask([alice], **overrides)
            self.assertEqual(response.status_code, 400, overrides)
            self.assertEqual(body["message"]["error"]["code"], "INVALID_INPUT", overrides)

    def test_people_list_bounds_and_deduplication(self):
        alice, bob = self.user("alice"), self.user("bob")
        self.grant(bob, alice)
        frappe.set_user(alice)
        for users in (
            [],
            [bob],
            [alice] + ["m26-%s-u%d@m26.example.invalid" % (RUN, index) for index in range(10)],
            alice,
        ):
            response, body = self.ask(users)
            self.assertEqual(response.status_code, 400, users)
            self.assertEqual(body["message"]["error"]["code"], "INVALID_INPUT", users)

        _, body = self.ask([alice, alice, bob])
        self.assertEqual([entry["user"] for entry in body["message"]["busy"]], [alice, bob])

    def test_unknown_parameter_is_refused(self):
        alice = self.user("alice")
        frappe.set_user(alice)
        response = api.query(users=[alice], start_utc=START, end_utc=END, min_minutes=20,
                             display_timezone=TZ, limit=10)
        self.assertEqual(response.status_code, 400)

    def test_success_and_error_responses_are_no_store(self):
        alice = self.user("alice")
        frappe.set_user(alice)
        self.assertEqual(self.ask([alice])[0].headers["Cache-Control"], "no-store")
        self.assertEqual(self.ask([alice], min_minutes=0)[0].headers["Cache-Control"], "no-store")

    def fixed_clock(self, now):
        return patch.object(api, "_now", return_value=now)

    def test_thirty_requests_per_minute_then_429(self):
        alice = self.user("alice")
        frappe.set_user(alice)
        with self.fixed_clock(FIXED_NOW):
            for _ in range(api.RATE_LIMIT):
                self.assertEqual(self.ask([alice])[0].status_code, 200)
            response, body = self.ask([alice])
        self.assertEqual(response.status_code, 429)
        self.assertEqual(body["message"]["error"]["code"], "RATE_LIMITED")

    def test_another_identity_does_not_inherit_the_exhausted_budget(self):
        alice, bob = self.user("alice"), self.user("bob")
        with self.fixed_clock(FIXED_NOW):
            frappe.set_user(alice)
            for _ in range(api.RATE_LIMIT + 1):
                self.ask([alice])
            self.assertEqual(self.ask([alice])[0].status_code, 429)

            frappe.set_user(bob)
            self.assertEqual(self.ask([bob])[0].status_code, 200)

    def test_bucket_boundary_closes_the_old_budget(self):
        alice = self.user("alice")
        frappe.set_user(alice)
        bucket = int(FIXED_NOW // api.RATE_WINDOW_SECONDS)
        last_moment = bucket * api.RATE_WINDOW_SECONDS + api.RATE_WINDOW_SECONDS - 0.001
        next_moment = (bucket + 1) * api.RATE_WINDOW_SECONDS
        self.assertNotEqual(
            api._rate_raw_key(api._session_digest(), last_moment),
            api._rate_raw_key(api._session_digest(), next_moment),
        )
        with self.fixed_clock(last_moment):
            for _ in range(api.RATE_LIMIT):
                self.assertEqual(self.ask([alice])[0].status_code, 200)
            self.assertEqual(self.ask([alice])[0].status_code, 429)
        with self.fixed_clock(next_moment):
            self.assertEqual(self.ask([alice])[0].status_code, 200)

    def test_counter_key_expires(self):
        alice = self.user("alice")
        frappe.set_user(alice)
        with self.fixed_clock(FIXED_NOW):
            self.assertEqual(self.ask([alice])[0].status_code, 200)
        key = frappe.cache.make_key(api._rate_raw_key(api._session_digest(), FIXED_NOW))
        ttl = frappe.cache.ttl(key)
        self.assertGreater(ttl, 0)
        self.assertLessEqual(ttl, api.RATE_WINDOW_SECONDS * 2)

    def test_counter_is_atomic_under_parallel_calls(self):
        alice = self.user("alice")
        frappe.set_user(alice)
        key = frappe.cache.make_key(api._rate_raw_key(api._session_digest(), FIXED_NOW))

        with ThreadPoolExecutor(max_workers=8) as pool:
            counts = sorted(pool.map(lambda _: api._bump(key), range(40)))

        self.assertEqual(counts, list(range(1, 41)))

    def test_cache_outage_denies_instead_of_waiving_the_limit(self):
        alice = self.user("alice")
        frappe.set_user(alice)
        with patch.object(frappe.cache, "pipeline", side_effect=RedisError("cache down")):
            response, body = self.ask([alice])
        self.assertEqual(response.status_code, 429)
        self.assertEqual(body["message"]["error"]["code"], "RATE_LIMITED")

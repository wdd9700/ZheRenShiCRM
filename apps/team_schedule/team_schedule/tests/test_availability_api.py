"""Real-site checks for team_schedule.availability.api.query (D010300 §4, §7.3).

Requires a Frappe site::

    bench --site <isolated-site> run-tests --module team_schedule.tests.test_availability_api

M26 never executed this module: the worker environment has no Frappe install.
It is written for the M9 isolated run and must not be reported as passing
until that run exists.
"""

import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from redis.exceptions import RedisError

from team_schedule import service
from team_schedule.availability import api

START = "2026-11-04T09:00:00Z"
END = "2026-11-04T14:00:00Z"
WEEK = "2026-11-11T09:00:00Z"
TZ = "Asia/Shanghai"
CANARY = "m26-canary-private-title"


def make_user(local):
    email = "%s@m26.example.invalid" % local
    if not frappe.db.exists("User", email):
        frappe.get_doc({
            "doctype": "User",
            "email": email,
            "first_name": local,
            "user_type": "System User",
            "enabled": 1,
            "send_welcome_email": 0,
        }).insert()
    return email


def keys_of(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key
            yield from keys_of(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from keys_of(nested)


class BusyFreeQueryTest(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.alice = make_user("m26-alice")
        cls.bob = make_user("m26-bob")
        cls.carol = make_user("m26-carol")
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        for user in (cls.alice, cls.bob, cls.carol):
            names = frappe.get_all("Team Schedule", filters={"owner": user}, pluck="name")
            if names:
                frappe.db.delete("Team Schedule Member", {"parent": ["in", names]})
                frappe.db.delete("Team Schedule", {"name": ["in", names]})
            frappe.db.delete("Team Schedule Request", {"owner": user})
            frappe.db.delete("Team Schedule Busy Grant", {"subject_user": user})
            frappe.db.delete("Team Schedule Busy Grant", {"viewer_user": user})
        frappe.db.commit()
        for user in (cls.alice, cls.bob, cls.carol):
            if frappe.db.exists("User", user):
                frappe.delete_doc("User", user, force=True)
        frappe.db.commit()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        for user in (self.alice, self.bob, self.carol):
            frappe.set_user(user)
            frappe.cache.delete_value(api._rate_raw_key(api._session_digest()))
        frappe.set_user("Administrator")

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
        self.schedule(self.alice, "2026-11-04T09:07:00Z", "2026-11-04T09:42:00Z")
        self.schedule(self.alice, "2026-11-04T13:03:00Z", "2026-11-04T13:18:00Z")
        self.schedule(self.bob, "2026-11-04T09:30:00Z", "2026-11-04T10:05:00Z")
        self.schedule(self.bob, "2026-11-04T13:18:00Z", "2026-11-04T13:31:00Z")
        self.grant(self.bob, self.alice)
        frappe.set_user(self.alice)

        response, body = self.ask([self.alice, self.bob])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["message"]["busy"], [
            {"user": self.alice, "intervals": [
                {"start_utc": "2026-11-04T09:07:00Z", "end_utc": "2026-11-04T09:42:00Z"},
                {"start_utc": "2026-11-04T13:03:00Z", "end_utc": "2026-11-04T13:18:00Z"},
            ]},
            {"user": self.bob, "intervals": [
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
        busy = self.schedule(self.alice, "2026-11-04T10:00:00Z", "2026-11-04T11:00:00Z")
        self.schedule(self.alice, "2026-11-04T12:00:00Z", "2026-11-04T13:00:00Z", availability="Free")
        frappe.set_user(self.alice)
        _, body = self.ask([self.alice], min_minutes=1)
        self.assertEqual(body["message"]["busy"][0]["intervals"], [
            {"start_utc": "2026-11-04T10:00:00Z", "end_utc": "2026-11-04T11:00:00Z"},
        ])
        self.assertEqual(body["message"]["common_free"], [
            {"start_utc": START, "end_utc": "2026-11-04T10:00:00Z"},
            {"start_utc": "2026-11-04T11:00:00Z", "end_utc": END},
        ])

        frappe.set_user(self.alice)
        service.cancel(busy.name, frappe.get_doc("Team Schedule", busy.name).revision)
        frappe.db.commit()
        _, body = self.ask([self.alice], min_minutes=1)
        self.assertEqual(body["message"]["busy"][0]["intervals"], [])
        self.assertEqual(body["message"]["common_free"], [{"start_utc": START, "end_utc": END}])

    def test_member_occupies_only_after_accepting(self):
        doc = self.schedule(
            self.alice,
            "2026-11-04T10:00:00Z",
            "2026-11-04T11:00:00Z",
            members=[{"user": self.bob, "access": "Read"}],
        )
        frappe.set_user(self.bob)
        _, body = self.ask([self.bob])
        self.assertEqual(body["message"]["busy"][0]["intervals"], [])

        self.participate(self.bob, doc.name, True)
        _, body = self.ask([self.bob])
        self.assertEqual(body["message"]["busy"][0]["intervals"], [
            {"start_utc": "2026-11-04T10:00:00Z", "end_utc": "2026-11-04T11:00:00Z"},
        ])

        self.participate(self.bob, doc.name, False)
        _, body = self.ask([self.bob])
        self.assertEqual(body["message"]["busy"][0]["intervals"], [])

    def test_unreadable_people_are_refused_uniformly(self):
        frappe.set_user(self.alice)
        response, body = self.ask([self.alice, self.bob])
        self.assertEqual(response.status_code, 403)
        self.assertEqual(body["message"]["error"]["code"], "FORBIDDEN")

        response, body = self.ask([self.alice, "m26-absent@m26.example.invalid"])
        self.assertEqual(response.status_code, 403)
        self.assertEqual(body, {"message": {"error": {"code": "FORBIDDEN"}}})

    def test_revoked_grant_is_refused_on_the_next_request(self):
        self.grant(self.bob, self.alice)
        frappe.set_user(self.alice)
        self.assertEqual(self.ask([self.alice, self.bob])[0].status_code, 200)

        self.grant(self.bob, self.alice, allow=False)
        frappe.set_user(self.alice)
        self.assertEqual(self.ask([self.alice, self.bob])[0].status_code, 403)

    def test_revocation_during_the_scan_denies_through_the_post_check(self):
        frappe.set_user(self.alice)
        with patch.object(api.service, "assert_busy_access", return_value=self.alice):
            response, body = self.ask([self.alice, self.bob])
        self.assertEqual(response.status_code, 403)
        self.assertEqual(body["message"]["error"]["code"], "FORBIDDEN")

        self.grant(self.bob, self.alice)
        frappe.set_user(self.alice)
        with patch.object(api.service, "assert_busy_access", return_value=self.alice):
            self.assertEqual(self.ask([self.alice, self.bob])[0].status_code, 200)

    def test_response_carries_no_schedule_content(self):
        doc = self.schedule(self.alice, "2026-11-04T10:00:00Z", "2026-11-04T11:00:00Z")
        self.grant(self.alice, self.bob)
        frappe.set_user(self.bob)
        response, body = self.ask([self.bob, self.alice])

        raw = response.get_data(as_text=True)
        self.assertNotIn(CANARY, raw)
        self.assertNotIn(doc.name, raw)
        self.assertEqual(set(keys_of(body["message"])), {
            "busy", "user", "intervals", "start_utc", "end_utc", "common_free", "display_timezone",
        })

    def test_window_minutes_and_timezone_bounds(self):
        frappe.set_user(self.alice)
        self.assertEqual(self.ask([self.alice], end_utc=WEEK)[0].status_code, 200)
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
            response, body = self.ask([self.alice], **overrides)
            self.assertEqual(response.status_code, 400, overrides)
            self.assertEqual(body["message"]["error"]["code"], "INVALID_INPUT", overrides)

    def test_people_list_bounds_and_deduplication(self):
        self.grant(self.bob, self.alice)
        frappe.set_user(self.alice)
        for users in (
            [],
            [self.bob],
            [self.alice] + ["m26-u%d@m26.example.invalid" % index for index in range(10)],
            self.alice,
        ):
            response, body = self.ask(users)
            self.assertEqual(response.status_code, 400, users)
            self.assertEqual(body["message"]["error"]["code"], "INVALID_INPUT", users)

        _, body = self.ask([self.alice, self.alice, self.bob])
        self.assertEqual([entry["user"] for entry in body["message"]["busy"]], [self.alice, self.bob])

    def test_unknown_parameter_is_refused(self):
        frappe.set_user(self.alice)
        response = api.query(users=[self.alice], start_utc=START, end_utc=END, min_minutes=20,
                             display_timezone=TZ, limit=10)
        self.assertEqual(response.status_code, 400)

    def test_success_and_error_responses_are_no_store(self):
        frappe.set_user(self.alice)
        self.assertEqual(self.ask([self.alice])[0].headers["Cache-Control"], "no-store")
        self.assertEqual(self.ask([self.alice], min_minutes=0)[0].headers["Cache-Control"], "no-store")

    def test_thirty_requests_per_minute_then_429(self):
        frappe.set_user(self.alice)
        for _ in range(api.RATE_LIMIT):
            self.assertEqual(self.ask([self.alice])[0].status_code, 200)
        response, body = self.ask([self.alice])
        self.assertEqual(response.status_code, 429)
        self.assertEqual(body["message"]["error"]["code"], "RATE_LIMITED")

    def test_another_identity_does_not_inherit_the_exhausted_budget(self):
        frappe.set_user(self.alice)
        for _ in range(api.RATE_LIMIT + 1):
            self.ask([self.alice])
        self.assertEqual(self.ask([self.alice])[0].status_code, 429)

        frappe.set_user(self.bob)
        self.assertEqual(self.ask([self.bob])[0].status_code, 200)

    def test_counter_is_atomic_under_parallel_calls(self):
        now = 4000000000
        raw = api._rate_raw_key(api._session_digest(), now)
        frappe.cache.delete_value(raw)
        key = frappe.cache.make_key(raw)

        with ThreadPoolExecutor(max_workers=8) as pool:
            counts = sorted(pool.map(lambda _: api._bump(key), range(40)))

        self.assertEqual(counts, list(range(1, 41)))

    def test_cache_outage_denies_instead_of_waiving_the_limit(self):
        frappe.set_user(self.alice)
        with patch.object(frappe.cache, "pipeline", side_effect=RedisError("cache down")):
            response, body = self.ask([self.alice])
        self.assertEqual(response.status_code, 429)
        self.assertEqual(body["message"]["error"]["code"], "RATE_LIMITED")

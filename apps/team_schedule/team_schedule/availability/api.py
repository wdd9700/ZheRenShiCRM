"""Frozen busy/common-free entry point: team_schedule.availability.api.query.

D010300 §4. Reuses the backend core (timeutils validation, permissions
session identity, service.assert_busy_access, api.parameters) so error codes,
POST-only whitelisting and ``Cache-Control: no-store`` stay in one place.
The session identity is taken with a shared lock (``identity_lock="shared"``)
and the final authorization is delegated to ``service.confirm_busy_access``,
so concurrent queries never hold each other's actor rows exclusively.
429 RATE_LIMITED is the tower-approved extension of the frozen code table.
"""

import hashlib
import time

import frappe
from redis.exceptions import RedisError

from team_schedule import service, timeutils
from team_schedule.api import parameters
from team_schedule.availability import core, scanner
from team_schedule.timeutils import ScheduleError

RATE_LIMIT = 30
RATE_WINDOW_SECONDS = 60


def _session_digest():
    """Opaque per-session handle; the session id itself never reaches a key or output."""
    sid = getattr(frappe.session, "sid", None) or "user:" + frappe.session.user
    return hashlib.sha256(sid.encode("utf-8")).hexdigest()


def _now():
    return time.time()


def _rate_raw_key(digest, now=None):
    bucket = int((_now() if now is None else now) // RATE_WINDOW_SECONDS)
    return "team_schedule:availability:rate:%s:%s" % (digest, bucket)


def _bump(key):
    """Atomic INCR+EXPIRE in one transaction; a cache outage denies rather than waives."""
    try:
        pipe = frappe.cache.pipeline()
        pipe.incr(key)
        pipe.expire(key, RATE_WINDOW_SECONDS * 2)
        return int(pipe.execute()[0])
    except RedisError:
        raise ScheduleError("RATE_LIMITED", 429)


def _throttle(digest, now=None):
    if _bump(frappe.cache.make_key(_rate_raw_key(digest, now))) > RATE_LIMIT:
        raise ScheduleError("RATE_LIMITED", 429)


def _still_granted(actor, users):
    """Post-scan authorization boundary, after the scan and before the answer.

    Delegates to the backend's full current-read check: every participant's
    User row (enabled, user_type) and every directed grant are re-read with
    LOCK IN SHARE MODE, so a disablement, type change or revocation committed
    after the scan is seen and the request fails closed. Kept as a named step
    because it is this request's authorization linearization point.
    """
    service.confirm_busy_access(actor, users)


def _encode(interval):
    start, end = interval
    return {"start_utc": timeutils.encode_utc(start), "end_utc": timeutils.encode_utc(end)}


@parameters("users", "start_utc", "end_utc", "min_minutes", "display_timezone", identity_lock="shared")
def query(users, start_utc, end_utc, min_minutes=20, display_timezone=None):
    if not isinstance(users, list) or any(not isinstance(user, str) for user in users):
        timeutils.invalid()
    unique = list(dict.fromkeys(users))
    if not 1 <= len(unique) <= core.MAX_PEOPLE:
        timeutils.invalid()
    start, end = timeutils.validate_window(start_utc, end_utc, core.WINDOW_DAYS)
    if type(min_minutes) is not int or not core.MIN_MINUTES_FLOOR <= min_minutes <= core.MIN_MINUTES_CEILING:
        timeutils.invalid()
    timeutils.validate_timezone(display_timezone)

    _throttle(_session_digest())
    actor = service.assert_busy_access(unique)

    rows = frappe.db.sql(scanner.statement(unique), scanner.parameters(unique, start_utc, end_utc), as_dict=True)
    _still_granted(actor, unique)
    try:
        core.guard_scan(rows)
    except core.ScanLimitExceeded:
        raise ScheduleError("LIMIT_EXCEEDED", 413)

    occupied = [
        {"user": row.user, "start_utc": timeutils.parse_utc(row.start_utc), "end_utc": timeutils.parse_utc(row.end_utc)}
        for row in rows
    ]
    busy = core.busy_by_user(unique, occupied, start, end)
    free = core.common_free([pieces for _, pieces in busy], start, end, min_minutes)
    return {
        "busy": [{"user": user, "intervals": [_encode(piece) for piece in pieces]} for user, pieces in busy],
        "common_free": [_encode(piece) for piece in free],
        "display_timezone": display_timezone,
    }

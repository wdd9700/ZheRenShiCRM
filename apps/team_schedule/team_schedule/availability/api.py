"""Frozen busy/common-free entry point: team_schedule.availability.api.query.

D010300 §4. Reuses the backend core (timeutils validation, permissions
session identity, service.assert_busy_access, api.parameters) so error codes,
POST-only whitelisting and ``Cache-Control: no-store`` stay in one place.
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


def _rate_raw_key(digest, now=None):
    bucket = int((time.time() if now is None else now) // RATE_WINDOW_SECONDS)
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
    """Authoritative grant check after the occupancy scan.

    A plain SELECT reuses this transaction's REPEATABLE READ read view, which
    was opened by the first consistent read at request start, so it cannot see
    a revocation committed meanwhile (proved with two real connections).
    LOCK IN SHARE MODE is a current read: it returns the latest committed rows
    regardless of the snapshot, and holds the shared lock until this request
    commits, which happens after the response is built. A concurrent revoke
    therefore either commits before this check (row gone -> 403) or waits for
    this request to finish (row present -> the answer stays authorized).

    Lock order is the actor's User row, already held by current_user(), then
    grant rows - the same order service.set_busy_grant takes - so no lock cycle
    is introduced; shared locks do not conflict with concurrent queries.
    """
    others = [user for user in users if user != actor]
    if not others:
        return
    placeholders = ", ".join(["%s"] * len(others))
    granted = {
        row[0]
        for row in frappe.db.sql(
            "SELECT subject_user FROM `tabTeam Schedule Busy Grant` "
            "WHERE viewer_user=%s AND subject_user IN (" + placeholders + ") "
            "LOCK IN SHARE MODE",
            tuple([actor] + others),
        )
    }
    if granted != set(others):
        raise ScheduleError("FORBIDDEN", 403)


def _encode(interval):
    start, end = interval
    return {"start_utc": timeutils.encode_utc(start), "end_utc": timeutils.encode_utc(end)}


@parameters("users", "start_utc", "end_utc", "min_minutes", "display_timezone")
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

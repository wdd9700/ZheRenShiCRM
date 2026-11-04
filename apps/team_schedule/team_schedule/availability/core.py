"""Busy/free composition for availability.api.query.

Contract D010300 §4: per person clip to the window, merge overlapping and
adjacent busy pieces, union everyone's busy, then take the complement in the
window and filter by minute length. Pure functions; the caller owns parsing,
authorization and response encoding.
"""

from team_schedule.availability import intervals

SCAN_LIMIT = 10000
MAX_PEOPLE = 10
WINDOW_DAYS = 7
MIN_MINUTES_FLOOR = 1
MIN_MINUTES_CEILING = 10080


class ScanLimitExceeded(Exception):
    """The occupying rows were not read in full, so free time cannot be proven."""


def guard_scan(rows, limit=SCAN_LIMIT):
    if len(rows) > limit:
        raise ScanLimitExceeded()
    return rows


def busy_by_user(users, rows, window_start, window_end):
    """Ordered (user, merged intervals) pairs; users with no rows get []."""
    clipped = {user: [] for user in users}
    for row in rows:
        user = row.get("user")
        if user not in clipped:
            continue
        piece = intervals.clip((row["start_utc"], row["end_utc"]), window_start, window_end)
        if piece is not None:
            clipped[user].append(piece)
    return [(user, intervals.merge(clipped[user])) for user in users]


def common_free(pieces_per_user, window_start, window_end, min_minutes):
    union = []
    for pieces in pieces_per_user:
        union.extend(pieces)
    free = intervals.complement(window_start, window_end, union)
    return intervals.filter_minutes(free, min_minutes)

"""Bounded read of occupying rows for availability.api.query.

D010300 §4: only Active+Busy schedules count, and one counts for a person
when they own it or accepted an ``occupies`` member row. Exactly the three
columns the union needs are selected, so no schedule name, title, body,
member list, source or UID can reach a response. One statement reads every
person's rows, which is also what makes the snapshot consistent.
"""

from team_schedule.availability.core import MAX_PEOPLE, SCAN_LIMIT

BRANCH = (
    "SELECT %s AS `user`, t.start_utc AS start_utc, t.end_utc AS end_utc"
    " FROM `tabTeam Schedule` t"
    " WHERE t.status='Active' AND t.availability='Busy'"
    " AND t.start_utc < %s AND t.end_utc > %s"
    " AND (t.owner=%s OR EXISTS (SELECT 1 FROM `tabTeam Schedule Member` m"
    " WHERE m.parent=t.name AND m.user=%s AND m.occupies=1))"
)


def statement(users):
    if not isinstance(users, list) or not 1 <= len(users) <= MAX_PEOPLE:
        raise ValueError("users out of range")
    branches = " UNION ALL ".join([BRANCH] * len(users))
    return "SELECT * FROM (%s) AS occupying LIMIT %d" % (branches, SCAN_LIMIT + 1)


def parameters(users, start_utc, end_utc):
    values = []
    for user in users:
        values.extend([user, end_utc, start_utc, user, user])
    return tuple(values)

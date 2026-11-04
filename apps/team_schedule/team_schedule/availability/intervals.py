"""Half-open [start, end) interval algebra over aware UTC datetimes.

No Frappe, ORM or timezone-conversion dependency: the acceptance arithmetic
is exercised directly by tests, and all wall-clock semantics stay in the
caller (timeutils owns parsing/encoding).
"""

from datetime import timedelta

MINUTE = timedelta(minutes=1)


def _normalized(interval):
    start, end = interval
    if start.utcoffset() is None or end.utcoffset() is None:
        raise ValueError("interval boundaries must be timezone-aware")
    return start, end


def clip(interval, window_start, window_end):
    """Intersect with [window_start, window_end); empty results are None."""
    start, end = _normalized(interval)
    lower, upper = max(start, window_start), min(end, window_end)
    return (lower, upper) if lower < upper else None


def merge(intervals):
    """Sort, drop empty pieces and join overlapping or touching pieces."""
    ordered = sorted(item for item in (_normalized(entry) for entry in intervals) if item[0] < item[1])
    merged = []
    for start, end in ordered:
        if merged and start <= merged[-1][1]:
            if end > merged[-1][1]:
                merged[-1] = (merged[-1][0], end)
            continue
        merged.append((start, end))
    return merged


def union(*groups):
    """Merged union of any number of already-normalized interval sequences."""
    combined = []
    for group in groups:
        combined.extend(group)
    return merge(combined)


def complement(window_start, window_end, busy):
    """Parts of [window_start, window_end) covered by no busy piece."""
    free = []
    cursor = window_start
    for start, end in merge(busy):
        start, end = max(start, window_start), min(end, window_end)
        if start >= end:
            continue
        if start > cursor:
            free.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < window_end:
        free.append((cursor, window_end))
    return free


def minutes(interval):
    """Exact length in whole minutes; sub-minute input is rejected, not rounded."""
    start, end = _normalized(interval)
    seconds = (end - start).total_seconds()
    if seconds % 60 or seconds <= 0:
        raise ValueError("interval must be a positive whole number of minutes")
    return int(seconds // 60)


def filter_minutes(intervals, minimum):
    """Keep pieces lasting at least ``minimum`` minutes (contract: >=)."""
    if type(minimum) is not int or minimum < 1:
        raise ValueError("minimum must be a positive integer")
    return [interval for interval in intervals if minutes(interval) >= minimum]

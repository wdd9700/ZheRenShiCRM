import re
from datetime import datetime, timedelta, timezone as dt_timezone

import pytz


class ScheduleError(ValueError):
    def __init__(self, code, status=400, details=None):
        super().__init__(code)
        self.code = code
        self.status = status
        self.details = details


def invalid():
    raise ScheduleError("INVALID_INPUT")


def parse_utc(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00Z", value):
        invalid()
    try:
        result = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt_timezone.utc)
    except ValueError:
        invalid()
    if encode_utc(result) != value:
        invalid()
    return result


def encode_utc(value):
    if value.tzinfo is None or value.second or value.microsecond:
        invalid()
    value = value.astimezone(dt_timezone.utc)
    if value.second or value.microsecond:
        invalid()
    return f"{value.year:04d}-{value.month:02d}-{value.day:02d}T{value.hour:02d}:{value.minute:02d}:00Z"


def validate_timezone(name):
    if not isinstance(name, str) or name not in pytz.all_timezones_set:
        invalid()
    return name


def validate_window(start_utc, end_utc, max_days=31):
    start, end = parse_utc(start_utc), parse_utc(end_utc)
    if not start < end or end - start > timedelta(days=max_days):
        invalid()
    return start, end


def resolve_local(local, timezone, offset_minutes=None):
    validate_timezone(timezone)
    if not isinstance(local, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", local):
        invalid()
    if offset_minutes is not None and (type(offset_minutes) is not int or not -1440 < offset_minutes < 1440):
        invalid()
    try:
        naive = datetime.strptime(local, "%Y-%m-%dT%H:%M")
    except ValueError:
        invalid()
    zone = pytz.timezone(timezone)
    try:
        candidates = [zone.localize(naive, is_dst=None)]
    except pytz.NonExistentTimeError:
        invalid()
    except pytz.AmbiguousTimeError:
        candidates = [zone.localize(naive, is_dst=True), zone.localize(naive, is_dst=False)]
    offsets = sorted({int(item.utcoffset().total_seconds() / 60) for item in candidates})
    if len(offsets) > 1 and offset_minutes is None:
        raise ScheduleError("AMBIGUOUS_LOCAL_TIME", details={"offset_minutes": offsets})
    chosen = [item for item in candidates if offset_minutes is None or int(item.utcoffset().total_seconds() / 60) == offset_minutes]
    if not chosen:
        invalid()
    value = chosen[0]
    return {"utc": encode_utc(value), "timezone": timezone, "offset_minutes": int(value.utcoffset().total_seconds() / 60)}

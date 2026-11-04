import base64
import binascii
import hashlib
import importlib
import json
import re
from datetime import datetime, timedelta, timezone

import pytz

MAX_BYTES = 1024 * 1024
MAX_EVENTS = 200
EVENT_PROPERTIES = {
    "UID", "SEQUENCE", "DTSTAMP", "LAST-MODIFIED", "SUMMARY", "DESCRIPTION",
    "DTSTART", "DTEND", "TRANSP", "STATUS",
}


class ICSError(ValueError):
    def __init__(self, code="INVALID_INPUT", status=400):
        super().__init__(code)
        self.code = code
        self.status = status


def canonical_digest(value):
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def decode_file(file_base64):
    if not isinstance(file_base64, str):
        raise ICSError()
    if len(file_base64) > 4 * ((MAX_BYTES + 2) // 3):
        raise ICSError("LIMIT_EXCEEDED", 413)
    try:
        raw = base64.b64decode(file_base64, validate=True)
    except (ValueError, binascii.Error):
        raise ICSError() from None
    if len(raw) > MAX_BYTES:
        raise ICSError("LIMIT_EXCEEDED", 413)
    return raw


def _reader():
    try:
        module = importlib.import_module("vobject")
        return module.readOne
    except (ImportError, AttributeError):
        raise ICSError("DEPENDENCY_UNAVAILABLE", 503) from None


def parse_file(raw):
    return _parse_file(raw, _reader())


def _lines(raw):
    if not isinstance(raw, bytes):
        raise ICSError()
    if len(raw) > MAX_BYTES:
        raise ICSError("LIMIT_EXCEEDED", 413)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ICSError() from None
    text = text.replace("\r\n", "\n")
    if "\r" in text or any(ord(char) < 32 and char not in "\n\t" for char in text):
        raise ICSError()
    groups = []
    for line in text.split("\n"):
        if line.startswith((" ", "\t")):
            if not groups or not groups[-1][0]:
                raise ICSError()
            groups[-1].append(line[1:])
        else:
            groups.append([line])
    while groups and groups[-1] == [""]:
        groups.pop()
    if not groups or any(not group[0] for group in groups):
        raise ICSError()
    return ["".join(group) for group in groups]


def _split(raw):
    lines = _lines(raw)
    if lines[0].upper() != "BEGIN:VCALENDAR" or lines[-1].upper() != "END:VCALENDAR":
        raise ICSError()
    calendar, events, event, stack = [], [], None, []
    for line in lines[1:-1]:
        upper = line.upper()
        if upper.startswith("BEGIN:"):
            component = upper[6:]
            if not stack:
                if component != "VEVENT":
                    raise ICSError()
                event = []
            stack.append(component)
            if len(stack) > 1:
                event.append(line)
        elif upper.startswith("END:"):
            if not stack or upper[4:] != stack[-1]:
                raise ICSError()
            stack.pop()
            if stack:
                event.append(line)
            else:
                events.append(event)
                event = None
                if len(events) > MAX_EVENTS:
                    raise ICSError("LIMIT_EXCEEDED", 413)
        elif stack:
            event.append(line)
        else:
            calendar.append(line)
    if stack:
        raise ICSError()
    return calendar, events


def _property(line):
    quoted = False
    split_at = None
    for index, char in enumerate(line):
        if char == '"':
            quoted = not quoted
        elif char == ":" and not quoted:
            split_at = index
            break
    if quoted or split_at is None:
        raise ICSError()
    head, value = line[:split_at], line[split_at + 1:]
    parts, start, quoted = [], 0, False
    for index, char in enumerate(head):
        if char == '"':
            quoted = not quoted
        elif char == ";" and not quoted:
            parts.append(head[start:index])
            start = index + 1
    parts.append(head[start:])
    name = parts[0].upper()
    if not re.fullmatch(r"[A-Z0-9-]+", name):
        raise ICSError("UNSUPPORTED_ICS")
    params = {}
    for part in parts[1:]:
        key, separator, entry = part.partition("=")
        key = key.upper()
        if not separator or not re.fullmatch(r"[A-Z0-9-]+", key) or key in params:
            raise ICSError()
        if entry.startswith('"') and entry.endswith('"') and len(entry) >= 2:
            entry = entry[1:-1]
        if not entry or any(char in entry for char in '\";,'):
            raise ICSError()
        params[key] = entry
    return name, params, value


def _text(value):
    result = []
    index = 0
    escapes = {"n": "\n", "N": "\n", "\\": "\\", ";": ";", ",": ","}
    while index < len(value):
        char = value[index]
        if char == "\\":
            index += 1
            if index == len(value) or value[index] not in escapes:
                raise ICSError()
            char = escapes[value[index]]
        result.append(char)
        index += 1
    return "".join(result)


def _timestamp(value):
    if not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z", value):
        raise ICSError("INVALID_TIME")
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ")
    except ValueError:
        raise ICSError("INVALID_TIME") from None


def _datetime(params, value):
    if set(params) - {"TZID", "VALUE"} or params.get("VALUE", "DATE-TIME").upper() != "DATE-TIME":
        raise ICSError("UNSUPPORTED_ICS")
    zone_name = params.get("TZID", "UTC")
    try:
        if value.endswith("Z"):
            if "TZID" in params:
                raise ICSError("INVALID_TIME")
            result = _timestamp(value).replace(tzinfo=timezone.utc)
        else:
            if "TZID" not in params or zone_name not in pytz.all_timezones_set:
                raise ICSError("INVALID_TIME")
            if not re.fullmatch(r"[0-9]{8}T[0-9]{6}", value):
                raise ICSError("INVALID_TIME")
            naive = datetime.strptime(value, "%Y%m%dT%H%M%S")
            result = pytz.timezone(zone_name).localize(naive, is_dst=None)
        if result.second or result.microsecond:
            raise ICSError("INVALID_TIME")
        result = result.astimezone(timezone.utc)
        if result.second or result.microsecond:
            raise ICSError("INVALID_TIME")
        encoded = f"{result.year:04d}-{result.month:02d}-{result.day:02d}T{result.hour:02d}:{result.minute:02d}:00Z"
        return encoded, zone_name, result
    except (ValueError, OverflowError, pytz.AmbiguousTimeError, pytz.NonExistentTimeError):
        raise ICSError("INVALID_TIME") from None


def _check_library(reader, lines):
    try:
        component = reader("\r\n".join(lines) + "\r\n", validate=False, transform=False,
                           ignoreUnreadable=False, allowQP=False)
        if component is None:
            raise ICSError()
    except Exception:
        raise ICSError() from None


def _event(lines, method, reader):
    properties = {}
    for line in lines:
        name, params, value = _property(line)
        if name not in EVENT_PROPERTIES:
            raise ICSError("UNSUPPORTED_ICS")
        if name in properties:
            raise ICSError()
        allowed = {"TZID", "VALUE"} if name in ("DTSTART", "DTEND") else {"LANGUAGE"} if name in ("SUMMARY", "DESCRIPTION") else set()
        if set(params) - allowed:
            raise ICSError("UNSUPPORTED_ICS")
        if "LANGUAGE" in params and not re.fullmatch(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", params["LANGUAGE"]):
            raise ICSError()
        properties[name] = (params, value)
    _check_library(reader, ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Team Schedule//ICS//EN",
                            "BEGIN:VEVENT", *lines, "END:VEVENT", "END:VCALENDAR"])
    uid = _text(properties.get("UID", ({}, ""))[1])
    if not uid.strip() or len(uid) > 255:
        raise ICSError("INVALID_UID")
    sequence_text = properties.get("SEQUENCE", ({}, "0"))[1]
    if not re.fullmatch(r"[0-9]+", sequence_text) or len(sequence_text) > 10 or int(sequence_text) > 2147483647:
        raise ICSError()
    sequence = int(sequence_text)
    status = properties.get("STATUS", ({}, "CONFIRMED"))[1].upper()
    if status not in ("CONFIRMED", "TENTATIVE", "CANCELLED"):
        raise ICSError("UNSUPPORTED_ICS")
    cancelled = method == "CANCEL" or status == "CANCELLED"
    if cancelled and "SEQUENCE" not in properties:
        raise ICSError()
    for name in ("DTSTAMP", "LAST-MODIFIED"):
        if name in properties:
            _timestamp(properties[name][1])
    payload = {"status": "Cancelled" if cancelled else "Active"}
    for name, field, maximum in (("SUMMARY", "title", 140), ("DESCRIPTION", "description", 4000)):
        if name in properties:
            value = _text(properties[name][1])
            if len(value) > maximum or (field == "title" and not value.strip()):
                raise ICSError()
            payload[field] = value
        elif not cancelled:
            payload[field] = ""
    if not cancelled and not payload["title"].strip():
        raise ICSError()
    if "TRANSP" in properties or not cancelled:
        transp = properties.get("TRANSP", ({}, "OPAQUE"))[1].upper()
        if transp not in ("OPAQUE", "TRANSPARENT"):
            raise ICSError("UNSUPPORTED_ICS")
        payload["availability"] = "Free" if transp == "TRANSPARENT" else "Busy"
    times = {name: _datetime(*properties[name]) for name in ("DTSTART", "DTEND") if name in properties}
    if not cancelled and len(times) != 2:
        raise ICSError("INVALID_TIME")
    if len(times) == 2:
        start, end = times["DTSTART"], times["DTEND"]
        if not start[2] < end[2] or end[2] - start[2] > timedelta(days=31):
            raise ICSError("INVALID_TIME")
        payload.update(start_utc=start[0], end_utc=end[0], source_timezone=start[1])
    normalized = {"uid": uid, "cancelled": cancelled, "payload": payload,
                  "times": {name: list(value[:2]) for name, value in times.items()}}
    return {"uid": uid, "sequence": sequence, "cancelled": cancelled,
            "payload": payload, "digest": canonical_digest(normalized)}


def _parse_file(raw, reader):
    calendar, events = _split(raw)
    metadata = {}
    for line in calendar:
        name, params, value = _property(line)
        if name not in ("VERSION", "PRODID", "METHOD") or params or name in metadata:
            raise ICSError()
        metadata[name] = value
    if metadata.get("VERSION") != "2.0" or metadata.get("METHOD", "PUBLISH").upper() not in ("PUBLISH", "CANCEL"):
        raise ICSError()
    _check_library(reader, ["BEGIN:VCALENDAR", *calendar, "END:VCALENDAR"])
    items, uids = [], set()
    for index, lines in enumerate(events):
        try:
            item = _event(lines, metadata.get("METHOD", "PUBLISH").upper(), reader)
        except ICSError as error:
            item = {"error": error.code}
        for line in lines:
            try:
                name, params, value = _property(line)
                if name == "UID":
                    uid = _text(value)
                    if uid in uids:
                        raise ICSError("DUPLICATE_UID")
                    uids.add(uid)
            except ICSError as error:
                if error.code == "DUPLICATE_UID":
                    raise ICSError() from None
        items.append({"index": index, **item})
    return items

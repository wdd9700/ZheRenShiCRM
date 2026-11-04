import hashlib
import json
import secrets
from uuid import UUID

import frappe

from team_schedule import permissions
from team_schedule.timeutils import ScheduleError, invalid, validate_timezone, validate_window

DETAIL_FIELDS = ("name", "owner", "title", "description", "start_utc", "end_utc", "source_timezone", "status", "availability", "revision")
CONTENT_FIELDS = {"title", "description", "start_utc", "end_utc", "source_timezone", "availability"}
TIME_FIELDS = {"start_utc", "end_utc", "source_timezone"}


def fields(value, allowed, required=()):
    if not isinstance(value, dict) or set(value) - set(allowed) or not set(required) <= set(value):
        invalid()
    return value


def text(value, maximum, required=False):
    if not isinstance(value, str) or len(value) > maximum or "\x00" in value or (required and not value.strip()):
        invalid()
    return value


def enabled_member(user):
    if not isinstance(user, str) or user == "Guest" or not frappe.db.get_value("User", {"name": user, "enabled": 1, "user_type": "System User"}, "name"):
        invalid()
    return user


def validate_members(rows, owner, old=None):
    if not isinstance(rows, list) or len(rows) > 100:
        invalid()
    seen = {owner}
    result = []
    old = {row.user: bool(row.occupies) for row in old or []}
    for row in rows:
        fields(row, {"user", "access"}, {"user", "access"})
        user = enabled_member(row["user"])
        if user in seen or row["access"] not in ("Read", "Edit"):
            invalid()
        seen.add(user)
        result.append({"user": user, "access": row["access"], "occupies": int(old.get(user, False))})
    return result


def validate_schedule(doc):
    text(doc.title, 140, True)
    text(doc.description or "", 4000)
    validate_window(doc.start_utc, doc.end_utc)
    validate_timezone(doc.source_timezone)
    if doc.availability not in ("Busy", "Free") or doc.status not in ("Active", "Cancelled") or type(doc.revision) is not int or doc.revision < 1:
        invalid()
    users = {doc.owner}
    for row in doc.get("members", []):
        if not isinstance(row.user, str) or not frappe.db.exists("User", row.user):
            invalid()
        if row.user in users or row.access not in ("Read", "Edit") or row.occupies not in (0, 1):
            invalid()
        users.add(row.user)


def detail(doc):
    if not permissions.can_read(doc):
        raise ScheduleError("NOT_FOUND", 404)
    result = {key: doc.get(key) for key in DETAIL_FIELDS}
    result["description"] = result["description"] or ""
    result["members"] = [{"user": row.user, "access": row.access, "occupies": bool(row.occupies)} for row in doc.get("members", [])]
    return result


def audit(doc, action):
    entry = {"actor": frappe.session.user, "action": action, "id": doc.name, "revision": doc.get("revision")}
    frappe.db.after_commit.add(lambda: frappe.logger("team_schedule").info(json.dumps(entry, sort_keys=True)))


def lock_user(user):
    frappe.db.sql("SELECT name FROM `tabUser` WHERE name=%s FOR UPDATE", (user,))


def locked_schedule(name, expected_revision=None, mode="read"):
    actor = permissions.current_user()
    text(name, 140, True)
    if mode not in ("read", "edit", "owner"):
        invalid()
    rows = frappe.db.sql("SELECT name FROM `tabTeam Schedule` WHERE name=%s FOR UPDATE", (name,))
    if not rows:
        raise ScheduleError("NOT_FOUND", 404)
    doc = frappe.get_doc("Team Schedule", name, for_update=True)
    if not permissions.can_read(doc, actor):
        raise ScheduleError("NOT_FOUND", 404)
    if mode == "edit" and not permissions.can_edit(doc, actor):
        raise ScheduleError("FORBIDDEN", 403)
    if mode == "owner" and doc.owner != actor and not permissions.is_maintenance(actor):
        raise ScheduleError("FORBIDDEN", 403)
    if expected_revision is not None:
        if type(expected_revision) is not int or expected_revision < 1:
            invalid()
        if doc.revision != expected_revision:
            raise ScheduleError("REVISION_CONFLICT", 409)
    return doc


def save(doc, action):
    with permissions.internal_write():
        doc.save()
    audit(doc, action)
    return doc


def insert(doctype, values, action):
    actor = permissions.current_user()
    with permissions.internal_write():
        doc = frappe.get_doc({"doctype": doctype, "owner": actor, **values}).insert()
    audit(doc, action)
    return doc


def create_schedule(payload, request_id=None):
    actor = permissions.current_user()
    fields(payload, CONTENT_FIELDS | {"members"}, CONTENT_FIELDS | {"members"})
    if not isinstance(payload["members"], list) or len(payload["members"]) > 100:
        invalid()
    for row in payload["members"]:
        fields(row, {"user", "access"}, {"user", "access"})
        text(row["user"], 140, True)
    canonical = {**payload, "members": sorted(payload["members"], key=lambda row: row["user"])}
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    if request_id is not None:
        try:
            if not isinstance(request_id, str) or str(UUID(request_id)) != request_id:
                invalid()
        except (ValueError, AttributeError):
            invalid()
        lock_user(actor)
        name = frappe.db.get_value("Team Schedule Request", {"owner": actor, "request_id": request_id}, "name", for_update=True)
        if name:
            request = frappe.get_doc("Team Schedule Request", name, for_update=True)
            if request.payload_digest != digest:
                raise ScheduleError("IDEMPOTENCY_CONFLICT", 409)
            return locked_schedule(request.schedule)
    members = validate_members(payload["members"], actor)
    doc = insert("Team Schedule", {**payload, "members": members, "revision": 1, "status": "Active"}, "create")
    if request_id is not None:
        insert("Team Schedule Request", {"request_id": request_id, "payload_digest": digest, "schedule": doc.name}, "create_request")
    return doc


def mutate_schedule(name, expected_revision, changes):
    fields(changes, CONTENT_FIELDS)
    if not changes or (TIME_FIELDS & set(changes) and not TIME_FIELDS <= set(changes)):
        invalid()
    doc = locked_schedule(name, required_revision(expected_revision), "edit")
    if doc.status != "Active":
        raise ScheduleError("FORBIDDEN", 403)
    doc.update(changes)
    doc.revision += 1
    return save(doc, "update")


def required_revision(value):
    if type(value) is not int or value < 1:
        invalid()
    return value


def set_members(name, expected_revision, members):
    doc = locked_schedule(name, required_revision(expected_revision), "owner")
    if doc.status != "Active":
        raise ScheduleError("FORBIDDEN", 403)
    doc.set("members", validate_members(members, doc.owner, doc.members))
    doc.revision += 1
    return save(doc, "members")


def set_participation(name, expected_revision, occupies):
    if type(occupies) is not bool:
        invalid()
    doc = locked_schedule(name, required_revision(expected_revision))
    row = permissions.member(doc, frappe.session.user)
    if row is None or doc.status != "Active":
        raise ScheduleError("FORBIDDEN", 403)
    row.occupies = int(occupies)
    doc.revision += 1
    return save(doc, "participation")


def cancel(name, expected_revision):
    doc = locked_schedule(name, required_revision(expected_revision), "edit")
    if doc.status == "Cancelled":
        return doc
    doc.status = "Cancelled"
    doc.revision += 1
    return save(doc, "cancel")


def set_busy_grant(viewer_user, allow):
    actor = permissions.current_user()
    if type(allow) is not bool:
        invalid()
    text(viewer_user, 140, True)
    if allow:
        enabled_member(viewer_user)
    if viewer_user == actor:
        invalid()
    lock_user(actor)
    name = frappe.db.get_value("Team Schedule Busy Grant", {"subject_user": actor, "viewer_user": viewer_user}, "name", for_update=True)
    if allow and not name:
        insert("Team Schedule Busy Grant", {"subject_user": actor, "viewer_user": viewer_user}, "grant")
    elif not allow and name:
        frappe.db.delete("Team Schedule Busy Grant", {"name": name, "subject_user": actor})
        audit(frappe._dict(name=name), "revoke_grant")
    return {"viewer_user": viewer_user, "allow": allow}


def assert_busy_access(users):
    actor = permissions.current_user()
    if not isinstance(users, list) or not users or any(not isinstance(user, str) for user in users):
        invalid()
    users = list(dict.fromkeys(users))
    if not 1 <= len(users) <= 10 or actor not in users:
        invalid()
    for user in users:
        if not frappe.db.get_value("User", {"name": user, "enabled": 1, "user_type": "System User"}, "name"):
            raise ScheduleError("FORBIDDEN", 403)
        if user != actor and not frappe.db.exists("Team Schedule Busy Grant", {"subject_user": user, "viewer_user": actor}):
            raise ScheduleError("FORBIDDEN", 403)
    return actor


def list_schedules(start_utc, end_utc, include_cancelled=False, cursor=None, limit=100):
    actor = permissions.current_user()
    validate_window(start_utc, end_utc)
    if type(include_cancelled) is not bool or type(limit) is not int or not 1 <= limit <= 100:
        invalid()
    binding = [actor, start_utc, end_utc, include_cancelled]
    position = None
    if cursor is not None:
        text(cursor, 64, True)
        state = frappe.cache.get_value("team_schedule:cursor:" + cursor)
        if not state or state.get("binding") != binding:
            invalid()
        position = state["position"]
    conditions = permissions.query_conditions(actor)
    params = [end_utc, start_utc]
    if not include_cancelled:
        conditions += " AND status='Active'"
    if position:
        conditions += " AND (start_utc > %s OR (start_utc = %s AND name > %s))"
        params.extend([position[0], position[0], position[1]])
    params.append(limit + 1)
    names = frappe.db.sql(f"SELECT name,start_utc FROM `tabTeam Schedule` WHERE start_utc < %s AND end_utc > %s AND ({conditions}) ORDER BY start_utc,name LIMIT %s", tuple(params), as_dict=True)
    next_cursor = None
    if len(names) > limit:
        next_cursor = secrets.token_urlsafe(24)
        last = names[limit - 1]
        frappe.cache.set_value("team_schedule:cursor:" + next_cursor, {"binding": binding, "position": [last.start_utc, last.name]}, expires_in_sec=900)
    items = []
    for row in names[:limit]:
        doc = frappe.get_doc("Team Schedule", row.name)
        if permissions.can_read(doc, actor):
            items.append(detail(doc))
    return {"items": items, "next_cursor": next_cursor}


def get_source(source_id, lock=False):
    actor = permissions.current_user()
    text(source_id, 140, True)
    if not frappe.db.get_value("Team Schedule Source", source_id, "name", for_update=lock):
        raise ScheduleError("NOT_FOUND", 404)
    doc = frappe.get_doc("Team Schedule Source", source_id, for_update=lock)
    if doc.owner != actor and not permissions.is_maintenance(actor):
        raise ScheduleError("NOT_FOUND", 404)
    return doc


def create_source(label):
    text(label, 140, True)
    return insert("Team Schedule Source", {"label": label}, "create_source")


def uid_key(uid):
    text(uid, 255, True)
    return hashlib.sha256(uid.encode("utf-8")).hexdigest()


def lock_source_item(source_id, uid):
    get_source(source_id, lock=True)
    key = uid_key(uid)
    rows = frappe.db.sql("SELECT name FROM `tabTeam Schedule Source Item` WHERE source=%s AND uid_key=%s FOR UPDATE", (source_id, key))
    if not rows:
        return None
    doc = frappe.get_doc("Team Schedule Source Item", rows[0][0], for_update=True)
    if doc.uid != uid:
        raise ScheduleError("FORBIDDEN", 403)
    return doc


def save_source_item(source_id, uid, values):
    fields(values, {"schedule", "source_sequence", "source_digest", "last_import_revision", "tombstone"}, {"source_sequence", "source_digest", "tombstone"})
    doc = lock_source_item(source_id, uid)
    if type(values["source_sequence"]) is not int or values["source_sequence"] < 0:
        invalid()
    digest = values["source_digest"]
    if not isinstance(digest, str) or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        invalid()
    if type(values["tombstone"]) not in (bool, int) or values["tombstone"] not in (0, 1):
        invalid()
    schedule = values.get("schedule")
    if schedule:
        target = locked_schedule(schedule, mode="owner")
        if target.owner != get_source(source_id).owner:
            raise ScheduleError("FORBIDDEN", 403)
        if values.get("last_import_revision") != target.revision:
            raise ScheduleError("REVISION_CONFLICT", 409)
    elif not values["tombstone"]:
        invalid()
    if doc:
        doc.update(values)
        return save(doc, "source_item")
    return insert("Team Schedule Source Item", {"source": source_id, "uid": uid, "uid_key": uid_key(uid), **values}, "source_item")


def save_import_schedule(source_id, payload, schedule_name=None, expected_revision=None):
    source = get_source(source_id, lock=True)
    if source.owner != permissions.current_user():
        raise ScheduleError("FORBIDDEN", 403)
    fields(payload, CONTENT_FIELDS | {"status"})
    if schedule_name is None:
        fields(payload, CONTENT_FIELDS | {"status"}, CONTENT_FIELDS)
        return insert("Team Schedule", {**payload, "members": [], "revision": 1, "status": payload.get("status", "Active")}, "import_create")
    if TIME_FIELDS & set(payload) and not TIME_FIELDS <= set(payload):
        invalid()
    doc = locked_schedule(schedule_name, required_revision(expected_revision), "owner")
    if doc.owner != source.owner:
        raise ScheduleError("NOT_FOUND", 404)
    doc.update(payload)
    doc.revision += 1
    return save(doc, "import_update")


def export_owned(start_utc, end_utc):
    actor = permissions.current_user()
    validate_window(start_utc, end_utc)
    rows = frappe.db.sql("SELECT name FROM `tabTeam Schedule` WHERE owner=%s AND start_utc < %s AND end_utc > %s ORDER BY start_utc,name LIMIT 1001", (actor, end_utc, start_utc), as_dict=True)
    if len(rows) > 1000:
        raise ScheduleError("LIMIT_EXCEEDED", 413)
    schedules = [detail(frappe.get_doc("Team Schedule", row.name)) for row in rows]
    sources = frappe.get_all("Team Schedule Source", filters={"owner": actor}, fields=["name", "label"], limit_page_length=1001)
    if len(sources) > 1000:
        raise ScheduleError("LIMIT_EXCEEDED", 413)
    mappings = []
    names = {row.name for row in rows}
    for source in sources:
        items = frappe.get_all("Team Schedule Source Item", filters={"source": source.name, "owner": actor}, fields=["source", "uid", "schedule", "source_sequence", "source_digest", "last_import_revision", "tombstone"], limit_page_length=1001)
        for item in items:
            if item.tombstone or item.schedule in names:
                mappings.append(item)
        if len(items) > 1000 or len(mappings) > 1000:
            raise ScheduleError("LIMIT_EXCEEDED", 413)
    return {"schedules": schedules, "sources": sources, "source_items": mappings}

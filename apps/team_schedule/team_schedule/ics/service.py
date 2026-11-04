import hashlib
import re
import secrets
import time

import frappe

from team_schedule import permissions, service as core
from team_schedule.timeutils import ScheduleError, invalid
from team_schedule.ics import parser

TTL = 900
CACHE_PREFIX = "team_schedule:ics:"
REPLACE = "replace_from_source"


def _actor_source(source_id):
    actor = permissions.current_user()
    source = core.get_source(source_id, lock=True)
    if source.owner != actor:
        raise ScheduleError("NOT_FOUND", 404)
    return actor


def _session_binding():
    sid = getattr(frappe.session, "sid", None)
    if not isinstance(sid, str) or not sid or sid == "Guest":
        raise ScheduleError("AUTH_REQUIRED", 401)
    return hashlib.sha256(sid.encode("utf-8")).hexdigest()


def _parse(file_base64):
    try:
        raw = parser.decode_file(file_base64)
        items = parser.parse_file(raw)
    except parser.ICSError as error:
        raise ScheduleError(error.code, error.status) from None
    plan = [{"index": item["index"], "error": item["error"]} if "error" in item else {
        "index": item["index"], "uid_hash": core.uid_key(item["uid"]),
        "sequence": item["sequence"], "digest": item["digest"], "cancelled": item["cancelled"],
    } for item in items]
    return items, hashlib.sha256(raw).hexdigest(), parser.canonical_digest(plan)


def _snapshot(source_id, item):
    mapping = core.lock_source_item(source_id, item["uid"])
    state = {"mapping": {"exists": False}, "target": {"exists": False}}
    if mapping is None:
        return state
    state["mapping"] = {"exists": True, **{field: mapping.get(field) for field in (
        "schedule", "source_sequence", "source_digest", "last_import_revision")},
        "tombstone": bool(mapping.tombstone)}
    if mapping.schedule:
        try:
            target = core.locked_schedule(mapping.schedule, mode="owner")
        except ScheduleError as error:
            if error.code != "NOT_FOUND":
                raise
            state["target"] = {"exists": False, "name": mapping.schedule}
        else:
            if target.owner != permissions.current_user():
                raise ScheduleError("NOT_FOUND", 404)
            state["target"] = {"exists": True, "name": target.name, "revision": target.revision}
    return state


def _duplicate(item, state):
    mapping = state["mapping"]
    return mapping["exists"] and mapping["source_sequence"] == item["sequence"] and mapping["source_digest"] == item["digest"]


def _action(item, state):
    if "error" in item:
        return "error"
    mapping, target = state["mapping"], state["target"]
    if not mapping["exists"]:
        return "unknown_cancelled" if item["cancelled"] else "create"
    if _duplicate(item, state):
        return "duplicate"
    if item["sequence"] < mapping["source_sequence"]:
        return "stale"
    if item["sequence"] == mapping["source_sequence"]:
        return "version_conflict"
    if mapping["tombstone"] and not item["cancelled"]:
        return "cancelled_source"
    if not mapping["schedule"]:
        return "unknown_cancelled" if item["cancelled"] else "cancelled_source"
    if not target["exists"]:
        return "revision_conflict"
    if target["revision"] != mapping["last_import_revision"]:
        return "local_conflict"
    return "cancel" if item["cancelled"] else "update"


def _code(action, item):
    if action == "error":
        return item["error"]
    return action.upper() if action in ("stale", "version_conflict", "cancelled_source", "local_conflict", "revision_conflict") else None


def create_source(label):
    permissions.current_user()
    return {"source_id": core.create_source(label).name}


def preview(source_id, file_base64):
    actor = _actor_source(source_id)
    session = _session_binding()
    items, file_digest, plan_digest = _parse(file_base64)
    plans, results = [], []
    for item in items:
        state = _snapshot(source_id, item) if "error" not in item else None
        action = _action(item, state)
        revision = state["target"]["revision"] if action == "local_conflict" else None
        allowed = [REPLACE] if action == "local_conflict" else []
        plans.append({"index": item["index"], "state": state, "action": action,
                      "allowed_resolutions": allowed, "expected_revision": revision})
        result = {"index": item["index"], "action": action, "code": _code(action, item),
                  "allowed_resolutions": allowed, "expected_revision": revision}
        if "error" not in item:
            result["preview"] = item["payload"]
        results.append(result)
    receipt = secrets.token_urlsafe(32)
    frappe.cache.set_value(CACHE_PREFIX + receipt, {
        "actor": actor, "session": session, "source": source_id, "file_digest": file_digest,
        "plan_digest": plan_digest, "plans": plans, "expires_at": time.time() + TTL,
    }, expires_in_sec=TTL)
    return {"receipt": receipt, "expires_in": TTL, "items": results}


def _resolutions(confirm, resolutions, plans):
    if confirm is not True or not isinstance(resolutions, list):
        invalid()
    by_index = {plan["index"]: plan for plan in plans}
    selected = {}
    for resolution in resolutions:
        core.fields(resolution, {"index", "action", "expected_revision"}, {"index", "action", "expected_revision"})
        index = resolution["index"]
        if type(index) is not int or index not in by_index or index in selected:
            invalid()
        plan = by_index[index]
        if not isinstance(resolution["action"], str) or resolution["action"] not in plan["allowed_resolutions"]:
            invalid()
        revision = resolution["expected_revision"]
        if type(revision) is not int or revision < 1 or revision != plan["expected_revision"]:
            invalid()
        selected[index] = resolution["action"]
    return selected


def _result(item, action, state=None, code=None):
    result = {"index": item["index"], "result": action, "code": code if code is not None else _code(action, item)}
    if state and state["target"]["exists"]:
        result.update(schedule_name=state["target"]["name"], revision=state["target"]["revision"])
    return result


def _write(source_id, item, state, action):
    target = state["target"]
    schedule_name = target.get("name") if target["exists"] else None
    revision = target.get("revision") if target["exists"] else None
    if action != "unknown_cancelled":
        doc = core.save_import_schedule(source_id, item["payload"], schedule_name, revision)
        for field in ("title", "description"):
            if field in item["payload"] and doc.get(field) != item["payload"][field]:
                raise ScheduleError("UNSUPPORTED_TEXT")
        schedule_name, revision = doc.name, doc.revision
    core.save_source_item(source_id, item["uid"], {
        "schedule": schedule_name, "source_sequence": item["sequence"],
        "source_digest": item["digest"], "last_import_revision": revision,
        "tombstone": item["cancelled"],
    })
    result = {"index": item["index"], "result": action, "code": None}
    if schedule_name:
        result.update(schedule_name=schedule_name, revision=revision)
    return result


def apply(receipt, source_id, file_base64, confirm, resolutions):
    actor = _actor_source(source_id)
    session = _session_binding()
    if not isinstance(receipt, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", receipt):
        invalid()
    saved = frappe.cache.get_value(CACHE_PREFIX + receipt)
    if not isinstance(saved, dict) or saved.get("expires_at", 0) <= time.time():
        invalid()
    if (saved.get("actor"), saved.get("session"), saved.get("source")) != (actor, session, source_id):
        invalid()
    items, file_digest, plan_digest = _parse(file_base64)
    if saved.get("file_digest") != file_digest or saved.get("plan_digest") != plan_digest:
        invalid()
    plans = saved["plans"]
    selected = _resolutions(confirm, resolutions, plans)
    results = []
    for item, plan in zip(items, plans):
        if "error" in item:
            results.append(_result(item, "error"))
            continue
        point = "ics_" + str(item["index"])
        frappe.db.savepoint(point)
        try:
            _actor_source(source_id)
            state = _snapshot(source_id, item)
            if _duplicate(item, state):
                result = _result(item, "duplicate", state)
            elif state != plan["state"]:
                result = _result(item, "revision_conflict")
            else:
                action = _action(item, state)
                if action == "local_conflict" and selected.get(item["index"]) == REPLACE:
                    action = "cancel" if item["cancelled"] else "update"
                if action in ("create", "update", "cancel", "unknown_cancelled"):
                    result = _write(source_id, item, state, action)
                else:
                    result = _result(item, action)
        except ScheduleError as error:
            frappe.db.rollback(save_point=point)
            if error.code in ("AUTH_REQUIRED", "FORBIDDEN", "NOT_FOUND"):
                raise
            result = _result(item, "error", code=error.code)
        except Exception:
            frappe.db.rollback(save_point=point)
            frappe.local.message_log = []
            result = _result(item, "error", code="WRITE_FAILED")
        results.append(result)
    return {"items": results}

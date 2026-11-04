import json
import frappe
from werkzeug.wrappers import Response

from team_schedule import permissions, service, timeutils
from team_schedule.timeutils import ScheduleError


def json_response(result, status=200):
    return Response(json.dumps({"message": result}, ensure_ascii=False), status=status,
                    content_type="application/json; charset=utf-8", headers={"Cache-Control": "no-store"})


def endpoint(function, *, identity_lock="exclusive"):
    if identity_lock not in ("exclusive", "shared"):
        raise ValueError("Invalid internal identity lock mode")
    def call(**kwargs):
        frappe.local.flags.disable_traceback = True
        try:
            permissions.current_user(lock_mode=identity_lock)
            request = getattr(frappe.local, "request", None)
            if request and request.headers.get("Authorization"):
                raise ScheduleError("AUTH_REQUIRED", 401)
            kwargs.pop("cmd", None)
            service.fields(kwargs, function.__annotations__["fields"])
            result = function(**kwargs)
            if isinstance(result, Response):
                result.headers["Cache-Control"] = "no-store"
                return result
            return json_response(result)
        except ScheduleError as error:
            status = error.status
            result = {"error": {"code": error.code}}
            if error.code == "AMBIGUOUS_LOCAL_TIME":
                result["error"].update(error.details or {})
        except frappe.PermissionError:
            status, result = 403, {"error": {"code": "FORBIDDEN"}}
        except (TypeError, ValueError, frappe.ValidationError):
            status, result = 400, {"error": {"code": "INVALID_INPUT"}}
        except Exception:
            status, result = 500, {"error": {"code": "INTERNAL_ERROR"}}
        frappe.db.rollback()
        frappe.local.message_log = []
        return json_response(result, status)
    call.__name__ = function.__name__
    call.__qualname__ = function.__qualname__
    call.__module__ = function.__module__
    return frappe.whitelist(methods=["POST"])(call)


def parameters(*names, identity_lock="exclusive"):
    if identity_lock not in ("exclusive", "shared"):
        raise ValueError("Invalid internal identity lock mode")
    def decorate(function):
        function.__annotations__["fields"] = set(names)
        return endpoint(function, identity_lock=identity_lock)
    return decorate


@parameters("local", "timezone", "offset_minutes")
def resolve_local(local, timezone, offset_minutes=None):
    return timeutils.resolve_local(local, timezone, offset_minutes)


@parameters("title", "description", "start_utc", "end_utc", "source_timezone", "availability", "members", "request_id")
def create(title, description, start_utc, end_utc, source_timezone, availability, members, request_id):
    payload = {"title": title, "description": description, "start_utc": start_utc, "end_utc": end_utc, "source_timezone": source_timezone, "availability": availability, "members": members}
    if request_id is None:
        timeutils.invalid()
    return {"schedule": service.detail(service.create_schedule(payload, request_id))}


@parameters("name")
def get(name):
    return {"schedule": service.detail(service.locked_schedule(name))}


@parameters("start_utc", "end_utc", "include_cancelled", "cursor", "limit")
def list(start_utc, end_utc, include_cancelled=False, cursor=None, limit=100):
    return service.list_schedules(start_utc, end_utc, include_cancelled, cursor, limit)


@parameters("name", "expected_revision", "changes")
def update(name, expected_revision, changes):
    return {"schedule": service.detail(service.mutate_schedule(name, expected_revision, changes))}


@parameters("name", "expected_revision", "members")
def set_members(name, expected_revision, members):
    return {"schedule": service.detail(service.set_members(name, expected_revision, members))}


@parameters("name", "expected_revision", "occupies")
def set_participation(name, expected_revision, occupies):
    return {"schedule": service.detail(service.set_participation(name, expected_revision, occupies))}


@parameters("name", "expected_revision")
def cancel(name, expected_revision):
    return {"schedule": service.detail(service.cancel(name, expected_revision))}


@parameters("viewer_user", "allow")
def set_busy_grant(viewer_user, allow):
    return service.set_busy_grant(viewer_user, allow)


@parameters("start_utc", "end_utc")
def export_owned(start_utc, end_utc):
    data = service.export_owned(start_utc, end_utc)
    return Response(json.dumps(data, ensure_ascii=False, sort_keys=True),
                    content_type="application/json; charset=utf-8",
                    headers={"Cache-Control": "no-store", "Content-Disposition": 'attachment; filename="team-schedule.json"'})

from contextlib import contextmanager
from contextvars import ContextVar

import frappe

from team_schedule.timeutils import ScheduleError

DOCTYPES = ("Team Schedule", "Team Schedule Member", "Team Schedule Busy Grant", "Team Schedule Source", "Team Schedule Source Item", "Team Schedule Request", "Team Schedule Audit")
_writing = ContextVar("team_schedule_writing", default=False)


@contextmanager
def internal_write():
    token = _writing.set(True)
    try:
        yield
    finally:
        _writing.reset(token)


def writing():
    return _writing.get()


def is_team_user(user, *, lock_mode="shared"):
    if lock_mode not in ("exclusive", "shared"):
        raise ValueError("Invalid internal identity lock mode")
    if not user or user == "Guest":
        return False
    clause = "FOR UPDATE" if lock_mode == "exclusive" else "LOCK IN SHARE MODE"
    rows = frappe.db.sql("SELECT enabled,user_type FROM `tabUser` WHERE name=%s " + clause, (user,))
    return bool(rows and rows[0][0] and rows[0][1] == "System User")


def current_user(*, lock_mode="exclusive"):
    user = frappe.session.user
    if not user or user == "Guest":
        raise ScheduleError("AUTH_REQUIRED", 401)
    if not is_team_user(user, lock_mode=lock_mode):
        raise ScheduleError("FORBIDDEN", 403)
    assert_no_shares()
    return user


def is_maintenance(user=None):
    user = user or frappe.session.user
    return user == "Administrator" or "System Manager" in frappe.get_roles(user)


def assert_no_shares():
    if frappe.db.exists("DocShare", {"share_doctype": ["in", DOCTYPES]}):
        raise ScheduleError("FORBIDDEN", 403)


def member(doc, user):
    return next((row for row in doc.get("members", []) if row.user == user), None)


def can_read(doc, user=None):
    user = user or frappe.session.user
    if not is_team_user(user):
        return False
    if doc.doctype in ("Team Schedule Request", "Team Schedule Audit"):
        return writing() and doc.owner == user
    if doc.doctype == "Team Schedule Member":
        if doc.parenttype != "Team Schedule" or not doc.parent:
            return False
        parent = frappe.get_doc("Team Schedule", doc.parent)
        return can_read(parent, user)
    if is_maintenance(user):
        return True
    if doc.doctype == "Team Schedule Busy Grant":
        return user in (doc.subject_user, doc.viewer_user)
    if doc.doctype == "Team Schedule":
        return doc.owner == user or member(doc, user) is not None
    return doc.owner == user


def can_edit(doc, user=None):
    user = user or frappe.session.user
    if not can_read(doc, user):
        return False
    row = member(doc, user)
    return doc.owner == user or is_maintenance(user) or (row is not None and row.access == "Edit")


def has_permission(doc, user=None, permission_type=None, ptype=None):
    operation = permission_type or ptype or "read"
    try:
        assert_no_shares()
    except ScheduleError:
        return False
    if operation in ("read", "select"):
        return can_read(doc, user)
    if operation in ("create", "write", "delete"):
        return writing() and is_team_user(user or frappe.session.user)
    return False


def query_conditions(user=None, doctype="Team Schedule"):
    user = user or frappe.session.user
    assert_no_shares()
    if not is_team_user(user):
        return "1=0"
    if doctype in ("Team Schedule Request", "Team Schedule Audit"):
        return "1=0"
    if is_maintenance(user):
        return "1=1"
    escaped = frappe.db.escape(user)
    table = f"`tab{doctype}`"
    if doctype == "Team Schedule":
        return f"({table}.owner={escaped} OR EXISTS (SELECT 1 FROM `tabTeam Schedule Member` m WHERE m.parent={table}.name AND m.parenttype='Team Schedule' AND m.parentfield='members' AND m.user={escaped}))"
    if doctype == "Team Schedule Member":
        return f"EXISTS (SELECT 1 FROM `tabTeam Schedule` s WHERE s.name={table}.parent AND {table}.parenttype='Team Schedule' AND (s.owner={escaped} OR EXISTS (SELECT 1 FROM `tabTeam Schedule Member` m WHERE m.parent=s.name AND m.parenttype='Team Schedule' AND m.parentfield='members' AND m.user={escaped})))"
    if doctype == "Team Schedule Busy Grant":
        return f"({table}.subject_user={escaped} OR {table}.viewer_user={escaped})"
    return f"{table}.owner={escaped}"


def grant_query(user=None):
    return query_conditions(user, "Team Schedule Busy Grant")


def source_query(user=None):
    return query_conditions(user, "Team Schedule Source")


def source_item_query(user=None):
    return query_conditions(user, "Team Schedule Source Item")


def request_query(user=None):
    return query_conditions(user, "Team Schedule Request")


def member_query(user=None):
    return query_conditions(user, "Team Schedule Member")


PRINT_METHODS = frozenset((
    "frappe.utils.print_format.download_pdf",
    "frappe.utils.print_format.download_multi_pdf",
    "frappe.utils.print_format.download_multi_pdf_async",
    "frappe.utils.print_format.print_by_server",
    "frappe.utils.weasyprint.download_pdf",
    "frappe.www.printview.get_html_and_style",
    "frappe.www.printview.get_rendered_raw_commands",
))


def reject_print(doc, method=None, *args, **kwargs):
    frappe.throw("FORBIDDEN", frappe.PermissionError)


_PRINT_DOCTYPES = frozenset(name.casefold() for name in DOCTYPES)


def _print_target(value):
    if isinstance(value, str):
        if value.casefold() in _PRINT_DOCTYPES:
            return True
        if not value.lstrip().startswith("{"):
            return False
        try:
            value = frappe.parse_json(value)
        except (ValueError, TypeError):
            return False
    if isinstance(value, dict):
        return any(isinstance(name, str) and name.casefold() in _PRINT_DOCTYPES for name in value) or _print_target(value.get("doctype"))
    return False


def reject_print_request():
    request = getattr(frappe.local, "request", None)
    if request is None:
        return
    path = request.path.strip("/")
    command = frappe.form_dict.get("cmd")
    if not command:
        for prefix in ("api/method/", "api/v1/method/", "api/v2/method/"):
            if path.startswith(prefix):
                command = path[len(prefix):].split("/")[0]
                break
    if path not in ("printview", "printview.html") and (not isinstance(command, str) or command not in PRINT_METHODS):
        return
    if _print_target(frappe.form_dict.get("doctype")) or _print_target(frappe.form_dict.get("doc")):
        reject_print(None)


def reject_share(doc, method=None):
    if doc.share_doctype in DOCTYPES:
        frappe.throw("FORBIDDEN", frappe.PermissionError)


def reject_sidecar(doc, method=None):
    references = ((doc.get("attached_to_doctype"), doc.get("attached_to_name")), (doc.get("ref_doctype"), doc.get("docname")), (doc.get("reference_doctype"), doc.get("reference_name")))
    if any(doctype in DOCTYPES for doctype, name in references):
        frappe.throw("FORBIDDEN", frappe.PermissionError)

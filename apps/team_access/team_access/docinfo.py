import frappe

from team_access.api import check
from team_access.permissions import PRIVATE_TYPES, PROTECTED, can_reference, permitted


def scrub(doctype, name):
    info = frappe.response.get("docinfo")
    if not info or doctype not in PROTECTED or frappe.session.user == "Administrator":
        return
    mapping = {
        "versions": "Version", "comments": "Comment", "attachment_logs": "Comment",
        "attachments": "File", "assignments": "ToDo", "communications": "Communication",
        "automated_messages": "Communication",
    }
    for key, target in mapping.items():
        if key in info:
            info[key] = [row for row in info[key] if can_reference(target, row.get("name"), frappe.session.user)]
    if doctype in PRIVATE_TYPES:
        doc = check(doctype, name)
        writer = permitted(doc, ptype="write")
        if not writer:
            for key in ("views", "energy_point_logs", "additional_timeline_content", "milestones", "shared"):
                info[key] = []
        for key in ("write", "delete", "share"):
            if not permitted(doc, ptype=key):
                info.setdefault("permissions", {})[key] = 0
        visible_users = {doc.owner}
        for key in mapping:
            visible_users.update(row.get("owner") for row in info.get(key, []))
        info["user_info"] = {user: value for user, value in info.get("user_info", {}).items() if user in visible_users}


@frappe.whitelist()
def getdoc(doctype: str, name: str):
    from frappe.desk.form.load import getdoc as original

    if doctype in PROTECTED:
        check(doctype, name)
    result = original(doctype, name)
    scrub(doctype, name)
    return result


@frappe.whitelist()
def get_docinfo(doc=None, doctype=None, name=None):
    from frappe.desk.form.load import get_docinfo as original

    if doc:
        values = frappe.parse_json(doc) if isinstance(doc, str) else doc
        doctype, name = values.get("doctype"), values.get("name")
    if doctype not in PROTECTED:
        return original(doc=doc, doctype=doctype, name=name)
    authoritative = check(doctype, name)
    result = original(doc=authoritative)
    scrub(doctype, name)
    return result

import frappe

from team_access.api import check
from team_access.permissions import PRIVATE_TYPES, PROTECTED, PARENTS, can_reference, get_record, permitted


def communication_rows(rows):
    from team_access.permissions import MAX_ROWS, deny

    if len(rows) > MAX_ROWS:
        deny()
    result = []
    for row in rows:
        record = get_record("Communication", row.get("name"))
        if not record or not permitted(record):
            continue
        files = frappe.get_all("File", filters={"attached_to_doctype": "Communication", "attached_to_name": record.name}, fields=["name", "file_url", "is_private"], limit_page_length=MAX_ROWS + 1)
        if len(files) > MAX_ROWS:
            deny()
        row["attachments"] = frappe.as_json([{key: file.get(key) for key in ("file_url", "is_private")} for file in files if can_reference("File", file.name, frappe.session.user)])
        result.append(row)
    return result


def attachment_logs(doctype, name):
    from team_access.permissions import MAX_ROWS, deny

    check(doctype, name)
    rows = frappe.get_all("Comment", filters={"reference_doctype": doctype, "reference_name": name, "comment_type": ["in", ["Attachment", "Attachment Removed"]]}, fields=["name", "creation", "content", "owner", "comment_type", "published"], order_by="creation desc", limit_page_length=MAX_ROWS + 1)
    if len(rows) > MAX_ROWS:
        deny()
    return [row for row in rows if (record := get_record("Comment", row.name)) and permitted(record)]


def scrub(doctype, name):
    info = frappe.response.get("docinfo")
    if not info or doctype not in (*PROTECTED, *PARENTS) or frappe.session.user == "Administrator":
        return
    info["attachment_logs"] = attachment_logs(doctype, name)
    mapping = {
        "versions": "Version", "comments": "Comment", "attachment_logs": "Comment",
        "assignment_logs": "Comment", "info_logs": "Comment", "like_logs": "Comment",
        "workflow_logs": "Comment",
        "attachments": "File", "assignments": "ToDo", "communications": "Communication",
        "automated_messages": "Communication",
    }
    for key, target in mapping.items():
        if key in info:
            if target == "Communication":
                info[key] = communication_rows(info[key])
            elif target == "Comment":
                info[key] = [row for row in info[key] if (record := get_record(target, row.get("name"))) and permitted(record)]
            else:
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
    doc = get_record(doctype, name)
    visible_users = {doc.get("owner"), doc.get("modified_by")} if doc else set()
    for key in (*mapping, "views", "shared"):
        for row in info.get(key, []):
            visible_users.update(row.get(field) for field in ("owner", "sender", "user"))
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
    if doctype not in (*PROTECTED, *PARENTS):
        return original(doc=doc, doctype=doctype, name=name)
    authoritative = check(doctype, name)
    result = original(doc=authoritative)
    scrub(doctype, name)
    return result


@frappe.whitelist()
def get_filtered_attachments(dt: str, dn: str, filters):
    from frappe.desk.form.load import get_filtered_attachments as original

    check(dt, dn)
    from team_access.permissions import MAX_ROWS, deny

    rows = original(dt, dn, filters)
    if len(rows) > MAX_ROWS:
        deny()
    return [row for row in rows if can_reference("File", row.get("name"), frappe.session.user)]


@frappe.whitelist()
def get_communications(doctype: str, name: str, start=0, limit=20):
    from frappe.desk.form.load import get_communications as original

    check(doctype, name)
    rows = original(doctype, name, start, limit)
    return communication_rows(rows)


@frappe.whitelist()
def get_assigned_users(doctype: str, name: str, default_assigned_to=None):
    from crm.api.doc import get_assigned_users as original

    doc = check(doctype, name)
    from team_access.references import private_roots

    roots = {(doctype, str(name))} if doctype in PRIVATE_TYPES else private_roots(doc=doc)
    from team_access.permissions import can_contribute

    if roots and not all(can_contribute(*root, frappe.session.user) for root in roots):
        return []
    return original(doctype, name, default_assigned_to)

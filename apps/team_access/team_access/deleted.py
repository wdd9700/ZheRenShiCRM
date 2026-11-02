import frappe

from team_access.permissions import MAX_ROWS, PARENTS, PRIVATE_TYPES, can_reference, deny, get_record
from team_access.references import GRAPH_TYPES, private_roots, references

METHODS = (
    "frappe.core.doctype.deleted_document.deleted_document.restore",
    "frappe.core.doctype.deleted_document.deleted_document.bulk_restore",
)


def permitted_snapshot(doc, user):
    try:
        doctype = doc.get("deleted_doctype")
        if not isinstance(doctype, str) or not doctype or not doc.get("deleted_name"):
            return False
        from team_access.relations import EDGE_TABLES

        if doctype in (*PRIVATE_TYPES, *EDGE_TABLES, "File", "ToDo", "CRM Notification", "Notification Log", "Deleted Document"):
            return False
        data = frappe.parse_json(doc.get("data"))
        if not isinstance(data, dict) or data.get("doctype") != doctype or data.get("name") is None or str(data.get("name")) != str(doc.get("deleted_name")):
            return False
        from team_access.responses import RAW_FIELDS

        if any(data.get(key) and data.get(key) not in ("[]", "{}") for key in (*RAW_FIELDS, "_link_titles")):
            return False
        if doctype == "Comment" and data.get("comment_type") in ("Attachment", "Attachment Removed"):
            return False
        if doctype in GRAPH_TYPES:
            snapshot = frappe._dict(data)
            targets = references(snapshot)
            if private_roots(doc=snapshot) or not targets:
                return False
            return all(dt in PARENTS and name and can_reference(dt, name, user) for dt, name in targets)
        return bool(doctype)
    except (ValueError, TypeError, frappe.PermissionError, frappe.DoesNotExistError):
        return False


def check_snapshot(name):
    doc = get_record("Deleted Document", name)
    if not doc or not permitted_snapshot(doc, frappe.session.user) or not frappe.has_permission("Deleted Document", "read", doc=doc, user=frappe.session.user, throw=False):
        deny()
    return doc


@frappe.whitelist()
def restore(name: str, alert=True):
    from frappe.core.doctype.deleted_document.deleted_document import restore as original

    check_snapshot(name)
    return original(name, alert)


@frappe.whitelist()
def bulk_restore(docnames):
    from frappe.core.doctype.deleted_document.deleted_document import bulk_restore as original

    names = frappe.parse_json(docnames)
    if not isinstance(names, list) or len(names) > MAX_ROWS:
        deny()
    for name in names:
        check_snapshot(name)
    return original(names)

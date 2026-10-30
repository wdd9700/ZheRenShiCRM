import frappe
from frappe.core.doctype.file.file import File

from team_access.permissions import PRIVATE_TYPES, can_reference, deny, get_record


def private_root(doctype, name):
    seen = set()
    while doctype and name and (doctype, str(name)) not in seen and len(seen) < 12:
        if doctype in PRIVATE_TYPES:
            return doctype, name
        if doctype not in ("Comment", "Communication"):
            return None
        seen.add((doctype, str(name)))
        parent = get_record(doctype, name)
        if not parent:
            return None
        doctype, name = parent.get("reference_doctype"), parent.get("reference_name")
    return None


def private_target(doctype, name):
    return bool(private_root(doctype, name))


def validate_attachment(doc):
    root = private_root(doc.get("attached_to_doctype"), doc.get("attached_to_name"))
    old = get_record("File", doc.get("name"))
    old_root = private_root(old.get("attached_to_doctype"), old.get("attached_to_name")) if old else None
    if old_root and old_root != root:
        raise frappe.PermissionError("Private activity attachments cannot be detached or reparented through the document API")
    if not root:
        return
    target = get_record(*root)
    if not old and target and target.get("custom_team_visibility") == "Shared":
        raise frappe.PermissionError("Shared text-only activities do not accept attachments; use a separate Private record")
    url = str(doc.get("file_url") or "")
    if str(doc.get("is_private")) not in ("1", "True") or (url and not url.startswith("/private/files/")):
        raise frappe.PermissionError("Private activity attachments must use local private storage")
    if frappe.session.user != "Administrator" and not can_reference(doc.attached_to_doctype, doc.attached_to_name, frappe.session.user):
        deny()


class ActivityFile(File):
    def before_insert(self):
        validate_attachment(self)
        super().before_insert()

    def validate(self):
        validate_attachment(self)
        super().validate()

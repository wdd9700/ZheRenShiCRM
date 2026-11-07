import frappe
from frappe.core.doctype.file.file import File

from team_access.permissions import can_reference, deny, get_record


def private_target(doctype, name):
    from team_access.references import private_roots

    return bool(private_roots(doctype, name))


def activity_roots(doc):
    from team_access.permissions import MAX_ROWS
    from team_access.references import private_roots

    roots = private_roots(doc.get("attached_to_doctype"), doc.get("attached_to_name"))
    if doc.get("file_url"):
        aliases = frappe.get_all("File", filters={"file_url": doc.file_url}, fields=["attached_to_doctype", "attached_to_name"], limit_page_length=MAX_ROWS + 1)
        if len(aliases) > MAX_ROWS:
            deny()
        for alias in aliases:
            roots.update(private_roots(alias.attached_to_doctype, alias.attached_to_name))
    return roots


def validate_attachment(doc):
    from team_access.permissions import can_contribute
    from team_access.references import private_roots

    roots = private_roots(doc.get("attached_to_doctype"), doc.get("attached_to_name"))
    if activity_roots(doc) != roots:
        raise frappe.PermissionError("Private activity file URLs cannot be reused outside their original activities")
    old = get_record("File", doc.get("name"))
    old_roots = private_roots(old.get("attached_to_doctype"), old.get("attached_to_name")) if old else set()
    if old_roots and (old_roots != roots or any(old.get(key) != doc.get(key) for key in ("attached_to_doctype", "attached_to_name", "file_url"))):
        raise frappe.PermissionError("Private activity attachments cannot be detached or reparented through the document API")
    if not roots:
        return
    for root in roots:
        target = get_record(*root)
        if not old and target.get("custom_team_visibility") == "Shared":
            raise frappe.PermissionError("Shared text-only activities do not accept attachments; use a separate Private record")
        if frappe.session.user != "Administrator" and not can_contribute(*root, frappe.session.user):
            deny()
    url = str(doc.get("file_url") or "")
    if str(doc.get("is_private")) not in ("1", "True") or (url and not url.startswith("/private/files/")):
        raise frappe.PermissionError("Private activity attachments must use local private storage")
    if frappe.session.user != "Administrator" and not can_reference(doc.attached_to_doctype, doc.attached_to_name, frappe.session.user):
        deny()


class ActivityFile(File):
    def on_trash(self):
        from team_access.events import prevent_private_deletion

        prevent_private_deletion(self)
        return super().on_trash()

    def notify_update(self):
        if not getattr(frappe.local, "team_access_private_communication_update", False) and not activity_roots(self):
            return super().notify_update()

    def before_insert(self):
        validate_attachment(self)
        super().before_insert()

    def validate(self):
        validate_attachment(self)
        super().validate()

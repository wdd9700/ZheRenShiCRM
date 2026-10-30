import frappe

from team_access.permissions import PRIVATE_TYPES, PROTECTED, PARENTS, can_reference, deny, get_record, parent_readable, permitted

ACL_FIELDS = ("owner", "reference_doctype", "reference_docname", "custom_team_visibility", "custom_team_collaborator", "assigned_to")


def validate(doc, method=None):
    user = frappe.session.user
    if user == "Administrator" or frappe.flags.in_install or frappe.flags.in_migrate:
        return
    if doc.doctype == "DocShare" and doc.get("share_doctype") in PROTECTED:
        deny()
    if doc.doctype not in PROTECTED:
        return
    if doc.doctype in PRIVATE_TYPES:
        validate_private(doc, user)
    elif doc.doctype in ("CRM Notification", "Notification Log"):
        recipient = doc.get("to_user") or doc.get("for_user")
        if not permitted(doc, recipient):
            deny()
    elif doc.doctype == "File":
        if doc.get("attached_to_doctype") in PRIVATE_TYPES and not doc.get("is_private"):
            raise frappe.ValidationError("Activity attachments must use private storage")
        if not permitted(doc, user, "write"):
            deny()
    elif doc.doctype in ("Comment", "Communication"):
        dt, name = doc.get("reference_doctype"), doc.get("reference_name")
        if not can_reference(dt, name, user):
            deny()
        old = get_record(doc.doctype, doc.get("name"))
        if old and (old.owner != user or old.get("reference_doctype") != dt or old.get("reference_name") != name):
            deny()
    elif doc.doctype == "ToDo" and doc.get("reference_type") in PRIVATE_TYPES:
        target = get_record(doc.reference_type, doc.get("reference_name"))
        if not target or target.owner != user or not permitted(target, doc.get("allocated_to")):
            deny()
    elif doc.doctype == "CRM Call Log":
        if not permitted(doc, user, "write"):
            deny()
    content = doc.get("content") or doc.get("description")
    if content and doc.doctype in (*PRIVATE_TYPES, "Comment"):
        from crm.api.comment import extract_mentions

        for mention in extract_mentions(content):
            if not permitted(doc, mention.email):
                raise frappe.PermissionError("A mentioned user is not authorized to read this activity")


def validate_private(doc, user):
    old = get_record(doc.doctype, doc.get("name"))
    if old:
        if not permitted(old, user, "write"):
            deny()
        if old.owner != user and any((doc.get(f) or "") != (old.get(f) or "") for f in ACL_FIELDS):
            deny()
        if doc.owner != old.owner:
            raise frappe.ValidationError("Activity ownership transfer requires a reviewed migration")
    elif doc.owner and doc.owner != user:
        deny()
    doc.owner = doc.owner or user
    dt, name = doc.get("reference_doctype"), doc.get("reference_docname")
    if bool(dt) != bool(name) or (dt and dt not in PARENTS) or not parent_readable(doc, user):
        deny()
    visibility = doc.get("custom_team_visibility") or "Private"
    if visibility not in ("Private", "Shared") or (visibility == "Shared" and not dt):
        raise frappe.ValidationError("Shared activities require a readable CRM Lead or CRM Deal")
    doc.custom_team_visibility = visibility
    if visibility == "Shared":
        from team_access.files import private_root
        from team_access.permissions import MAX_ROWS

        files = frappe.get_all("File", fields=["attached_to_doctype", "attached_to_name"], limit_page_length=MAX_ROWS + 1)
        attached = any(private_root(file.attached_to_doctype, file.attached_to_name) == (doc.doctype, doc.name) for file in files)
        content = (doc.get("content") or "") + (doc.get("description") or "")
        if len(files) > MAX_ROWS or attached or "/private/files/" in content:
            raise frappe.ValidationError("Shared publishes current text only; remove private attachment references or keep this activity Private")
    for recipient in {doc.get("custom_team_collaborator"), doc.get("assigned_to")} - {None, ""}:
        if not frappe.db.exists("User", {"name": recipient, "enabled": 1, "user_type": "System User"}):
            raise frappe.ValidationError("Collaborator must be an active system user")
        if dt and not can_reference(dt, name, recipient):
            raise frappe.ValidationError("Collaborator must be able to read the linked parent")


def on_trash(doc, method=None):
    if doc.doctype in PROTECTED and frappe.session.user != "Administrator" and not permitted(doc, ptype="delete"):
        deny()

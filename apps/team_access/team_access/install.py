import frappe

from team_access import __version__

PRIVATE_TYPES = ("FCRM Note", "CRM Task")


def preflight():
    import crm

    if frappe.__version__ != "15.125.0" or crm.__version__ != "1.90.0":
        frappe.throw("Team Access 0.1 requires Frappe 15.125.0 and CRM 1.90.0; audit before upgrading.")
    from team_access.files import private_target
    from team_access.hooks import override_whitelisted_methods

    file_overrides = frappe.get_hooks("override_doctype_class", {}).get("File", [])
    if any(value != "team_access.files.ActivityFile" for value in file_overrides):
        frappe.throw("A conflicting File controller override requires security review before installing Team Access.")
    existing_overrides = frappe.get_hooks("override_whitelisted_methods", {})
    for method, replacement in override_whitelisted_methods.items():
        if any(value != replacement for value in existing_overrides.get(method, [])):
            frappe.throw("A conflicting activity API override requires security review before installing Team Access.")
    definitions = (("custom_team_visibility", "Select", "Private\nShared", "Private"), ("custom_team_collaborator", "Link", "User", ""))
    for doctype in PRIVATE_TYPES:
        for fieldname, fieldtype, options, default in definitions:
            existing = frappe.db.get_value("Custom Field", {"dt": doctype, "fieldname": fieldname}, ["fieldtype", "options", "default"], as_dict=True)
            if existing and any((existing.get(key) or "") != value for key, value in (("fieldtype", fieldtype), ("options", options), ("default", default))):
                frappe.throw("An incompatible Team Access field blocks installation; no schema was changed.")

    files = frappe.get_all("File", filters={"is_folder": 0}, fields=["attached_to_doctype", "attached_to_name", "is_private", "file_url"], limit_page_length=0)
    unsafe = sum(private_target(file.attached_to_doctype, file.attached_to_name) and (not file.is_private or not (file.file_url or "").startswith("/private/files/")) for file in files)
    if unsafe:
        frappe.throw(f"{unsafe} public or remote activity attachment(s) block installation. Keep maintenance mode on and review them through the administrator File list before migrating bytes to private storage; nothing was moved or deleted.")


def migrate():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    fields = {}
    for doctype in PRIVATE_TYPES:
        fields[doctype] = [
            {
                "fieldname": "custom_team_visibility",
                "label": "Activity Visibility",
                "fieldtype": "Select",
                "options": "Private\nShared",
                "default": "Private",
                "insert_after": "reference_docname",
                "description": "Private: owner and explicit collaborator only. Shared: also readable by the parent record's readers. Sharing never grants editing.",
            },
            {
                "fieldname": "custom_team_collaborator",
                "label": "Read/write collaborator",
                "fieldtype": "Link",
                "options": "User",
                "insert_after": "custom_team_visibility",
                "description": "Only the owner can grant or revoke this access. A linked parent must remain readable.",
            },
        ]
    for doctype, definitions in fields.items():
        for definition in definitions:
            existing = frappe.db.get_value("Custom Field", {"dt": doctype, "fieldname": definition["fieldname"]}, ["fieldtype", "options", "default"], as_dict=True)
            if existing and any((existing.get(key) or "") != (definition.get(key) or "") for key in ("fieldtype", "options", "default")):
                frappe.throw("An incompatible Team Access field exists; review the schema before migrating.")
    create_custom_fields(fields, update=False)
    frappe.db.set_default("team_access_schema_version", __version__)
    frappe.clear_cache()


def prevent_uninstall():
    frappe.throw("Do not uninstall an access-control boundary. Restore a reviewed compatible Team Access image under maintenance mode, or export and isolate all private data first.")

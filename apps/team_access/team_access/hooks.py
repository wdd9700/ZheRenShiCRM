app_name = "team_access"
app_title = "Team Activity Access"
app_publisher = "CRM Team"
app_description = "Explicit private and shared CRM activities"
app_email = "noreply@example.invalid"
app_license = "AGPL-3.0"
required_apps = ["crm"]

before_install = "team_access.install.preflight"
after_install = "team_access.install.migrate"
before_migrate = "team_access.install.preflight"
after_migrate = "team_access.install.migrate"
before_uninstall = "team_access.install.prevent_uninstall"

auth_hooks = ["team_access.request.guard"]
after_request = ["team_access.request.after_request"]

permission_query_conditions = {"*": "team_access.permissions.query_condition"}
has_permission = {"*": "team_access.permissions.has_permission"}
doc_events = {
    "*": {"before_validate": "team_access.events.validate", "on_trash": "team_access.events.on_trash"},
    "Communication": {"validate": "team_access.events.validate"},
}

override_doctype_class = {"File": "team_access.files.ActivityFile"}

override_whitelisted_methods = {
    "frappe.desk.form.load.getdoc": "team_access.docinfo.getdoc",
    "frappe.desk.form.load.get_docinfo": "team_access.docinfo.get_docinfo",
    "crm.api.activities.get_activities": "team_access.api.get_activities",
    "crm.api.doc.get_data": "team_access.api.get_data",
    "crm.api.doc.get_linked_docs_of_document": "team_access.api.get_linked_docs",
    "crm.api.notifications.get_notifications": "team_access.api.get_notifications",
    "crm.fcrm.doctype.crm_call_log.crm_call_log.get_call_log": "team_access.api.get_call_log",
    "crm.integrations.api.add_note_to_call_log": "team_access.api.add_note_to_call_log",
    "crm.integrations.api.add_task_to_call_log": "team_access.api.add_task_to_call_log",
    "frappe.desk.form.linked_with.get": "team_access.api.get_linked_with",
    "frappe.desk.notifications.get_open_count": "team_access.api.get_open_count",
}

doctype_js = {
    "FCRM Note": "public/access.js",
    "CRM Task": "public/access.js",
    "Comment": "public/access.js",
}
web_include_js = ["/assets/team_access/access.js"]

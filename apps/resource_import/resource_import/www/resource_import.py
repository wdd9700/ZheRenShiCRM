import frappe

from resource_import.service import authorize

no_cache = 1


def get_context(context):
    frappe.local.flags.disable_traceback = True
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=%2Fresource-import"
        raise frappe.Redirect
    authorize()
    context.csrf_token = frappe.sessions.get_csrf_token()
    context.no_cache = 1
    return context

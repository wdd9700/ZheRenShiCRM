import frappe


no_cache = 1


def get_context(context):
    frappe.local.flags.disable_traceback = True
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=%2Fteam-schedule"
        raise frappe.Redirect
    context.csrf_token = frappe.sessions.get_csrf_token()
    context.session_user = frappe.session.user
    context.no_cache = 1
    return context

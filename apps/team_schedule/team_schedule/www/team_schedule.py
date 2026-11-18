import frappe


no_cache = 1


def redirect_to(location):
    frappe.local.flags.redirect_location = location
    redirect = frappe.Redirect()
    redirect.http_status_code = 302
    raise redirect


def get_context(context):
    frappe.local.flags.disable_traceback = True
    # Only enable after verifying the native bundle and backend on this site.
    setting = frappe.conf.get("team_schedule_native_workspace")
    native = setting is True or (type(setting) is int and setting == 1)
    if frappe.session.user == "Guest":
        redirect_to("/login?redirect-to=%2Fcrm%2Fteam-schedule" if native else "/login?redirect-to=%2Fteam-schedule")
    if native:
        redirect_to("/crm/team-schedule")
    context.csrf_token = frappe.sessions.get_csrf_token()
    context.session_user = frappe.session.user
    context.no_cache = 1
    return context

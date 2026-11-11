import frappe
from frappe import _


def update_website_context(context):
    if context.get('path') != 'login':
        return
    brand = _('哲人石CRM')
    context['app_name'] = brand
    context['title'] = _('Login to {0}').format(brand)
    context['body_class'] = (context.get('body_class') or '') + ' crm-login-brand'
    context['head_html'] = (context.get('head_html') or '') + (
        '<link rel="stylesheet" href="/assets/team_schedule/crm-theme.css">'
        '<link rel="stylesheet" href="/assets/crm/css/login-theme.css">'
    )

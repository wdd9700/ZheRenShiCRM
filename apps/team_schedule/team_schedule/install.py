import frappe


def before_install():
    frappe.cache.delete_value("app_modules")
    frappe.setup_module_map(include_all_apps=True)

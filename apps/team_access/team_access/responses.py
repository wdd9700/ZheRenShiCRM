import re

import frappe

from team_access.permissions import PARENTS, PROTECTED, can_reference, deny

RAW_FIELDS = ("_comments", "_assign", "_liked_by", "_seen", "_user_tags", "__onload")


def reject_raw_fields(args):
    for key in ("fields", "fieldname", "order_by", "group_by", "filters", "or_filters", "export_filters", "pluck", "searchfield", "search_fields"):
        value = str(args.get(key) or "")
        if any(re.search(r"(?<![\w])" + re.escape(field) + r"(?![\w])", value, re.IGNORECASE) for field in RAW_FIELDS):
            deny()


def sanitize(value, scoped=False):
    if isinstance(value, list):
        return [sanitize(item, scoped) for item in value]
    if not isinstance(value, dict):
        return value
    scoped = scoped or value.get("doctype") in (*PROTECTED, *PARENTS)
    if scoped and isinstance(value.get("keys"), list) and isinstance(value.get("values"), list):
        indices = [i for i, key in enumerate(value["keys"]) if key not in RAW_FIELDS]
        value = {**value, "keys": [value["keys"][i] for i in indices], "values": [[row[i] for i in indices] for row in value["values"]]}
    result = {}
    for key, item in value.items():
        if scoped and key in RAW_FIELDS:
            continue
        if key == "_link_titles" and isinstance(item, dict):
            result[key] = {}
            for target, title in item.items():
                parts = target.split("::", 1)
                if len(parts) == 2 and can_reference(*parts, frappe.session.user):
                    result[key][target] = title
        else:
            result[key] = sanitize(item, scoped)
    return result


def sanitize_response(response):
    if frappe.session.user == "Administrator" or response.mimetype != "application/json":
        return
    value = response.get_json(silent=True)
    if value is not None:
        scoped = getattr(frappe.local, "team_access_doctype", None) in (*PROTECTED, *PARENTS)
        response.set_data(frappe.as_json(sanitize(value, scoped)))

from copy import deepcopy

import frappe

from team_access.permissions import PARENTS, PROTECTED, deny
from team_access.responses import RAW_FIELDS, reject_raw_fields


def parse_options(options):
    result = deepcopy(options)
    for key in ("rows", "columns", "kanban_fields", "kanban_columns"):
        value = result.get(key)
        value = [] if value is None or value == "" else frappe.parse_json(value)
        if not isinstance(value, list):
            deny()
        result[key] = value
    view = result.get("view")
    view = {} if view is None or view == "" else frappe.parse_json(view)
    if not isinstance(view, dict):
        deny()
    result["view"] = view
    return result


def validate_options(options, doctype, filters=None, order_by=None):
    for key in ("rows", "kanban_fields"):
        if not all(isinstance(field, str) for field in options[key]):
            deny()
    if not all(isinstance(column, dict) and isinstance(column.get("key"), str) for column in options["columns"]):
        deny()
    if not all(isinstance(column, dict) for column in options["kanban_columns"]):
        deny()
    names = [column["key"] for column in options["columns"]]
    names.extend(options["kanban_fields"])
    names.extend(options.get(key) for key in ("column_field", "title_field") if options.get(key))
    if options["view"].get("group_by_field"):
        names.append(options["view"]["group_by_field"])
    if not all(isinstance(name, str) for name in names):
        deny()
    values = {"fields": options["rows"], "fieldname": names, "filters": filters, "order_by": order_by}
    reject_raw_fields(values, doctype)
    options["rows"] = values["fields"]


def without_caches(rows, columns):
    if not isinstance(rows, list) or not all(isinstance(field, str) for field in rows) or not isinstance(columns, list) or not all(isinstance(column, dict) and isinstance(column.get("key"), str) for column in columns):
        deny()
    return [field for field in rows if field not in RAW_FIELDS], [column for column in columns if column.get("key") not in RAW_FIELDS]


def prepare(doctype, options, filters, order_by):
    if doctype not in (*PROTECTED, *PARENTS) or frappe.session.user == "Administrator":
        return options, None
    from frappe.model.document import get_controller

    options = parse_options(options)
    validate_options(options, doctype, filters, order_by)
    controller = get_controller(doctype)
    defaults = deepcopy(controller.default_list_data()) if hasattr(controller, "default_list_data") else {}
    defaults_rows, defaults_columns = without_caches(defaults.get("rows") or [], defaults.get("columns") or [])
    default_result = None
    view_type = options["view"].get("view_type")
    if view_type != "kanban" and not (options["rows"] or options["columns"]):
        settings_filters = {"dt": doctype, "type": view_type or "list", "is_standard": 1, "user": frappe.session.user}
        if frappe.db.exists("CRM View Settings", settings_filters):
            settings = frappe.get_doc("CRM View Settings", settings_filters)
            resolved = parse_options({"rows": settings.get("rows"), "columns": settings.get("columns")})
            resolved["rows"], resolved["columns"] = without_caches(resolved["rows"], resolved["columns"])
            validate_options(resolved, doctype, filters, order_by)
            options.update(rows=resolved["rows"], columns=resolved["columns"])
            is_default = frappe.db.get_value("CRM View Settings", options["view"]["custom_view_name"], "load_default_columns") if options["view"].get("custom_view_name") else False
            default_result = (is_default, deepcopy(resolved["columns"]))
        else:
            options.update(rows=defaults_rows, columns=defaults_columns)
            default_result = (True, deepcopy(defaults_columns))
    elif view_type == "kanban":
        if not options["rows"]:
            options["rows"] = defaults_rows
        kanban = controller.default_kanban_settings() if hasattr(controller, "default_kanban_settings") else {}
        if not options.get("title_field"):
            options["title_field"] = kanban.get("title_field") or "name"
        if not options["kanban_fields"]:
            options["kanban_fields"] = [field for field in (frappe.parse_json(kanban.get("kanban_fields")) or ["name"]) if field not in RAW_FIELDS]
    if not options["rows"]:
        options["rows"] = ["name"]
    if view_type != "kanban" and not options["columns"]:
        options["columns"] = [{"label": "Name", "type": "Data", "key": "name", "width": "16rem"}, {"label": "Last Modified", "type": "Datetime", "key": "modified", "width": "8rem"}]
    if view_type == "kanban" and not options["kanban_fields"]:
        options["kanban_fields"] = ["name"]
    validate_options(options, doctype, filters, order_by)
    return options, default_result


def finish(result, default_result):
    result["rows"], result["columns"] = without_caches(result.get("rows") or [], result.get("columns") or [])
    result["fields"] = [field for field in result.get("fields", []) if field.get("fieldname") not in RAW_FIELDS]
    if default_result is not None:
        result["is_default"] = default_result[0]
        if not default_result[1]:
            result["columns"] = []
    return result

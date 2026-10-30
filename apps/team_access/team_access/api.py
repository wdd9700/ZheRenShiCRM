import inspect

import frappe

from team_access.permissions import PRIVATE_TYPES, PROTECTED, PARENTS, append_filter, can_reference, deny, get_record, permitted


def check(doctype, name, ptype="read"):
    doc = get_record(doctype, name)
    if not doc or (doctype in PROTECTED and not permitted(doc, ptype=ptype)):
        deny()
    doc.check_permission(ptype)
    return doc


def filter_rows(doctype, rows):
    from team_access.permissions import MAX_ROWS

    if len(rows) > MAX_ROWS:
        frappe.response["team_access_limit"] = MAX_ROWS
        raise frappe.PermissionError("Team Access activity response exceeds the safe scan limit")
    return [row for row in rows if can_reference(doctype, row.get("name"), frappe.session.user)]


@frappe.whitelist()
def get_activities(name: str):
    from crm.api import activities as upstream

    doctype = next((dt for dt in PARENTS if frappe.db.exists(dt, name)), None)
    if not doctype:
        deny()
    check(doctype, name)
    try:
        activities, calls, notes, tasks, attachments = upstream.get_activities(name)
        notes = filter_rows("FCRM Note", notes)
        tasks = filter_rows("CRM Task", tasks)
        calls = filter_rows("CRM Call Log", calls)
        attachments = filter_rows("File", attachments)
        note_names = {n["name"] for n in notes}

        def keep(activity):
            kind = activity.get("activity_type")
            if kind == "note":
                return activity.get("data", {}).get("note") in note_names
            if kind in ("comment", "attachment_log"):
                return can_reference("Comment", activity.get("name"), frappe.session.user)
            if kind in ("changed", "added", "removed") and activity.get("options"):
                option = activity["options"]
                if option in (*PROTECTED, *PARENTS):
                    data = activity.get("data", {})
                    return all(can_reference(option, value, frappe.session.user) for value in (data.get("value"), data.get("old_value")) if value)
            return True

        result = []
        for activity in activities:
            members = [activity, *activity.pop("other_notes", [])]
            for member in members:
                if keep(member):
                    member["other_versions"] = [v for v in member.get("other_versions", []) if keep(v)]
                    if "attachments" in member:
                        member["attachments"] = filter_rows("File", member["attachments"])
                    result.append(member)
        return upstream.group_note_activities(result), calls, notes, tasks, attachments
    finally:
        frappe.response.pop("docinfo", None)


@frappe.whitelist()
def get_data(doctype: str, filters=None, order_by="modified desc", **kwargs):
    from crm.api.doc import get_data as original

    filters = frappe.parse_json(filters) or {}
    defaults = frappe.parse_json(kwargs.pop("default_filters", None)) or {}
    if not isinstance(filters, dict) or not isinstance(defaults, dict):
        raise frappe.ValidationError("CRM list filters must be objects")
    filters.update(defaults)
    if doctype in PROTECTED:
        names = frappe.get_list(doctype, filters=append_filter(doctype, filters), pluck="name", limit_page_length=0)
        filters["name"] = ["in", names]
    options = {key: value for key, value in kwargs.items() if key in inspect.signature(original).parameters}
    result = original(doctype=doctype, filters=filters, order_by=order_by, **options)
    rows = result.get("data", [])
    if result.get("view_type") == "kanban":
        rows = [row for column in rows for row in column.get("data", [])]
    if doctype in PARENTS:
        for row in rows:
            for dt, key in (("FCRM Note", "_note_count"), ("CRM Task", "_task_count"), ("Comment", "_comment_count"), ("Communication", "_email_count")):
                ref_field = "reference_docname" if dt in PRIVATE_TYPES else "reference_name"
                children = frappe.get_all(dt, filters={"reference_doctype": doctype, ref_field: row.name}, fields=["name"], limit_page_length=0)
                row[key] = sum(can_reference(dt, child.name, frappe.session.user) for child in children)
    return result


@frappe.whitelist()
def get_linked_docs(doctype: str, docname: str):
    from crm.api.doc import get_linked_docs_data

    doc = check(doctype, docname)
    return [row for row in get_linked_docs_data(doc) if can_reference(row.get("reference_doctype"), row.get("reference_docname"), frappe.session.user)]


@frappe.whitelist()
def get_linked_with(doctype: str, docname: str):
    from frappe.desk.form.linked_with import get

    check(doctype, docname)
    return {dt: [row for row in rows if can_reference(dt, row.get("name"), frappe.session.user)] for dt, rows in get(doctype, docname).items()}


@frappe.whitelist()
def get_open_count(doctype: str, name: str, items=None):
    from frappe.desk.notifications import get_dynamic_link_filters, get_filters_for, get_internal_links

    doc = check(doctype, name)
    links = doc.meta.get_dashboard_data()
    if items is None:
        items = [dt for group in links.get("transactions", []) for dt in group.get("items", [])]
    items = frappe.parse_json(items) if isinstance(items, str) else items
    result = {"external_links_found": [], "internal_links_found": []}
    for target in items:
        internal = links.get("internal_links", {}).get(target) or links.get("internal_and_external_links", {}).get(target)
        if internal:
            data = get_internal_links(doc, internal, target)
            data["names"] = [n for n in data.get("names", []) if can_reference(target, n, frappe.session.user)]
            data["count"] = len(data["names"])
            data["open_count"] = 0
            result["internal_links_found"].append(data)
            continue
        fieldname = links.get("non_standard_fieldnames", {}).get(target, links.get("fieldname"))
        if not fieldname:
            continue
        filters = {fieldname: name}
        filters.update(get_dynamic_link_filters(target, links, fieldname) or {})

        def count(extra=None):
            conditions = {**filters, **(extra or {})}
            if target in PROTECTED:
                conditions = append_filter(target, conditions)
            try:
                rows = frappe.get_list(target, fields=["name"], filters=conditions, limit_page_length=0)
            except frappe.PermissionError:
                return 0
            return sum(can_reference(target, row.name, frappe.session.user) for row in rows)

        all_count = count()
        open_filters = get_filters_for(target)
        result["external_links_found"].append({"doctype": target, "count": all_count, "open_count": count(open_filters) if open_filters else 0})
    return {"count": result}


@frappe.whitelist()
def get_call_log(name: str):
    from crm.fcrm.doctype.crm_call_log.crm_call_log import parse_call_log

    doc = check("CRM Call Log", name)
    call = parse_call_log(doc.as_dict())
    refs = [(row.get("link_doctype"), row.get("link_name")) for row in doc.get("links", [])]
    if doc.get("note"):
        refs.append(("FCRM Note", doc.note))
    if doc.get("reference_doctype"):
        refs.append((doc.reference_doctype, doc.reference_docname))
    call["_notes"] = [check(dt, n).as_dict() for dt, n in refs if dt == "FCRM Note"]
    call["_tasks"] = [check(dt, n).as_dict() for dt, n in refs if dt == "CRM Task"]
    for dt, n in refs:
        if dt in PARENTS:
            call["_lead" if dt == "CRM Lead" else "_deal"] = n
    return call


@frappe.whitelist()
def get_notifications():
    from crm.api.notifications import get_notifications as original

    allowed = [row.name for row in frappe.get_all("CRM Notification", filters={"to_user": frappe.session.user}, fields=["name"], limit_page_length=0) if can_reference("CRM Notification", row.name, frappe.session.user)]
    rows = frappe.get_all("CRM Notification", filters={"name": ["in", allowed]}, fields=["notification_type_doctype", "notification_type_doc", "creation"], limit_page_length=0)
    keys = {(row.notification_type_doctype, row.notification_type_doc, row.creation) for row in rows}
    return [row for row in original() if (row.get("notification_type_doctype"), row.get("notification_type_doc"), row.get("creation")) in keys]


def save_call_child(call_sid, data, doctype):
    call = check("CRM Call Log", call_sid, "write")
    data = frappe.parse_json(data)
    if data.get("name"):
        child = check(doctype, data["name"], "write")
    else:
        child = frappe.new_doc(doctype)
        if call.get("reference_doctype") in PARENTS:
            child.reference_doctype = call.reference_doctype
            child.reference_docname = call.reference_docname
    fields = ("title", "content") if doctype == "FCRM Note" else ("title", "description", "assigned_to", "due_date", "status", "priority")
    child.update({field: data[field] for field in fields if field in data})
    child.save()
    call.link_with_reference_doc(doctype, child.name)
    call.save()
    return child


@frappe.whitelist()
def add_note_to_call_log(call_sid: str, note: dict):
    return save_call_child(call_sid, note, "FCRM Note")


@frappe.whitelist()
def add_task_to_call_log(call_sid: str, task: dict):
    return save_call_child(call_sid, task, "CRM Task")


@frappe.whitelist()
def list_activities(doctype: str):
    if doctype not in PRIVATE_TYPES:
        deny()
    names = frappe.get_list(doctype, fields=["name"], filters=append_filter(doctype), limit_page_length=0)
    return [check(doctype, row.name).as_dict() for row in names]


@frappe.whitelist(methods=["POST"])
def save_activity(document):
    data = frappe.parse_json(document)
    doctype = data.get("doctype")
    if doctype not in PRIVATE_TYPES:
        deny()
    doc = check(doctype, data["name"], "write") if data.get("name") else frappe.new_doc(doctype)
    allowed = ("title", "content", "description", "reference_doctype", "reference_docname", "custom_team_visibility", "custom_team_collaborator", "assigned_to", "status", "priority", "due_date")
    doc.update({field: data[field] for field in allowed if field in data})
    return doc.save().as_dict()


@frappe.whitelist()
def parent_options(doctype: str, txt: str = ""):
    if doctype not in PARENTS:
        deny()
    return frappe.get_list(doctype, filters={"name": ["like", "%" + txt[:100] + "%"]}, fields=["name"], page_length=20)

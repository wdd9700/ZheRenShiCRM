import json
from urllib.parse import unquote

import frappe

from team_access.permissions import PRIVATE_TYPES, PROTECTED, append_filter, can_reference, deny, get_record

FILTER_METHODS = {
    "frappe.client.get_list": "filters",
    "frappe.client.get_value": "filters",
    "frappe.client.get_count": "filters",
    "frappe.desk.reportview.get": "filters",
    "frappe.desk.reportview.get_list": "filters",
    "frappe.desk.reportview.get_count": "filters",
    "frappe.desk.reportview.export_query": "filters",
    "frappe.desk.search.search_link": "filters",
    "frappe.desk.search.search_widget": "filters",
    "frappe.core.doctype.data_import.data_import.download_template": "export_filters",
    "frappe.core.doctype.data_export.exporter.export_data": "filters",
}


def guard():
    request = frappe.local.request
    parts = [unquote(p) for p in request.path.strip("/").split("/")]
    args = frappe.form_dict
    method = args.get("cmd")
    if method:
        parts = []
    if not method and "method" in parts and parts[0] == "api":
        method = parts[parts.index("method") + 1] if len(parts) > parts.index("method") + 1 else method
    doctype = args.get("doctype") or args.get("dt") or args.get("reference_doctype")
    from team_access.deleted import METHODS as snapshot_methods

    payload = args.get("doc") or args.get("docs") or args.get("document")
    values = payload if isinstance(payload, (dict, list)) else {}
    if isinstance(payload, str) and payload.lstrip().startswith(("{", "[")):
        values = frappe.parse_json(payload)
    from team_access.relations import guard_request

    guard_request(parts, args, method, values)
    if method in snapshot_methods or (isinstance(values, dict) and values.get("doctype") == "Deleted Document"):
        doctype = "Deleted Document"
    if frappe.session.user == "Administrator" and doctype != "Deleted Document" and "Deleted Document" not in parts:
        return
    if method in ("run_doc_method", "runserverobj", "frappe.handler.run_doc_method", "frappe.handler.runserverobj", "frappe.api.v2.run_doc_method") or parts[:4] == ["api", "v2", "method", "run_doc_method"]:
        values = frappe.parse_json(args.get("docs") or args.get("document")) if args.get("docs") or args.get("document") else {}
        if doctype in PROTECTED or (isinstance(values, dict) and values.get("doctype") in PROTECTED):
            deny()
    if not args.get("cmd") and parts[:3] == ["api", "v2", "method"] and len(parts) >= 5:
        doctype = parts[3]
        if doctype in PROTECTED:
            if doctype == "FCRM Note" and parts[4] == "set_pinned":
                method = "crm.fcrm.doctype.fcrm_note.fcrm_note.set_pinned"
            else:
                deny()
    field = FILTER_METHODS.get(method)
    if isinstance(doctype, str) and doctype.startswith("["):
        doctype = frappe.parse_json(doctype)
    if isinstance(doctype, list) and method in FILTER_METHODS:
        deny()
    if method == "frappe.core.doctype.data_export.exporter.export_data":
        parent = args.get("parent_doctype")
        if not doctype:
            if parent in PROTECTED:
                doctype = parent
                args["doctype"] = parent
            else:
                deny()
        if (doctype in PROTECTED or parent in PROTECTED) and parent and parent != doctype:
            deny()
    target_name = args.get("name") or args.get("docname") or args.get("dn") or args.get("reference_name")
    if parts[:2] == ["api", "resource"] or parts[:3] == ["api", "v1", "resource"]:
        offset = 2 if parts[1] == "resource" else 3
        if len(parts) > offset:
            doctype = parts[offset]
            if len(parts) == offset + 1 and request.method == "GET":
                field = "filters"
            elif len(parts) > offset + 1:
                target_name = "/".join(parts[offset + 1:])
    if parts[:3] == ["api", "v2", "document"] and len(parts) >= 4:
        doctype = parts[3]
        if len(parts) == 4 and request.method == "GET":
            field = "filters"
        elif len(parts) > 4:
            target_name = parts[4]
    if parts[:3] == ["api", "v2", "doctype"] and len(parts) == 5 and parts[4] == "count":
        doctype, field = parts[3], "filters"
    if method == "crm.fcrm.doctype.fcrm_note.fcrm_note.set_pinned":
        doctype = "FCRM Note"
    if method in ("frappe.desk.form.utils.update_comment", "frappe.desk.form.utils.delete_comment"):
        doctype = "Comment"
    from team_access.permissions import PARENTS
    from team_access.responses import reject_raw_fields

    if doctype in (*PROTECTED, *PARENTS):
        frappe.local.team_access_doctype = doctype
        reject_raw_fields(args, doctype)
        if method == "frappe.desk.reportview.export_query" and str(args.get("export_in_background", "0")) not in ("0", "False", "false"):
            raise frappe.PermissionError("Activity exports must run synchronously with current permissions")
    if method == "upload_file" or (method and method.endswith(".upload_file")):
        from team_access.files import private_target

        if private_target(doctype, target_name):
            if str(args.get("is_private", "0")) != "1" or args.get("file_url") or args.get("method"):
                raise frappe.PermissionError("Activity attachments require a direct private upload")
    safe_methods = {
        "frappe.client.get", "frappe.client.insert", "frappe.client.save", "frappe.client.set_value", "frappe.client.delete",
        "frappe.desk.form.load.getdoc", "frappe.desk.form.load.get_docinfo", "frappe.desk.form.load.getdoctype",
        "frappe.desk.form.linked_with.get", "frappe.desk.notifications.get_open_count",
        "frappe.desk.form.utils.update_comment", "frappe.desk.form.utils.delete_comment", "upload_file",
        "frappe.core.doctype.communication.email.make", "crm.api.comment.add_comment", "frappe.desk.form.utils.add_comment",
        "frappe.desk.form.load.get_filtered_attachments", "frappe.desk.form.load.get_communications",
        "frappe.realtime.can_subscribe_doc",
        "crm.fcrm.doctype.fcrm_note.fcrm_note.set_pinned", "crm.api.doc.get_data",
        "crm.api.doc.get_linked_docs_of_document", "crm.api.doc.add_seen", "crm.api.doc.get_assigned_users",
        "crm.api.doc.get_quick_filters", "crm.api.doc.get_fields", "crm.api.doc.get_filterable_fields",
        "crm.api.doc.get_sort_options", "crm.api.doc.get_group_by_fields",
        "crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_fields_layout",
        "crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_sidepanel_sections",
    }
    safe_methods.update(snapshot_methods)
    if doctype in PROTECTED and method and not field and method not in safe_methods:
        if not method.startswith(("team_access.api.", "frappe.desk.form.assign_to.")):
            raise frappe.PermissionError("This activity endpoint has not been reviewed; use the activity access page")
    if doctype in PROTECTED and target_name and not field:
        if method == "frappe.desk.form.utils.update_comment":
            from team_access.permissions import permitted

            comment = get_record("Comment", target_name)
            if not comment or not permitted(comment, ptype="write"):
                deny()
        elif not can_reference(doctype, target_name, frappe.session.user):
            deny()
    if doctype in PROTECTED and field:
        if method in ("frappe.desk.search.search_link", "frappe.desk.search.search_widget"):
            if args.get("query") or args.get("ignore_user_permissions") not in (None, False, 0, "0", "false"):
                deny()
        if method == "frappe.desk.reportview.export_query":
            if args.get("selected_items"):
                selected = frappe.parse_json(args.pop("selected_items"))
                filters = append_filter(doctype, args.get(field))
                filters.append([doctype, "name", "in", selected])
                args[field] = filters
            else:
                args[field] = append_filter(doctype, args.get(field))
        else:
            filters = args.get(field)
            if method == "frappe.client.get_value" and isinstance(filters, str):
                try:
                    filters = json.loads(filters)
                except ValueError:
                    filters = {"name": filters}
            args[field] = append_filter(doctype, filters)
        args.pop("cache", None)
        if "ignore_user_permissions" in args:
            args["ignore_user_permissions"] = False
    if method and method.startswith("frappe.desk.form.assign_to."):
        assignment = frappe.parse_json(args.get("args")) if args.get("args") else args
        if assignment.get("doctype") in PRIVATE_TYPES:
            doc = get_record(assignment["doctype"], assignment.get("name"))
            if not doc or doc.owner != frappe.session.user:
                deny()
            if not can_reference(doc.doctype, doc.name, frappe.session.user):
                deny()
            users = frappe.parse_json(assignment.get("assign_to")) or []
            for user in users:
                if doc.get("reference_doctype") and not can_reference(doc.reference_doctype, doc.reference_docname, user):
                    deny()
            if users:
                raise frappe.PermissionError("Set the task assignee or explicit collaborator on the activity access page; generic assignment does not grant activity access")


def after_request(response=None):
    if not response:
        return
    from team_access.responses import sanitize_response

    sanitize_response(response)
    path = frappe.local.request.path
    if path == "/crm" or path.startswith("/crm/"):
        if response.mimetype == "text/html" and response.status_code == 200:
            html = response.get_data(as_text=True)
            tag = '<script defer src="/assets/team_access/access.js"></script>'
            if tag not in html:
                response.set_data(html.replace("</body>", tag + "</body>"))
    if path.startswith("/api/") or path == "/team-activities" or path == "/crm" or path.startswith("/crm/"):
        response.headers["Cache-Control"] = "no-store, private"
        response.headers["Pragma"] = "no-cache"

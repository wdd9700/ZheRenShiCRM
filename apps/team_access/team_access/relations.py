import frappe
from frappe.core.doctype.communication_link.communication_link import CommunicationLink
from frappe.core.doctype.dynamic_link.dynamic_link import DynamicLink

from team_access.permissions import READ_TYPES, can_reference, deny, get_record

EDGE_TABLES = ("Communication Link", "Dynamic Link")
READ_METHODS = {
    "frappe.client.get", "frappe.client.get_list", "frappe.client.get_value", "frappe.client.get_count",
    "frappe.desk.form.load.getdoc", "frappe.desk.form.load.get_docinfo", "frappe.desk.form.load.getdoctype",
    "frappe.desk.reportview.get", "frappe.desk.reportview.get_list", "frappe.desk.reportview.get_count",
    "frappe.desk.reportview.export_query", "frappe.desk.search.search_link", "frappe.desk.search.search_widget",
}


def reject_independent(doctype):
    if doctype in EDGE_TABLES:
        raise frappe.PermissionError("Independent activity relation changes are disabled. Save the authorized parent document without removing existing private provenance instead.")


def parent_record(doc):
    stored = get_record(doc.doctype, doc.get("name"))
    if not stored or not all(stored.get(key) for key in ("parenttype", "parent", "parentfield")):
        deny()
    meta = frappe.get_meta(stored.parenttype)
    field = meta.get_field(stored.parentfield)
    if meta.istable or not field or field.fieldtype not in ("Table", "Table MultiSelect") or field.options != doc.doctype:
        deny()
    parent = get_record(stored.parenttype, stored.parent)
    if not parent or not any(str(row.get("name")) == str(stored.name) for row in parent.get(stored.parentfield, [])):
        deny()
    return stored, parent


def permitted(doc, user, ptype, seen):
    if ptype not in READ_TYPES:
        return False
    try:
        stored, parent = parent_record(doc)
        return can_reference(parent.doctype, parent.name, user, seen) and can_reference(stored.get("link_doctype"), stored.get("link_name"), user, seen)
    except (frappe.PermissionError, frappe.DoesNotExistError):
        return False


def validate_parent(doc):
    reject_independent(doc.doctype)
    for field in frappe.get_meta(doc.doctype).get_table_fields():
        if field.options not in EDGE_TABLES:
            continue
        for row in doc.get(field.fieldname, []) or []:
            if row.get("doctype") != field.options:
                deny()
            stored = get_record(field.options, row.get("name"))
            if stored and any(str(stored.get(key) or "") != str(value or "") for key, value in (
                ("parenttype", doc.doctype), ("parent", doc.get("name")), ("parentfield", field.fieldname),
            )):
                deny()


def guard_request(parts, args, method, values):
    targets = [args.get("doctype"), args.get("dt")]
    if parts[:2] == ["api", "resource"] and len(parts) >= 3:
        targets.append(parts[2])
    elif parts[:3] in (["api", "v1", "resource"], ["api", "v2", "document"], ["api", "v2", "doctype"], ["api", "v2", "method"]) and len(parts) >= 4:
        targets.append(parts[3])
    documents = values if isinstance(values, list) else [values]
    targets.extend(doc.get("doctype") for doc in documents if isinstance(doc, dict))
    targets.extend(doc.get("document_type") for doc in documents if isinstance(doc, dict) and doc.get("doctype") == "Bulk Update")
    for doctype in targets:
        if isinstance(doctype, str) and doctype.startswith("["):
            for member in frappe.parse_json(doctype):
                reject_independent(member)
        elif doctype in EDGE_TABLES and (frappe.local.request.method not in ("GET", "HEAD") or method and method not in READ_METHODS):
            reject_independent(doctype)


class RelationUpdate:
    def has_permission(self, permtype="read", *, debug=False, user=None):
        if permtype not in READ_TYPES:
            reject_independent(self.doctype)
        return permitted(self, user or frappe.session.user, permtype, ((self.doctype, str(self.get("name"))),)) and super().has_permission(permtype, debug=debug, user=user)

    def on_trash(self):
        reject_independent(self.doctype)


class ActivityCommunicationLink(RelationUpdate, CommunicationLink):
    pass


class ActivityDynamicLink(RelationUpdate, DynamicLink):
    pass

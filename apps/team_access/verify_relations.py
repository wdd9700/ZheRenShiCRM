from copy import deepcopy
import json
from types import SimpleNamespace
from typing import Optional


def verify_r4(h, upstream):
    from team_access import events, permissions as policy, realtime, references, relations, request

    frappe, Doc, records = h.frappe, h.Doc, h.records
    snapshot, old_meta = deepcopy(records), frappe.get_meta
    fields = {
        "Communication": [Doc(fieldname="timeline_links", options="Communication Link", fieldtype="Table", permlevel=0)],
        "CRM Call Log": [Doc(fieldname="links", options="Dynamic Link", fieldtype="Table", permlevel=0)],
        "Contact": [Doc(fieldname="links", options="Dynamic Link", fieldtype="Table", permlevel=0)],
    }
    def meta(dt):
        rows = fields.get(dt, [])
        return Doc(istable=dt in relations.EDGE_TABLES, is_virtual=0, issingle=0, is_submittable=0,
                   get_table_fields=lambda: rows, get_field=lambda name: next((row for row in rows if row.fieldname == name), None),
                   get_permlevel_access=lambda *args, **kwargs: [0])
    frappe.get_meta = meta
    frappe.session.user = "a"
    try:
        call = h.put("CRM Call Log", "r4-call", reference_doctype="CRM Lead", reference_docname="parent", note="note", links=[])
        child = h.put("Communication Link", "r4-edge", parenttype="Communication", parent="r4-comm", parentfield="timeline_links", link_doctype="CRM Call Log", link_name=call.name)
        comm = h.put("Communication", "r4-comm", reference_doctype="CRM Lead", reference_name="parent", timeline_links=[child])
        file = h.put("File", "r4-file", attached_to_doctype="CRM Call Log", attached_to_name=call.name, file_url="/private/files/r4.txt", is_private=1)
        alias = h.put("File", "r4-alias", attached_to_doctype="CRM Lead", attached_to_name="parent", file_url=file.file_url, is_private=1)
        consumers = (call, comm, file, alias)
        def private():
            from team_access import api, docinfo
            from frappe.desk.form import load

            assert all(not policy.permitted(records[(doc.doctype, doc.name)], "b") for doc in consumers)
            assert realtime.private_document(records[(comm.doctype, comm.name)])
            assert comm.name not in policy.allowed_names("Communication", "b")
            assert file.name not in policy.allowed_names("File", "b")
            user, info, get_rows = frappe.session.user, frappe.response.get("docinfo"), load._get_communications
            try:
                frappe.session.user = "b"
                frappe.response["docinfo"] = {"communications": [deepcopy(comm)], "attachments": [deepcopy(file), deepcopy(alias)]}
                docinfo.scrub("CRM Lead", "parent")
                assert not frappe.response["docinfo"]["communications"] and not frappe.response["docinfo"]["attachments"]
                load._get_communications = lambda *args, **kwargs: [deepcopy(comm)]
                assert not api.communication_activities(records[("CRM Lead", "parent")], SimpleNamespace(get_attachments=lambda *args: []))
            finally:
                frappe.session.user, frappe.response["docinfo"], load._get_communications = user, info, get_rows
        private()
        for field, value in (("note", ""), ("note", "other-note")):
            changed = deepcopy(call)
            changed[field] = value
            if value:
                h.put("FCRM Note", value, reference_doctype="CRM Lead", reference_docname="parent", custom_team_visibility="Private")
            h.forbidden(lambda: events.validate(changed))
            private()
        for source in (Doc(call, note="", reference_doctype="FCRM Note", reference_docname="note"), Doc(call, note="", links=[Doc(doctype="Dynamic Link", link_doctype="FCRM Note", link_name="note")])):
            records[(call.doctype, call.name)] = deepcopy(source)
            for change in ({"reference_doctype": "CRM Lead", "reference_docname": "parent", "links": [], "note": ""}, {"reference_doctype": "CRM Task", "reference_docname": "7", "links": [], "note": ""}):
                h.forbidden(lambda: events.validate(Doc(source, **change)))
            events.validate(Doc(source, status="Completed"))
        records[(call.doctype, call.name)] = deepcopy(call)
        added = Doc(call, links=[Doc(doctype="Dynamic Link", link_doctype="CRM Task", link_name="7")])
        h.forbidden(lambda: events.validate(added))
        assert references.private_roots(doc=added) == {("FCRM Note", "note"), ("CRM Task", "7")}
        fresh = Doc(added, name="r5-first-call")
        events.validate(fresh)
        h.native_denied.add(("CRM Task", "7", "a", "write"))
        h.forbidden(lambda: events.validate(added))
        h.native_denied.clear()
        h.native_denied.add(("FCRM Note", "note", "a", "write"))
        h.forbidden(lambda: events.validate(Doc(call, status="Completed")))
        h.native_denied.clear()
        forged = Doc(child, parenttype="Contact", parent="r4-contact", parentfield="links", link_doctype="CRM Lead", link_name="parent")
        assert policy.permitted(child, "a") and not policy.permitted(forged, "b")
        assert relations.parent_record(forged)[1].name == comm.name
        for key in ("parent", "parenttype", "parentfield"):
            before = child.get(key)
            child[key] = "missing"
            assert not policy.permitted(child, "a")
            child[key] = before
        for dt, row in (("Communication Link", child), ("Dynamic Link", h.put("Dynamic Link", "r4-dynamic", parenttype=call.doctype, parent=call.name, parentfield="links", link_doctype="FCRM Note", link_name="note"))):
            for user in ("a", "b", "Administrator"):
                frappe.session.user = user
                for action in (lambda: events.validate(Doc(row, parent="forged")), lambda: events.on_trash(row), lambda: policy.has_permission(row, "write"), lambda: events.validate_integrity(row)):
                    h.forbidden(action)
                for path in (f"/api/resource/{dt}/{row.name}", f"/api/v1/resource/{dt}/{row.name}", f"/api/v2/document/{dt}/{row.name}"):
                    for verb in ("POST", "PUT", "PATCH", "DELETE"):
                        frappe.local.request = SimpleNamespace(path=path, method=verb)
                        frappe.form_dict = Doc(parent="forged")
                        h.forbidden(request.guard)
                for method, args in (
                    ("frappe.client.save", {"doc": json.dumps(forged)}),
                    ("frappe.client.insert", {"doc": {"doctype": dt, "parent": "forged"}}),
                    ("frappe.client.insert_many", {"docs": [{"doctype": "Contact"}, {"doctype": dt}]}),
                    ("frappe.client.bulk_update", {"docs": json.dumps([{"doctype": "Contact"}, {"doctype": dt, "docname": row.name}])}),
                    ("frappe.client.set_value", {"doctype": dt, "name": row.name, "fieldname": "link_name", "value": "parent"}),
                    ("frappe.client.delete", {"doctype": dt, "name": row.name}),
                    ("frappe.desk.reportview.delete_items", {"doctype": dt, "items": [row.name]}),
                    ("frappe.desk.doctype.bulk_update.bulk_update.submit_cancel_or_update_docs", {"doctype": dt, "docnames": [row.name], "action": "update"}),
                    ("run_doc_method", {"docs": {"doctype": "Bulk Update", "document_type": dt}}),
                ):
                    frappe.local.request = SimpleNamespace(path="/api/method/" + method, method="POST")
                    frappe.form_dict = Doc(args)
                    h.forbidden(request.guard)
        frappe.session.user = "a"
        contact = h.put("Contact", "r4-contact", links=[])
        stolen = Doc(contact, links=[Doc(child, doctype="Dynamic Link")])
        h.put("Dynamic Link", child.name, parenttype=call.doctype, parent=call.name, parentfield="links", link_doctype="CRM Lead", link_name="parent")
        h.forbidden(lambda: events.validate(stolen))
        events.validate(Doc(contact, links=[Doc(doctype="Dynamic Link", link_doctype="CRM Lead", link_name="parent")]))
        from team_access import deleted

        for dt in relations.EDGE_TABLES:
            snapshot_doc = Doc(deleted_doctype=dt, deleted_name="old-child", data=json.dumps({"doctype": dt, "name": "old-child", "parenttype": "Communication", "parent": comm.name, "parentfield": "timeline_links"}))
            assert not any(deleted.permitted_snapshot(snapshot_doc, user) for user in ("a", "b", "Administrator"))
        private()
        print("PASS R4 unified graph provenance with R5 existing-root freeze: Call main/note/links removal, replacement and addition denied; stored parent/type/field child authority and all-user REST/client/bulk independent mutation denial; snapshots denied, parent docinfo/activity copies and File aliases stay private, ordinary Contact parent validation preserved")
        from verify_transitions import verify_freeze

        verify_freeze(h)
        if upstream:
            verify_native(h, upstream, meta, private)
    finally:
        records.clear()
        records.update(snapshot)
        frappe.get_meta = old_meta
        frappe.session.user = "a"
        h.native_denied.clear()


def verify_native(h, upstream, meta, consumers):
    from team_access import events, permissions as policy, relations, request

    frappe, Doc, records = h.frappe, h.Doc, h.records
    root = upstream / "apps/frappe/frappe"
    trace = []
    original_get, original_db = frappe.get_doc, frappe.db
    original_model = getattr(frappe, "model", None)
    original_client = getattr(frappe, "client", None)
    original_qb = getattr(frappe, "qb", None)
    class Field:
        def __init__(self, key):
            self.key = key
        def __eq__(self, value):
            return lambda row: row.get(self.key) == value
        def notin(self, values):
            return lambda row: row.get(self.key) not in values
    class Table:
        def __init__(self, doctype):
            self.doctype = doctype
        def __getattr__(self, key):
            return Field(key)
    class Query:
        def __init__(self, table):
            self.table, self.conditions = table, []
        def where(self, condition):
            self.conditions.append(condition)
            return self
        def delete(self):
            return self
        def run(self):
            trace.append("child_delete_query:" + self.table.doctype)
            for key, row in list(records.items()):
                if key[0] == self.table.doctype and all(condition(row) for condition in self.conditions):
                    del records[key]
    frappe.qb = SimpleNamespace(DocType=Table, from_=Query)
    sequence = []
    def name_child(doc):
        sequence.append(1)
        doc.name = "r4-new-" + str(len(sequence))
    native = {"frappe": frappe, "Optional": Optional, "set_new_name": name_child}
    h.load_native(root / "model/document.py", {"insert", "check_permission", "save", "_save", "run_before_save_methods", "update_children", "update_child_table", "set_parent_in_children", "set_name_in_children"}, native, "Document")

    class Saved(Doc):
        insert, check_permission = native["insert"], native["check_permission"]
        save, _save = native["save"], native["_save"]
        run_before_save_methods = native["run_before_save_methods"]
        update_children, update_child_table = native["update_children"], native["update_child_table"]
        set_parent_in_children, set_name_in_children = native["set_parent_in_children"], native["set_name_in_children"]
        def __delattr__(self, key):
            self.pop(key, None)
        def set(self, key, value):
            self[key] = value
        def update(self, values):
            dict.update(self, values)
            for field in meta(self.doctype).get_table_fields():
                if field.fieldname in values:
                    self[field.fieldname] = [child_classes[field.options](dict(row, doctype=field.options, parentfield=field.fieldname)) for row in self.get(field.fieldname, [])]
        @property
        def docstatus(self):
            return Doc(is_cancelled=lambda: False)
        def has_permission(self, ptype="read", **kwargs):
            return self.doctype not in policy.PROTECTED or policy.permitted(records.get((self.doctype, self.name), self), frappe.session.user, ptype)
        def _handle_permission_failure(self, ptype):
            raise frappe.PermissionError()
        def get_all_children(self):
            return [row for field in self.meta.get_table_fields() for row in self.get(field.fieldname, [])]
        def run_method(self, method):
            trace.append(method)
            if method == "validate" and self.get("_controller_mutation"):
                self.update(self._controller_mutation)
            if method == "before_save" and self.get("_before_save_mutation"):
                self.update(self._before_save_mutation)
            if method in ("before_validate", "validate"):
                events.validate(self)
            if method in ("before_save", "before_submit", "before_cancel", "before_update_after_submit"):
                events.validate_integrity(self)
            if method == "on_trash":
                if self.doctype in relations.EDGE_TABLES:
                    self.on_trash()
                events.on_trash(self)
        def db_update(self):
            trace.append("db_update:" + self.doctype)
            fields = {key: deepcopy(value) for key, value in self.items() if key not in ("meta", "flags", "_action", "_controller_mutation")}
            records[(self.doctype, self.name)] = Doc(fields)
        def as_dict(self):
            return dict(self)
        def getone(self, filters):
            return next(row for row in self.get_all_children() if all(row.get(key) == value for key, value in filters.items()))
        def remove(self, row):
            self[row.parentfield].remove(row)
        def clear_cache(self):
            trace.append("cache")
    for name in ("check_if_locked", "_set_defaults", "set_user_and_timestamp", "set_docstatus", "check_if_latest", "validate_higher_perm_levels", "_validate_links", "_validate", "reset_seen", "set_title_field", "apply_fieldlevel_read_permissions"):
        setattr(Saved, name, lambda self: None)
    Saved.run_post_save_methods = lambda self: trace.append("post_save")
    child_classes = {}
    for dt, slug, name in (("Communication Link", "communication_link", "CommunicationLink"), ("Dynamic Link", "dynamic_link", "DynamicLink")):
        ns = {"Document": Saved}
        h.load_native(root / f"core/doctype/{slug}/{slug}.py", {name}, ns)
        child_classes[dt] = type("Protected" + name, (relations.RelationUpdate, ns[name]), {})
    def get_doc(dt, name=None, **kwargs):
        data = deepcopy(dt if isinstance(dt, dict) else records[(dt, str(name))])
        doc = child_classes.get(data["doctype"], Saved)(data)
        doc.flags, doc.meta, doc._action = Doc(), meta(doc.doctype), "save"
        for field in doc.meta.get_table_fields():
            doc[field.fieldname] = [child_classes[field.options](dict(row, doctype=field.options, parentfield=field.fieldname)) for row in doc.get(field.fieldname, [])]
        return doc
    frappe.get_doc = get_doc
    frappe.flags.in_test = False
    frappe.model = SimpleNamespace(default_fields=[], child_table_fields=[])
    frappe.db = SimpleNamespace(**vars(original_db))
    frappe.db.get_value = lambda dt, name, fields=None, as_dict=False, **kwargs: Doc({field: records[(dt, name)].get(field) for field in fields}) if as_dict and isinstance(fields, (tuple, list)) else tuple(records[(dt, name)].get(field) for field in fields) if isinstance(fields, (tuple, list)) else None
    versions = []
    for api in ("v1", "v2"):
        ns = {"frappe": frappe, "get_request_form_data": lambda: frappe.form_dict}
        h.load_native(root / f"api/{api}.py", {"update_doc", "delete_doc"}, ns)
        versions.append(ns)
    client = {"frappe": frappe, "json": json, "Any": object}
    h.load_native(root / "client.py", {"save", "delete_doc", "set_value", "bulk_update"}, client)
    permissions = {"frappe": frappe, "_": lambda value: value, "has_permission": lambda *args, **kwargs: True, "push_perm_check_log": lambda *args, **kwargs: None}
    h.load_native(root / "permissions.py", {"has_child_permission"}, permissions)
    deletion = {"frappe": frappe, "_": lambda value: value, "is_virtual_doctype": lambda dt: False, "delete_all_passwords_for": lambda *args: None, "update_flags": lambda *args: None, "check_permission_and_not_submitted": lambda doc: permissions["has_child_permission"](doc.doctype, "delete", doc, user="a")}
    for name in ("check_if_doc_is_linked", "check_if_doc_is_dynamically_linked", "update_naming_series", "delete_from_table", "remove_all", "delete_for_document", "delete_tags_for_document", "add_to_deleted_document", "insert_feed"):
        deletion[name] = lambda *args, _name=name, **kwargs: trace.append(_name)
    h.load_native(root / "model/delete_doc.py", {"delete_doc", "check_permission_and_not_submitted"}, deletion)
    frappe.client = SimpleNamespace(delete_doc=client["delete_doc"])
    frappe.is_table = lambda dt: dt in relations.EDGE_TABLES
    def call_update(api, changes, dt="CRM Call Log", name="r4-call"):
        frappe.form_dict = Doc(deepcopy(changes))
        trace.clear()
        return api["update_doc"](dt, name)
    old_traceback = getattr(frappe.utils, "get_traceback", None)
    frappe.utils.get_traceback = lambda: "replacement store denied"
    bulk = {"frappe": frappe, "_": lambda value: value}
    h.load_native(root / "desk/doctype/bulk_update/bulk_update.py", {"_bulk_action"}, bulk)
    frappe.db.commit = lambda: trace.append("commit")
    frappe.db.rollback = lambda: trace.append("rollback")
    frappe.log_error = lambda *args: trace.append("log_error")
    frappe.publish_progress = lambda **kwargs: trace.append("progress")
    try:
        dynamic = records[("Dynamic Link", "r4-dynamic")]
        dynamic.link_doctype, dynamic.link_name = "CRM Task", "7"
        records[("CRM Call Log", "r4-call")].links = [deepcopy(dynamic)]
        for api in versions:
            for changes in ({"note": ""}, {"note": "", "links": []}, {"note": "other-note"}, {"_controller_mutation": {"note": ""}}, {"_before_save_mutation": {"note": ""}}):
                h.forbidden(lambda: call_update(api, changes))
                assert not any(item.startswith("db_update") for item in trace) and "post_save" not in trace
                consumers()
            call_update(api, {"status": "Completed"})
            assert trace.index("validate") < trace.index("db_update:CRM Call Log") < trace.index("db_update:Dynamic Link") < trace.index("post_save")
        child = records[("Communication Link", "r4-edge")]
        assert permissions["has_child_permission"]("Communication Link", "delete", get_doc(child), user="a", parent_doctype="forged")
        for dt in relations.EDGE_TABLES:
            for user in ("a", "Administrator"):
                frappe.session.user = user
                trace.clear()
                pending = get_doc(Doc(doctype=dt, parent="forged", parenttype="Contact", parentfield="links"))
                h.forbidden(lambda: pending.insert(ignore_permissions=True))
                assert not trace
        frappe.session.user = "a"
        for user in ("a", "Administrator"):
            frappe.session.user = user
            trace.clear()
            h.forbidden(lambda: deletion["delete_doc"]("Communication Link", child.name))
            assert trace == (["on_trash"] if user == "Administrator" else [])
        frappe.session.user = "a"
        assert child.name in policy.allowed_names("Communication Link", "a")
        for dt, name in (("Communication Link", child.name), ("Dynamic Link", "r4-dynamic")):
            for api in versions:
                for changes in ({"link_name": "parent"}, {"parent": "r4-contact", "parenttype": "Contact", "parentfield": "links"}):
                    h.forbidden(lambda: call_update(api, changes, dt, name))
                    assert not any(item.startswith("db_update") for item in trace)
            h.forbidden(lambda: client["delete_doc"](dt, name))
            h.forbidden(lambda: client["set_value"](dt, name, "link_name", "parent"))
        h.forbidden(lambda: client["save"](dict(records[("CRM Call Log", "r4-call")], note="")))
        assert client["bulk_update"](json.dumps([{"doctype": "CRM Call Log", "docname": "r4-call", "note": ""}]))["failed_docs"]
        for dt, name, changes in (("CRM Call Log", "r4-call", {"note": ""}), ("Communication Link", child.name, {"link_name": "parent"}), ("Dynamic Link", "r4-dynamic", {"parent": "r4-contact"})):
            trace.clear()
            assert bulk["_bulk_action"](dt, [name], "update", changes) == [name]
            assert "rollback" in trace and "commit" not in trace and not any(item.startswith("db_update") for item in trace)
        print("PASS fixed v1/v2 PUT -> complete Document._save/run_before_save_methods/update_children: graph loss and post-controller loss denied before DB; fixed has_child_permission accepts native parent delete but delete_doc child guard denies before delete/queue; actual child insert and native client save/delete/set_value/bulk plus Desk bulk loss denied")
        for dt, field, child_dt in (("Contact", "links", "Dynamic Link"), ("CRM Call Log", "links", "Dynamic Link"), ("Communication", "timeline_links", "Communication Link")):
            name = "r4-ordinary-" + dt
            h.put(dt, name, reference_doctype="CRM Lead", reference_name="parent", reference_docname="parent", **{field: []})
            call_update(versions[0], {field: [Doc(doctype=child_dt, link_doctype="CRM Lead", link_name="parent")]}, dt, name)
            rows = records[(dt, name)][field]
            assert len(rows) == 1 and records[(child_dt, rows[0].name)].parent == name
            assert trace.count("before_validate") == 1 and "db_update:" + child_dt in trace
            call_update(versions[1], {field: []}, dt, name)
            assert not records[(dt, name)][field] and (child_dt, rows[0].name) not in records
        borrowed = deepcopy(records[("Dynamic Link", "r4-dynamic")])
        for field in ("parent", "parenttype", "parentfield"):
            borrowed[field] = "forged"
        h.forbidden(lambda: call_update(versions[0], {"links": [borrowed]}, "Contact", "r4-contact"))
        assert not any(item.startswith("db_update") for item in trace)
        for api in versions:
            h.forbidden(lambda: call_update(api, {"timeline_links": []}, "Communication", "r4-comm"))
        old_call = deepcopy(records[("CRM Call Log", "r4-call")])
        for form in (Doc(old_call, note="", links=[], reference_doctype="FCRM Note", reference_docname="note"), Doc(old_call, note="", links=[Doc(doctype="Dynamic Link", link_doctype="FCRM Note", link_name="note")])):
            records[("CRM Call Log", "r4-call")] = form
            h.forbidden(lambda: call_update(versions[0], {"reference_doctype": "CRM Lead", "reference_docname": "parent", "links": []}))
            assert not any(item.startswith("db_update") for item in trace)
        records[("CRM Call Log", "r4-call")] = old_call
        links = deepcopy(old_call.links)
        h.forbidden(lambda: call_update(versions[0], {"links": [*links, Doc(doctype="Dynamic Link", link_doctype="FCRM Note", link_name="other-note")]}))
        call_update(versions[1], {"links": links})
        consumers()
        trace.clear()
        assert bulk["_bulk_action"]("CRM Call Log", ["r4-ordinary-CRM Call Log"], "update", {"status": "Completed"}) == []
        assert "commit" in trace and "db_update:CRM Call Log" in trace
        print("PASS actual fixed parent save/child-table sync allows ordinary Contact/Call/Communication association create and remove without independent child hooks; ordinary Call bulk persists; stored ownership prevents normalized child theft; main/note/links loss, addition and combined mutations denied, unchanged private roots still save")
        from verify_transitions import verify_native as verify_native_freeze

        verify_native_freeze(h, upstream, Saved, native, get_doc, versions, trace)
    finally:
        frappe.get_doc, frappe.db = original_get, original_db
        frappe.model, frappe.client, frappe.qb = original_model, original_client, original_qb
        frappe.utils.get_traceback = old_traceback

from contextlib import contextmanager
from copy import deepcopy
import inspect
import json
import re
import sys
import types
from urllib.parse import quote


TYPES = {"FCRM Note": ("fcrm_note", "FCRMNote", "content"), "CRM Task": ("crm_task", "CRMTask", "description"), "CRM Lead": ("crm_lead", "CRMLead", "lead_name"), "CRM Deal": ("crm_deal", "CRMDeal", "organization")}


@contextmanager
def environment(h, upstream=None):
    frappe, Doc = h.frappe, h.Doc
    saved_records = deepcopy(h.records)
    saved_modules = {name: (module, dict(vars(module))) for name, module in sys.modules.items() if name in ("frappe", "crm") or name.startswith(("frappe.", "crm."))}
    try:
        h.records.clear()
        frappe.session = types.SimpleNamespace(user="b")
        frappe.local = types.SimpleNamespace(response={})
        frappe.db = types.SimpleNamespace(**vars(frappe.db))
        controllers, metas, fixtures, saved_views, queries, loads = {}, {}, {}, {}, [], []
        for dt, (slug, cls, body) in TYPES.items():
            methods = {"default_list_data": staticmethod(lambda body=body: {"rows": ["name", body, "status", "_assign"], "columns": [{"key": body, "label": "Body"}]})}
            if upstream:
                namespace = {"_": lambda value: value}
                names = {"default_list_data"} | ({"default_kanban_settings"} if dt != "FCRM Note" else set())
                h.load_native(upstream / f"apps/crm/crm/fcrm/doctype/{slug}/{slug}.py", names, namespace, cls)
                methods = {name: namespace[name] for name in names}
            controller = controllers[dt] = type(cls, (), methods)
            defaults = controller.default_list_data()
            permitted = set(defaults["rows"]) | {body, "title", "status", "name", "owner", "creation", "modified", "modified_by", "reference_doctype", "reference_docname"}
            if hasattr(controller, "default_kanban_settings"):
                kanban = controller.default_kanban_settings()
                permitted.update(json.loads(kanban["kanban_fields"]))
                permitted.add(kanban["title_field"])
            permitted -= {"_assign", "_liked_by", "_seen", "_user_tags"}
            fields = [Doc(fieldname=name, label=name, fieldtype="Data", options="", hidden=0) for name in sorted(permitted | {"permission_denied"})]
            metas[dt] = Doc(fields=fields, track_seen=1, default_fields=["name", "owner", "creation", "modified", "modified_by"], get_field=lambda name, fields=fields: next((field for field in fields if field.fieldname == name), None), get_table_fields=lambda: [], get_high_permlevel_fields=lambda: [], get_permlevel_access=lambda **kwargs: [0], get_valid_columns=lambda permitted=permitted: list(permitted | {"_assign", "_liked_by", "_seen", "_user_tags"}), get_permitted_fieldnames=lambda permitted=permitted, **kwargs: list(permitted), istable=0)
            values = {body: "Visible current " + dt, "title": "Visible title", "status": "Open", "custom_team_visibility": "Shared", "custom_team_collaborator": "", "_assign": '["history-assignee"]', "_liked_by": '["history-liker"]', "_seen": '["history-viewer"]', "permission_denied": "role-hidden"}
            if dt in ("FCRM Note", "CRM Task"):
                values.update(reference_doctype="CRM Lead", reference_docname="r7-crm-lead")
            fixtures[dt] = h.put(dt, "r7-" + slug.replace("_", "-"), **values)
        h.put("ToDo", "r7-legacy", reference_type="FCRM Note", reference_name=fixtures["FCRM Note"].name, allocated_to="history-assignee", description="Old private assignment")
        h.put("FCRM Note", "r7-private", content="Never publish", reference_doctype="CRM Lead", reference_docname=fixtures["CRM Lead"].name, custom_team_visibility="Private")
        frappe.get_meta = lambda dt: metas[dt]
        frappe.only_has_select_perm = lambda *args, **kwargs: False
        frappe.is_table = lambda dt: False
        frappe.db.exists = lambda dt, key: bool(saved_views) if dt == "CRM View Settings" else (dt, str(key)) in h.records
        frappe.db.get_value = lambda *args, **kwargs: False
        def get_doc(dt, key):
            if dt == "CRM View Settings":
                loads.append(deepcopy(key))
                return deepcopy(saved_views[key["dt"]])
            return deepcopy(h.records[(dt, str(key))])
        frappe.get_doc = get_doc
        h.module("frappe.model.document", get_controller=lambda dt: controllers[dt])
        model = h.module("frappe.model", optional_fields=("_user_tags", "_assign", "_liked_by", "_seen"), default_fields=("name", "owner", "creation", "modified", "modified_by"))
        model.get_permitted_fields = lambda dt, **kwargs: [*metas[dt].default_fields, *model.optional_fields, *metas[dt].get_permitted_fieldnames()]
        rv = {"frappe": frappe, "json": json, "_": lambda value: value, "default_fields": model.default_fields, "optional_fields": model.optional_fields, "child_table_fields": [], "get_permitted_fields": model.get_permitted_fields}
        def extract(field):
            value = re.split(r"\s+as\s+", field, flags=re.IGNORECASE)[0]
            if "(" in value:
                value = value.split("(", 1)[1].rstrip(")")
            return [value.rsplit(".", 1)[-1].strip("`")]
        rv["extract_fieldnames"] = extract
        if upstream:
            model_ns = {"frappe": frappe, "CORE_DOCTYPES": set(), "DEFAULT_FIELDS": set(model.default_fields), "optional_fields": model.optional_fields, "child_table_fields": []}
            h.load_native(upstream / "apps/frappe/frappe/model/__init__.py", {"get_permitted_fields"}, model_ns)
            model.get_permitted_fields = rv["get_permitted_fields"] = model_ns["get_permitted_fields"]
            h.load_native(upstream / "apps/frappe/frappe/desk/reportview.py", {"validate_args", "parse_json", "setup_group_by", "validate_fields", "validate_filters", "is_standard", "get_meta_and_docfield", "get_parenttype_and_fieldname", "update_wildcard_field_param", "raise_invalid_field"}, rv)
        h.module("frappe.desk.reportview", extract_fieldnames=extract)
        field_ns = {"frappe": frappe, "get_permitted_fields": model.get_permitted_fields, "OPTIONAL_FIELDS": set(model.optional_fields), "wrap_grave_quotes": lambda table: "`" + table + "`"}
        if upstream:
            h.load_native(upstream / "apps/frappe/frappe/model/db_query.py", {"apply_fieldlevel_read_permissions", "remove_field"}, field_ns, "DatabaseQuery")
        def get_list(doctype, fields=None, filters=None, pluck=None, **kwargs):
            selected = deepcopy(fields or [pluck or "name"])
            if upstream:
                query = Doc(doctype=doctype, parent_doctype=None, fields=selected, permission_map={doctype: "read"}, flags=Doc(ignore_permissions=False), as_list=False, linked_table_aliases={}, query_tables=[])
                query.remove_field = types.MethodType(field_ns["remove_field"], query)
                field_ns["apply_fieldlevel_read_permissions"](query)
                selected = query.fields
            queries.append((doctype, deepcopy(selected), deepcopy(filters)))
            rows = h.get_all(doctype, filters=frappe.parse_json(filters) or {})
            if pluck:
                return [row.get(pluck) for row in rows]
            if any(field.lower().startswith("count(") for field in selected):
                return [Doc(total_count=len(rows))]
            result = []
            for row in rows:
                projected = Doc()
                for field in selected:
                    parts = re.split(r"\s+as\s+", field, flags=re.IGNORECASE)
                    key = parts[-1].strip("`") if len(parts) > 1 else extract(field)[0]
                    projected[key] = row.get(extract(field)[0])
                result.append(projected)
            return result
        frappe.get_list = get_list
        yield Doc(frappe=frappe, fixtures=fixtures, saved_views=saved_views, controllers=controllers, rv=rv, queries=queries, loads=loads)
    finally:
        h.records.clear()
        h.records.update(saved_records)
        for name in tuple(sys.modules):
            if (name in ("frappe", "crm") or name.startswith(("frappe.", "crm."))) and name not in saved_modules:
                del sys.modules[name]
        for name, (module, values) in saved_modules.items():
            sys.modules[name] = module
            vars(module).clear()
            vars(module).update(values)


def guard(h, path, args):
    h.frappe.local = types.SimpleNamespace(request=h.Doc(path=path, method="GET"), response={})
    h.frappe.form_dict = deepcopy(args)
    h.frappe.local.form_dict = h.frappe.form_dict
    from team_access.request import guard as before_request
    before_request()
    return h.frappe.form_dict


def run(h, upstream=None):
    from team_access import projections

    with environment(h) as env:
        dt = "FCRM Note"
        for payload in ({"rows": ["_assign as history"]}, {"columns": [{"key": "_seen as history"}]}, {"view": {"view_type": "group_by", "group_by_field": "_assign"}}, {"kanban_fields": ["_liked_by as history"]}, {"column_field": "_assign"}, {"title_field": "_seen"}):
            h.forbidden(lambda payload=payload: projections.prepare(dt, payload, {}, "modified desc"))
        options, defaults = projections.prepare(dt, {}, {}, "modified desc")
        assert "content" in options["rows"] and "_assign" not in options["rows"] and defaults[0]
        env.saved_views[dt] = h.Doc(rows='["name", "content", "_assign"]', columns='[{"key":"content","label":"Body"}]')
        options, defaults = projections.prepare(dt, {}, {}, "modified desc")
        assert options["rows"] == ["name", "content"] and defaults[0] is False
        env.saved_views[dt].rows = '["_assign as history"]'
        h.forbidden(lambda: projections.prepare(dt, {}, {}, "modified desc"))
        assert projections.prepare(dt, {"rows": ["name", "content"], "view": {"view_type": "group_by", "group_by_field": "title"}}, {}, "title asc")[0]["view"]["group_by_field"] == "title"
    print("PASS R7 resolved CRM request/default/saved projections: raw aliases and group/kanban selectors denied before query, canonical legacy default caches removed without deleting settings, body and legal grouping retained")
    if upstream:
        verify_crm(h, upstream)
        verify_rest(h, upstream)


def verify_crm(h, upstream):
    from team_access import api, docinfo, permissions as policy, responses

    with environment(h, upstream) as env:
        frappe, Doc = h.frappe, h.Doc
        namespace = {"frappe": frappe, "json": json, "_": lambda value: value, "get_controller": lambda dt: env.controllers[dt], "no_value_fields": [], "COUNT_NAME": "count(name) as total_count", "get_views": lambda dt: [], "get_form_script": lambda *args: None, "set_activity_counts": lambda *args: None, "make_filter_tuple": lambda dt, key, value: [dt, key, *(value if isinstance(value, list) else ["=", value])]}
        h.load_native(upstream / "apps/crm/crm/api/doc.py", {"get_data", "parse_list_data", "convert_filter_to_tuple", "get_records_based_on_order"}, namespace)
        h.module("crm.api.doc", get_data=namespace["get_data"])
        note = env.fixtures["FCRM Note"]
        assert policy.permitted(note, "b") and not policy.permitted(note, "b", "write") and not policy.permitted(h.records[("ToDo", "r7-legacy")], "b")
        assert docinfo.get_assigned_users(note.doctype, note.name) == []
        def call(dt, **kwargs):
            args = Doc(doctype=dt, filters={"name": env.fixtures[dt].name}, order_by="modified desc")
            args.update(kwargs)
            args = guard(h, "/api/method/crm.api.doc.get_data", args)
            return responses.sanitize(api.get_data(**args), True)
        raw_rows = ["name", "content", "_assign as history_assignment", "_liked_by as history_liker", "_seen as history_viewer"]
        old = responses.sanitize(namespace["get_data"]("FCRM Note", {"name": note.name}, "modified desc", rows=raw_rows, columns=[{"key": "content", "label": "Body"}]), True)
        assert all(marker in json.dumps(old) for marker in ("history-assignee", "history-liker", "history-viewer"))
        old_group = responses.sanitize(namespace["get_data"]("FCRM Note", {"name": note.name}, "modified desc", rows=["name", "content"], columns=[{"key": "content", "label": "Body"}], view={"view_type": "group_by", "group_by_field": "_assign"}), True)
        assert "history-assignee" in json.dumps(old_group["group_by_field"]["options"])
        for payload in ({"rows": raw_rows}, {"columns": [{"key": "_liked_by as history", "label": "History"}]}, {"view": {"view_type": "group_by", "group_by_field": "_assign"}}, {"view": {"view_type": "kanban"}, "column_field": "_assign"}, {"view": {"view_type": "kanban"}, "title_field": "_seen"}, {"view": {"view_type": "kanban"}, "kanban_fields": ["_assign as history"]}, {"default_filters": {"_seen": "history-viewer"}}, {"order_by": "_assign asc"}):
            before = len(env.queries)
            if "order_by" in payload:
                h.forbidden(lambda: call("FCRM Note", **payload))
            else:
                h.forbidden(lambda payload=payload: call("FCRM Note", **payload))
            assert len(env.queries) == before
        for dt, (_, _, body) in TYPES.items():
            for kwargs in ({}, {"rows": ["name", body, "permission_denied"], "columns": [{"key": body, "label": "Body"}]}, {"rows": ["*"]}, {"rows": json.dumps(["name", body]), "view": "{\"view_type\":\"list\"}"}):
                data = call(dt, **kwargs)
                assert env.fixtures[dt][body] in json.dumps(data["data"])
                assert all(marker not in json.dumps(data) for marker in ("history-assignee", "history-liker", "history-viewer", "role-hidden"))
                assert not set(data["rows"]) & set(responses.RAW_FIELDS)
            grouped = call(dt, rows=["name", body], columns=[{"key": body, "label": "Body"}], view={"view_type": "group_by", "group_by_field": body})
            assert env.fixtures[dt][body] in grouped["group_by_field"]["options"]
            for kwargs in ({"rows": ["name", body], "title_field": body, "kanban_fields": [body]}, {}):
                kanban = call(dt, column_field="status", kanban_columns=[{"name": "Open"}], view={"view_type": "kanban"}, **kwargs)
                assert env.fixtures[dt][body] in json.dumps(kanban["data"]) and "history-assignee" not in json.dumps(kanban)
            env.saved_views[dt] = Doc(rows=json.dumps(["name", body, "_assign"]), columns=json.dumps([{"key": body, "label": "Body"}, {"key": "_assign", "label": "Old cache"}]))
            before = len(env.loads)
            saved = call(dt)
            assert env.fixtures[dt][body] in json.dumps(saved["data"]) and saved["is_default"] is False and len(env.loads) == before + 1
            saved_group = call(dt, view={"view_type": "group_by", "group_by_field": body})
            assert env.fixtures[dt][body] in saved_group["group_by_field"]["options"]
            for key in ("rows", "columns"):
                env.saved_views[dt] = Doc(rows=json.dumps(["name", body]), columns=json.dumps([{"key": body, "label": "Body"}]))
                env.saved_views[dt][key] = json.dumps(["name", "_assign as history"]) if key == "rows" else json.dumps([{"key": "_seen as history", "label": "History"}])
                before = len(env.queries)
                h.forbidden(lambda dt=dt: call(dt))
                assert len(env.queries) == before
            env.saved_views.clear()
        assert note._assign and ("ToDo", "r7-legacy") in h.records
    print("PASS R7 full fixed CRM get_data/parse_list_data + native field-read permissions -> sanitizer: native raw-alias/group-options leakage baseline; current all-selector and loaded-view denials precede query; Note/Task/Lead/Deal body/default/bare/explicit/field-permission/group/kanban/saved-view positives survive")


def verify_rest(h, upstream):
    from team_access import responses

    with environment(h, upstream) as env:
        frappe, Doc = h.frappe, h.Doc
        client_ns = {"frappe": frappe, "Any": object, "validate_args": env.rv["validate_args"], "check_parent_permission": lambda *args: None}
        h.load_native(upstream / "apps/frappe/frappe/client.py", {"get_list"}, client_ns)
        h.module("frappe.client", get_list=client_ns["get_list"])
        frappe.call = lambda fn, *args, **kwargs: fn(*args, **{key: value for key, value in kwargs.items() if key in inspect.signature(fn).parameters})
        adapters = {}
        for version in ("v1", "v2"):
            namespace = {"frappe": frappe, "json": json, "sbool": lambda value: str(value).lower() in ("1", "true")}
            h.load_native(upstream / f"apps/frappe/frappe/api/{version}.py", {"document_list"}, namespace)
            adapters[version] = namespace["document_list"]
        completed = 0
        for dt, (_, _, body) in TYPES.items():
            for prefix, version in (("/api/resource/", "v1"), ("/api/v1/resource/", "v1"), ("/api/v2/document/", "v2")):
                path = prefix + quote(dt, safe="")
                for fields in ('["*"]', json.dumps(["name", body, "permission_denied"]), None):
                    args = Doc()
                    if fields is not None:
                        args.fields = fields
                    args = guard(h, path, args)
                    if fields is not None:
                        assert isinstance(args.fields, str) and "*" not in json.loads(args.fields)
                        assert not set(json.loads(args.fields)) & set(responses.RAW_FIELDS)
                    result = responses.sanitize(adapters[version](dt), True)
                    text = json.dumps(result)
                    assert result and "r7-private" not in text and all(marker not in text for marker in ("history-assignee", "history-liker", "history-viewer", "role-hidden"))
                    if fields is not None:
                        assert env.fixtures[dt][body] in text
                    else:
                        assert set(result[0]) == {"name"}
                    completed += 1
                before = len(env.queries)
                h.forbidden(lambda: guard(h, path, Doc(fields='["_assign as history"]')))
                assert len(env.queries) == before
        assert completed == 36
    print("PASS R7 guard -> fixed v1/explicit-v1/v2 document_list -> full client.get_list/reportview validation -> native field permissions -> replacement query: 36 Note/Task/Lead/Deal bare/explicit/default positives, JSON string contract retained, private/raw/role-hidden negatives")

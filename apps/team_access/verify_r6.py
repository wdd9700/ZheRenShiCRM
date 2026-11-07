from copy import deepcopy
import csv
import io
import json
import sys
import types


def run(h, upstream=None):
    from team_access import docinfo, events, permissions as policy, request, responses

    frappe, Doc, records = h.frappe, h.Doc, h.records
    saved_records = deepcopy(records)
    saved_modules = {name: (module, dict(vars(module))) for name, module in sys.modules.items() if name == "frappe" or name.startswith("frappe.")}
    try:
        records.clear()
        frappe.session = types.SimpleNamespace(user="a")
        frappe.local = types.SimpleNamespace(lang="en")
        frappe.db = types.SimpleNamespace(**vars(frappe.db))
        frappe.db.is_table_missing = frappe.db.is_missing_column = lambda error: False
        names = ("name", "owner", "title", "content", "_assign", "_liked_by", "_seen", "_user_tags")
        fields = [Doc(fieldname=name, name=name, label=name, fieldtype="Data") for name in names]
        meta = Doc(default_fields=["name", "owner"], get_valid_columns=lambda: list(names), get_permitted_fieldnames=lambda **kwargs: ["title", "content"], get_field=lambda name: next((row for row in fields if row.name == name), None), get_table_fields=lambda: [], istable=0, issingle=0)
        frappe.get_meta = lambda dt: meta
        frappe.only_has_select_perm = lambda *args, **kwargs: False
        frappe.as_unicode = str
        model = h.module("frappe.model", optional_fields=("_user_tags", "_assign", "_liked_by", "_seen"), default_fields=("name", "owner"))
        model.get_permitted_fields = lambda dt, **kwargs: ["name", "owner", "_user_tags", "_assign", "_liked_by", "_seen", "title", "content"]
        if upstream:
            namespace = {"frappe": frappe, "CORE_DOCTYPES": set(), "DEFAULT_FIELDS": {"name", "owner"}, "optional_fields": model.optional_fields, "child_table_fields": []}
            h.load_native(upstream / "apps/frappe/frappe/model/__init__.py", {"get_permitted_fields"}, namespace)
            model.get_permitted_fields = namespace["get_permitted_fields"]

        parent = h.put("CRM Lead", "r6-parent", title="Visible parent", content="Visible parent body", _assign='["history-assignee"]', _liked_by='["history-liker"]', _seen='["history-viewer"]')
        note = h.put("FCRM Note", "r6-note", title="Shared title", content="Shared current body", reference_doctype=parent.doctype, reference_docname=parent.name, custom_team_visibility="Private", custom_team_collaborator="", _assign="[]", _liked_by='["history-liker"]', _seen='["history-viewer"]')
        todo = h.put("ToDo", "r6-todo", allocated_to="history-assignee", status="Open", reference_type=note.doctype, reference_name=note.name, description="Old private assignment")
        h.put("User", "history-assignee", full_name="Hidden fullname", user_image="/private/hidden-avatar", email="hidden-email@example.invalid", time_zone="Hidden/Timezone")
        frappe.db.get_values = lambda *args, **kwargs: [todo.allocated_to]
        frappe.db.set_value = lambda dt, name, field, value, **kwargs: records[(dt, str(name))].__setitem__(field, value)
        if upstream:
            namespace = {"frappe": frappe, "json": json}
            h.load_native(upstream / "apps/frappe/frappe/desk/doctype/todo/todo.py", {"update_in_reference"}, namespace, "ToDo")
            namespace["update_in_reference"](todo)
        else:
            note._assign = json.dumps([todo.allocated_to])
        assert json.loads(note._assign) == [todo.allocated_to]
        changed = deepcopy(note)
        changed.custom_team_visibility = "Shared"
        events.validate(changed)
        records[(note.doctype, note.name)] = note = changed
        frappe.session.user = "b"
        assert policy.permitted(note, "b") and not policy.permitted(note, "b", "write")
        assert not policy.permitted(todo, "b") and docinfo.get_assigned_users(note.doctype, note.name) == []
        assert note._assign and note._liked_by and note._seen and (todo.doctype, todo.name) in records

        def guarded(doctype, fields=None, method="frappe.desk.reportview.get", **extra):
            frappe.local = types.SimpleNamespace(lang="en", request=Doc(path="/api/method/" + method, method="GET"))
            frappe.form_dict = Doc(doctype=doctype, **extra)
            if fields is not None:
                frappe.form_dict.fields = deepcopy(fields)
            frappe.local.form_dict = frappe.form_dict
            request.guard()
            return frappe.form_dict

        for dt in (note.doctype, parent.doctype):
            for projection in ("*", ["*"], '["*"]', ("*",)):
                args = guarded(dt, projection)
                assert args.fields == ["name", "owner", "title", "content"]
            assert guarded(dt, ["name", "content"]).fields == ["name", "content"]
            assert "fields" not in guarded(dt)
            for projection in (["name", "*"], ["`tabFCRM Note`.*"], ["* as body"], ["name", "_assign as body"], ["`_LiKeD_By` as body"], ["_seen"], ["_user_tags"]):
                h.forbidden(lambda dt=dt, projection=projection: guarded(dt, projection))
            for value in ("1", 1, True):
                h.forbidden(lambda dt=dt, value=value: guarded(dt, ["name"], method="frappe.desk.reportview.export_query", export_in_background=value))
            assert guarded(dt, ["name"], method="frappe.desk.reportview.export_query", export_in_background="0").fields == ["name"]
        for key in ("fieldname", "select_columns", "export_fields", "pluck", "searchfield", "search_fields"):
            for value in ("*", "_assign"):
                h.forbidden(lambda key=key, value=value: responses.reject_raw_fields({key: value}, note.doctype))
        for projection in (["count(*) as total"], ["title", "count(*) as total"]):
            assert guarded(note.doctype, projection).fields == projection
        for method in ("frappe.client.get_list", "frappe.desk.reportview.get", "frappe.desk.reportview.get_list", "frappe.desk.reportview.export_query"):
            for projection in (["_assign"], ["name", "_liked_by as history"], ["_seen"], ["name", "*"]):
                for value in (projection, json.dumps(projection), h.encoded_json(projection)):
                    h.forbidden(lambda value=value, method=method: guarded(note.doctype, value, method=method))
            for projection in (["name", "content"], ["*"]):
                values = [guarded(note.doctype, value, method=method).fields for value in (projection, json.dumps(projection), h.encoded_json(projection))]
                assert all((json.loads(value) if isinstance(value, str) else value) == values[0] for value in values)
        for key, value in (("fieldname", ["_assign as history"]), ("filters", {"_seen": "history-viewer"}), ("or_filters", [["_liked_by", "=", "history-liker"]]), ("export_filters", {"_assign": "history-assignee"}), ("select_columns", {note.doctype: ["_assign"]}), ("export_fields", {note.doctype: ["_seen"]}), ("search_fields", ["_liked_by"])):
            for variant in (value, json.dumps(value), h.encoded_json(value)):
                h.forbidden(lambda key=key, variant=variant: responses.reject_raw_fields({key: variant}, note.doctype))
        for key in ("select_columns", "export_fields"):
            for value in ({note.doctype: ["name", "content"]}, json.dumps({note.doctype: ["name", "content"]}), h.encoded_json({note.doctype: ["name", "content"]})):
                args = {key: value}
                responses.reject_raw_fields(args, note.doctype)
                assert args[key] == value
        print("PASS R8 decoded JSON projection semantics: existing list/CSV guards reject encoded and canonical raw fields/aliases/mixed wildcard/filter/export selectors equally; legal body, export columns and safe wildcard retained without changing wire contracts")
        h.forbidden(lambda: responses.reject_raw_fields({"fields": ["*"]}))
        assert guarded("Contact", ["*"]).fields == ["*"]
        frappe.session.user = "Administrator"
        assert guarded(note.doctype, ["*"]).fields == ["*"]
    finally:
        records.clear()
        records.update(saved_records)
        for name in tuple(sys.modules):
            if (name == "frappe" or name.startswith("frappe.")) and name not in saved_modules:
                del sys.modules[name]
        for name, (module, contents) in saved_modules.items():
            sys.modules[name] = module
            vars(module).clear()
            vars(module).update(contents)
    print("PASS R6 request projection guards: safe bare wildcard, qualified/mixed/raw aliases denied, legal explicit/default/count fields and synchronous parent exports retained; Shared body does not grant assignment history")
    if upstream:
        verify_native_output(h, upstream)


def verify_native_output(h, upstream):
    from team_access import request, responses

    frappe, Doc, records = h.frappe, h.Doc, h.records
    saved_records = deepcopy(records)
    saved_modules = {name: (module, dict(vars(module))) for name, module in sys.modules.items() if name == "frappe" or name.startswith("frappe.")}
    try:
        records.clear()
        frappe.session = types.SimpleNamespace(user="b")
        frappe.local = types.SimpleNamespace(lang="en")
        names = ["name", "owner", "_assign", "_liked_by", "_seen", "_user_tags", "title", "content"]
        columns = [Doc(name=name, fieldname=name, label=name, fieldtype="Data") for name in names]
        meta = Doc(default_fields=["name", "owner"], get_valid_columns=lambda: names, get_permitted_fieldnames=lambda **kwargs: ["title", "content"], get_field=lambda name: next((row for row in columns if row.name == name), None), get_table_fields=lambda: [], istable=0, issingle=0)
        frappe.get_meta = lambda dt: meta
        frappe.only_has_select_perm = lambda *args, **kwargs: False
        frappe.as_unicode = str
        h.module("frappe.permissions", can_export=lambda *args, **kwargs: True)
        h.module("frappe.desk.query_report", add_total_row=lambda values, keys, meta: values)
        captures, lookups = [], []
        def csv_bytes(rows, params):
            stream = io.StringIO(newline="")
            csv.writer(stream).writerows(rows)
            return stream.getvalue().encode("utf-8")
        h.module("frappe.desk.utils", get_csv_bytes=csv_bytes, provide_binary_file=lambda title, extension, content: captures.append((title, extension, content)))
        h.module("frappe.utils.xlsxutils", handle_html=lambda value: value, make_xlsx=lambda *args: (_ for _ in ()).throw(AssertionError("unexpected Excel path")))
        model = h.module("frappe.model", optional_fields=("_user_tags", "_assign", "_liked_by", "_seen"), default_fields=("name", "owner"))
        namespace = {"frappe": frappe, "json": json, "_": lambda text, **kwargs: text, "_UserInfo": dict, "CORE_DOCTYPES": set(), "DEFAULT_FIELDS": {"name", "owner"}, "optional_fields": model.optional_fields, "child_table_fields": [], "make_access_log": lambda **kwargs: None}
        h.load_native(upstream / "apps/frappe/frappe/model/__init__.py", {"get_permitted_fields"}, namespace)
        model.get_permitted_fields = namespace["get_permitted_fields"]
        h.load_native(upstream / "apps/frappe/frappe/utils/__init__.py", {"add_user_info"}, namespace)
        h.load_native(upstream / "apps/frappe/frappe/desk/reportview.py", {"parse_json", "update_wildcard_field_param", "compress", "_export_query", "get_field_info", "parse_field", "handle_duration_fieldtype_values"}, namespace)
        parent = h.put("CRM Lead", "r6-parent", title="Visible parent", content="Visible parent body", _assign="[]")
        note = h.put("FCRM Note", "r6-note", title="Shared title", content="Shared current body", reference_doctype=parent.doctype, reference_docname=parent.name, custom_team_visibility="Private", _assign="[]", _liked_by='["history-liker"]', _seen='["history-viewer"]', _user_tags="hidden-history-tag")
        todo = h.put("ToDo", "r6-todo", allocated_to="history-assignee", status="Open", reference_type=note.doctype, reference_name=note.name)
        h.put("User", "history-assignee", full_name="Hidden fullname", user_image="/private/hidden-avatar", email="hidden-email@example.invalid", time_zone="Hidden/Timezone")
        frappe.db = types.SimpleNamespace(**vars(frappe.db))
        frappe.db.get_values = lambda *args, **kwargs: [todo.allocated_to]
        frappe.db.set_value = lambda dt, name, field, value, **kwargs: records[(dt, str(name))].__setitem__(field, value)
        h.load_native(upstream / "apps/frappe/frappe/desk/doctype/todo/todo.py", {"update_in_reference"}, namespace, "ToDo")
        namespace["update_in_reference"](todo)
        from team_access import events, permissions as policy
        frappe.session.user = "a"
        shared = deepcopy(note)
        shared.custom_team_visibility = "Shared"
        events.validate(shared)
        records[(note.doctype, note.name)] = note = shared
        frappe.session.user = "b"
        assert policy.permitted(note, "b") and not policy.permitted(todo, "b")
        def get_all(*args, **kwargs):
            if args[0] == "User":
                lookups.append(args)
            return h.get_all(*args, **kwargs)
        frappe.get_all = get_all
        class DatabaseQuery:
            def __init__(self, doctype):
                self.doctype = doctype
            def execute(self, fields=None, **kwargs):
                self.fields = fields or ["name"]
                row = records[(self.doctype, "r6-note" if self.doctype == note.doctype else "r6-parent")]
                return [[row.get(field) for field in self.fields]]
        namespace["DatabaseQuery"] = DatabaseQuery
        def export(args):
            namespace["_export_query"](deepcopy(args), {})
            assert captures[-1][1] == "csv"
            return captures[-1][2].decode("utf-8")
        raw = Doc(doctype=note.doctype, fields=["*"], file_format_type="CSV")
        assert namespace["update_wildcard_field_param"](raw)
        old_csv = export(raw)
        assert all(marker in old_csv for marker in ("history-assignee", "history-liker", "history-viewer"))
        raw_row = Doc({field: note.get(field) for field in raw.fields})
        old_compressed = namespace["compress"]([raw_row])
        assert lookups and old_compressed["user_info"]["history-assignee"]["email"] == "hidden-email@example.invalid"
        cleaned = responses.sanitize(old_compressed, True)
        assert cleaned["user_info"] == {} and not set(responses.RAW_FIELDS) & set(cleaned["keys"])
        assert all(marker not in json.dumps(cleaned) for marker in ("history-assignee", "history-liker", "history-viewer", "Hidden fullname", "hidden-email@example.invalid", "hidden-avatar", "Hidden/Timezone"))
        for dt, row in ((note.doctype, note), (parent.doctype, parent)):
            for fields in ('["*"]', ["name", "title", "content"]):
                args = Doc(doctype=dt, fields=fields, file_format_type="CSV", filters=[["name", "=", row.name]], selected_items=json.dumps([row.name]))
                frappe.local = types.SimpleNamespace(lang="en", request=Doc(path="/api/method/frappe.desk.reportview.export_query", method="GET"), form_dict=args)
                frappe.form_dict = args
                request.guard()
                namespace["parse_json"](args)
                assert not namespace["update_wildcard_field_param"](args)
                assert not set(args.fields) & set(responses.RAW_FIELDS)
                text = export(args)
                assert row.content in text and row.name in text
                assert all(marker not in text for marker in ("history-assignee", "history-liker", "history-viewer", "hidden-history-tag"))
                before = len(lookups)
                compressed = namespace["compress"]([Doc({field: row.get(field) for field in args.fields})])
                assert len(lookups) == before and responses.sanitize(compressed, True)["user_info"] == {}
        class Field(Doc):
            def copy(self):
                return Field(self)
        import_fields = [Field(parent=note.doctype, fieldname=name, label=name, fieldtype="Data") for name in ("title", "content")]
        import_meta = Doc(fields=import_fields, get_field=lambda name: next((field for field in import_fields if field.fieldname == name), None), is_nested_set=lambda: False)
        frappe.get_meta = lambda dt: import_meta
        frappe._dict = Field
        h.module("frappe.core.doctype.docfield.docfield", DocField=type("NativeDocField", (), {}))
        frappe.db.get_list = lambda *args, **kwargs: [deepcopy(note)]
        import_ns = {"frappe": frappe, "_": lambda text: text, "Any": object, "display_fieldtypes": [], "no_value_fields": [], "table_fieldtypes": ["Table", "Table MultiSelect"], "groupby_metric": lambda rows, **kwargs: {}, "build_csv_response": lambda rows, title: captures.append((title, "csv", csv_bytes(rows, {})))}
        h.load_native(upstream / "apps/frappe/frappe/core/doctype/data_import/exporter.py", {"Exporter"}, import_ns)
        h.load_native(upstream / "apps/frappe/frappe/core/doctype/data_import/data_import.py", {"download_template"}, import_ns)
        args = Doc(doctype=note.doctype, export_fields={note.doctype: ["name", "content"]}, export_records="all", export_filters=[["name", "=", note.name]])
        frappe.local = types.SimpleNamespace(request=Doc(path="/api/method/frappe.core.doctype.data_import.data_import.download_template", method="GET"), form_dict=args)
        frappe.form_dict = args
        request.guard()
        import_ns["download_template"](**args)
        template = captures[-1][2].decode("utf-8")
        assert note.content in template and note.name in template and "history-assignee" not in template
        for key in ("select_columns", "export_fields"):
            h.forbidden(lambda key=key: responses.reject_raw_fields({key: {note.doctype: ["_assign"]}}, note.doctype))
            h.forbidden(lambda key=key: responses.reject_raw_fields({key: {note.doctype: ["*"]}}, note.doctype))
        assert note._assign and (todo.doctype, todo.name) in records
    finally:
        records.clear()
        records.update(saved_records)
        for name in tuple(sys.modules):
            if (name == "frappe" or name.startswith("frappe.")) and name not in saved_modules:
                del sys.modules[name]
        for name, (module, contents) in saved_modules.items():
            sys.modules[name] = module
            vars(module).clear()
            vars(module).update(contents)
    print("PASS R6 fixed native ToDo.update_in_reference -> Shared -> get_permitted_fields/wildcard -> _export_query CSV sink and compress/add_user_info: old leakage reproduced, guarded body/explicit/selected parent CSV and complete Data Import download_template/Exporter preserved, no historical identity lookup or derived profile output")

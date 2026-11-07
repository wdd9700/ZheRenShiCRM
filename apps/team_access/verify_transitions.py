from copy import deepcopy
import importlib


def verify_freeze(h, save=None, trace=None):
    from team_access import events, files, install, permissions as policy, references

    frappe, Doc, records = h.frappe, h.Doc, h.records
    snapshot, user, enumerate_files = deepcopy(records), frappe.session.user, frappe.get_all
    native = save is not None
    trace = trace if trace is not None else []
    def save_local(dt, name, changes):
        trace.clear()
        doc = Doc(records[(dt, name)], **changes)
        events.validate(doc)
        events.validate_integrity(doc)
        trace.append("db_update:" + dt)
        records[(dt, name)] = doc
    save = save or save_local
    def rejected(dt, name, changes):
        before = deepcopy(records)
        disk = list(h.writes)
        trace.clear()
        h.forbidden(lambda: save(dt, name, changes))
        assert not any(item.startswith(("db_update", "db_insert", "disk")) for item in trace)
        assert "post_save" not in trace and records == before and h.writes == disk
    def start(dt):
        records.clear()
        h.put("CRM Lead", "parent")
        h.put("FCRM Note", "note", reference_doctype="CRM Lead", reference_docname="parent", custom_team_visibility="Private")
        h.put("FCRM Note", "second", reference_doctype="CRM Lead", reference_docname="parent", custom_team_visibility="Private")
        return h.put(dt, "r5-parent", reference_doctype="CRM Lead", reference_docname="parent", reference_name="parent", note="", links=[], timeline_links=[])
    try:
        for dt in ("CRM Call Log", "Communication"):
            for storage in ("public", "remote", "unknown", "private", "none", "nested", "url-alias", "hash-alias"):
                frappe.session.user = "a"
                parent = start(dt)
                target = parent
                if storage == "nested":
                    bridge = h.put("Communication", "r5-bridge", reference_doctype="CRM Lead", reference_name="parent", timeline_links=[Doc(link_doctype=dt, link_name=parent.name)])
                    target = h.put("Comment", "r5-nested", reference_doctype="Communication", reference_name=bridge.name, comment_type="Comment")
                if storage != "none":
                    url = "https://example.invalid/r5.txt" if storage == "remote" else "" if storage == "unknown" else "/private/files/r5.txt" if storage in ("private", "hash-alias") else "/files/r5.txt"
                    file = h.put("File", "r5-file", attached_to_doctype=target.doctype, attached_to_name=target.name, is_folder=0, is_private=int(storage in ("private", "hash-alias")), file_url=url, content_hash="r5-hash")
                    if storage in ("url-alias", "hash-alias"):
                        h.put("File", "r5-alias", attached_to_doctype="CRM Lead", attached_to_name="parent", is_folder=0, is_private=0, file_url=url if storage == "url-alias" else "/files/r5-copy.txt", content_hash=file.content_hash)
                    files.validate_attachment(file)
                    assert policy.permitted(file, "b")
                install.preflight()
                changes = [{"note": "note"}, {"reference_doctype": "FCRM Note", "reference_docname": "note"}, {"links": [Doc(doctype="Dynamic Link", link_doctype="FCRM Note", link_name="note")]}] if dt == "CRM Call Log" else [{"timeline_links": [Doc(doctype="Communication Link", link_doctype="FCRM Note", link_name="note")]}]
                for account in ("a", "Administrator"):
                    frappe.session.user = account
                    for change in changes:
                        rejected(dt, parent.name, change)
                        install.preflight()
                        assert not references.private_roots(dt, parent.name)
                        if storage != "none":
                            assert policy.permitted(records[("File", "r5-file")], "b")
                frappe.session.user = "a"
                before = deepcopy(records[(dt, parent.name)])
                change = changes[0]
                records[(dt, parent.name)] = Doc(before, **change)
                if storage not in ("none", "private"):
                    h.forbidden(install.preflight)
                    assert not policy.permitted(records[("File", "r5-file")], "b")
                else:
                    install.preflight()
                records[(dt, parent.name)] = before
                def unavailable(*args, **kwargs):
                    raise AssertionError("root transitions must not depend on an attachment scan, its visibility or its size")
                frappe.get_all = unavailable
                rejected(dt, parent.name, change)
                frappe.get_all = enumerate_files
                save(dt, parent.name, {"status": "Completed", "content": "ordinary edit"})
                assert "db_update:" + dt in trace
                install.preflight()
        parent = start("CRM Call Log")
        parent.note = "note"
        rejected(parent.doctype, parent.name, {"links": [Doc(doctype="Dynamic Link", link_doctype="FCRM Note", link_name="second")]})
        rejected(parent.doctype, parent.name, {"note": "second"})
        save(parent.doctype, parent.name, {"links": [Doc(doctype="Dynamic Link", link_doctype="FCRM Note", link_name="note")]})
        assert references.private_roots(parent.doctype, parent.name) == {("FCRM Note", "note")}
        first = Doc(doctype="Communication", name="r5-first", owner="a", reference_doctype="CRM Lead", reference_name="parent", timeline_links=[Doc(doctype="Communication Link", link_doctype="FCRM Note", link_name="note")])
        events.validate(first)
        events.validate(Doc(first, name="r5-first-nested", reference_doctype="CRM Call Log", reference_name=parent.name, timeline_links=[]))
        print("PASS R5 " + ("fixed v1/Document save" if native else "local policy") + ": initial preflight accepts ordinary public/remote/unknown and URL/hash alias fixtures; every existing Call/Communication private-root addition denied before DB/disk, nested inbound files unchanged and preflight still accepts; unsafe counterfactual state fails preflight; no-file/private exceptions also denied without any attachment scan; same-root and ordinary edits survive")
    finally:
        records.clear()
        records.update(snapshot)
        frappe.session.user, frappe.get_all = user, enumerate_files


def verify_native(h, upstream, Saved, native, get_doc, versions, trace):
    from team_access import events, files, hooks, permissions as policy, references

    frappe, Doc, records = h.frappe, h.Doc, h.records
    snapshot = deepcopy(records)
    attrs = ("get_doc_hooks", "get_attr")
    old_attrs = {key: getattr(frappe, key, None) for key in attrs}
    old_method, old_new_name = Saved.run_method, getattr(Saved, "set_new_name", None)
    old_local_flags = getattr(frappe.local, "flags", None)
    old_value = frappe.db.get_value
    frappe.db.get_value = lambda dt, *args, **kwargs: None if dt == "Custom Field" else old_value(dt, *args, **kwargs)
    frappe.local.flags = Doc(in_install=False)
    frappe.flags.in_setup_wizard = False
    namespace = {"frappe": frappe, "Document": Saved, "run_webhooks": lambda *args: None, "run_server_script_for_doc_event": lambda *args: None, "validate_name": lambda dt, name: name, "set_new_name": native["set_new_name"]}
    h.load_native(upstream / "apps/frappe/frappe/model/document.py", {"run_method", "hook", "set_new_name"}, namespace, "Document")
    Saved.hook = staticmethod(namespace["hook"])
    Saved.set_new_name = namespace["set_new_name"]
    namespace["set_new_name"] = native["set_new_name"]
    Saved.run_notifications = lambda *args: None
    def invoke(self, method, *args, **kwargs):
        trace.append(method)
        return namespace["run_method"](self, method, *args, **kwargs)
    Saved.run_method = invoke
    def validate(self):
        if self.get("_controller_mutation"):
            self.update(self._controller_mutation)
    def before_save(self):
        if self.get("_before_save_mutation"):
            self.update(self._before_save_mutation)
    Saved.validate, Saved.before_save = validate, before_save
    frappe.get_doc_hooks = lambda: {dt: {event: [path] for event, path in mappings.items()} for dt, mappings in hooks.doc_events.items()}
    frappe.get_attr = lambda path: getattr(importlib.import_module(path.rpartition(".")[0]), path.rpartition(".")[2])
    def save(dt, name, changes):
        trace.clear()
        frappe.form_dict = Doc(deepcopy(changes))
        return versions[0]["update_doc"](dt, name)
    try:
        from team_access import install

        current_validation = references.validate_change
        def r4_subset_validation(doc):
            if doc.doctype not in references.GRAPH_NODES:
                return
            old = policy.get_record(doc.doctype, doc.get("name"))
            if not old and doc.doctype == "Comment" and doc.get("comment_type") == "Attachment Removed":
                return
            current_roots = references.private_roots(doc=doc)
            if old and not references.private_roots(doc=old).issubset(current_roots):
                policy.deny()
            if frappe.session.user != "Administrator" and (
                not references.history_permitted(doc, frappe.session.user) or old and not references.history_permitted(old, frappe.session.user)
            ):
                policy.deny()
        try:
            references.validate_change = r4_subset_validation
            for dt in ("CRM Call Log", "Communication"):
                records.clear()
                frappe.session.user = "a"
                h.put("CRM Lead", "parent")
                h.put("FCRM Note", "note", reference_doctype="CRM Lead", reference_docname="parent", custom_team_visibility="Private")
                parent = h.put(dt, "r5-baseline", reference_doctype="CRM Lead", reference_docname="parent", reference_name="parent", note="", links=[], timeline_links=[])
                file = h.put("File", "r5-public-baseline", attached_to_doctype=dt, attached_to_name=parent.name, file_url="/files/baseline.txt", is_private=0, is_folder=0)
                install.preflight()
                changes = {"note": "note"} if dt == "CRM Call Log" else {"timeline_links": [Doc(doctype="Communication Link", link_doctype="FCRM Note", link_name="note")]}
                before = deepcopy(file)
                save(dt, parent.name, changes)
                assert "db_update:" + dt in trace and "post_save" in trace
                assert not policy.permitted(records[("File", file.name)], "b") and records[("File", file.name)] == before
                h.forbidden(install.preflight)
        finally:
            references.validate_change = current_validation
        print("PASS R5 isolated R4 subset-policy baseline through fixed v1/Document/run_method/hook: initial preflight accepts public File, Call/Communication root addition reaches DB/post-save without File save, canonical then denies B but public URL survives and resulting preflight fails; current policy restored before candidate tests")
        verify_freeze(h, save, trace)
        frappe.session.user = "a"
        records.clear()
        h.put("CRM Lead", "parent")
        h.put("FCRM Note", "note", reference_doctype="CRM Lead", reference_docname="parent", custom_team_visibility="Private")
        ordinary = h.put("CRM Call Log", "r5-existing", reference_doctype="CRM Lead", reference_docname="parent", note="", links=[])
        for changes in ({"_controller_mutation": {"note": "note"}}, {"_before_save_mutation": {"note": "note"}}):
            trace.clear()
            h.forbidden(lambda: save(ordinary.doctype, ordinary.name, changes))
            assert not any(item.startswith("db_update") for item in trace)
        import hashlib
        import json

        evidence = upstream / "apps/frappe/frappe/core/doctype"
        utilities = evidence / "file/utils.py"
        manifest = json.loads((upstream / "supplement-manifest-file-utils-M8R5.json").read_text(encoding="utf-8-sig"))
        assert hashlib.sha256(utilities.read_bytes()).hexdigest() == manifest["files"]["apps/frappe/frappe/core/doctype/file/utils.py"]["sha256"]
        relink = {"frappe": frappe, "relink_files": lambda *args: (_ for _ in ()).throw(AssertionError("unexpected Attach field in fixed Call/Communication schema"))}
        h.load_native(utilities, {"relink_mismatched_files"}, relink)
        schemas = {}
        for dt, path in (("CRM Call Log", upstream / "apps/crm/crm/fcrm/doctype/crm_call_log/crm_call_log.json"), ("Communication", evidence / "communication/communication.json"), ("Dynamic Link", evidence / "dynamic_link/dynamic_link.json"), ("Communication Link", evidence / "communication_link/communication_link.json")):
            schemas[dt] = [Doc(row) for row in json.loads(path.read_text(encoding="utf-8"))["fields"]]
        class Schema(Doc):
            def get(self, key, default=None):
                if key == "fields" and isinstance(default, dict):
                    return [row for row in dict.get(self, key, []) if all(row.get(field) in value[1] if isinstance(value, list) and value[0] == "in" else row.get(field) == value for field, value in default.items())]
                return dict.get(self, key, default)
        old_meta = frappe.get_meta
        frappe.get_meta = lambda dt: Schema(old_meta(dt), fields=schemas.get(dt, []))
        def relink_actual(doc):
            trace.append("relink_mismatched_files")
            relink["relink_mismatched_files"](doc)
        native["relink_mismatched_files"] = relink_actual
        Saved.delete_key = lambda self, key: self.pop(key, None)
        def insert(data, **kwargs):
            trace.clear()
            doc = get_doc(Doc(data))
            doc.meta = frappe.get_meta(doc.doctype)
            return doc.insert(**kwargs)
        def db_insert(self, **kwargs):
            trace.append("db_insert:" + self.doctype)
            assert (self.doctype, self.name) not in records
            self.db_update()
            for key in ("__islocal", "__temporary_name"):
                records[(self.doctype, self.name)].pop(key, None)
        Saved.db_insert = db_insert
        for account in ("a", "Administrator"):
            frappe.session.user = account
            h.forbidden(lambda: insert(Doc(ordinary, note="note"), set_name=ordinary.name, ignore_if_duplicate=True))
            assert not any(item.startswith(("db_insert", "db_update")) for item in trace)
        frappe.session.user = "a"
        dangling = h.put("Communication", "r5-dangling", reference_doctype="CRM Lead", reference_name="parent", timeline_links=[Doc(link_doctype="CRM Call Log", link_name="r5-missing")])
        h.put("File", "r5-dangling-file", attached_to_doctype=dangling.doctype, attached_to_name=dangling.name, is_folder=0, is_private=0, file_url="/files/dangling.txt")
        from team_access import install

        h.forbidden(install.preflight)
        pending = Doc(doctype="File", name="r5-pending-file", attached_to_doctype="CRM Call Log", attached_to_name="r5-not-created", file_url="/files/pending.txt", is_private=0)
        before = list(h.writes)
        h.forbidden(lambda: files.ActivityFile(pending).before_insert())
        assert h.writes == before
        del records[("File", "r5-dangling-file")]
        del records[(dangling.doctype, dangling.name)]
        private = h.put("CRM Call Log", "r5-private", reference_doctype="CRM Lead", reference_docname="parent", note="note", links=[])
        public = h.put("File", "r5-public", attached_to_doctype="CRM Lead", attached_to_name="parent", is_folder=0, is_private=0, file_url="/files/ordinary.txt")
        h.forbidden(lambda: save("File", public.name, {"attached_to_doctype": private.doctype, "attached_to_name": private.name}))
        assert not any(item.startswith("db_update") for item in trace)
        print("PASS R5 actual Document.run_method/hook wildcard composition: controller/before-save additions and insert(set_name=existing, ignore_if_duplicate=True) denied before DB; missing first target fails preflight and File before-insert before storage; public File reparent to an established private Call denied")
        incoming = deepcopy(public)
        for dt, name, values in (("CRM Call Log", "r5-new-call", {"reference_doctype": "CRM Lead", "reference_docname": "parent", "note": "note", "links": []}), ("Communication", "r5-new-comm", {"reference_doctype": "CRM Lead", "reference_name": "parent", "timeline_links": [Doc(doctype="Communication Link", link_doctype="CRM Call Log", link_name="r5-new-call")]})):
            assert not any(row.fieldtype in ("Attach", "Attach Image") for row in schemas[dt])
            created = insert(Doc(doctype=dt, name=name, owner="a", __temporary_name="r5-existing", **values), set_name=name)
            assert trace.index("db_insert:" + dt) < trace.index("relink_mismatched_files") < trace.index("post_save")
            assert references.private_roots(dt, created.name) == {("FCRM Note", "note")}
            assert not policy.permitted(records[(dt, created.name)], "b") and records[("File", public.name)] == incoming
            save(dt, created.name, {"status": "Completed"})
        stolen = h.put("Dynamic Link", "r5-old-child", parenttype="CRM Call Log", parent=ordinary.name, parentfield="links", link_doctype="CRM Lead", link_name="parent")
        h.forbidden(lambda: insert(Doc(doctype="CRM Call Log", name="r5-steal", owner="a", note="note", reference_doctype="CRM Lead", reference_docname="parent", links=[stolen]), set_name="r5-steal", set_child_names=False))
        assert not any(item.startswith(("db_insert", "db_update")) for item in trace)
        install.preflight()
        print("PASS R5 first insert with fixed schemas and actual relink_mismatched_files: new private Call and nested Communication establish roots, temporary-name relink finds no Attach fields, existing public File remains unchanged; same-root later edits survive and reused stored child identity is denied before DB. No physical storage or general concurrent File/hash guarantee")
    finally:
        records.clear()
        records.update(snapshot)
        frappe.db.get_value = old_value
        if "old_meta" in locals():
            frappe.get_meta = old_meta
        Saved.run_method = old_method
        if old_new_name is None:
            del Saved.set_new_name
        else:
            Saved.set_new_name = old_new_name
        for key, value in old_attrs.items():
            if value is None:
                delattr(frappe, key)
            else:
                setattr(frappe, key, value)
        frappe.local.flags = old_local_flags
        frappe.session.user = "a"

import argparse
import ast
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
import types

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))


class Doc(dict):
    def __getattr__(self, key):
        return self.get(key)

    def __setattr__(self, key, value):
        self[key] = value

    def check_permission(self, ptype):
        if not native(self.doctype, ptype, self, frappe.session.user):
            raise PermissionError()

    def is_new(self):
        return bool(self.get("__islocal"))

    def get_doc_before_save(self):
        return self.get("_before")


records, native_denied, pushed, writes = {}, set(), [], []


def module(name, **values):
    if name not in sys.modules:
        parent, _, child = name.rpartition(".")
        result = types.ModuleType(name)
        result.__path__ = []
        sys.modules[name] = result
        if parent:
            setattr(module(parent), child, result)
    result = sys.modules[name]
    result.__dict__.update(values)
    return result


def native(doctype, ptype="read", doc=None, user=None, **kwargs):
    return (doctype, str(doc.name if isinstance(doc, dict) else doc), user or frappe.session.user, ptype) not in native_denied


def get_all(doctype, filters=None, fields=None, limit_page_length=0, **kwargs):
    rows = [deepcopy(doc) for (dt, _), doc in records.items() if dt == doctype]
    if isinstance(filters, dict):
        rows = [doc for doc in rows if all((doc.get(key) or 0) == value for key, value in filters.items())]
    if limit_page_length:
        rows = rows[:limit_page_length]
    return rows


def put(doctype, name, **values):
    doc = Doc(doctype=doctype, name=str(name), owner="a", **values)
    records[(doctype, str(name))] = doc
    return doc


def forbidden(call):
    try:
        call()
    except PermissionError:
        return
    raise AssertionError("expected fail-closed denial")


class Base(Doc):
    def notify_update(self):
        pushed.append(("update", self.doctype, self.name))

    def notify_change(self, action):
        pushed.append(("body", self.doctype, self.name, action))

    def after_insert(self):
        pushed.append(("after_insert", self.doctype, self.name))

    def before_insert(self):
        writes.append("before_insert")

    def validate(self):
        writes.append("validate")


def build_environment(upstream):
    global frappe
    frappe = module("frappe", __version__="15.125.0", PermissionError=PermissionError, DoesNotExistError=LookupError, ValidationError=ValueError)
    frappe._dict = Doc
    frappe.session = types.SimpleNamespace(user="a")
    frappe.local = types.SimpleNamespace(response={})
    frappe.response = frappe.local.response
    frappe.flags = types.SimpleNamespace(in_install=False, in_migrate=False)
    frappe.whitelist = lambda *args, **kwargs: lambda fn: fn
    frappe.has_permission = native
    frappe.get_doc = lambda dt, name: deepcopy(records[(dt, str(name))])
    frappe.get_all = get_all
    frappe.as_json = json.dumps
    frappe.parse_json = lambda value: json.loads(value) if isinstance(value, str) else value
    frappe.throw = lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError())
    frappe.get_hooks = lambda *args: {}
    frappe.db = types.SimpleNamespace(exists=lambda dt, name: (dt, str(name)) in records, get_value=lambda *args, **kwargs: None, set_value=lambda *args, **kwargs: writes.append(args))
    module("crm", __version__="1.90.0")
    for path, name in (
        ("crm.fcrm.doctype.fcrm_note.fcrm_note", "FCRMNote"),
        ("crm.fcrm.doctype.crm_task.crm_task", "CRMTask"),
        ("crm.fcrm.doctype.crm_lead.crm_lead", "CRMLead"),
        ("crm.fcrm.doctype.crm_deal.crm_deal", "CRMDeal"),
        ("crm.fcrm.doctype.crm_call_log.crm_call_log", "CRMCallLog"),
        ("crm.fcrm.doctype.crm_notification.crm_notification", "CRMNotification"),
        ("frappe.core.doctype.comment.comment", "Comment"),
        ("frappe.core.doctype.communication.communication", "Communication"),
        ("frappe.core.doctype.version.version", "Version"),
        ("frappe.core.doctype.file.file", "File"),
        ("frappe.desk.doctype.todo.todo", "ToDo"),
        ("frappe.desk.doctype.notification_log.notification_log", "NotificationLog"),
    ):
        module(path, **{name: type(name, (Base,), {})})
    module("crm.api.comment", extract_mentions=lambda text: [])
    module("frappe.realtime", can_subscribe_doc=lambda dt, dn: True)
    module("frappe.desk.form.load", get_filtered_attachments=lambda *args: get_all("File"), get_communications=lambda *args: [deepcopy(doc) for (dt, _), doc in records.items() if dt == "Communication"])
    module("crm.api.doc", get_assigned_users=lambda *args: ["b"])
    if upstream:
        path = upstream / "apps/crm/crm/fcrm/doctype/crm_task/crm_task.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "CRMTask")
        def unassign(dt, name, user):
            from team_access.permissions import can_contribute

            assert can_contribute(dt, name, user)
            writes.append(("unassign", (dt, name, user)))
            records[(dt, str(name))].assigned_to = None

        def assign(args):
            from team_access.permissions import can_contribute

            assert all(can_contribute(args["doctype"], args["name"], user) for user in args["assign_to"])
            writes.append(("assign", args))

        namespace = {"Document": Base, "assign": assign, "unassign": unassign}
        exec(compile(ast.Module(body=[cls], type_ignores=[]), str(path), "exec"), namespace)
        sys.modules["crm.fcrm.doctype.crm_task.crm_task"].CRMTask = namespace["CRMTask"]
        for doctype, name in (("crm_lead", "CRMLead"), ("crm_deal", "CRMDeal")):
            path = upstream / f"apps/crm/crm/fcrm/doctype/{doctype}/{doctype}.py"
            tree = ast.parse(path.read_text(encoding="utf-8"))
            cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == name)
            namespace = {"Document": Base, "frappe": frappe}
            exec(compile(ast.Module(body=[cls], type_ignores=[]), str(path), "exec"), namespace)
            setattr(sys.modules[f"crm.fcrm.doctype.{doctype}.{doctype}"], name, namespace[name])


def run(upstream):
    build_environment(upstream)
    from team_access import docinfo, events, files, install, permissions as policy, realtime, references, request, responses

    put("CRM Lead", "parent")
    note = put("FCRM Note", "note", reference_doctype="CRM Lead", reference_docname="parent", custom_team_visibility="Shared", custom_team_collaborator="")
    task = put("CRM Task", 7, reference_doctype="CRM Lead", reference_docname="parent", custom_team_visibility="Shared", assigned_to="")
    roots = {("FCRM Note", "note"), ("CRM Task", "7")}
    linked = put("Communication", "linked", reference_doctype="CRM Lead", reference_name="parent", timeline_links=[Doc(link_doctype=dt, link_name=name) for dt, name in roots])
    formal = put("Communication", "formal", reference_doctype="CRM Lead", reference_name="parent", timeline_links=[])
    nested = put("Comment", "nested", reference_doctype="Communication", reference_name="linked")
    assert references.private_roots(doc=linked) == roots
    assert references.private_roots("Comment", "nested") == roots
    assert policy.permitted(linked, "a") and not policy.permitted(linked, "b")
    assert policy.permitted(note, "b") and not policy.permitted(note, "b", "write")
    note.custom_team_collaborator = "b"
    assert not policy.permitted(linked, "b")
    task.assigned_to = "b"
    assert policy.permitted(linked, "b")
    task.assigned_to = ""
    assert not policy.permitted(linked, "b")
    note.custom_team_collaborator = ""
    native_denied.add(("CRM Task", "7", "a", "write"))
    assert not policy.permitted(linked, "a")
    native_denied.clear()
    ordinary_call = put("CRM Call Log", "ordinary-call", reference_doctype="CRM Lead", reference_docname="parent", links=[])
    private_call = put("CRM Call Log", "private-call", reference_doctype="CRM Lead", reference_docname="parent", links=[], note="note")
    assert not realtime.private_document(ordinary_call) and realtime.private_document(private_call)
    assert realtime.ActivityNote(note).no_feed_on_delete and realtime.ActivityCall(private_call).no_feed_on_delete
    assert not realtime.ActivityCall(ordinary_call).no_feed_on_delete
    print("PASS canonical multi-root/timeline/nested/Call roots; Shared-only and one-of-two grants denied; revoke/native-write rechecked; private delete feed disabled")

    for dt, name in (("FCRM Note", "note"), ("CRM Task", "7")):
        todo = put("ToDo", "todo-" + name, allocated_to="b", assigned_by="a", reference_type=dt, reference_name=name, description="old-private-copy")
        assert policy.permitted(todo, "a") and not policy.permitted(todo, "b")
        frappe.session.user = "b"
        assert docinfo.get_assigned_users(dt, name) == []
        forbidden(lambda: policy.has_permission(todo, "read", "b"))
        frappe.session.user = "a"
        closing = deepcopy(todo)
        closing.status = "Cancelled"
        events.validate(closing)
    print("PASS legacy ToDo detail/list predicate and assignment side response require current activity writer; owner can close old assignment")

    original = put("File", "original", attached_to_doctype="Communication", attached_to_name="linked", file_url="/private/files/secret.txt", is_private=1, is_folder=0, content_hash="same")
    alias = put("File", "alias", attached_to_doctype="CRM Lead", attached_to_name="parent", file_url=original.file_url, is_private=1, is_folder=0, content_hash="same", file_name="secret-name")
    alias.owner = "b"
    assert files.activity_roots(alias) == roots
    assert policy.permitted(original, "a") and policy.permitted(alias, "a")
    assert not policy.permitted(original, "b") and not policy.permitted(alias, "b")
    assert files.private_target("Communication", "linked")
    files.validate_attachment(deepcopy(original))
    forbidden(lambda: files.validate_attachment(deepcopy(alias)))
    detached = deepcopy(original)
    detached.attached_to_doctype = detached.attached_to_name = ""
    forbidden(lambda: files.validate_attachment(detached))
    frappe.session.user = "b"
    forbidden(lambda: files.validate_attachment(deepcopy(original)))
    assert docinfo.get_filtered_attachments("CRM Lead", "parent", []) == []
    frappe.session.user = "a"
    assert len(docinfo.get_filtered_attachments("CRM Lead", "parent", [])) == 2
    public = put("File", "public-copy", attached_to_doctype="CRM Lead", attached_to_name="parent", is_private=0, is_folder=0, file_url="/files/public.txt", content_hash="same")
    forbidden(install.preflight)
    del records[("File", public.name)]
    install.preflight()
    assert not writes
    print("PASS timeline-only multi-root File aliases incl foreign owner denied; dt/dn gallery filtered; preflight hash alias rejects without mutations")

    for user in ("a", "b"):
        frappe.session.user = user
        frappe.response["docinfo"] = {
            "communications": [Doc(name="linked", content="private-body"), Doc(name="formal", content="formal-body")],
            "automated_messages": [Doc(name="linked", content="private-body")],
            "attachments": [Doc(name="alias", file_name="secret-name")],
            "assignments": [Doc(name="todo-note", description="old-private-copy", owner="b")],
            "user_info": {"a": {}, "b": {}, "hidden-sender": {}},
        }
        docinfo.scrub("CRM Lead", "parent")
        body = json.dumps(frappe.response["docinfo"])
        assert "formal-body" in body and "hidden-sender" not in body
        assert ("private-body" in body) == (user == "a")
        assert ("secret-name" in body) == (user == "a")
        assert ("old-private-copy" in body) == (user == "a")
    print("PASS parent native docinfo/automated_messages/attachments/ToDo and user_info filtered while formal communication survives")

    frappe.session.user = "b"
    value = {"docs": [{"doctype": "FCRM Note", "name": "note", "content": "shared-current", "_comments": "old-private", "_assign": "hidden-user", "__onload": {"secret": "old-private"}}], "_link_titles": {"Comment::nested": "secret-title", "CRM Lead::parent": "public-title"}}
    cleaned = responses.sanitize(value)
    assert "old-private" not in json.dumps(cleaned) and "secret-title" not in json.dumps(cleaned) and "public-title" in json.dumps(cleaned)
    table = responses.sanitize({"keys": ["name", "_comments", "title"], "values": [["note", "old-private", "current"]]}, True)
    assert table == {"keys": ["name", "title"], "values": [["note", "current"]]}
    for field in responses.RAW_FIELDS:
        forbidden(lambda: responses.reject_raw_fields({"fields": ["`tabFCRM Note`.`" + field + "` as alias"]}))
        forbidden(lambda: responses.reject_raw_fields({"or_filters": [["FCRM Note", field, "like", "%secret%"]]}))
    class Response:
        mimetype, status_code = "application/json", 200

        def __init__(self):
            self.headers, self.data = {}, None

        def get_json(self, silent=False):
            return value

        def set_data(self, body):
            self.data = body
            self.headers["Content-Length"] = str(len(body.encode()))

    response = Response()
    frappe.local.request = types.SimpleNamespace(path="/api/resource/FCRM%20Note/note", method="GET")
    request.after_request(response)
    assert "old-private" not in response.data and "shared-current" in response.data
    assert response.headers["Cache-Control"] == "no-store, private" and int(response.headers["Content-Length"]) == len(response.data.encode())
    frappe.form_dict = Doc(dt="CRM Lead", dn="parent", filters=[])
    frappe.local.request = types.SimpleNamespace(path="/api/method/frappe.desk.form.load.get_filtered_attachments", method="GET")
    request.guard()
    assert frappe.local.team_access_doctype == "CRM Lead"
    frappe.form_dict = Doc(dt="FCRM Note", dn="note")
    frappe.local.request.path = "/api/method/run_doc_method"
    forbidden(request.guard)
    print("PASS raw metadata/nested onload/link-title and compressed table sanitizing; explicit aliased raw fields and private controller RPC denied")

    for doctype in ("Comment", "Communication"):
        draft = Doc(doctype=doctype, owner="b", reference_doctype="FCRM Note", reference_name="note", content="new-private-copy", timeline_links=[])
        forbidden(lambda: events.validate(draft))
        draft.reference_doctype, draft.reference_name = "CRM Lead", "parent"
        events.validate(draft)
    frappe.session.user = "a"
    changed = deepcopy(linked)
    changed.timeline_links = []
    forbidden(lambda: events.validate(changed))
    cyclic = put("Comment", "cycle", reference_doctype="Comment", reference_name="cycle")
    forbidden(lambda: references.private_roots(doc=cyclic))
    del records[("Comment", "cycle")]
    dangling = Doc(doctype="Communication", timeline_links=[Doc(link_doctype="FCRM Note", link_name="missing")])
    forbidden(lambda: references.private_roots(doc=dangling))
    forbidden(lambda: references.private_roots(doc=Doc(doctype="Communication", reference_doctype="FCRM Note")))
    chain = "note"
    dt = "FCRM Note"
    for index in range(13):
        row = put("Comment", "depth-" + str(index), reference_doctype=dt, reference_name=chain)
        dt, chain = row.doctype, row.name
    forbidden(lambda: references.private_roots(dt, chain))
    oversized = Doc(doctype="Communication", timeline_links=[Doc(link_doctype="CRM Lead", link_name="parent")] * (policy.MAX_ROWS + 1))
    forbidden(lambda: references.private_roots(doc=oversized))
    limit = references.MAX_ROWS
    references.MAX_ROWS = 2
    forbidden(lambda: references.private_roots(doc=linked))
    references.MAX_ROWS = limit
    print("PASS old/new graph immutability, dangling/half reference, cycle, depth12, edge2000 and visited-node bounds fail closed")

    for cls, source in ((realtime.ActivityNote, note), (realtime.ActivityTask, task), (realtime.ActivityComment, nested), (realtime.ActivityCommunication, linked), (realtime.ActivityToDo, records[("ToDo", "todo-note")]), (files.ActivityFile, alias)):
        cls(source).notify_update()
    realtime.ActivityComment(nested).notify_change("add")
    realtime.ActivityCommunication(linked).notify_change("add")
    chat = realtime.ActivityCommunication(linked)
    chat.communication_type = "Chat"
    chat.after_insert()
    assert not pushed
    realtime.ActivityCommunication(formal).notify_update()
    realtime.ActivityCommunication(formal).notify_change("add")
    realtime.ActivityCommunication(formal).after_insert()
    assert len(pushed) == 3
    for user in ("a", "b", "Administrator"):
        frappe.session.user = user
        forbidden(lambda: realtime.can_subscribe_doc("FCRM Note", "note"))
        forbidden(lambda: realtime.can_subscribe_doc("File", "alias"))
        assert realtime.can_subscribe_doc("CRM Lead", "parent")
    print("PASS no private body/doc/list realtime emits; ordinary formal events preserved; all-user private doc subscriptions denied, parent allowed")

    if upstream:
        frappe.session.user = "a"
        before = deepcopy(task)
        pending = realtime.ActivityTask(task)
        pending.assigned_to = "b"
        pending._before = before
        pending.validate()
        assert not writes
        task.assigned_to = "b"
        pending.on_update()
        assert writes and writes[-1][0] == "assign" and writes[-1][1]["assign_to"] == ["b"]
        assert policy.can_contribute("CRM Task", "7", "b")
        pending = realtime.ActivityTask(task)
        pending._before = deepcopy(task)
        pending.assigned_to = "a"
        pending.validate()
        assert writes[-1][0] == "unassign" and task.assigned_to is None
        task.assigned_to = "a"
        pending.on_update()
        assert writes[-1][0] == "assign" and writes[-1][1]["assign_to"] == ["a"] and task.assigned_to == "a"
        print("PASS fixed upstream CRMTask assign deferred until stored grant; old unassign preserved before DB update without clearing the new assignee")
    verify_parent_controllers(upstream)
    if upstream:
        verify_delete_feed(upstream)
    verify_snapshots()
    verify_driver()
    print("LOCAL ONLY: in-memory Frappe replacement, not installed framework/HTTP/socket/UI acceptance")


def verify_parent_controllers(upstream):
    from team_access import hooks, parents
    from crm.fcrm.doctype.crm_lead.crm_lead import CRMLead
    from crm.fcrm.doctype.crm_deal.crm_deal import CRMDeal

    for doctype, cls, original in (("CRM Lead", parents.ActivityLead, CRMLead), ("CRM Deal", parents.ActivityDeal, CRMDeal)):
        assert cls.__bases__ == (original,) and cls.no_feed_on_delete is True
        assert set(cls.__dict__) - {"__module__", "__doc__", "__firstlineno__", "__static_attributes__"} == {"no_feed_on_delete"}
        assert hooks.override_doctype_class[doctype] == "team_access.parents." + cls.__name__
        for name, value in original.__dict__.items():
            if callable(value) or isinstance(value, (staticmethod, classmethod)):
                assert getattr(cls, name) is getattr(original, name)
        if upstream:
            assert original.__bases__ == (Base,)
            assert not hasattr(original, "no_feed_on_delete")
            assert "on_trash" not in original.__dict__ and "after_delete" not in original.__dict__
        pending = cls(doctype=doctype, name="parent", owner="a")
        before = len(pushed)
        pending.notify_update()
        assert len(pushed) == before + 1
        pushed.pop()
    source = "fixed native class definitions" if upstream else "in-memory controller replacements"
    print("PASS parent subclasses only disable delete feed; hook mapping, inherited methods and ordinary update notification preserved (" + source + ")")


def verify_delete_feed(upstream):
    from team_access import events, parents, realtime

    path = upstream / "apps/frappe/frappe/model/delete_doc.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "insert_feed")
    namespace = {"frappe": frappe, "_": lambda value: value}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)
    module("frappe.utils", get_fullname=lambda user: user)
    frappe.flags.in_uninstall = frappe.flags.in_import = False
    frappe.session.user = "a"
    original = frappe.get_doc
    emitted = []

    class Feed(Doc):
        def insert(self, **kwargs):
            emitted.append(dict(self))
            events.validate(self)

    frappe.get_doc = lambda values: Feed(values)
    try:
        for doctype in ("CRM Lead", "CRM Deal"):
            before = len(emitted)
            forbidden(lambda: namespace["insert_feed"](Doc(doctype=doctype, name="parent", owner="a", no_feed_on_delete=False)))
            assert len(emitted) == before + 1 and emitted[-1]["comment_type"] == "Deleted" and not emitted[-1].get("reference_name")
        for doctype, cls in (("CRM Lead", parents.ActivityLead), ("CRM Deal", parents.ActivityDeal)):
            namespace["insert_feed"](cls(doctype=doctype, name="parent", owner="a"))
        namespace["insert_feed"](realtime.ActivityNote(records[("FCRM Note", "note")]))
        assert len(emitted) == 2
    finally:
        frappe.get_doc = original
    print("PASS actual fixed insert_feed: original parent half-reference denied, Lead/Deal subclasses and private activity skip only feed generation; real CRUD/snapshot persistence still untested")


def verify_snapshots():
    from team_access import deleted, events, permissions as policy, request

    snapshots = [
        ("s-note", {"doctype": "FCRM Note", "name": "gone-note", "custom_team_visibility": "Shared"}),
        ("s-history", {"doctype": "Comment", "name": "gone-history", "reference_doctype": "FCRM Note", "reference_name": "missing-root"}),
        ("s-linked", {"doctype": "Communication", "name": "gone-linked", "reference_doctype": "CRM Lead", "reference_name": "parent", "timeline_links": [{"link_doctype": "FCRM Note", "link_name": "note"}]}),
        ("s-alias", {"doctype": "File", "name": "gone-alias", "attached_to_doctype": "CRM Lead", "attached_to_name": "parent", "is_private": 1}),
        ("s-cache", {"doctype": "CRM Lead", "name": "gone-cached-parent", "_comments": "private-old-cache"}),
        ("s-formal", {"doctype": "Comment", "name": "gone-formal", "reference_doctype": "CRM Lead", "reference_name": "parent"}),
        ("s-parent", {"doctype": "CRM Lead", "name": "gone-parent"}),
    ]
    for name, data in snapshots:
        put("Deleted Document", name, deleted_doctype=data["doctype"], deleted_name=data["name"], data=json.dumps(data))
    put("Deleted Document", "s-bad", deleted_doctype="Comment", deleted_name="missing", data="{invalid")
    put("Deleted Document", "s-mismatch", deleted_doctype="CRM Lead", deleted_name="other", data=json.dumps({"doctype": "FCRM Note", "name": "other"}))
    restored = []
    module("frappe.core.doctype.deleted_document.deleted_document", restore=lambda *args: restored.append(args), bulk_restore=lambda names: restored.extend(names))
    frappe.db.escape = lambda value, **kwargs: "'" + value + "'"
    for user in ("a", "b", "System Manager", "Administrator"):
        frappe.session.user = user
        allowed = policy.allowed_names("Deleted Document", user)
        assert set(allowed) == {"s-formal", "s-parent"}
        assert "s-note" not in policy.query_condition(user, "Deleted Document")
        for name in ("s-note", "s-history", "s-linked", "s-alias", "s-cache", "s-bad", "s-mismatch"):
            doc = records[("Deleted Document", name)]
            assert not policy.permitted(doc, user)
            forbidden(lambda: deleted.restore(name))
            forbidden(lambda: events.on_trash(doc))
            frappe.form_dict = Doc()
            frappe.local.request = types.SimpleNamespace(path="/api/resource/Deleted%20Document/" + name, method="GET")
            forbidden(request.guard)
        before = len(restored)
        forbidden(lambda: deleted.bulk_restore(["s-parent", "s-note"]))
        assert len(restored) == before
        deleted.restore("s-parent")
        deleted.bulk_restore(["s-formal", "s-parent"])
        assert len(restored) == before + 3
    native_denied.add(("CRM Lead", "parent", "b", "read"))
    assert not deleted.permitted_snapshot(records[("Deleted Document", "s-formal")], "b")
    native_denied.clear()
    assert len([key for key in records if key[0] == "Deleted Document"]) == len(snapshots) + 2
    print("PASS Deleted Document snapshot structure/missing-root/alias/cache denials for all identities incl admin; list/query/detail guard/single+bulk restore preflight; formal/current-parent positives, no snapshot deletion")


def verify_driver():
    import base64
    import verify_http as driver

    docs, contents = {}, {}

    class Session:
        def __init__(self, user):
            self.user = user

        def resource(self, doctype, name=None, method="GET", payload=None, **kwargs):
            if method == "POST":
                data = {"doctype": doctype, "name": "fixture-" + str(len(docs)), "owner": self.user, **payload}
                if doctype == "File":
                    data.setdefault("file_url", "/private/files/" + data["file_name"])
                    if data.get("content"):
                        contents[data["file_url"]] = base64.b64decode(data["content"]) if data.get("decode") else data["content"].encode()
                docs[(doctype, data["name"])] = data
            else:
                data = docs[(doctype, str(name))]
                if method == "PUT":
                    data.update(payload)
            return driver.Result(200, json.dumps({"data": data}).encode(), {})

        def request(self, method, path):
            return driver.Result(200, contents[path], {})

    a, b, maintenance = Session("a"), Session("b"), Session("maintenance")
    f = {"prefix": "M8-local", "user_a": "a", "user_b": "b", "legacy_shares": True, "shared_parent": "parent", "note": "note", "task": "task"}
    for key, dt in (("note", "FCRM Note"), ("task", "CRM Task")):
        docs[(dt, key)] = {"doctype": dt, "name": key, "owner": "a", "title": "M8-local-" + key, "reference_doctype": "CRM Lead", "reference_docname": "parent"}
    driver.prepare_history(a, maintenance, f)
    assert len(f["history"]) == 2 and all(len(value) == 4 for value in f["history"].values())
    driver.prepare_legacy(a, b, maintenance, f)
    graph = f["legacy_graph"]
    assert graph["alias"]["file_url"] == graph["file"]["file_url"]
    assert docs[("File", graph["alias"]["name"])]["owner"] == "b"
    linked = docs[("Communication", graph["communication"]["name"])]
    assert linked["reference_doctype"] == "CRM Lead" and len(linked["timeline_links"]) == 2
    assert all(docs[("ToDo", todo["name"])]["allocated_to"] == "b" for todo in graph["todos"].values())
    count = len(docs)
    for setup in (lambda: driver.prepare_legacy(a, b, maintenance, f), lambda: driver.prepare_history(a, maintenance, f)):
        try:
            setup()
        except RuntimeError:
            pass
        else:
            raise AssertionError("duplicate preparation accepted")
    assert len(docs) == count
    fresh = {key: value for key, value in f.items() if key != "legacy_graph"}
    docs[("FCRM Note", "note")]["custom_team_visibility"] = "Private"
    try:
        driver.prepare_legacy(a, b, maintenance, fresh)
    except RuntimeError:
        pass
    else:
        raise AssertionError("post-install legacy setup accepted")
    assert len(docs) == count
    print("PASS real HTTP driver's synthetic preparation logic: 8 buckets/2 linked communications, legacy two-root foreign-owner alias, ToDo, duplicate/post-install refusal; transport is simulated")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deterministic, standard-library-only permission regression; never connects to a site or database")
    parser.add_argument("--upstream-root", type=Path, help="optional fixed-source evidence root for CRMTask methods, Lead/Deal inheritance and native insert_feed")
    run(parser.parse_args().upstream_root)

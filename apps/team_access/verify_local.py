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
    if isinstance(filters, list):
        filters = {row[-3]: [row[-2], row[-1]] if row[-2] != "=" else row[-1] for row in filters}
    if isinstance(filters, dict):
        def matches(doc, key, value):
            if isinstance(value, (tuple, list)):
                operation, expected = value
                if operation == "in":
                    return doc.get(key) in expected
                if operation == "like":
                    return expected.strip("%") in str(doc.get(key) or "")
                raise AssertionError("unsupported replacement-store filter")
            return (doc.get(key) or 0) == value
        rows = [doc for doc in rows if all(matches(doc, key, value) for key, value in filters.items())]
    if limit_page_length:
        rows = rows[:limit_page_length]
    if kwargs.get("pluck"):
        values = [row.get(kwargs["pluck"]) for row in rows]
        return list(dict.fromkeys(values)) if kwargs.get("distinct") else values
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
    frappe.conf = Doc(team_access_synthetic_only=1)
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
    frappe.get_meta = lambda dt: Doc(get_table_fields=lambda: [], get_field=lambda field: None, istable=0)
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
        ("frappe.core.doctype.communication_link.communication_link", "CommunicationLink"),
        ("frappe.core.doctype.dynamic_link.dynamic_link", "DynamicLink"),
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
    verify_r3(upstream)
    from verify_relations import verify_r4

    verify_r4(sys.modules[__name__], upstream)
    from verify_r6 import run as verify_r6

    verify_r6(sys.modules[__name__], upstream)
    from verify_r7 import run as verify_r7

    verify_r7(sys.modules[__name__], upstream)
    verify_driver()
    print("LOCAL ONLY: in-memory Frappe replacement, not installed framework/HTTP/socket/UI acceptance")


def verify_parent_controllers(upstream):
    from team_access import hooks, parents, realtime
    from crm.fcrm.doctype.crm_lead.crm_lead import CRMLead
    from crm.fcrm.doctype.crm_deal.crm_deal import CRMDeal

    for doctype, cls, original in (("CRM Lead", parents.ActivityLead, CRMLead), ("CRM Deal", parents.ActivityDeal, CRMDeal)):
        assert cls.__bases__ == (realtime.PrivateUpdate, original) and cls.no_feed_on_delete is True
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
    print("PASS parent hook mapping and pre-delete mixin; inherited business methods and ordinary update notification preserved (" + source + ")")


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
    print("PASS isolated fixed insert_feed: original parent half-reference denied and subclass feed suppressed; R3 separately blocks parent/activity deletion, real lifecycle/snapshot persistence still untested")


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


def load_native(path, names, namespace, controller=None):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes = tree.body if controller is None else next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == controller).body
    selected = [n for n in nodes if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names]
    assert len(selected) == len(names)
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


def verify_r3(upstream):
    from html import escape
    from urllib.parse import quote
    from team_access import api, docinfo, events, files, install, parents, permissions as policy, realtime, references

    frappe.session.user = "a"
    frappe.safe_encode = lambda value: value.encode()
    for key in list(records):
        if key[0] == "Comment" and key[1].startswith("depth-"):
            del records[key]
    for value in (None, 0, "1", True, 2):
        frappe.conf.team_access_synthetic_only = value
        forbidden(install.preflight)
    frappe.conf.team_access_synthetic_only = 1
    install.preflight()
    assert "Communication" in frappe.response["team_access_legacy_provenance_unverified"]
    note = records[("FCRM Note", "note")]
    task = records[("CRM Task", "7")]
    for user in ("a", "b", "Administrator"):
        frappe.session.user = user
        for cls, source in ((realtime.ActivityNote, note), (realtime.ActivityTask, task), (realtime.ActivityCommunication, records[("Communication", "linked")]), (realtime.ActivityComment, records[("Comment", "nested")]), (files.ActivityFile, records[("File", "original")]), (files.ActivityFile, records[("File", "alias")]), (parents.ActivityLead, records[("CRM Lead", "parent")]), (parents.ActivityDeal, Doc(doctype="CRM Deal", name="deal", owner="a"))):
            forbidden(lambda: cls(source).on_trash())
            forbidden(lambda: events.on_trash(source))
        orphan = Doc(doctype="FCRM Note", name="standalone", owner=user)
        forbidden(lambda: realtime.ActivityNote(orphan).on_trash())
    frappe.session.user = "a"
    events.on_trash(records[("Communication", "formal")])
    events.on_trash(Doc(doctype="Contact", name="ordinary", owner="a"))
    print("PASS synthetic-only preflight missing/illegal value refusal; all-identity Note/Task/Lead/Deal and multi-root/nested/File deletion refusal; ordinary formal/unrelated deletion predicate preserved")

    ordinary = put("File", "ordinary-file", attached_to_doctype="CRM Lead", attached_to_name="parent", file_name="ordinary.txt", file_url="/private/files/ordinary.txt", is_private=1, is_folder=0)
    alias = records[("File", "alias")]
    native_file = None
    if upstream:
        namespace = {"frappe": frappe, "quote": quote, "escape_html": escape}
        load_native(upstream / "apps/frappe/frappe/core/doctype/file/file.py", {"after_insert", "create_attachment_record", "add_comment_in_reference_doc", "on_trash"}, namespace, "File")
        native_file = type("NativeFileLifecycle", (Base,), {key: namespace[key] for key in ("after_insert", "create_attachment_record", "add_comment_in_reference_doc", "on_trash")})
    logs = []
    original_get = frappe.get_doc
    def add_log(kind, content):
        log = put("Comment", "r3-log-" + str(len(logs)), reference_doctype="CRM Lead", reference_name="parent", comment_type=kind, content=content, creation="2026-01-02")
        logs.append(log)
        return log
    try:
        frappe.get_doc = lambda dt, name: Doc(add_comment=add_log)
        for source in (alias, ordinary):
            if native_file:
                native_file(source).after_insert()
            else:
                add_log("Attachment", f"<a href='{quote(source.file_url, safe='/:')}' target='_blank'>{escape(source.file_name)}</a> <i class=\"fa fa-lock text-warning\"></i>")
    finally:
        frappe.get_doc = original_get
    secret_log, ordinary_log = logs
    opaque = add_log("Attachment Removed", alias.file_name)
    forged = add_log("Attachment", ordinary_log.content + "unexpected-private-copy")
    missing = add_log("Attachment", "<a href='/private/files/gone.txt' target='_blank'>gone.txt</a>")
    copied = put("Comment", "r3-copy", reference_doctype="Comment", reference_name=secret_log.name, comment_type="Info", content="copied-log")
    version = put("Version", "r3-log-version", ref_doctype="Comment", docname=secret_log.name, data="{}")
    assert references.private_roots(doc=secret_log) == {("FCRM Note", "note"), ("CRM Task", "7")}
    normalized = deepcopy(ordinary_log)
    normalized.content = normalized.content.replace("href='", 'href="').replace("' target='_blank'", '" target="_blank"')
    assert policy.permitted(normalized, "b")
    unknown_copy = put("Comment", "r3-unknown-copy", reference_doctype="Comment", reference_name=opaque.name, comment_type="Info", content="hidden-removed-copy")
    assert not policy.permitted(unknown_copy, "b") and realtime.private_document(unknown_copy)
    events.validate(Doc(doctype="Comment", owner="a", comment_type="Attachment Removed", reference_doctype="CRM Lead", reference_name="parent", content="ordinary.txt"))
    for user in ("a", "b"):
        frappe.session.user = user
        assert policy.permitted(secret_log, user) == (user == "a")
        assert policy.permitted(copied, user) == (user == "a")
        assert policy.permitted(version, user) == (user == "a")
        assert policy.permitted(ordinary_log, user)
        assert all(not policy.permitted(log, user) for log in (opaque, forged, missing))
        frappe.response["docinfo"] = {"attachment_logs": deepcopy(logs), "user_info": {}}
        docinfo.scrub("CRM Lead", "parent")
        visible = {row.name for row in frappe.response["docinfo"]["attachment_logs"]}
        assert ordinary_log.name in visible and (secret_log.name in visible) == (user == "a")
        assert not {opaque.name, forged.name, missing.name} & visible
        allowed = set(policy.allowed_names("Comment", user))
        assert (secret_log.name in allowed) == (user == "a") and ordinary_log.name in allowed
    if upstream:
        namespace = {"frappe": frappe, "has_controller_permissions": lambda probe, ptype, user=None: policy.has_permission(probe, ptype, user) is not False}
        load_native(upstream / "apps/frappe/frappe/core/doctype/comment/comment.py", {"get_document_comments"}, namespace)
        load_native(upstream / "apps/frappe/frappe/desk/form/load.py", {"add_comments"}, namespace)
        for user in ("a", "b"):
            frappe.session.user = user
            info = Doc()
            namespace["add_comments"](records[("CRM Lead", "parent")], info)
            assert not info.attachment_logs
            frappe.response["docinfo"] = info
            docinfo.scrub("CRM Lead", "parent")
            visible = {row.name for row in info.attachment_logs}
            assert ordinary_log.name in visible and (secret_log.name in visible) == (user == "a")
    before = len(pushed)
    realtime.ActivityComment(secret_log).notify_change("add")
    realtime.ActivityComment(opaque).notify_change("add")
    assert len(pushed) == before
    realtime.ActivityComment(ordinary_log).notify_change("add")
    assert len(pushed) == before + 1
    pushed.pop()
    print("PASS native attachment-log source generation/metadata filtering, direct/list/history copies and parent docinfo; all URL aliases rechecked; unknown/removed/forged logs hidden, ordinary log and owner positives")

    note.title, note.creation = "current-note", "2026-01-01"
    pins = [put("Version", "r3-pin-" + str(index), ref_doctype="FCRM Note", docname="note", owner_marker="historical-actor", creation="2026-01-0" + str(index + 3), data=json.dumps({"changed": [["pinned", 1 - index, index]]})) for index in (0, 1)]
    for pin in pins:
        pin.owner = "historical-actor"
    if upstream:
        namespace = {"frappe": frappe, "json": json}
        load_native(upstream / "apps/crm/crm/api/activities.py", {"get_note_activities", "group_note_activities", "ungroup_note_activities"}, namespace)
        project = lambda: namespace["group_note_activities"](namespace["get_note_activities"]([deepcopy(note)], True))
        group = namespace["group_note_activities"]
    else:
        project = lambda: [{"activity_type": "note", "name": "note", "owner": "a", "creation": note.creation, "data": {"action": "added", "note": "note"}, "other_notes": [{"activity_type": "note", "name": pin.name, "creation": pin.creation, "owner": pin.owner, "data": {"action": "pinned" if index else "unpinned", "note": "note"}} for index, pin in enumerate(pins)]}]
        group = lambda value: value
    upstream_api = module("crm.api.activities", get_attachments=lambda *args: [], group_note_activities=group, parse_attachment_log=lambda content, kind: {"content": content, "kind": kind})
    def aggregate_source(name):
        entries = project()
        entries.extend({"activity_type": "attachment_log", "name": log.name, "creation": log.creation, "data": {"content": log.content}} for log in logs)
        return entries, [], [deepcopy(note)], [], []
    upstream_api.get_activities = aggregate_source
    module("frappe.desk.form.load", _get_communications=lambda *args, **kwargs: [])
    for user, grant in (("a", ""), ("b", ""), ("b", "b"), ("b", "")):
        frappe.session.user, note.custom_team_collaborator = user, grant
        data = json.dumps(api.get_activities("parent"))
        writer = user == "a" or grant == "b"
        assert all((pin.name in data) == writer for pin in pins)
        assert ("historical-actor" in data) == writer and "current-note" in data
        assert (secret_log.name in data) == (user == "a") and ordinary_log.name in data
        assert "unexpected-private-copy" not in data and missing.name not in data and opaque.name not in data
    note.custom_team_collaborator = ""
    print("PASS fixed note pin/unpin projections through complete aggregate incl grouped other_notes: current added note survives, Shared-only history hidden, owner/collaborator positive and revoke immediate; attachment log aggregate filtered")
    if upstream:
        verify_native_deletion(upstream, native_file)
        verify_native_communication(upstream)


def verify_native_deletion(upstream, native_file):
    from team_access import events, files, parents, realtime, permissions as policy
    from frappe.core.doctype.file.file import File

    path = upstream / "apps/frappe/frappe/model/delete_doc.py"
    trace = []
    namespace = {"frappe": frappe, "_": lambda value: value, "is_virtual_doctype": lambda dt: False, "delete_all_passwords_for": lambda *args: None, "update_flags": lambda *args: None, "check_permission_and_not_submitted": lambda *args: trace.append("permission")}
    for name in ("check_if_doc_is_linked", "check_if_doc_is_dynamically_linked", "update_naming_series", "delete_from_table", "remove_all", "delete_for_document", "delete_tags_for_document", "add_to_deleted_document", "insert_feed"):
        namespace[name] = lambda *args, _name=name, **kwargs: trace.append(_name)
    load_native(path, {"delete_doc", "delete_dynamic_links", "delete_references", "clear_references", "clear_timeline_references"}, namespace)
    original_get, original_db = frappe.get_doc, frappe.db
    original_trash = File.__dict__.get("on_trash")
    original_enqueue = getattr(frappe, "enqueue", None)
    File.on_trash = native_file.on_trash
    frappe.flags.in_test = frappe.flags.in_patch = False
    frappe.enqueue = lambda *args, **kwargs: trace.append("enqueue")
    controllers = {"FCRM Note": realtime.ActivityNote, "CRM Task": realtime.ActivityTask, "Communication": realtime.ActivityCommunication, "Comment": realtime.ActivityComment, "File": files.ActivityFile, "CRM Lead": parents.ActivityLead, "CRM Deal": parents.ActivityDeal}
    def get_doc(dt, name):
        pending = controllers.get(dt, Base)(records[(dt, str(name))])
        pending.flags = Doc()
        pending.clear_cache = lambda: trace.append("cache")
        pending.run_method = lambda method: (getattr(pending, method)() if callable(getattr(pending, method, None)) else None, events.on_trash(pending) if method == "on_trash" else None)
        pending.validate_empty_folder = lambda: trace.append("folder")
        pending.validate_protected_file = lambda: trace.append("protected_file")
        pending._delete_file_on_disk = lambda: trace.append("disk_delete")
        pending.add_comment_in_reference_doc = lambda *args: trace.append("removed_log")
        return pending
    frappe.get_doc = get_doc
    frappe.db = types.SimpleNamespace(**vars(original_db))
    frappe.db.get_value = lambda *args, **kwargs: None
    try:
        for user in ("a", "b", "Administrator"):
            frappe.session.user = user
            for dt, name in (("FCRM Note", "note"), ("CRM Task", "7"), ("Communication", "linked"), ("Comment", "nested"), ("File", "original"), ("File", "alias"), ("CRM Lead", "parent")):
                trace.clear()
                forbidden(lambda: namespace["delete_doc"](dt, name))
                assert trace == ["permission"]
        frappe.session.user = "a"
        trace.clear()
        namespace["delete_doc"]("File", "ordinary-file")
        assert "disk_delete" in trace and "delete_from_table" in trace and "enqueue" in trace
        trace.clear()
        namespace["delete_doc"]("Communication", "formal")
        assert "delete_from_table" in trace and "enqueue" in trace
    finally:
        frappe.get_doc, frappe.db = original_get, original_db
        frappe.enqueue = original_enqueue
        if original_trash is None:
            del File.on_trash
        else:
            File.on_trash = original_trash
    snapshot = deepcopy(records)
    def delete(dt, filters):
        if dt == "Communication Link":
            for (kind, _), row in records.items():
                if kind == "Communication":
                    row.timeline_links = [link for link in row.get("timeline_links", []) if not all(link.get(key) == value for key, value in filters.items())]
        else:
            for key, row in list(records.items()):
                if key[0] == dt and all(row.get(field) == value for field, value in filters.items()):
                    del records[key]
    def sql(query, args):
        dt, name = args
        for (kind, _), row in records.items():
            if kind == "Communication" and row.get("reference_doctype") == dt and row.get("reference_name") == name:
                row.reference_doctype = row.reference_name = None
    original_db = frappe.db
    frappe.db = types.SimpleNamespace(**vars(original_db))
    frappe.db.delete, frappe.db.sql = delete, sql
    try:
        namespace["delete_dynamic_links"]("FCRM Note", "note")
        assert not policy.permitted(records[("Communication", "linked")], "b")
        namespace["delete_dynamic_links"]("CRM Task", "7")
        assert not records[("Communication", "linked")].timeline_links
        assert policy.permitted(records[("Communication", "linked")], "b")
    finally:
        records.clear()
        records.update(snapshot)
        frappe.db = original_db
    assert not policy.permitted(records[("Communication", "linked")], "b")
    print("PASS actual delete_doc order: every private/parent rejection precedes disk/delete/queue side effects incl Admin; ordinary File/formal lifecycle positive. Actual async cleanup reproduces unsafe legacy loss only in restored isolated replacement store; protected deletion never enqueues it")


def verify_native_communication(upstream):
    from team_access import parents, realtime
    from frappe.core.doctype.communication.communication import Communication

    path = upstream / "apps/frappe/frappe/core/doctype/communication/communication.py"
    trace, published = [], []
    parent = parents.ActivityLead(doctype="CRM Lead", name="parent", creation=10, modified=20, status="Replied", first_response_time=0)
    parent.meta = Doc(get_field=lambda name: Doc(options="Open\nReplied") if name == "status" else None, has_field=lambda name: name in ("first_response_time", "first_responded_on", "avg_response_time"))
    def db_set(field, value):
        trace.append((field, value))
        parent[field] = value
    parent.db_set = db_set
    parent.run_method = lambda method, *args: trace.append((method,))
    namespace = {"frappe": frappe, "Document": Base, "CommunicationEmailMixin": type("CommunicationEmailMixin", (), {}), "get_parent_doc": lambda doc: parent, "apply_assignment_rule": lambda doc: trace.append(("assignment_rule",)), "is_system_user": lambda sender: True, "time_diff_in_seconds": lambda a, b: a - b, "json": json, "is_virtual_doctype": lambda dt: False, "clear_cache": lambda *args: None}
    load_native(upstream / "apps/frappe/frappe/core/doctype/comment/comment.py", {"update_comment_in_doc", "get_comments_from_parent", "update_comments_in_parent"}, namespace)
    load_native(path, {"Communication", "update_parent_document_on_communication", "update_first_response_time", "set_avg_response_time"}, namespace)
    native = namespace["Communication"]
    document = {"frappe": frappe}
    load_native(upstream / "apps/frappe/frappe/model/document.py", {"notify_update"}, document, "Document")
    old_update = Communication.__dict__.get("on_update")
    old_notify, old_db = Base.notify_update, frappe.db
    old_list = getattr(frappe, "get_list", None)
    Communication.on_update = native.on_update
    Base.notify_update = document["notify_update"]
    frappe.publish_realtime = lambda *args, **kwargs: published.append((args, kwargs))
    frappe.flags.in_patch = False
    frappe.get_cached_value = lambda *args: None
    frappe.get_list = lambda *args, **kwargs: [Doc(sent_or_received="Received", creation=12), Doc(sent_or_received="Sent", creation=20)]
    frappe.db = types.SimpleNamespace(**vars(old_db))
    frappe.db.get_value = lambda dt, name, field=None, **kwargs: None
    frappe.db.set_value = lambda *args, **kwargs: trace.append(("cache_write", args[2], args[3]))
    def exercise(cls, private, sent="Sent"):
        trace.clear()
        published.clear()
        parent.status, parent.first_response_time = "Replied", 0
        value = cls(doctype="Communication", name="r3-comm", reference_doctype="CRM Lead", reference_name="parent", timeline_links=[Doc(link_doctype="FCRM Note", link_name="note")] if private else [], communication_type="Communication", sent_or_received=sent, sender="a", creation=20, content="business-copy", comment_type="Comment")
        value.on_update()
        assert not getattr(frappe.local, "team_access_private_communication_update", False)
        return list(trace), list(published)
    try:
        frappe.session.user = "a"
        baseline, emitted = exercise(native, True)
        assert len(emitted) == 2 and any("user" in args[1] for args, _ in emitted)
        persisted, hidden = exercise(realtime.ActivityCommunication, True)
        assert persisted == baseline and not hidden
        assert any(row[0] == "first_response_time" for row in persisted) and any(row[0] == "avg_response_time" for row in persisted) and any(row[0] == "cache_write" for row in persisted)
        formal, emitted = exercise(realtime.ActivityCommunication, False)
        assert formal == baseline and len(emitted) == 2
        baseline, _ = exercise(native, True, "Received")
        persisted, hidden = exercise(realtime.ActivityCommunication, True, "Received")
        assert persisted == baseline and not hidden and ("status", "Open") in persisted and ("assignment_rule",) in persisted
        parent.on_communication_update = lambda doc: (trace.append(("custom_parent_callback",)), parent.notify_update())
        _, hidden = exercise(realtime.ActivityCommunication, True)
        assert not hidden and ("custom_parent_callback",) in trace
        _, emitted = exercise(realtime.ActivityCommunication, False)
        assert len(emitted) == 2
        parent.on_communication_update = lambda doc: (_ for _ in ()).throw(RuntimeError("synthetic callback failure"))
        try:
            exercise(realtime.ActivityCommunication, True)
        except RuntimeError:
            assert not getattr(frappe.local, "team_access_private_communication_update", False)
        else:
            raise AssertionError("callback failure not preserved")
    finally:
        Base.notify_update, frappe.db, frappe.get_list = old_notify, old_db, old_list
        if old_update is None:
            del Communication.on_update
        else:
            Communication.on_update = old_update
    print("PASS full fixed Communication.on_update + actual parent/cache/response-time/assignment/publish methods: private persistence equals native, shared-parent doc/list events suppressed; ordinary formal/callback positives and scoped-state exception restoration")


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

        def rpc(self, method, args):
            assert method == "frappe.desk.form.load.get_docinfo"
            logs = [{"name": "log-" + doc["name"], "comment_type": "Attachment", "content": doc["file_name"] + " " + doc["file_url"]} for (dt, _), doc in docs.items() if dt == "File" and doc.get("attached_to_doctype") == args["doctype"] and doc.get("attached_to_name") == args["name"]]
            return driver.Result(200, json.dumps({"docinfo": {"attachment_logs": logs}}).encode(), {})

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
    parser.add_argument("--upstream-root", type=Path, help="optional fixed-source evidence root for native task, parent, attachment-log, pin-aggregate, deletion, full Communication update, v1/v2 PUT parent-save, independent relation lifecycle, existing-root freeze/preflight transition, first-insert/relink and ToDo -> Shared -> wildcard CSV/compressed-user-info, CRM resolved saved-view/group/kanban projection and REST collection JSON-contract regressions")
    run(parser.parse_args().upstream_root)

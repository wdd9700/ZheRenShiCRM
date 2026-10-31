import argparse
import base64
import getpass
import http.cookiejar
import json
import os
from pathlib import Path
import re
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request


class Result:
    def __init__(self, status, body, headers):
        self.status, self.body, self.headers = status, body, headers

    def json(self):
        return json.loads(self.body)


class Session:
    def __init__(self, base, site, user, password, purpose="sales"):
        self.base, self.site, self.user = base.rstrip("/"), site, user
        self.csrf = None
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        require(self.request("POST", "/api/method/login", form={"usr": user, "pwd": password}).status == 200, "login")
        identity = self.rpc("frappe.auth.get_logged_user")
        require(identity.status == 200 and identity.json().get("message") == user and user != "Administrator", "independent non-admin identity")
        page = self.request("GET", "/crm")
        match = re.search(rb"csrf_token[\"'\]]*\s*[:=]\s*[\"']([^\"']+)", page.body)
        self.csrf = next((c.value for c in self.jar if c.name == "csrf_token"), None) or (match.group(1).decode() if match else None)
        require(bool(self.csrf), "CSRF session token")
        profile = self.resource("User", user)
        require(profile.status == 200, "own role profile available")
        roles = {r["role"] for r in profile.json()["data"].get("roles", [])}
        if purpose == "history":
            require("System Manager" in roles, "existing System Manager history maintenance account")
        else:
            require(purpose == "sales" and "Sales User" in roles and not roles.intersection({"System Manager", "Sales Manager"}), "Sales User without manager roles")

    def request(self, method, path, params=None, payload=None, form=None):
        if params:
            path += "?" + urllib.parse.urlencode({k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in params.items()})
        headers = {"Host": self.site, "Accept": "application/json", "Cache-Control": "no-cache"}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        if form is not None:
            data = urllib.parse.urlencode(form).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if self.csrf and method not in ("GET", "HEAD"):
            headers["X-Frappe-CSRF-Token"] = self.csrf
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            response = self.opener.open(request, timeout=60)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return Result(response.code, response.read(), response.headers)

    def rpc(self, method, data=None, write=False):
        return self.request("POST" if write else "GET", "/api/method/" + method, payload=data if write else None, params=None if write else data)

    def resource(self, doctype, name=None, method="GET", payload=None, params=None):
        path = "/api/resource/" + urllib.parse.quote(doctype, safe="")
        if name is not None:
            path += "/" + urllib.parse.quote(str(name), safe="")
        return self.request(method, path, params=params, payload=payload)


def require(condition, label):
    if not condition:
        raise RuntimeError(label)


def success(response, label):
    require(response.status == 200 and not response.json().get("exc"), label)
    return response.json().get("data", response.json().get("message"))


def denied(response, label):
    require(response.status == 403, label + " must return 403")


def clean(response, forbidden, label, allow_denied=False):
    require(response.status == 200 or (allow_denied and response.status == 403), label + " status")
    for value in forbidden:
        text = str(value)
        if text.isdigit():
            pattern = rb'"(?:name|note|reference_docname|link_name|value)"\s*:\s*"?' + re.escape(text.encode()) + rb'"?(?=[,}\s])'
            leaked = bool(re.search(pattern, response.body))
            try:
                parsed = response.json()
                table = parsed.get("message", parsed.get("data", {}))
                if isinstance(table, dict) and "name" in table.get("keys", []):
                    index = table["keys"].index("name")
                    leaked = leaked or any(str(row[index]) == text for row in table.get("values", []))
            except (ValueError, AttributeError, IndexError, TypeError):
                pass
            if "csv" in (response.headers.get("Content-Type", "") + response.headers.get("Content-Disposition", "")).lower():
                import csv
                import io

                leaked = leaked or any(text in row for row in csv.reader(io.StringIO(response.body.decode("utf-8-sig"))))
        else:
            leaked = text.encode() in response.body
        require(not leaked, label + " leaked a private marker or identifier")


def create(session, doctype, values):
    return success(session.resource(doctype, method="POST", payload=values), "create fixture " + doctype)


def update(session, doctype, name, values):
    return session.resource(doctype, name, "PUT", values)


def share(session, doctype, name, user, active=True):
    if active:
        return session.rpc("frappe.share.add", {"doctype": doctype, "name": name, "user": user, "read": 1, "write": int(doctype in ("FCRM Note", "CRM Task"))}, True)
    return session.rpc("frappe.share.remove", {"doctype": doctype, "name": name, "user": user}, True)


def prepare(a, b, legacy):
    prefix = "M8-" + secrets.token_hex(8)
    statuses = success(a.resource("CRM Lead Status", params={"fields": ["name"], "limit_page_length": 1}), "lead status")
    require(bool(statuses), "lead status exists")
    status = statuses[0]["name"]
    fixtures = {"prefix": prefix, "user_a": a.user, "user_b": b.user, "legacy_shares": legacy}
    for key, session in (("private_parent", a), ("shared_parent", a), ("b_parent", b)):
        doc = create(session, "CRM Lead", {"first_name": prefix + "-" + key, "status": status, "lead_owner": session.user})
        fixtures[key] = doc["name"]
    success(share(a, "CRM Lead", fixtures["shared_parent"], b.user), "explicit parent read share")
    for key, session, parent, dt in (
        ("private_note", a, "private_parent", "FCRM Note"),
        ("note", a, "shared_parent", "FCRM Note"),
        ("task", a, "shared_parent", "CRM Task"),
        ("b_note", b, "b_parent", "FCRM Note"),
        ("b_task", b, "b_parent", "CRM Task"),
    ):
        marker = prefix + "-BODY-" + key
        body_field = "content" if dt == "FCRM Note" else "description"
        values = {"title": prefix + "-" + key, body_field: marker, "reference_doctype": "CRM Lead", "reference_docname": fixtures[parent]}
        if dt == "CRM Task":
            values.update(status="Todo", priority="Medium")
        doc = create(session, dt, values)
        fixtures[key], fixtures[key + "_marker"] = doc["name"], marker
    if legacy:
        for key, dt in (("note", "FCRM Note"), ("task", "CRM Task")):
            success(share(a, dt, fixtures[key], b.user), "legacy child DocShare fixture")
    return fixtures


HISTORY_TYPES = {"assignment_logs": "Assigned", "info_logs": "Info", "like_logs": "Like", "workflow_logs": "Workflow"}


def prepare_history(a, maintenance, f):
    require(f["user_a"] == a.user and f["prefix"].startswith("M8-") and not f.get("history") and not f.get("history_communications"), "new M8 history manifest")
    history, communications = {}, {}
    for key, dt in (("note", "FCRM Note"), ("task", "CRM Task")):
        record = success(a.resource(dt, f[key]), "history fixture owner read")
        require(record["owner"] == a.user and record["title"].startswith(f["prefix"]) and record["reference_doctype"] == "CRM Lead" and record["reference_docname"] == f["shared_parent"], "history setup refuses non-M8 targets")
        require(not record.get("custom_team_collaborator") and record.get("custom_team_visibility", "Private") in (None, "", "Private"), "history setup requires unused Private fixture")
        grant = "custom_team_visibility" in record
        if grant:
            success(update(a, dt, f[key], {"custom_team_collaborator": maintenance.user}), "temporary explicit history collaborator")
        try:
            history[key] = {}
            for bucket, comment_type in HISTORY_TYPES.items():
                marker = f["prefix"] + "-HISTORY-" + key + "-" + bucket
                comment = create(maintenance, "Comment", {"comment_type": comment_type, "reference_doctype": dt, "reference_name": f[key], "content": marker})
                history[key][bucket] = {"name": comment["name"], "marker": marker}
            marker = f["prefix"] + "-HISTORY-COMM-" + key
            linked = create(maintenance, "Communication", {"communication_type": "Communication", "communication_medium": "Other", "subject": marker, "content": marker, "reference_doctype": dt, "reference_name": f[key], "timeline_links": [{"link_doctype": "CRM Lead", "link_name": f["shared_parent"]}]})
            communications[key] = {"name": linked["name"], "marker": marker}
        finally:
            if grant:
                success(update(a, dt, f[key], {"custom_team_collaborator": ""}), "withdraw temporary history collaborator")
    f["history"], f["history_communications"] = history, communications


def prepare_legacy(a, b, maintenance, f):
    require(f.get("legacy_shares") and not f.get("legacy_graph") and f["prefix"].startswith("M8-"), "fresh pre-install legacy graph fixture required")
    graph = {"todos": {}}
    for key, dt in (("note", "FCRM Note"), ("task", "CRM Task")):
        target = success(a.resource(dt, f[key]), "legacy target owner read")
        require(target["owner"] == a.user and target["title"].startswith(f["prefix"]) and "custom_team_visibility" not in target, "legacy-prepare requires pre-install M8 activities; never bypass installed guards")
        marker = f["prefix"] + "-LEGACY-TODO-" + key
        todo = create(maintenance, "ToDo", {"owner": a.user, "allocated_to": b.user, "assigned_by": a.user, "reference_type": dt, "reference_name": f[key], "description": marker, "status": "Open"})
        graph["todos"][key] = {"name": todo["name"], "marker": marker}
        values = {"title": f["prefix"] + "-FILE-" + key, "content" if dt == "FCRM Note" else "description": f["prefix"] + "-FILE-ROOT-" + key, "reference_doctype": "CRM Lead", "reference_docname": f["shared_parent"]}
        if dt == "CRM Task":
            values.update(status="Todo", priority="Medium")
        root = create(a, dt, values)
        graph[key] = root["name"]
    marker = f["prefix"] + "-TIMELINE-ONLY-MULTI-ROOT"
    linked = create(maintenance, "Communication", {"communication_type": "Communication", "communication_medium": "Other", "subject": marker, "content": marker, "reference_doctype": "CRM Lead", "reference_name": f["shared_parent"], "timeline_links": [{"link_doctype": "FCRM Note", "link_name": graph["note"]}, {"link_doctype": "CRM Task", "link_name": graph["task"]}]})
    graph["communication"] = {"name": linked["name"], "marker": marker}
    file_marker = f["prefix"] + "-LEGACY-PRIVATE-BYTES"
    original = create(a, "File", {"file_name": f["prefix"] + "-private-original.txt", "content": base64.b64encode(file_marker.encode()).decode(), "decode": 1, "is_private": 1, "attached_to_doctype": "Communication", "attached_to_name": linked["name"]})
    alias = create(b, "File", {"file_name": f["prefix"] + "-private-alias.txt", "file_url": original["file_url"], "is_private": 1, "attached_to_doctype": "CRM Lead", "attached_to_name": f["shared_parent"]})
    require(alias["owner"] == b.user and alias["file_url"] == original["file_url"], "legacy foreign-owner same-URL alias prepared")
    graph["file"] = {key: original[key] for key in ("name", "file_name", "file_url")}
    graph["alias"] = {key: alias[key] for key in ("name", "file_name", "file_url")}
    graph["file_marker"] = file_marker
    require(file_marker.encode() in success_bytes(b.request("GET", original["file_url"]), "pre-install alias byte reproduction"), "legacy alias baseline reproduces before extension")
    ordinary = create(a, "File", {"file_name": f["prefix"] + "-ordinary-parent.txt", "content": f["prefix"] + "-FORMAL-FILE", "is_private": 1, "attached_to_doctype": "CRM Lead", "attached_to_name": f["shared_parent"]})
    graph["ordinary_file"] = {key: ordinary[key] for key in ("name", "file_name", "file_url")}
    response = b.rpc("frappe.desk.form.load.get_docinfo", {"doctype": "CRM Lead", "name": f["shared_parent"]})
    require(response.status == 200, "pre-install attachment-log baseline")
    logs = response.json().get("docinfo", {}).get("attachment_logs", [])
    graph["attachment_logs"] = {}
    for key, file in (("alias", alias), ("ordinary", ordinary)):
        matching = [row["name"] for row in logs if row.get("comment_type") == "Attachment" and file["file_name"] in row.get("content", "") and file["file_url"] in row.get("content", "")]
        require(bool(matching), "native pre-install File must generate independent attachment log")
        graph["attachment_logs"][key] = matching
    f["legacy_graph"] = graph


def verify_legacy(a, b, f):
    graph = f.get("legacy_graph")
    require(graph and set(graph.get("todos", {})) == {"note", "task"}, "pre-install legacy-prepare is required for old ToDo and foreign-owner URL alias")
    for key, dt in (("note", "FCRM Note"), ("task", "CRM Task")):
        root = success(a.resource(dt, graph[key]), "legacy attachment root owner read")
        require(root["owner"] == a.user and root["title"].startswith(f["prefix"]), "refuse mutation of non-M8 attachment roots")
    require(set(graph.get("attachment_logs", {})) == {"alias", "ordinary"}, "native pre-install Attachment Comment IDs are required; old manifests must be prepared again in an isolated first-install environment")
    hidden = [graph["communication"]["name"], graph["communication"]["marker"], graph["file_marker"], *graph["attachment_logs"]["alias"]]
    for name in graph["attachment_logs"]["alias"]:
        denied(b.resource("Comment", name), "old alias Attachment Comment direct denial")
        clean(b.resource("Comment", params={"fields": ["name", "content"], "filters": {"name": name}}), [name, graph["alias"]["file_name"], graph["alias"]["file_url"]], "old alias Attachment Comment list", allow_denied=True)
        require(name.encode() in success_bytes(a.rpc("frappe.desk.form.load.get_docinfo", {"doctype": "CRM Lead", "name": f["shared_parent"]}), "owner attachment log parent positive"), "owner retains authorized historical log through native parent authorization")
    for key in ("file", "alias"):
        hidden.extend(graph[key].values())
        denied(b.resource("File", graph[key]["name"]), "old alias metadata cannot bypass canonical roots")
        clean(b.resource("File", params={"fields": ["name", "file_name", "file_url"], "filters": {"name": graph[key]["name"]}}), hidden, "old alias File list")
    denied(b.request("GET", graph["file"]["file_url"]), "old foreign-owner alias cannot expose private bytes")
    require(graph["file_marker"].encode() in success_bytes(a.request("GET", graph["file"]["file_url"]), "owner private bytes"), "owner attachment positive")
    gallery = {"dt": "CRM Lead", "dn": f["shared_parent"], "filters": [["File", "name", "in", [graph["alias"]["name"], graph["ordinary_file"]["name"]]]]}
    clean(b.rpc("frappe.desk.form.load.get_filtered_attachments", gallery), hidden, "dt/dn Attachment Gallery hides old URL alias metadata")
    require(graph["ordinary_file"]["file_name"].encode() in success_bytes(b.rpc("frappe.desk.form.load.get_filtered_attachments", gallery), "ordinary parent gallery"), "ordinary parent attachment remains visible")
    for method in ("frappe.desk.form.load.getdoc", "frappe.desk.form.load.get_docinfo", "frappe.desk.form.load.get_communications"):
        clean(b.rpc(method, {"doctype": "CRM Lead", "name": f["shared_parent"]}), hidden, "parent native response hides timeline-only multi-root Communication and alias")
    clean(b.rpc("crm.api.activities.get_activities", {"name": f["shared_parent"]}), hidden, "old alias Attachment Comment hidden from parsed activities")
    for method in ("frappe.desk.form.load.getdoc", "frappe.desk.form.load.get_docinfo"):
        body = success_bytes(b.rpc(method, {"doctype": "CRM Lead", "name": f["shared_parent"]}), "ordinary attachment log parent positive")
        require(all(name.encode() in body for name in graph["attachment_logs"]["ordinary"]), "ordinary native Attachment Comment remains visible")
    for dt, name in (("FCRM Note", graph["note"]), ("CRM Task", graph["task"]), ("Communication", graph["communication"]["name"]), ("File", graph["file"]["name"]), ("CRM Lead", f["shared_parent"])):
        denied(a.resource(dt, name, "DELETE"), "experimental retention prevents deletion before unlink or disk side effects")
        success(a.resource(dt, name), "denied deletion retains synthetic record")
    clean(b.rpc("crm.api.activities.get_activities", {"name": f["shared_parent"]}), hidden, "denied root deletion keeps Communication, alias and logs private")
    denied(b.request("GET", graph["file"]["file_url"]), "denied root deletion does not expose bytes")
    success(update(a, "FCRM Note", graph["note"], {"custom_team_collaborator": b.user}), "grant only first attachment root")
    denied(b.request("GET", graph["file"]["file_url"]), "one of two activity roots cannot grant bytes")
    success(update(a, "CRM Task", graph["task"], {"assigned_to": b.user}), "grant second attachment root")
    require(graph["file_marker"].encode() in success_bytes(b.request("GET", graph["file"]["file_url"]), "all roots grant private bytes"), "all-root collaborator attachment positive")
    success(update(a, "CRM Task", graph["task"], {"assigned_to": ""}), "revoke second attachment root")
    denied(b.request("GET", graph["file"]["file_url"]), "same-session multi-root revocation")
    success(update(a, "FCRM Note", graph["note"], {"custom_team_collaborator": ""}), "restore attachment root privacy")
    for key, dt in (("note", "FCRM Note"), ("task", "CRM Task")):
        todo = graph["todos"][key]
        denied(b.resource("ToDo", todo["name"]), "legacy allocated_to cannot read private historical assignment")
        clean(b.resource("ToDo", params={"fields": ["name", "description"], "filters": {"name": todo["name"]}}), [todo["name"], todo["marker"]], "legacy ToDo list")
        require(todo["marker"].encode() in success_bytes(a.resource("ToDo", todo["name"]), "current writer ToDo positive"), "owner sees historical assignment")
    print("PASS old foreign-owner same-URL alias metadata/bytes/gallery; timeline-only multi-root intersection and revoke; legacy ToDo detail/list negatives and owner positives")


def communication(session, doctype, name, content):
    return session.rpc("frappe.core.doctype.communication.email.make", {"doctype": doctype, "name": name, "content": content, "subject": content, "communication_type": "Communication", "communication_medium": "Other", "send_email": 0}, True)


def verify_pin_history(a, b, f):
    note = success(a.resource("FCRM Note", f["note"]), "pin fixture owner")
    require(note["owner"] == a.user and note["title"].startswith(f["prefix"]) and not note.get("custom_team_collaborator"), "pin tests refuse non-M8 or already-granted notes")
    for pinned in (True, False):
        success(a.rpc("crm.fcrm.doctype.fcrm_note.fcrm_note.set_pinned", {"name": f["note"], "pinned": pinned}, True), "native pin/unpin creates history")
    def pin_rows(response):
        data = success(response, "note activity response")[0]
        def members(rows):
            for row in rows:
                yield row
                yield from members(row.get("other_notes", []))
        return [row for row in members(data) if row.get("activity_type") == "note" and row.get("data", {}).get("note") == f["note"] and row.get("data", {}).get("action") in ("pinned", "unpinned")]
    rows = pin_rows(a.rpc("crm.api.activities.get_activities", {"name": f["shared_parent"]}))
    require({row["data"]["action"] for row in rows} == {"pinned", "unpinned"}, "owner sees both native pin Version projections")
    identifiers = [row["name"] for row in rows]
    success(update(a, "FCRM Note", f["note"], {"custom_team_visibility": "Shared"}), "publish current-only pin fixture")
    try:
        response = b.rpc("crm.api.activities.get_activities", {"name": f["shared_parent"]})
        clean(response, identifiers, "Shared-only aggregate hides pin/unpin Version identifiers")
        require(not pin_rows(response), "Shared-only grouped pin history is absent")
        success(update(a, "FCRM Note", f["note"], {"custom_team_collaborator": b.user}), "explicit pin-history writer grant")
        require({row["name"] for row in pin_rows(b.rpc("crm.api.activities.get_activities", {"name": f["shared_parent"]}))} >= set(identifiers), "current writer sees historical pin projections")
        success(update(a, "FCRM Note", f["note"], {"custom_team_collaborator": ""}), "revoke pin-history grant")
        clean(b.rpc("crm.api.activities.get_activities", {"name": f["shared_parent"]}), identifiers, "pin history grant revocation is immediate")
    finally:
        success(update(a, "FCRM Note", f["note"], {"custom_team_collaborator": "", "custom_team_visibility": "Private"}), "restore pin fixture privacy")
    print("PASS real native pin/unpin Version aggregate owner/writer positives and Shared-only/revoked negatives including grouped notes")


def verify_history(a, b, f):
    require(set(f.get("history", {})) == {"note", "task"} and set(f.get("history_communications", {})) == {"note", "task"}, "history-prepare is required for both activity types and linked Communications")
    for key, dt in (("note", "FCRM Note"), ("task", "CRM Task")):
        history = f["history"][key]
        require(set(history) == set(HISTORY_TYPES), "all four independent history buckets required")
        linked = f["history_communications"][key]
        require(linked["marker"] == f["prefix"] + "-HISTORY-COMM-" + key, "independent linked Communication marker")
        forbidden = [linked["name"], linked["marker"]]
        for bucket in HISTORY_TYPES:
            fixture = history[bucket]
            require(fixture["marker"] == f["prefix"] + "-HISTORY-" + key + "-" + bucket, "independent M8 history marker")
            forbidden.extend((fixture["name"], fixture["marker"]))
        for method in ("frappe.desk.form.load.getdoc", "frappe.desk.form.load.get_docinfo"):
            response = a.rpc(method, {"doctype": dt, "name": f[key]})
            require(response.status == 200, "owner native history response")
            info = response.json().get("docinfo", {})
            for bucket in HISTORY_TYPES:
                require(any(row.get("name") == history[bucket]["name"] and history[bucket]["marker"] in row.get("content", "") for row in info.get(bucket, [])), "owner sees each native history bucket")
        require(linked["marker"].encode() in success_bytes(a.rpc("crm.api.activities.get_activities", {"name": f["shared_parent"]}), "owner linked Communication aggregate"), "owner sees linked private Communication")
        clean(b.rpc("crm.api.activities.get_activities", {"name": f["shared_parent"]}), forbidden, "private Communication cannot leak through parent timeline link")
        todo = f["legacy_graph"]["todos"][key]
        forbidden.extend((todo["name"], todo["marker"]))
        for method in ("frappe.desk.form.load.getdoc", "frappe.desk.form.load.get_docinfo", "frappe.desk.form.load.get_communications"):
            args = {"doctype": "CRM Lead", "name": f["shared_parent"]}
            clean(b.rpc(method, args), forbidden, "Private history hidden from native parent docinfo and communications")
            require(linked["marker"].encode() in success_bytes(a.rpc(method, args), "owner parent linked history"), "parent native owner history positive")
        current = f["prefix"] + "-SHARED-CURRENT-" + key
        body_field = "content" if dt == "FCRM Note" else "description"
        success(update(a, dt, f[key], {body_field: current, "custom_team_visibility": "Shared"}), "publish synthetic current text for history checks")
        require(current.encode() in success_bytes(b.resource(dt, f[key]), "shared current text"), "shared current text remains visible")
        for method in ("frappe.desk.form.load.getdoc", "frappe.desk.form.load.get_docinfo"):
            clean(b.rpc(method, {"doctype": dt, "name": f[key]}), forbidden, "Shared reader sees no historical Comment bucket or Communication")
        for method in ("frappe.desk.form.load.getdoc", "frappe.desk.form.load.get_docinfo", "frappe.desk.form.load.get_communications"):
            clean(b.rpc(method, {"doctype": "CRM Lead", "name": f["shared_parent"]}), forbidden, "Shared history stays private through native parent responses")
        denied(b.resource("ToDo", todo["name"]), "Shared-only legacy allocated_to cannot read historical description")
        clean(b.rpc("crm.api.doc.get_assigned_users", {"doctype": dt, "name": f[key]}), [b.user], "Shared-only assignment users hidden")
        for user_session in (a, b):
            denied(user_session.rpc("frappe.realtime.can_subscribe_doc", {"doctype": dt, "docname": f[key]}), "private activity socket subscription disabled even for owner")
        success(b.rpc("frappe.realtime.can_subscribe_doc", {"doctype": "CRM Lead", "docname": f["shared_parent"]}), "ordinary parent subscription remains allowed")
        denied(b.rpc("frappe.client.get_value", {"doctype": dt, "filters": f[key], "fieldname": "_comments"}), "raw historical comment cache cannot be selected")
        clean(b.rpc("crm.api.activities.get_activities", {"name": f["shared_parent"]}), forbidden, "Shared current text does not publish linked private Communication")
        formal_marker = f["prefix"] + "-FORMAL-COMM-" + key
        success(communication(a, "CRM Lead", f["shared_parent"], formal_marker), "ordinary formal Communication allowed")
        require(formal_marker.encode() in success_bytes(b.rpc("crm.api.activities.get_activities", {"name": f["shared_parent"]}), "formal Communication aggregate"), "ordinary formal Communication remains visible")
        rejected = f["prefix"] + "-REJECTED-" + key
        denied(b.rpc("crm.api.comment.add_comment", {"reference_doctype": dt, "reference_name": f[key], "content": rejected}, True), "Shared reader cannot add CRM comment")
        denied(communication(b, dt, f[key], rejected), "Shared reader cannot create Communication through native make")
        denied(b.resource("Communication", method="POST", payload={"communication_type": "Communication", "communication_medium": "Other", "subject": rejected, "content": rejected, "reference_doctype": dt, "reference_name": f[key]}), "Shared reader cannot REST-create Communication")
        denied(b.resource("Communication", method="POST", payload={"communication_type": "Communication", "communication_medium": "Other", "subject": rejected, "content": rejected, "reference_doctype": "CRM Lead", "reference_name": f["b_parent"], "timeline_links": [{"link_doctype": dt, "link_name": f[key]}]}), "readable parent cannot bypass private activity timeline write")
        owner_comment = success(a.rpc("crm.api.comment.add_comment", {"reference_doctype": dt, "reference_name": f[key], "content": f["prefix"] + "-OWNER-COMMENT-" + key}, True), "owner may add activity comment")
        success(a.rpc("frappe.desk.form.utils.update_comment", {"name": owner_comment["name"], "content": f["prefix"] + "-OWNER-EDIT-" + key}, True), "owner may edit own activity comment")
        success(communication(a, dt, f[key], f["prefix"] + "-OWNER-COMM-" + key), "owner may create activity Communication")
        success(update(a, dt, f[key], {"custom_team_collaborator": b.user}), "grant explicit history collaborator")
        visible = b.rpc("frappe.desk.form.load.get_docinfo", {"doctype": dt, "name": f[key]})
        require(visible.status == 200 and all(history[bucket]["marker"].encode() in visible.body for bucket in HISTORY_TYPES), "collaborator reads historical buckets")
        own = success(b.rpc("crm.api.comment.add_comment", {"reference_doctype": dt, "reference_name": f[key], "content": f["prefix"] + "-COLLAB-COMMENT-" + key}, True), "collaborator may add activity comment")
        success(b.rpc("frappe.desk.form.utils.update_comment", {"name": own["name"], "content": f["prefix"] + "-COLLAB-EDIT-" + key}, True), "collaborator may edit own activity comment")
        success(communication(b, dt, f[key], f["prefix"] + "-COLLAB-COMM-" + key), "collaborator may create activity Communication")
        denied(b.rpc("frappe.desk.form.utils.update_comment", {"name": owner_comment["name"], "content": rejected}, True), "collaborator cannot edit another comment owner")
        denied(update(b, "Comment", own["name"], {"reference_doctype": "CRM Lead", "reference_name": f["b_parent"]}), "collaborator cannot move comment to a readable parent")
        success(update(a, dt, f[key], {"custom_team_collaborator": ""}), "revoke history collaborator")
        denied(b.rpc("frappe.desk.form.utils.update_comment", {"name": own["name"], "content": rejected}, True), "revoked owner cannot edit own comment on Shared activity")
        denied(update(b, "Comment", own["name"], {"reference_doctype": "CRM Lead", "reference_name": f["b_parent"], "content": rejected}), "old activity write gate survives reparent attempt")
        formal = success(b.rpc("crm.api.comment.add_comment", {"reference_doctype": "CRM Lead", "reference_name": f["b_parent"], "content": f["prefix"] + "-OWN-FORMAL-" + key}, True), "own parent formal comment allowed")
        denied(update(b, "Comment", formal["name"], {"reference_doctype": dt, "reference_name": f[key], "content": rejected}), "new activity write gate survives reparent attempt")
        clean(a.rpc("frappe.desk.form.load.get_docinfo", {"doctype": dt, "name": f[key]}), [rejected], "rejected mutations were not committed")
        success(update(a, dt, f[key], {"custom_team_visibility": "Private"}), "restore history fixture privacy")
    print("PASS owner/collaborator history positives; four Comment buckets hidden from Shared readers; Comment/Communication creation, edits, and old/new reference denials")


def verify(a, b, f):
    require(f["user_a"] == a.user and f["user_b"] == b.user and f["prefix"].startswith("M8-"), "fixture identities")
    for key, session, dt in (("note", a, "FCRM Note"), ("private_note", a, "FCRM Note"), ("task", a, "CRM Task"), ("b_note", b, "FCRM Note"), ("b_task", b, "CRM Task")):
        record = success(session.resource(dt, f[key]), "fixture owner read")
        require(record["owner"] == session.user and record["title"].startswith(f["prefix"]), "refuse mutation of non-M8 records")
    hidden = [f["note"], f["note_marker"], f["task"], f["task_marker"]]
    for session, key, dt, marker in ((b, "note", "FCRM Note", "note_marker"), (b, "task", "CRM Task", "task_marker"), (a, "b_note", "FCRM Note", "b_note_marker"), (a, "b_task", "CRM Task", "b_task_marker")):
        denied(session.resource(dt, f[key]), "private direct detail")
        denied(update(session, dt, f[key], {"title": "M8 forbidden edit"}), "private REST write")
        for rpc in ("frappe.client.get_list", "frappe.desk.reportview.get", "frappe.desk.reportview.get_count"):
            clean(session.rpc(rpc, {"doctype": dt, "fields": ["name", "title"], "filters": {"name": f[key]}}), [f[key], f[marker]], rpc)
        clean(session.resource(dt, params={"fields": ["name", "title"], "filters": {"name": f[key]}}), [f[key], f[marker]], "REST list")
        denied(session.rpc("frappe.desk.form.load.getdoc", {"doctype": dt, "name": f[key]}), "native detail")
        denied(session.resource(dt, f["prefix"] + "-nonexistent"), "missing identifier indistinguishable")
        for selected in (False, True):
            args = {"doctype": dt, "fields": ["name", "title", "content" if dt == "FCRM Note" else "description"], "file_format_type": "CSV", "export_in_background": 0}
            if selected:
                args["selected_items"] = [f[key]]
            clean(session.rpc("frappe.desk.reportview.export_query", args), [f[key], f[marker]], "CSV selected/plain")
    clean(b.rpc("crm.api.activities.get_activities", {"name": f["shared_parent"]}), hidden, "activities private children")
    clean(b.rpc("crm.api.doc.get_linked_docs_of_document", {"doctype": "CRM Lead", "docname": f["shared_parent"]}), hidden, "associated candidates")
    denied(b.rpc("crm.api.activities.get_activities", {"name": f["private_parent"]}), "private parent activities")
    clean(b.rpc("frappe.desk.search.search_link", {"doctype": "FCRM Note", "txt": f["prefix"]}), hidden, "link candidates")
    print("PASS private REST/native/list/count/search/CSV/activities in two real sessions")
    verify_legacy(a, b, f)
    verify_pin_history(a, b, f)
    verify_history(a, b, f)

    public = f["prefix"] + "-PUBLIC-CURRENT"
    success(update(a, "FCRM Note", f["note"], {"content": public, "custom_team_visibility": "Shared"}), "publish current text")
    require(public.encode() in success_bytes(b.resource("FCRM Note", f["note"]), "shared read"), "shared text visible")
    denied(update(b, "FCRM Note", f["note"], {"content": "forbidden"}), "read share is not write")
    for method in ("frappe.desk.form.load.getdoc", "frappe.desk.form.load.get_docinfo"):
        clean(b.rpc(method, {"doctype": "FCRM Note", "name": f["note"]}), [f["note_marker"]], "shared current-only history")
    clean(b.resource("Version", params={"fields": ["name", "data"], "filters": {"ref_doctype": "FCRM Note", "docname": f["note"]}}), [f["note_marker"]], "Version direct list")
    success(update(a, "FCRM Note", f["note"], {"custom_team_visibility": "Private", "custom_team_collaborator": b.user}), "explicit collaborator")
    success(update(b, "FCRM Note", f["note"], {"content": public + "-collaborated"}), "collaborator content write")
    denied(update(b, "FCRM Note", f["note"], {"custom_team_visibility": "Shared"}), "collaborator cannot republish")
    denied(b.rpc("frappe.client.set_value", {"doctype": "FCRM Note", "name": f["note"], "fieldname": "owner", "value": b.user}, True), "collaborator cannot take ownership")
    success(update(a, "FCRM Note", f["note"], {"custom_team_collaborator": ""}), "revoke collaborator")
    denied(b.resource("FCRM Note", f["note"]), "same-session collaborator revocation")
    success(update(a, "CRM Task", f["task"], {"assigned_to": b.user}), "explicit task assignment")
    success(update(b, "CRM Task", f["task"], {"status": "Done"}), "assignee collaboration")
    denied(update(b, "CRM Task", f["task"], {"assigned_to": a.user}), "assignee cannot reassign")
    success(update(a, "CRM Task", f["task"], {"assigned_to": ""}), "revoke assignee")
    denied(b.resource("CRM Task", f["task"]), "same-session task revocation")
    success(update(a, "FCRM Note", f["note"], {"custom_team_visibility": "Shared"}), "re-publish text")
    success(share(a, "CRM Lead", f["shared_parent"], b.user, False), "withdraw parent read")
    denied(b.resource("FCRM Note", f["note"]), "parent withdrawal gates shared child")
    success(share(a, "CRM Lead", f["shared_parent"], b.user), "restore fixture parent read")
    success(update(a, "FCRM Note", f["note"], {"custom_team_visibility": "Private"}), "restore fixture privacy")
    denied(share(a, "FCRM Note", f["note"], b.user), "new child DocShare is not a bypass")
    print("PASS explicit sharing/current-only history/collaboration/revocation/parent gating")

    formal_marker = f["prefix"] + "-FORMAL-COMMENT"
    success(a.rpc("crm.api.comment.add_comment", {"reference_doctype": "CRM Lead", "reference_name": f["shared_parent"], "content": formal_marker}, True), "formal comment")
    require(formal_marker.encode() in success_bytes(b.rpc("crm.api.activities.get_activities", {"name": f["shared_parent"]}), "formal parent activity read"), "formal comment remains visible through native aggregate authorization")
    formal = success(b.rpc("crm.api.comment.add_comment", {"reference_doctype": "CRM Lead", "reference_name": f["shared_parent"], "content": formal_marker + "-READER"}, True), "parent reader may add formal comment")
    success(b.rpc("frappe.desk.form.utils.update_comment", {"name": formal["name"], "content": formal_marker + "-READER-EDIT"}, True), "parent reader may edit own formal comment")
    denied(b.rpc("crm.api.comment.add_comment", {"reference_doctype": "CRM Lead", "reference_name": f["private_parent"], "content": "forbidden"}, True), "private parent comment denied")
    mention = f'<span data-type="mention" data-id="{b.user}" data-label="Synthetic">test</span>'
    denied(update(a, "FCRM Note", f["note"], {"content": mention}), "unauthorized mention denied before notification")
    clean(b.rpc("crm.api.notifications.get_notifications"), [f["note"], f["note_marker"]], "notification side channel")
    file = create(a, "File", {"file_name": f["prefix"] + ".txt", "content": base64.b64encode(f["note_marker"].encode()).decode(), "decode": 1, "is_private": 1, "attached_to_doctype": "FCRM Note", "attached_to_name": f["note"]})
    denied(b.request("GET", file["file_url"]), "private file download")
    for session in (a, b):
        denied(session.resource("File", method="POST", payload={"file_name": f["prefix"] + "-alias.txt", "file_url": file["file_url"], "is_private": 1}), "private URL cannot become unattached alias")
    denied(a.resource("File", method="POST", payload={"file_name": f["prefix"] + "-remote.txt", "file_url": "https://example.invalid/private.txt", "is_private": 1, "attached_to_doctype": "FCRM Note", "attached_to_name": f["note"]}), "remote activity attachment blocked")
    unbound = create(a, "File", {"file_name": f["prefix"] + "-public-safe.txt", "content": "M8 public nonsensitive test bytes", "is_private": 0})
    denied(update(a, "File", unbound["name"], {"attached_to_doctype": "FCRM Note", "attached_to_name": f["note"], "is_private": 1}), "public-first attachment later binding blocked")
    denied(update(a, "File", file["name"], {"is_private": 0}), "public file conversion blocked")
    denied(update(a, "File", file["name"], {"attached_to_doctype": "", "attached_to_name": ""}), "private file detach blocked")
    require(update(a, "FCRM Note", f["note"], {"custom_team_visibility": "Shared"}).status in (403, 417), "attached activity cannot publish")
    denied(a.resource("File", method="POST", payload={"file_name": f["prefix"] + "-public.txt", "content": "forbidden-public-bytes", "is_private": 0, "attached_to_doctype": "FCRM Note", "attached_to_name": f["note"]}), "public insert blocked before bytes")
    print("PASS comments/mentions/notifications/private attachment download and mutation checks")
    require(f.get("legacy_shares"), "legacy DocShare OR negative was not prepared; do not label full boundary acceptance")
    print("PASS legacy DocShare OR rows did not bypass any tested boundary")
    print("MANUAL REQUIRED: native CRM editors/sharing/CSP/PWA, Call/integration, converted Lead/Deal and automatic Email links, Version details/exports, unknown/removed attachment logs and nested history copies, upload variants, native delete_doc/controller selection and no disk/queue side effects (including Administrator application denial, standalone/Shared Note/Task and all Lead/Deal), real socket B subscribed to shared parent AND Lead/Deal list before full private Communication on_update with no actor/timing events while ordinary formal events and persistence survive, Deleted Document detail/list/export/single+bulk restore, and restart/backup restore with explicit synthetic-only provenance acknowledgement. Private and parent deletion is unavailable, not complete CRUD or team MVP acceptance.")


def success_bytes(response, label):
    require(response.status == 200, label)
    return response.body


def main():
    parser = argparse.ArgumentParser(description="Two real Sales Users verify access; preparation uses an existing authorized maintenance account for synthetic history only. No Administrator login or ORM.")
    parser.add_argument("mode", choices=("prepare", "history-prepare", "legacy-prepare", "verify"))
    parser.add_argument("--base-url", default="http://127.0.0.1:8088")
    parser.add_argument("--site", default="crm.localhost")
    parser.add_argument("--user-a", required=True)
    parser.add_argument("--user-b", required=True)
    parser.add_argument("--history-user", help="existing non-Administrator System Manager; history-prepare/legacy-prepare only")
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--legacy-shares", action="store_true", help="prepare before extension installation to exercise pre-existing DocShare OR rows")
    args = parser.parse_args()
    require(args.user_a != args.user_b and "Administrator" not in (args.user_a, args.user_b), "two different Sales Users required")
    preparing_history = args.mode in ("history-prepare", "legacy-prepare")
    if preparing_history:
        require(bool(args.history_user) and args.history_user not in ("Administrator", args.user_a, args.user_b), "separate existing maintenance account required")
    parsed = urllib.parse.urlsplit(args.base_url)
    require(parsed.scheme in ("http", "https") and not parsed.username and not parsed.password, "no credentials in URL")
    passwords = [os.environ.get("TEAM_ACCESS_PASSWORD_A") or getpass.getpass("Sales User A password: "), os.environ.get("TEAM_ACCESS_PASSWORD_B") or getpass.getpass("Sales User B password: ")]
    a, b = [Session(args.base_url, args.site, user, password) for user, password in zip((args.user_a, args.user_b), passwords)]
    passwords.clear()
    if args.mode == "prepare":
        require(not args.fixture.exists(), "refuse to overwrite fixture manifest")
        fixture = prepare(a, b, args.legacy_shares)
        args.fixture.parent.mkdir(parents=True, exist_ok=True)
        with args.fixture.open("x", encoding="utf-8") as stream:
            json.dump(fixture, stream)
        print("PASS new M8 fixtures prepared; manifest contains IDs/markers only, never credentials or cookies")
    else:
        fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
        require(fixture["user_a"] == a.user and fixture["user_b"] == b.user, "fixture session identities")
        if preparing_history:
            password = os.environ.get("TEAM_ACCESS_PASSWORD_HISTORY") or getpass.getpass("Existing history maintenance account password: ")
            maintenance = Session(args.base_url, args.site, args.history_user, password, purpose="history")
            del password
            if args.mode == "history-prepare":
                prepare_history(a, maintenance, fixture)
            else:
                prepare_legacy(a, b, maintenance, fixture)
            with args.fixture.open("w", encoding="utf-8") as stream:
                json.dump(fixture, stream)
            print("PASS synthetic history preparation through authorized HTTP; no roles or accounts changed")
        else:
            verify(a, b, fixture)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("FAIL " + (str(error) if isinstance(error, RuntimeError) else type(error).__name__), file=sys.stderr)
        sys.exit(1)

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
    def __init__(self, base, site, user, password):
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
        require("Sales User" in roles and not roles.intersection({"System Manager", "Sales Manager"}), "Sales User without manager roles")

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

    comment = success(a.rpc("crm.api.comment.add_comment", {"reference_doctype": "CRM Lead", "reference_name": f["shared_parent"], "content": f["prefix"] + "-FORMAL-COMMENT"}, True), "formal comment")
    success(b.resource("Comment", comment["name"]), "shared formal comment readable")
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
    print("MANUAL REQUIRED: native CRM editors, sharing UI, CSP, PWA cache, Call Log/integration routes, direct Version detail and exports, upload variants, and restart cache invalidation; this script is not complete UI acceptance.")


def success_bytes(response, label):
    require(response.status == 200, label)
    return response.body


def main():
    parser = argparse.ArgumentParser(description="Two real Sales User sessions; only new M8 synthetic records are mutated. No Administrator login or ORM.")
    parser.add_argument("mode", choices=("prepare", "verify"))
    parser.add_argument("--base-url", default="http://127.0.0.1:8088")
    parser.add_argument("--site", default="crm.localhost")
    parser.add_argument("--user-a", required=True)
    parser.add_argument("--user-b", required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--legacy-shares", action="store_true", help="prepare before extension installation to exercise pre-existing DocShare OR rows")
    args = parser.parse_args()
    require(args.user_a != args.user_b and "Administrator" not in (args.user_a, args.user_b), "two different Sales Users required")
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
        verify(a, b, json.loads(args.fixture.read_text(encoding="utf-8")))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("FAIL " + (str(error) if isinstance(error, RuntimeError) else type(error).__name__), file=sys.stderr)
        sys.exit(1)

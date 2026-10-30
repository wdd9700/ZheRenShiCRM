#!/usr/bin/env python3
"""Configure and validate the isolated M6 synthetic team-access fixtures."""

import argparse
import http.cookiejar
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

DISTRO = "Ubuntu-24.04"
CONTAINER = "crm-mvp-v15-backend-1"
SITE = "crm.localhost"
BASE_URL = "http://127.0.0.1:8088"
USER_A = "m6-a@example.invalid"
USER_B = "m6-b@example.invalid"
PRIVATE_LEAD = "M6-PRIVATE-RESOURCE-A"
SHARED_LEAD = "M6-SHARED-RESOURCE"
PRIVATE_NOTE = "M6-PRIVATE-NOTE-A"
PRIVATE_ON_SHARED_NOTE = "M6-PRIVATE-ON-SHARED-NOTE-A"
SHARED_NOTE = "M6-SHARED-NOTE"
PRIVATE_NOTE_SENTINEL = "M6_PRIVATE_NOTE_SENTINEL"
PRIVATE_ON_SHARED_SENTINEL = "M6_PRIVATE_ON_SHARED_SENTINEL"
SHARED_NOTE_SENTINEL = "M6_SHARED_NOTE_SENTINEL"
PRIVATE_LEAD_MEMO_SENTINEL = "M6_PRIVATE_LEAD_MEMO_SENTINEL"
COLLABORATION_SENTINEL = "M6_B_COLLABORATION"


def container_configure(mode):
    import frappe

    frappe.init(site=SITE, sites_path=".")
    frappe.connect()
    try:
        frappe.set_user("Administrator")
        passwords = {USER_A: secrets.token_urlsafe(32), USER_B: secrets.token_urlsafe(32)}
        for index, (email, password) in enumerate(passwords.items(), start=1):
            if frappe.db.exists("User", email):
                user = frappe.get_doc("User", email)
            else:
                user = frappe.get_doc({"doctype": "User", "email": email})
            user.update(
                {
                    "enabled": 1,
                    "first_name": f"M6 User {index}",
                    "last_name": "Synthetic",
                    "user_type": "System User",
                    "send_welcome_email": 0,
                    "new_password": password,
                }
            )
            user.flags.no_welcome_mail = True
            existing_roles = {role.role for role in user.roles}
            if existing_roles - {"Sales User"}:
                raise RuntimeError(f"M6 user {email} has an unexpected role")
            if "Sales User" not in existing_roles:
                user.append("roles", {"role": "Sales User"})
            user.save(ignore_permissions=True)

        statuses = frappe.get_all("CRM Lead Status", pluck="name", order_by="creation asc", limit=1)
        if not statuses:
            raise RuntimeError("No CRM Lead Status is available")

        def save_with_owner(doc, values, owner):
            doc.update(values)
            doc.save(ignore_permissions=True)
            if doc.owner != owner:
                frappe.db.set_value(doc.doctype, doc.name, "owner", owner, update_modified=False)
                doc.reload()
            return doc.name

        def ensure_lead(title, owner, last_name, memo):
            names = frappe.get_all(
                "CRM Lead",
                filters={"first_name": title},
                pluck="name",
                order_by="creation asc",
                limit=1,
            )
            doc = frappe.get_doc("CRM Lead", names[0]) if names else frappe.get_doc({"doctype": "CRM Lead"})
            values = {
                "first_name": title,
                "last_name": last_name,
                "status": doc.get("status") or statuses[0],
                "organization": title,
                "company_description": memo,
            }
            if doc.is_new():
                values["lead_owner"] = owner
            name = save_with_owner(doc, values, owner)
            if doc.lead_owner != owner:
                frappe.db.set_value("CRM Lead", name, "lead_owner", owner, update_modified=False)
                doc.reload()
            return name

        def ensure_note(title, owner, lead_name, sentinel):
            names = frappe.get_all(
                "FCRM Note",
                filters={
                    "title": title,
                    "reference_doctype": "CRM Lead",
                    "reference_docname": lead_name,
                },
                pluck="name",
                order_by="creation asc",
                limit=1,
            )
            doc = frappe.get_doc("FCRM Note", names[0]) if names else frappe.get_doc({"doctype": "FCRM Note"})
            return save_with_owner(
                doc,
                {
                    "title": title,
                    "content": f"<p>{sentinel}</p>",
                    "reference_doctype": "CRM Lead",
                    "reference_docname": lead_name,
                },
                owner,
            )

        private_lead = ensure_lead(
            PRIVATE_LEAD, USER_A, "M6-A-OWNER", PRIVATE_LEAD_MEMO_SENTINEL
        )
        shared_lead = ensure_lead(
            SHARED_LEAD, USER_A, "M6-A-OWNER", "M6_FORMAL_SHARED_DESCRIPTION"
        )
        private_note = ensure_note(PRIVATE_NOTE, USER_A, private_lead, PRIVATE_NOTE_SENTINEL)
        private_on_shared = ensure_note(
            PRIVATE_ON_SHARED_NOTE, USER_A, shared_lead, PRIVATE_ON_SHARED_SENTINEL
        )
        shared_note = ensure_note(SHARED_NOTE, USER_A, shared_lead, SHARED_NOTE_SENTINEL)

        def ensure_user_permission(user, note_name, active):
            filters = {"user": user, "allow": "FCRM Note", "for_value": note_name}
            names = frappe.get_all("User Permission", filters=filters, pluck="name", limit=1)
            if names:
                doc = frappe.get_doc("User Permission", names[0])
            else:
                doc = frappe.get_doc({"doctype": "User Permission", **filters})
            doc.update(
                {
                    "applicable_for": "FCRM Note" if active else "CRM Deal",
                    "apply_to_all_doctypes": 0,
                    "is_default": 0,
                    "hide_descendants": 0,
                }
            )
            doc.save(ignore_permissions=True)

        guarded = mode == "guarded"
        for note_name in (private_note, private_on_shared, shared_note):
            ensure_user_permission(USER_A, note_name, guarded)
        ensure_user_permission(USER_B, shared_note, guarded)

        def ensure_share(doctype, name, user, active):
            filters = {"share_doctype": doctype, "share_name": name, "user": user}
            names = frappe.get_all("DocShare", filters=filters, pluck="name", limit=1)
            if names:
                doc = frappe.get_doc("DocShare", names[0])
            else:
                doc = frappe.get_doc({"doctype": "DocShare", **filters})
            doc.update(
                {
                    "read": int(active),
                    "write": int(active),
                    "share": 0,
                    "submit": 0,
                    "everyone": 0,
                }
            )
            doc.save(ignore_permissions=True)

        ensure_share("CRM Lead", shared_lead, USER_B, True)
        ensure_share("FCRM Note", shared_note, USER_B, guarded)

        def deactivate_existing(doctype, filters, values):
            for name in frappe.get_all(doctype, filters=filters, pluck="name"):
                doc = frappe.get_doc(doctype, name)
                doc.update(values)
                doc.save(ignore_permissions=True)

        stale_leads = frappe.get_all(
            "CRM Lead",
            filters={"first_name": SHARED_LEAD, "name": ["!=", shared_lead]},
            pluck="name",
        )
        for stale_lead in stale_leads:
            deactivate_existing(
                "ToDo",
                {
                    "reference_type": "CRM Lead",
                    "reference_name": stale_lead,
                    "allocated_to": USER_B,
                },
                {"status": "Cancelled"},
            )
            deactivate_existing(
                "DocShare",
                {"share_doctype": "CRM Lead", "share_name": stale_lead, "user": USER_B},
                {"read": 0, "write": 0, "share": 0, "submit": 0, "everyone": 0},
            )
            frappe.db.set_value(
                "CRM Lead", stale_lead, "lead_owner", USER_A, update_modified=False
            )

        stale_notes = frappe.get_all(
            "FCRM Note",
            filters={"title": SHARED_NOTE, "name": ["!=", shared_note]},
            pluck="name",
        )
        for stale_note in stale_notes:
            deactivate_existing(
                "User Permission",
                {"user": USER_B, "allow": "FCRM Note", "for_value": stale_note},
                {"applicable_for": "CRM Deal", "apply_to_all_doctypes": 0},
            )
            deactivate_existing(
                "DocShare",
                {"share_doctype": "FCRM Note", "share_name": stale_note, "user": USER_B},
                {"read": 0, "write": 0, "share": 0, "submit": 0, "everyone": 0},
            )

        todo_filters = {
            "description": "M6-SHARED-LEAD-ASSIGNMENT",
            "reference_type": "CRM Lead",
            "reference_name": shared_lead,
            "allocated_to": USER_B,
        }
        todo_names = frappe.get_all("ToDo", filters=todo_filters, pluck="name", limit=1)
        todo = (
            frappe.get_doc("ToDo", todo_names[0])
            if todo_names
            else frappe.get_doc({"doctype": "ToDo", **todo_filters})
        )
        todo.update({"status": "Open" if guarded else "Cancelled", "assigned_by": USER_A})
        todo.save(ignore_permissions=True)
        frappe.db.set_value(
            "CRM Lead", shared_lead, "lead_owner", USER_A, update_modified=False
        )
        for email in passwords:
            frappe.cache.hdel("user_permissions", email)
        frappe.db.commit()
        result = {
            "passwords": passwords,
            "private_lead": private_lead,
            "shared_lead": shared_lead,
            "private_note": private_note,
            "private_on_shared": private_on_shared,
            "shared_note": shared_note,
        }
        print("M6_CONFIG_JSON:" + json.dumps(result))
    finally:
        frappe.destroy()


class Response:
    def __init__(self, status, content_type, body):
        self.status = status
        self.content_type = content_type
        self.body = body

    def json(self):
        return json.loads(self.body.decode("utf-8"))

    def text(self):
        return self.body.decode("utf-8-sig", errors="replace")


class Session:
    def __init__(self, base_url, email, password):
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.csrf_token = None
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies)
        )
        response = self.request(
            "POST", "/api/method/login", form={"usr": email, "pwd": password}
        )
        assert response.status == 200, f"login status {response.status}"
        login_message = response.json().get("message")
        assert login_message == "Logged In", f"login message {login_message!r}"
        identity = self.request("GET", "/api/method/frappe.auth.get_logged_user")
        assert identity.status == 200, f"identity status {identity.status}"
        actual_identity = identity.json().get("message")
        assert actual_identity == email, f"expected {email}, got {actual_identity}"
        page = self.request("GET", "/crm")
        assert page.status == 200, f"CRM page status {page.status}"
        token = next((cookie.value for cookie in self.cookies if cookie.name == "csrf_token"), None)
        token_match = re.search(r'csrf_token["\'\]]*\s*[:=]\s*["\']([^"\']+)', page.text())
        self.csrf_token = token or (token_match.group(1) if token_match else None)
        assert self.csrf_token, "CRM session did not expose a CSRF token"

    def request(self, method, path, *, params=None, payload=None, form=None):
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = None
        headers = {"Accept": "application/json", "Host": SITE}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif form is not None:
            data = urllib.parse.urlencode(form).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if self.csrf_token and method not in ("GET", "HEAD", "OPTIONS"):
            headers["X-Frappe-CSRF-Token"] = self.csrf_token
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=30) as response:
                return Response(
                    response.status,
                    response.headers.get("Content-Type", ""),
                    response.read(),
                )
        except urllib.error.HTTPError as error:
            return Response(
                error.code, error.headers.get("Content-Type", ""), error.read()
            )

    def resource(self, doctype, name=None, *, fields=None, filters=None):
        path = "/api/resource/" + urllib.parse.quote(doctype, safe="")
        params = {}
        if name is not None:
            path += "/" + urllib.parse.quote(name, safe="")
        if fields is not None:
            params["fields"] = json.dumps(fields)
        if filters is not None:
            params["filters"] = json.dumps(filters)
        if name is None:
            params["limit_page_length"] = "1000"
        response = self.request("GET", path, params=params)
        return response

    def update(self, doctype, name, values):
        path = "/api/resource/" + urllib.parse.quote(doctype, safe="")
        path += "/" + urllib.parse.quote(name, safe="")
        return self.request("PUT", path, payload=values)

    def export_csv(self, doctype, fields, selected_items=None):
        form = {
            "doctype": doctype,
            "file_format_type": "CSV",
            "fields": json.dumps(fields),
            "filters": json.dumps({}),
            "order_by": "creation desc",
            "start": "0",
            "page_length": "1000",
            "view": "Report",
            "with_comment_count": "0",
            "export_in_background": "0",
        }
        if selected_items:
            form["selected_items"] = json.dumps(selected_items)
        return self.request(
            "POST", "/api/method/frappe.desk.reportview.export_query", form=form
        )


class Checks:
    def __init__(self):
        self.failures = []
        self.passes = []

    def run(self, name, function):
        try:
            function()
        except Exception as error:
            self.failures.append((name, str(error)))
            print(f"FAIL {name}: {error}")
        else:
            self.passes.append(name)
            print(f"PASS {name}")


def assert_denied(response):
    assert response.status in (403, 404), f"expected 403/404, got {response.status}"


def data_rows(response):
    assert response.status == 200, f"expected 200, got {response.status}"
    rows = response.json().get("data")
    assert isinstance(rows, list), "response data is not a list"
    return rows


def validate_http(config, base_url):
    checks = Checks()
    sessions = {}

    def login_a():
        sessions[USER_A] = Session(base_url, USER_A, config["passwords"][USER_A])

    def login_b():
        sessions[USER_B] = Session(base_url, USER_B, config["passwords"][USER_B])

    checks.run("A real session is the M6-A ordinary user", login_a)
    checks.run("B real session is the M6-B ordinary user", login_b)
    if len(sessions) != 2:
        return checks
    a = sessions[USER_A]
    b = sessions[USER_B]
    private_lead = config["private_lead"]
    shared_lead = config["shared_lead"]
    private_note = config["private_note"]
    private_on_shared = config["private_on_shared"]
    shared_note = config["shared_note"]

    def lead_lists():
        a_names = {row["name"] for row in data_rows(a.resource("CRM Lead", fields=["name"]))}
        b_rows = data_rows(b.resource("CRM Lead", fields=["name"]))
        b_names = {row["name"] for row in b_rows}
        assert {private_lead, shared_lead} <= a_names
        assert b_names == {shared_lead}, "B lead list is not limited to the shared M6 lead"

    def note_lists():
        a_names = {row["name"] for row in data_rows(a.resource("FCRM Note", fields=["name"]))}
        b_rows = data_rows(b.resource("FCRM Note", fields=["name", "title", "content"]))
        b_names = {row["name"] for row in b_rows}
        assert {private_note, private_on_shared, shared_note} <= a_names
        assert b_names == {shared_note}, "B note list exceeds the shared M6 note"
        serialized = json.dumps(b_rows)
        assert PRIVATE_NOTE_SENTINEL not in serialized
        assert PRIVATE_ON_SHARED_SENTINEL not in serialized

    def lead_details():
        assert a.resource("CRM Lead", private_lead).status == 200
        assert_denied(b.resource("CRM Lead", private_lead))
        assert b.resource("CRM Lead", shared_lead).status == 200

    def note_details():
        assert a.resource("FCRM Note", private_note).status == 200
        assert_denied(b.resource("FCRM Note", private_note))
        assert_denied(b.resource("FCRM Note", private_on_shared))
        assert b.resource("FCRM Note", shared_note).status == 200

    def related_notes():
        response = b.resource(
            "FCRM Note",
            fields=["name", "title", "content"],
            filters=[["FCRM Note", "reference_docname", "=", shared_lead]],
        )
        rows = data_rows(response)
        assert {row["name"] for row in rows} == {shared_note}
        assert PRIVATE_ON_SHARED_SENTINEL not in json.dumps(rows)

    def private_lead_write():
        response = b.update(
            "CRM Lead",
            private_lead,
            {"last_name": "M6-B-UNAUTHORIZED", "company_description": "M6-B-UNAUTHORIZED"},
        )
        assert_denied(response)
        owner_view = a.resource("CRM Lead", private_lead).json()["data"]
        assert owner_view["last_name"] == "M6-A-OWNER"
        assert owner_view["company_description"] == PRIVATE_LEAD_MEMO_SENTINEL

    def private_note_write():
        for name in (private_note, private_on_shared):
            response = b.update("FCRM Note", name, {"content": "<p>M6-B-UNAUTHORIZED</p>"})
            assert_denied(response)
        assert PRIVATE_NOTE_SENTINEL in a.resource("FCRM Note", private_note).text()
        assert PRIVATE_ON_SHARED_SENTINEL in a.resource("FCRM Note", private_on_shared).text()

    def shared_lead_write():
        response = b.update("CRM Lead", shared_lead, {"last_name": COLLABORATION_SENTINEL})
        assert response.status == 200, f"shared lead write status {response.status}"
        assert COLLABORATION_SENTINEL in a.resource("CRM Lead", shared_lead).text()

    def shared_note_write():
        response = b.update(
            "FCRM Note",
            shared_note,
            {"content": f"<p>{SHARED_NOTE_SENTINEL} {COLLABORATION_SENTINEL}</p>"},
        )
        assert response.status == 200, f"shared note write status {response.status}"
        owner_text = a.resource("FCRM Note", shared_note).text()
        assert SHARED_NOTE_SENTINEL in owner_text and COLLABORATION_SENTINEL in owner_text

    def private_timeline():
        response = b.request(
            "GET",
            "/api/method/crm.api.activities.get_activities",
            params={"name": private_lead},
        )
        assert_denied(response)

    def shared_timeline():
        response = b.request(
            "GET",
            "/api/method/crm.api.activities.get_activities",
            params={"name": shared_lead},
        )
        assert response.status == 200, f"shared timeline status {response.status}"
        text = response.text()
        assert SHARED_NOTE_SENTINEL in text
        assert PRIVATE_ON_SHARED_SENTINEL not in text, (
            "shared Lead timeline exposes a non-shared FCRM Note"
        )

    def lead_export():
        fields = ["name", "first_name", "lead_owner", "company_description"]
        response = b.export_csv("CRM Lead", fields)
        assert response.status == 200, f"lead export status {response.status}"
        text = response.text().replace("\\_", "_")
        assert shared_lead in text and SHARED_LEAD in text
        assert private_lead not in text and PRIVATE_LEAD not in text
        assert PRIVATE_LEAD_MEMO_SENTINEL not in text
        selected = b.export_csv("CRM Lead", fields, selected_items=[private_lead])
        assert selected.status in (200, 403, 404)
        selected_text = selected.text().replace("\\_", "_")
        assert private_lead not in selected_text and PRIVATE_LEAD not in selected_text
        assert PRIVATE_LEAD_MEMO_SENTINEL not in selected_text

    def note_export():
        response = b.export_csv("FCRM Note", ["name", "title", "content"])
        assert response.status == 200, f"note export status {response.status}"
        text = response.text().replace("\\_", "_")
        assert shared_note in text and SHARED_NOTE_SENTINEL in text
        assert private_note not in text and PRIVATE_NOTE_SENTINEL not in text
        assert private_on_shared not in text and PRIVATE_ON_SHARED_SENTINEL not in text
        selected = b.export_csv(
            "FCRM Note", ["name", "title", "content"], selected_items=[private_note]
        )
        assert selected.status in (200, 403, 404)
        selected_text = selected.text().replace("\\_", "_")
        assert private_note not in selected_text and PRIVATE_NOTE_SENTINEL not in selected_text

    checks.run("Lead lists enforce owner/share boundaries", lead_lists)
    checks.run("FCRM Note lists enforce record allow-list boundaries", note_lists)
    checks.run("Lead details deny the private record and allow the shared record", lead_details)
    checks.run("FCRM Note details deny private records and allow the shared record", note_details)
    checks.run("Related-note resource query does not cross the note boundary", related_notes)
    checks.run("B cannot modify the private Lead and A sees no tampering", private_lead_write)
    checks.run("B cannot modify private Notes and A sees no tampering", private_note_write)
    checks.run("B can collaborate on the shared Lead", shared_lead_write)
    checks.run("B can collaborate on the shared FCRM Note", shared_note_write)
    checks.run("Private Lead timeline is denied", private_timeline)
    checks.run("Shared Lead timeline filters non-shared Notes", shared_timeline)
    checks.run("Lead CSV export excludes the private record", lead_export)
    checks.run("FCRM Note CSV export excludes private records", note_export)
    return checks


def run_configuration(mode):
    source = Path(__file__).read_text(encoding="utf-8")
    prefix = ["wsl.exe", "-d", DISTRO, "--exec"] if os.name == "nt" else []
    command = prefix + [
        "docker",
        "exec",
        "-i",
        "-w",
        "/home/frappe/frappe-bench/sites",
        CONTAINER,
        "../env/bin/python",
        "-",
        "--container-configure",
        "--mode",
        mode,
    ]
    completed = subprocess.run(
        command,
        input=source,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=180,
        check=False,
    )
    if completed.returncode:
        error_types = [
            line.removeprefix("M6_CONFIG_ERROR:")
            for line in completed.stderr.splitlines()
            if line.startswith("M6_CONFIG_ERROR:")
        ]
        detail = f" ({error_types[-1]})" if error_types else ""
        raise RuntimeError(
            f"M6 configuration failed{detail}; credentials were not written"
        )
    marker = "M6_CONFIG_JSON:"
    lines = [line for line in completed.stdout.splitlines() if line.startswith(marker)]
    if len(lines) != 1:
        raise RuntimeError("M6 configuration did not return exactly one credential envelope")
    return json.loads(lines[0][len(marker) :])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument(
        "--phase",
        choices=("default", "guarded", "both"),
        default="guarded",
        help="run native-baseline or guarded checks in a fresh process (default: guarded)",
    )
    parser.add_argument("--container-configure", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--mode", choices=("default", "guarded"), default="guarded", help=argparse.SUPPRESS
    )
    args = parser.parse_args()
    if args.container_configure:
        try:
            container_configure(args.mode)
        except Exception as error:
            print(f"M6_CONFIG_ERROR:{type(error).__name__}", file=sys.stderr)
            raise SystemExit(2) from None
        return
    failures = []
    modes = ("default", "guarded") if args.phase == "both" else (args.phase,)
    for mode in modes:
        print(f"PHASE {mode}: two real Sales User sessions")
        config = run_configuration(mode)
        checks = validate_http(config, args.base_url)
        print(f"SUMMARY {mode} pass={len(checks.passes)} fail={len(checks.failures)}")
        failures.extend((mode, name, error) for name, error in checks.failures)
    if failures:
        print("RESULT M6 team-access validation failed; see docs/TEAM_ACCESS.md before use")
        raise SystemExit(1)
    print("RESULT M6 HTTP/API checks passed; UI visual validation remains separate")


if __name__ == "__main__":
    main()

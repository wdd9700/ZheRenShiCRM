import argparse
import csv
from datetime import datetime, timedelta, timezone
import secrets
import getpass
import http.cookiejar
import io
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request


def parse_datetime(value):
    return datetime.strptime(value.split(".")[0], "%Y-%m-%d %H:%M:%S")


class Session:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.http = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf = None

    def request(self, path, data=None, method=None):
        headers = {"Host": "crm.localhost"}
        if self.csrf:
            headers["X-Frappe-CSRF-Token"] = self.csrf
        if data is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(data).encode()
        req = urllib.request.Request("http://127.0.0.1:8088" + path, data=data, headers=headers, method=method)
        try:
            with self.http.open(req, timeout=60) as response:
                return response.status, response.read().decode()
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode()

    def api(self, name, data=None):
        status, text = self.request("/api/method/" + name, data)
        result = json.loads(text)
        assert status == 200, name + " HTTP " + str(status) + " type=" + str(result.get("exc_type")) + " (body withheld)"
        assert not any(key in result for key in ("exc", "exception")), "Unexpected traceback"
        return result.get("message")

    def login(self, user, password):
        self.api("login", {"usr": user, "pwd": password})
        assert self.api("frappe.auth.get_logged_user") == user
        status, text = self.request("/app")
        assert status == 200, "Desk unavailable"
        token = re.search(r'frappe.csrf_token\s*=\s*[\"\']([^\"\']+)', text)
        assert token, "Desk CSRF token missing"
        self.csrf = token.group(1)

    def doc(self, doctype, name):
        return self.api("frappe.client.get", {"doctype": doctype, "name": name})

    def save(self, doc):
        return self.api("frappe.client.save", {"doc": json.dumps(doc)})


def run_remote(phase):
    check = 'import json; c=json.load(open("sites/crm.localhost/site_config.json")); assert type(c.get("team_access_synthetic_only")) is int and c["team_access_synthetic_only"] == 1; assert type(c.get("mute_emails")) is int and c["mute_emails"] == 1; assert c.get("server_script_enabled") == 0'
    subprocess.run(["sudo", "-n", "docker", "exec", "crm-trial-c010400-backend-1", "python", "-c", check], check=True)
    password = json.load(sys.stdin)["password"]
    admin = Session()
    admin.login("Administrator", password)
    try:
        if phase == "inspect":
            settings = admin.doc("System Settings", "System Settings")
            keys = ("language", "time_zone", "allow_error_traceback", "enable_telemetry", "enable_password_policy", "minimum_password_score")
            print(json.dumps({key: settings.get(key) for key in keys}))
            errors = admin.api("frappe.client.get_list", {"doctype": "Error Log", "fields": ["name", "method", "error"], "order_by": "creation desc", "limit_page_length": 1})
            for error in errors:
                frames = [line.strip() for line in error["error"].splitlines() if line.strip().startswith('File "')]
                print("Latest error frames", json.dumps(frames))
            for doctype in ("CRM Lead", "CRM Deal", "Contact", "CRM Organization", "CRM Task", "FCRM Note"):
                docs = admin.api("frappe.client.get_list", {"doctype": doctype, "fields": ["name", "creation", "modified"], "limit_page_length": 20})
                print(doctype, json.dumps(docs))
        elif phase == "baseline":
            settings = admin.doc("System Settings", "System Settings")
            before = {key: settings.get(key) for key in ("language", "time_zone", "allow_error_traceback", "enable_telemetry")}
            settings.update(language=settings.get("language") or "zh", time_zone="Asia/Shanghai", allow_error_traceback=0, enable_telemetry=0)
            admin.save(settings)
            fresh = admin.doc("System Settings", "System Settings")
            assert fresh["allow_error_traceback"] == 0 and fresh["enable_telemetry"] == 0
            assert fresh["enable_password_policy"] == 1 and int(fresh["minimum_password_score"]) == 2
            print("PASS normal System Settings save", json.dumps(before), "->", json.dumps({key: fresh.get(key) for key in before}))
            guest = Session()
            status, body = guest.request("/api/method/resource_import.api.preview", {"csv_text": "", "source": "C010800", "shared_consent": True})
            assert status in (401, 403), "Anonymous import access accepted"
            assert not any(key in json.loads(body) for key in ("exc", "exception")), "Anonymous traceback"
            assert not any(cookie.name == "sid" and cookie.value != "Guest" for cookie in guest.jar)
            assert admin.api("frappe.auth.get_logged_user") == "Administrator"
            print("PASS anonymous import denied without traceback; authenticated identity intact")
        elif phase == "import":
            prefix = "C010800-REMOTE-20261102"
            output = io.StringIO(newline="")
            writer = csv.writer(output)
            writer.writerow(["序号", "姓名", "公司名称", "联系方式", "公司产品、服务", "需要的产品、服务"])
            row = ["1", prefix + "合成人员", prefix + "合成企业", "c010800@example.invalid", "合成服务", "合成需求"]
            writer.writerows([row, row, ["3", "", prefix + "错误企业", "", "", "缺姓名合成错误"]])
            payload = {"csv_text": output.getvalue(), "source": prefix + ".csv", "shared_consent": True}
            preview = admin.api("resource_import.api.preview", payload)
            assert len(preview["rows"]) == 3 and preview["rows"][2]["errors"]
            result = admin.api("resource_import.api.apply", dict(payload, token=preview["token"], confirm=True, choices={}))
            states = [row["state"] for row in result["rows"]]
            assert states == ["成功", "已导入", "失败"], str(states)
            repeated = admin.api("resource_import.api.apply", dict(payload, token=preview["token"], confirm=True, choices={}))
            assert [row["state"] for row in repeated["rows"]] == ["已导入", "已导入", "失败"]
            links = result["rows"][0]["links"]
            for key, doctype in (("lead", "CRM Lead"), ("organization", "CRM Organization"), ("contact", "Contact")):
                doc = admin.doc(doctype, links[key]["name"])
                assert doc["name"] == links[key]["name"]
            lead = admin.doc("CRM Lead", links["lead"]["name"])
            assert lead["custom_resource_requirement_verbatim"] == "合成需求"
            print("PASS preview/apply/duplicate/error/related detail", json.dumps(links, ensure_ascii=False))
        elif phase == "clock":
            now = datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None, microsecond=0)
            due = (now + timedelta(days=1)).isoformat(sep=" ")
            task = admin.api("frappe.client.insert", {"doc": {"doctype": "CRM Task", "title": "TEST-C010800-CLOCK-" + now.strftime("%Y%m%d%H%M%S"), "description": "无外联的合成跟进时间验收", "status": "Todo", "due_date": due, "reference_doctype": "CRM Lead", "reference_docname": "CRM-LEAD-2026-00001", "custom_team_visibility": "Private"}})
            fresh = admin.doc("CRM Task", task["name"])
            assert abs((parse_datetime(fresh["creation"]) - now).total_seconds()) < 120
            assert fresh["due_date"] == due
            print("PASS Shanghai creation/follow-up time round trip", fresh["name"], fresh["creation"], fresh["due_date"])
        elif phase == "team":
            team_flow(admin)
        else:
            raise AssertionError("Unknown phase")
    finally:
        admin.api("logout", {})


def visible_channels(session, doc, expected):
    doctype, name = doc["doctype"], doc["name"]
    title = doc.get("title") or doc.get("first_name") or name
    rows = session.api("frappe.client.get_list", {"doctype": doctype, "fields": ["name"], "filters": {"name": name}})
    assert bool(rows) is expected, "STOP inconsistent filtered list " + doctype
    links = session.api("frappe.desk.search.search_link", {"doctype": doctype, "txt": title, "page_length": 20})
    assert any(str(row.get("value")) == str(name) for row in links) is expected, "STOP inconsistent link search " + doctype
    payload = {"doctype": doctype, "file_format_type": "CSV", "fields": json.dumps(["name"]), "filters": json.dumps({"name": name}), "order_by": "creation desc", "start": 0, "page_length": 20, "view": "Report", "with_comment_count": 0, "export_in_background": 0}
    code, body = session.request("/api/method/frappe.desk.reportview.export_query", payload)
    assert code == 200, "Standard export unavailable HTTP " + str(code)
    exported = list(csv.reader(io.StringIO(body.lstrip("\ufeff"))))
    assert any(str(name) in row for row in exported[2:]) is expected, "STOP inconsistent standard export " + doctype
    if doctype in ("FCRM Note", "CRM Task"):
        timeline = session.api("crm.api.activities.get_activities", {"name": doc["reference_docname"]})
        assert (title in json.dumps(timeline, ensure_ascii=False)) is expected, "STOP inconsistent timeline " + doctype


def rejected_write(session, owner, doc):
    before = owner.doc(doc["doctype"], doc["name"])
    changed = dict(before, title=before.get("title", "") + "-UNAUTHORIZED")
    code, body = session.request("/api/method/frappe.client.save", {"doc": json.dumps(changed)})
    assert code in (403, 404), "STOP unauthorized write accepted HTTP " + str(code)
    after = owner.doc(doc["doctype"], doc["name"])
    assert before == after, "STOP rejected write changed record"


def team_flow(admin):
    prefix = "C010800-TEAM-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    sessions = []
    try:
        for suffix in ("a", "b"):
            email = prefix.lower() + "-" + suffix + "@example.invalid"
            password = secrets.token_urlsafe(36)
            user = admin.api("frappe.client.insert", {"doc": {"doctype": "User", "email": email, "first_name": prefix + suffix, "user_type": "System User", "enabled": 1, "send_welcome_email": 0, "new_password": password, "roles": [{"role": "Sales User"}]}})
            assert {role["role"] for role in user["roles"]} == {"Sales User"}
            session = Session()
            session.login(email, password)
            sessions.append((email, session))
        (email_a, a), (email_b, b) = sessions
        print("PASS two separate authenticated ordinary Sales User sessions", email_a, email_b)
        status = a.api("frappe.client.get_list", {"doctype": "CRM Lead Status", "fields": ["name"], "limit_page_length": 1})[0]["name"]
        lead = a.api("frappe.client.insert", {"doc": {"doctype": "CRM Lead", "first_name": prefix, "status": status, "lead_owner": email_a}})
        assert lead["owner"] == email_a

        def denied(doctype, name):
            code, body = b.request("/api/method/frappe.client.get", {"doctype": doctype, "name": name})
            assert code in (403, 404), "STOP unexpected private access: " + doctype + " HTTP " + str(code)
            assert not any(key in json.loads(body) for key in ("exc", "exception")), "Traceback leaked"
            rows = b.api("frappe.client.get_list", {"doctype": doctype, "fields": ["name"], "filters": {"name": name}})
            assert rows == [], "STOP private record appears in list"

        denied("CRM Lead", lead["name"])
        a.api("frappe.share.add", {"doctype": "CRM Lead", "name": lead["name"], "user": email_b, "read": 1, "write": 0, "notify": 0})
        assert b.doc("CRM Lead", lead["name"])["name"] == lead["name"]
        print("PASS private parent hidden then explicitly shared parent readable")
        note = a.api("frappe.client.insert", {"doc": {"doctype": "FCRM Note", "title": prefix + "私人记录", "content": "合成私有跟进记录", "reference_doctype": "CRM Lead", "reference_docname": lead["name"], "custom_team_visibility": "Private"}})
        due = (datetime.now(timezone(timedelta(hours=8))) + timedelta(days=1)).replace(tzinfo=None, microsecond=0).isoformat(sep=" ")
        task = a.api("frappe.client.insert", {"doc": {"doctype": "CRM Task", "title": prefix + "合成跟进", "description": "合成私有任务", "status": "Todo", "due_date": due, "reference_doctype": "CRM Lead", "reference_docname": lead["name"], "custom_team_visibility": "Private"}})
        created = parse_datetime(task["creation"])
        shanghai = datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)
        assert abs((shanghai - created).total_seconds()) < 120, "Creation is not Shanghai wall time"
        assert a.doc("CRM Task", task["name"])["due_date"] == due
        print("PASS Shanghai creation and follow-up round trip", task["creation"], due)
        for doc in (note, task):
            denied(doc["doctype"], doc["name"])
            visible_channels(a, doc, True)
            visible_channels(b, doc, False)
            rejected_write(b, a, doc)
            doc["custom_team_visibility"] = "Shared"
            doc = a.save(doc)
            assert b.doc(doc["doctype"], doc["name"])["name"] == doc["name"]
            visible_channels(b, doc, True)
            rejected_write(b, a, doc)
            doc["custom_team_collaborator"] = email_b
            doc = a.save(doc)
            editable = b.doc(doc["doctype"], doc["name"])
            editable["title"] += "-合法协作"
            doc = b.save(editable)
            assert a.doc(doc["doctype"], doc["name"])["title"].endswith("-合法协作")
            doc["custom_team_collaborator"] = ""
            doc["custom_team_visibility"] = "Private"
            doc = a.save(doc)
            denied(doc["doctype"], doc["name"])
            visible_channels(b, doc, False)
            rejected_write(b, a, doc)
            fresh_b = Session()
            fresh_b.login(email_b, password)
            sessions.append((email_b, fresh_b))
            visible_channels(fresh_b, doc, False)
        print("PASS private/shared/collaborator/revoked Note and Task detail, list, search, timeline, export; old/new B sessions")
        a.api("frappe.share.set_permission", {"doctype": "CRM Lead", "name": lead["name"], "user": email_b, "permission_to": "read", "value": 0})
        denied("CRM Lead", lead["name"])
        print("PASS parent sharing revoked; records retained", lead["name"], note["name"], task["name"])
    finally:
        for email, session in sessions:
            session.api("logout", {})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("inspect", "baseline", "import", "clock", "team"))
    parser.add_argument("--key")
    parser.add_argument("--known-hosts")
    parser.add_argument("--ssh", default="C:/Windows/System32/OpenSSH/ssh.exe")
    parser.add_argument("--remote", action="store_true")
    args = parser.parse_args()
    if args.remote:
        run_remote(args.phase)
        return
    assert args.key and args.known_hosts, "Explicit key and pinned known_hosts required"
    password = os.environ.get("CRM_TRIAL_ADMIN_PASSWORD") or getpass.getpass("Trial administrator password: ")
    code = Path(__file__).read_text(encoding="utf-8")
    command = [args.ssh, "-F", "NUL", "-i", args.key, "-o", "UserKnownHostsFile=" + args.known_hosts, "-o", "StrictHostKeyChecking=yes", "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "dev@8.133.190.46", "python3 -c " + shlex.quote(code) + " " + args.phase + " --remote"]
    result = subprocess.run(command, input=json.dumps({"password": password}), text=True, encoding="utf-8")
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()

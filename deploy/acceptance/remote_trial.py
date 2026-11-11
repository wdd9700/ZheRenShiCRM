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
        if phase == "preserve":
            subprocess.run(["sudo", "-n", "docker", "ps", "-a", "--filter", "label=com.docker.compose.project=crm-trial-c010400", "--format", "{{.Names}}|{{.Image}}|{{.Status}}"], check=True)
            subprocess.run(["ss", "-ltn"], check=True)
            assert admin.api("ping") == "pong"
            settings = admin.doc("System Settings", "System Settings")
            assert all(settings.get(key) == value for key, value in {"language": "zh", "time_zone": "Asia/Shanghai", "allow_error_traceback": 0, "enable_telemetry": 0}.items())
            import hashlib
            for doctype, name in (("CRM Lead", "CRM-LEAD-2026-00001"), ("CRM Organization", "C010800-REMOTE-20261102合成企业"), ("Contact", "C010800-REMOTE-20261102合成人员-C010800-REMOTE-20261102合成企业"), ("CRM Task", "1"), ("CRM Task", "2")):
                doc = admin.doc(doctype, name)
                canonical = json.dumps(doc, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
                print("PRESERVE", doctype, name, hashlib.sha256(canonical).hexdigest())
            print("PASS baseline retained; compare PRESERVE digests before/after controlled deployment")
        elif phase == "inspect":
            settings = admin.doc("System Settings", "System Settings")
            keys = ("language", "time_zone", "allow_error_traceback", "enable_telemetry", "enable_password_policy", "minimum_password_score")
            print(json.dumps({key: settings.get(key) for key in keys}))
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
            expected_first = "已导入" if preview["rows"][0]["state"] == "已导入" else "成功"
            assert states == [expected_first, "已导入", "失败"], str(states)
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
    search_field = "first_name" if doctype == "CRM Lead" else "title"
    searched = session.api("frappe.client.get_list", {"doctype": doctype, "fields": ["name"], "filters": {search_field: ["like", "%" + str(doc.get(search_field) or title) + "%"]}})
    assert any(str(row["name"]) == str(name) for row in searched) is expected, "STOP inconsistent normal text filter " + doctype
    if doctype in ("CRM Lead", "CRM Deal"):
        crm_list = session.api("crm.api.doc.get_data", {"doctype": doctype, "filters": {"name": name}, "order_by": "modified desc"})
        assert any(str(row["name"]) == str(name) for row in crm_list["data"]) is expected, "STOP inconsistent CRM list " + doctype
    links = session.api("frappe.desk.search.search_link", {"doctype": doctype, "txt": str(name), "page_length": 20})
    assert any(str(row.get("value")) == str(name) for row in links) is expected, "STOP inconsistent link search " + doctype
    payload = {"doctype": doctype, "file_format_type": "CSV", "fields": json.dumps(["name"]), "filters": json.dumps({"name": name}), "order_by": "creation desc", "start": 0, "page_length": 20, "view": "Report", "with_comment_count": 0, "export_in_background": 0}
    code, body = session.request("/api/method/frappe.desk.reportview.export_query", payload)
    assert code == 200, "Standard export unavailable HTTP " + str(code)
    exported = list(csv.reader(io.StringIO(body.lstrip("\ufeff"))))
    assert any(str(name) in row for row in exported) is expected, "STOP inconsistent standard export " + doctype
    if doctype in ("FCRM Note", "CRM Task"):
        timeline = session.api("crm.api.activities.get_activities", {"name": doc["reference_docname"]})
        assert (title in json.dumps(timeline, ensure_ascii=False)) is expected, "STOP inconsistent timeline " + doctype


def rejected_write(session, owner, doc):
    before = owner.doc(doc["doctype"], doc["name"])
    field = "first_name" if doc["doctype"] == "CRM Lead" else "title"
    changed = dict(before)
    changed[field] = before.get(field, "") + "-UNAUTHORIZED"
    code, body = session.request("/api/method/frappe.client.save", {"doc": json.dumps(changed)})
    assert code in (403, 404), "STOP unauthorized write accepted HTTP " + str(code)
    after = owner.doc(doc["doctype"], doc["name"])
    assert before == after, "STOP rejected write changed record"
    return code


def team_flow(admin):
    prefix = "TEST-C010800-TEAM-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
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
        for outsider in (a, b, Session()):
            code, body = outsider.request("/api/method/resource_import.api.preview", {"csv_text": "", "source": prefix, "shared_consent": True})
            assert code in (401, 403) and not any(key in json.loads(body) for key in ("exc", "exception"))
        print("PASS ordinary/anonymous import API denied without traceback")
        status = a.api("frappe.client.get_list", {"doctype": "CRM Lead Status", "fields": ["name"], "limit_page_length": 1})[0]["name"]
        lead = a.api("frappe.client.insert", {"doc": {"doctype": "CRM Lead", "first_name": prefix, "organization": prefix + "合成企业", "status": status, "lead_owner": email_a}})
        assert lead["owner"] == email_a
        visible_channels(a, lead, True)
        visible_channels(b, lead, False)

        def denied(session, doctype, name):
            code, body = session.request("/api/method/frappe.client.get", {"doctype": doctype, "name": name})
            assert code in (403, 404), "STOP unexpected private access: " + doctype + " HTTP " + str(code)
            assert not any(key in json.loads(body) for key in ("exc", "exception")), "Traceback leaked"
            rows = session.api("frappe.client.get_list", {"doctype": doctype, "fields": ["name"], "filters": {"name": name}})
            assert rows == [], "STOP private record appears in list"
            return code

        def new_b():
            session = Session()
            session.login(email_b, password)
            sessions.append((email_b, session))
            return session

        def revoked(session, doc, label):
            code = denied(session, doc["doctype"], doc["name"])
            write_code = rejected_write(session, a, doc)
            print("PASS revoked direct GET", label, doc["doctype"], doc["name"], "HTTP", code, "; write HTTP", write_code, "; owner full document unchanged")

        denied(b, "CRM Lead", lead["name"])
        a.api("frappe.share.add", {"doctype": "CRM Lead", "name": lead["name"], "user": email_b, "read": 1, "write": 0, "notify": 0})
        assert b.doc("CRM Lead", lead["name"])["name"] == lead["name"]
        print("PASS private parent hidden then explicitly shared parent readable")
        note = a.api("frappe.client.insert", {"doc": {"doctype": "FCRM Note", "title": prefix + "私人记录", "content": "合成私有跟进记录", "reference_doctype": "CRM Lead", "reference_docname": lead["name"], "custom_team_visibility": "Private"}})
        assert note["owner"] == email_a and a.doc("FCRM Note", note["name"])["name"] == note["name"]
        file_note = a.api("frappe.client.insert", {"doc": {"doctype": "FCRM Note", "title": prefix + "私附件记录", "content": "单独私有附件，不发布共享", "reference_doctype": "CRM Lead", "reference_docname": lead["name"], "custom_team_visibility": "Private"}})
        attachment_text = prefix + " harmless synthetic attachment"
        attachment = a.api("frappe.client.insert", {"doc": {"doctype": "File", "file_name": prefix + ".txt", "is_private": 1, "attached_to_doctype": "FCRM Note", "attached_to_name": file_note["name"], "content": attachment_text}})
        code, content = a.request(attachment["file_url"])
        assert code == 200 and content == attachment_text
        for outsider in (b, Session()):
            code, content = outsider.request(attachment["file_url"])
            assert code in (403, 404), "STOP private attachment downloadable without permission"
        file_note_before = a.doc("FCRM Note", file_note["name"])
        attachment_before = a.doc("File", attachment["name"])
        code, body = a.request("/api/method/frappe.client.save", {"doc": json.dumps(dict(file_note_before, custom_team_visibility="Shared"))})
        assert code == 417 and json.loads(body).get("exc_type") == "ValidationError"
        assert a.doc("FCRM Note", file_note["name"]) == file_note_before
        assert a.doc("File", attachment["name"]) == attachment_before
        denied(b, "FCRM Note", file_note["name"])
        assert b.request(attachment["file_url"])[0] in (403, 404)
        print("PASS owner Note/private attachment; direct Shared conversion refused 417 with record/visibility/file unchanged, B/anonymous denied")
        rejected_write(b, a, lead)
        due = (datetime.now(timezone(timedelta(hours=8))) + timedelta(days=1)).replace(tzinfo=None, microsecond=0).isoformat(sep=" ")
        task = a.api("frappe.client.insert", {"doc": {"doctype": "CRM Task", "title": prefix + "合成跟进", "description": "合成私有任务", "status": "Todo", "due_date": due, "reference_doctype": "CRM Lead", "reference_docname": lead["name"], "custom_team_visibility": "Private"}})
        assert task["owner"] == email_a
        task_read = a.doc("CRM Task", task["name"])
        assert task_read["owner"] == email_a and task_read["due_date"] == due
        print("PASS explicit owner CRM Task", task["name"], "created and read back as", email_a)
        created = parse_datetime(task["creation"])
        shanghai = datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)
        assert abs((shanghai - created).total_seconds()) < 120, "Creation is not Shanghai wall time"
        print("PASS Shanghai creation and follow-up round trip", task["creation"], due)
        for doc in (note, task):
            denied(b, doc["doctype"], doc["name"])
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
            revoked(b, doc, "old-B")
            visible_channels(b, doc, False)
            fresh_b = new_b()
            revoked(fresh_b, doc, "fresh-B-after-revoke")
            visible_channels(fresh_b, doc, False)
            print("PASS revoked list/text-filter/link/timeline/export old/fresh B", doc["doctype"], doc["name"])
        print("PASS Note/Task private, Shared read-only and explicit collaborator write; revoked direct GET/write tested independently for old/fresh B")
        file_note = a.doc("FCRM Note", file_note["name"])
        file_note["custom_team_collaborator"] = email_b
        file_note = a.save(file_note)
        assert b.request(attachment["file_url"]) == (200, attachment_text)
        file_note["custom_team_collaborator"] = ""
        a.save(file_note)
        fresh_b = new_b()
        for outsider in (b, fresh_b, Session()):
            assert outsider.request(attachment["file_url"])[0] in (403, 404)
        assert a.request(attachment["file_url"]) == (200, attachment_text)
        print("PASS private attachment explicit collaboration/revocation; owner intact, old/new/anonymous denied")
        a.api("frappe.share.set_permission", {"doctype": "CRM Lead", "name": lead["name"], "user": email_b, "permission_to": "read", "value": 0})
        revoked(b, lead, "old-B")
        visible_channels(b, lead, False)
        fresh_b = new_b()
        revoked(fresh_b, lead, "fresh-B-after-revoke")
        visible_channels(fresh_b, lead, False)
        assert admin.doc("CRM Lead", lead["name"])["owner"] == email_a
        guest_code, _ = Session().request("/api/method/frappe.client.get", {"doctype": "CRM Lead", "name": lead["name"]})
        assert guest_code in (401, 403)
        print("PASS parent sharing revoked; records retained", lead["name"], note["name"], task["name"])
        statuses = a.api("frappe.client.get_list", {"doctype": "CRM Deal Status", "fields": ["name", "type"], "limit_page_length": 30})
        deal_status = next((row["name"] for row in statuses if row.get("type") == "Open"), statuses[0]["name"])
        deal_name = a.api("crm.fcrm.doctype.crm_lead.crm_lead.convert_to_deal", {"lead": lead["name"], "deal": {"status": deal_status, "deal_owner": email_a}})
        deal = a.doc("CRM Deal", deal_name)
        assert deal["deal_owner"] == email_a and deal["lead"] == lead["name"]
        assert a.doc("CRM Organization", deal["organization"])["organization_name"] == prefix + "合成企业"
        assert len(deal["contacts"]) == 1
        a.doc("Contact", deal["contacts"][0]["contact"])
        denied(b, "CRM Deal", deal_name)
        a.api("frappe.share.add", {"doctype": "CRM Deal", "name": deal_name, "user": email_b, "read": 1, "write": 0, "notify": 0})
        assert b.doc("CRM Deal", deal_name)["name"] == deal_name
        rejected_write(b, a, deal)
        a.api("frappe.share.set_permission", {"doctype": "CRM Deal", "name": deal_name, "user": email_b, "permission_to": "read", "value": 0})
        revoked(b, deal, "old-B")
        fresh_b = new_b()
        revoked(fresh_b, deal, "fresh-B-after-revoke")
        print("PASS normal Lead conversion -> Organization/Contact/Deal relationships; Deal private/read-only share/revoked", deal_name)
        b_lead = b.api("frappe.client.insert", {"doc": {"doctype": "CRM Lead", "first_name": prefix + "B", "status": status, "lead_owner": email_b}})
        assert b_lead["owner"] == email_b and b.doc("CRM Lead", b_lead["name"])["owner"] == email_b
        print("PASS explicit owner CRM Lead", b_lead["name"], "created and read back as", email_b)
        b_note = b.api("frappe.client.insert", {"doc": {"doctype": "FCRM Note", "title": prefix + "B本人", "content": "B合成私文", "reference_doctype": "CRM Lead", "reference_docname": b_lead["name"]}})
        assert b_note["owner"] == email_b and b.doc("FCRM Note", b_note["name"])["name"] == b_note["name"]
        assert a.request("/api/method/frappe.client.get", {"doctype": "FCRM Note", "name": b_note["name"]})[0] == 403
        print("PASS B normal own Lead/Note creation and owner read, A denied")
    finally:
        for email, session in sessions:
            session.api("logout", {})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("inspect", "preserve", "baseline", "import", "clock", "team"))
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

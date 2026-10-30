import argparse
import concurrent.futures
import csv
import http.cookiejar
import importlib.util
import io
import json
from pathlib import Path
import re
import threading
import urllib.error
import urllib.parse
import urllib.request

COLUMNS = ["序号", "姓名", "公司名称", "联系方式", "公司产品、服务", "需要的产品、服务"]
BASE = "http://127.0.0.1:8088"


class Session:
    def __init__(self):
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(self.cookies))
        self.csrf = None

    def request(self, path, payload=None, csrf=True, method=None):
        headers = {"Host": "crm.localhost"}
        data = None
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode()
            headers["Content-Type"] = "application/json"
        if csrf and self.csrf:
            headers["X-Frappe-CSRF-Token"] = self.csrf
        request = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=90) as response:
                return response.status, response.read().decode(), response.url
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode(), exc.url

    def login(self, values):
        code, body, _ = self.request("/api/method/login", {"usr": "Administrator", "pwd": values["ADMIN_PASSWORD"]}, csrf=False)
        assert code == 200 and json.loads(body)["message"] == "Logged In", "Login failed (response withheld)"
        code, page, _ = self.request("/resource-import")
        assert code == 200 and "六列资源导入" in page, "Import page unavailable"
        token = re.search(r'<meta name="csrf-token" content="([^"]+)"', page)
        assert token, "CSRF meta missing"
        self.csrf = token.group(1)
        return page

    def api(self, method, payload, expected=200):
        code, body, _ = self.request("/api/method/resource_import.api." + method, payload)
        assert code == expected, f"{method} HTTP {code}, expected {expected}; body withheld"
        result = json.loads(body)
        assert not any(k in result for k in ("exc", "exception")), "Traceback leaked"
        return result.get("message")

    def listed(self, doctype, filters, fields=None):
        query = urllib.parse.urlencode({"filters": json.dumps(filters), "fields": json.dumps(fields or ["name"]), "limit_page_length": 1000})
        code, body, _ = self.request("/api/resource/" + urllib.parse.quote(doctype, safe="") + "?" + query)
        assert code == 200, "REST list failed"
        return json.loads(body)["data"]

    def doc(self, doctype, name):
        code, body, _ = self.request("/api/resource/" + urllib.parse.quote(doctype, safe="") + "/" + urllib.parse.quote(name, safe=""))
        assert code == 200, "REST detail failed"
        return json.loads(body)["data"]


def csv_text(rows):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(COLUMNS)
    writer.writerows(rows)
    return output.getvalue()


def verify(runtime_dir, prefix):
    spec = importlib.util.spec_from_file_location("crm_deploy_manage", Path(runtime_dir) / "manage.py")
    manage = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(manage)
    values = manage.read_env()
    guest = Session()
    code, page, url = guest.request("/resource-import")
    assert "login" in url and "csrf-token" not in page, "Anonymous page exposed import UI"
    code, body, _ = guest.request("/api/method/resource_import.api.preview", {"csv_text": "", "source": "M7.csv", "shared_consent": True})
    assert code in (401, 403), "Anonymous API allowed"
    admin = Session()
    page = admin.login(values)
    assert 'id="shared-consent" type="checkbox"' in page and "Sales User" in page, "Shared-data warning missing"
    assert 'id="shared-consent" type="checkbox" checked' not in page, "Sharing consent preselected"
    print("PASS anonymous page/API and authenticated HTML with unselected sharing consent")

    org_a, org_b = prefix + "企业甲", prefix + "企业乙"
    person, raw_contact = prefix + "张一", "13900007001 / 微信 <m7>&原文"
    offering = "产品 <img src=x onerror=alert(1)> & \"服务\"\n第二行,保留"
    requirement = "需求 <script>alert('M7')</script> & 原文\n第二行"
    long_org, long_person = prefix + "企" * (100 - len(prefix)), prefix + "人" * (100 - len(prefix))
    rows = [
        ["1", person, org_a, raw_contact, offering, requirement],
        ["2", person, org_a, raw_contact, offering, "同联系人第二条需求"],
        ["3", prefix + "李二", org_a, "微信 m7-opaque", "服务乙", "需求乙"],
        ["4", prefix + "王三", org_b, "13900007003 / m7-check@example.invalid", "产品丙", "需求丙"],
        ["5", person, org_a, raw_contact, offering, requirement],
        ["6", "", org_b, "微信 missing", "", "缺姓名行"],
        ["7", long_person, long_org, "微信 rollback", "回滚产品", "回滚需求"],
    ]
    payload = {"csv_text": csv_text(rows), "source": prefix + ".csv", "shared_consent": True}

    def counts():
        return tuple(len(admin.listed(dt, filters)) for dt, filters in (
            ("CRM Organization", {"organization_name": ["like", prefix + "%"]}),
            ("Contact", {"first_name": ["like", prefix + "%"]}),
            ("CRM Lead", {"first_name": ["like", prefix + "%"]}),
        ))

    before = counts()
    assert before == (0, 0, 0), "Use a new unique M7 prefix; existing synthetic records retained"
    preview = admin.api("preview", payload)
    assert counts() == before, "Preview wrote business records"
    assert len(preview["rows"]) == 7 and preview["rows"][5]["errors"] and preview["rows"][4]["state"] == "文件内重复"
    assert all(len(row["key"]) == 64 for row in preview["rows"])
    print("PASS read-only preview, per-row validation, within-file duplicate and full hash")
    code, body, _ = admin.request("/api/method/resource_import.api.preview", payload, csrf=False)
    assert code in (400, 403), "Missing CSRF accepted"
    code, _, _ = admin.request("/api/method/resource_import.api.preview", method="GET")
    assert code in (403, 405), "GET allowed for POST method"
    for changes in ({"shared_consent": False},):
        admin.api("preview", {**payload, **changes}, 422)
    apply_payload = {**payload, "token": preview["token"], "confirm": True, "choices": {}}
    for changes in ({"confirm": False}, {"shared_consent": False}, {"source": "changed.csv"}, {"csv_text": payload["csv_text"] + "\n"}, {"token": "0.invalid"}, {"token": "f" * 64}):
        admin.api("apply", {**apply_payload, **changes}, 422)
    another = Session()
    another.login(values)
    another.api("apply", apply_payload, 422)
    assert counts() == before
    print("PASS CSRF, POST-only, sharing/confirmation, tampered/missing/cross-session preview receipt rejection")

    result = admin.api("apply", apply_payload)
    states = [row["state"] for row in result["rows"]]
    assert states == ["成功", "成功", "成功", "成功", "已导入", "失败", "失败"], "Unexpected row states: " + repr(states)
    assert counts() == (2, 3, 4), "Wrong count or row rollback left orphan"
    lead = admin.doc("CRM Lead", result["rows"][0]["links"]["lead"]["name"])
    assert json.loads(lead["custom_resource_snapshot_verbatim"]) == dict(zip(COLUMNS, rows[0])), "Raw snapshot changed"
    assert lead["custom_resource_requirement_verbatim"] == requirement and lead["custom_resource_offering_verbatim"] == offering and lead["custom_resource_contact_verbatim"] == raw_contact
    assert lead["lead_owner"] == "Administrator" and len(lead["custom_resource_import_key"]) == 64
    assert json.loads(lead["custom_resource_source_verbatim"])["file"] == payload["source"]
    org = admin.doc("CRM Organization", result["rows"][0]["links"]["organization"]["name"])
    assert not org.get("company_description"), "Raw product leaked into shared organization"
    contact = admin.doc("Contact", result["rows"][0]["links"]["contact"]["name"])
    assert len(contact["custom_resource_contact_key"]) == 64
    for row in result["rows"][:4]:
        for link in row["links"].values():
            code, _, _ = admin.request(link["url"])
            assert code == 200, "Native entity link failed"
    print("PASS apply, row rollback without orphan, Lead raw preservation/source/owner, native links")

    again = admin.api("preview", payload)
    repeat = admin.api("apply", {**apply_payload, "token": again["token"]})
    assert [r["state"] for r in repeat["rows"][:5]] == ["已导入"] * 5 and counts() == (2, 3, 4)
    print("PASS repeated import no additional enterprise/contact/Lead")

    new_rows = [rows[0][:5] + ["明确复用联系人后的新需求"]]
    disambiguate = {**payload, "csv_text": csv_text(new_rows)}
    candidate = admin.api("preview", disambiguate)
    row = candidate["rows"][0]
    assert row["organizations"] and row["contacts"] and row["state"] == "待消歧"
    blocked = admin.api("apply", {**disambiguate, "token": candidate["token"], "confirm": True})
    assert blocked["rows"][0]["state"] == "失败" and counts() == (2, 3, 4)
    chosen = {str(row["line"]): {"organization": org["name"], "contact": contact["name"]}}
    applied = admin.api("apply", {**disambiguate, "token": candidate["token"], "confirm": True, "choices": chosen})
    assert applied["rows"][0]["state"] == "成功" and counts() == (2, 3, 5)
    print("PASS candidate requires explicit enterprise/contact selection, no implicit merge")

    race_rows = [["R", prefix + "并发人员", prefix + "并发企业", "微信 M7-race", "并发产品", "并发需求"]]
    race_payload = {**payload, "csv_text": csv_text(race_rows)}
    sessions = [Session(), Session()]
    for session in sessions:
        session.login(values)
    previews = [s.api("preview", race_payload) for s in sessions]
    barrier = threading.Barrier(2)

    def run(index):
        barrier.wait(timeout=15)
        return sessions[index].api("apply", {**race_payload, "token": previews[index]["token"], "confirm": True})

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, (0, 1)))
    assert sorted(r["rows"][0]["state"] for r in results) == sorted(["成功", "已导入"])
    assert counts() == (3, 4, 6), "Concurrent import left duplicate/orphan"
    print("PASS simultaneous real HTTP sessions: one success, one idempotent skip, no duplicates/orphans")
    print("Retained synthetic prefix: " + prefix)
    print("NOT covered: non-manager real-user denial, browser visual/upload/download interaction, backup restoration")


def main():
    parser = argparse.ArgumentParser(description="Explicit synthetic HTTP verification; creates retained M7 records, never deletes")
    parser.add_argument("--runtime-dir", required=True, help="Existing authorized deploy directory; credentials used internally, never printed")
    parser.add_argument("--prefix", required=True, help="Unique M7-prefixed synthetic marker")
    parser.add_argument("--confirm-synthetic-write", action="store_true")
    args = parser.parse_args()
    if not args.confirm_synthetic_write or not re.fullmatch(r"M7[A-Za-z0-9-]{4,35}", args.prefix):
        parser.error("Requires explicit synthetic write confirmation and a unique M7 alphanumeric/hyphen prefix")
    verify(args.runtime_dir, args.prefix)


if __name__ == "__main__":
    main()

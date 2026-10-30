#!/usr/bin/env python3
"""Run M6-owned negative access checks against the deployed M7 import app."""

import argparse
import csv
import http.cookiejar
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.request

try:
    from tools.access.m6_team_access import BASE_URL, CONTAINER, DISTRO, Checks, Session, USER_A
except ModuleNotFoundError:
    try:
        from m6_team_access import BASE_URL, CONTAINER, DISTRO, Checks, Session, USER_A
    except ModuleNotFoundError:
        BASE_URL = "http://127.0.0.1:8088"
        CONTAINER = "crm-mvp-v15-backend-1"
        DISTRO = "Ubuntu-24.04"
        USER_A = "m6-a@example.invalid"
        Checks = Session = None

SALES_MANAGER = "m6-sales-manager@example.invalid"
SYSTEM_MANAGER = "m6-system-manager@example.invalid"
SOURCE = "M6-M7-NEGATIVE.csv"
PERSON = "M6-M7-NEGATIVE-PERSON"
COLUMNS = ["序号", "姓名", "公司名称", "联系方式", "公司产品、服务", "需要的产品、服务"]


def input_csv():
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(COLUMNS)
    writer.writerow(["M6", PERSON, "M6-M7-NEGATIVE-ORG", "微信 M6-negative", "M6产品", "M6需求"])
    return output.getvalue()


def container_action(action, enabled=None, role=None):
    import frappe

    frappe.init(site="crm.localhost", sites_path=".")
    frappe.connect()
    try:
        frappe.set_user("Administrator")
        if action in ("set-enabled", "set-role"):
            user = frappe.get_doc("User", SYSTEM_MANAGER)
            if action == "set-enabled":
                user.enabled = int(enabled)
            else:
                if len(user.roles) != 1:
                    raise RuntimeError("M6 System Manager fixture must have exactly one role row")
                user.roles[0].role = role
            user.save(ignore_permissions=True)
            frappe.db.commit()
            return
        passwords = {}
        for email, role in ((USER_A, "Sales User"), (SALES_MANAGER, "Sales Manager"), (SYSTEM_MANAGER, "System Manager")):
            password = __import__("secrets").token_urlsafe(32)
            passwords[email] = password
            user = frappe.get_doc("User", email) if frappe.db.exists("User", email) else frappe.get_doc({"doctype": "User", "email": email})
            user.update(
                {
                    "enabled": 1,
                    "first_name": email.split("@")[0],
                    "last_name": "M6 Synthetic",
                    "user_type": "System User",
                    "send_welcome_email": 0,
                    "new_password": password,
                }
            )
            user.flags.no_welcome_mail = True
            roles = {row.role for row in user.roles}
            if roles - {role}:
                raise RuntimeError(f"M6 user {email} has an unexpected role")
            if role not in roles:
                user.append("roles", {"role": role})
            user.save(ignore_permissions=True)
        frappe.db.commit()
        print("M6_M7_CONFIG_JSON:" + json.dumps({"passwords": passwords}))
    finally:
        frappe.destroy()


def run_container(action="configure", enabled=None, role=None):
    source = Path(__file__).read_text(encoding="utf-8")
    prefix = ["wsl.exe", "-d", DISTRO, "--exec"] if os.name == "nt" else []
    command = prefix + [
        "docker", "exec", "-i", "-w", "/home/frappe/frappe-bench/sites", CONTAINER,
        "../env/bin/python", "-", "--container-action", action,
    ]
    if enabled is not None:
        command += ["--enabled", str(int(enabled))]
    if role is not None:
        command += ["--role", role]
    completed = subprocess.run(
        command, input=source, text=True, encoding="utf-8", capture_output=True,
        timeout=180, check=False,
    )
    if completed.returncode:
        error_types = [
            line.removeprefix("M6_M7_ERROR:")
            for line in completed.stderr.splitlines()
            if line.startswith("M6_M7_ERROR:")
        ]
        detail = f" ({error_types[-1]})" if error_types else ""
        raise RuntimeError(f"M6/M7 fixture configuration failed{detail}")
    if action != "configure":
        return None
    marker = "M6_M7_CONFIG_JSON:"
    lines = [line for line in completed.stdout.splitlines() if line.startswith(marker)]
    if len(lines) != 1:
        raise RuntimeError("M6/M7 configuration returned no credential envelope")
    return json.loads(lines[0][len(marker):])


def payload_with(token=None):
    payload = {"csv_text": input_csv(), "source": SOURCE, "shared_consent": True}
    if token is not None:
        payload.update({"token": token, "confirm": True, "choices": {}})
    return payload


def assert_safe_denial(response, allowed=(403,)):
    assert response.status in allowed, f"expected {allowed}, got {response.status}"
    text = response.text().lower()
    for marker in (
        "traceback", "apps/", "debug", "organizations", "contacts", "custom_resource",
        "m6-m7-negative-org", "site_config", "admin_password", "db_password",
    ):
        assert marker not in text, f"denial response contains {marker}"
    assert not re.search(r'file ".+?", line \d+', text), "denial response contains a source location"
    try:
        payload = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = {}
    if isinstance(payload, dict):
        assert "exc" not in payload and "exception" not in payload
        if "exc_type" in payload:
            assert payload["exc_type"] in ("ValidationError", "PermissionError", "AuthenticationError")


def validate(config):
    checks = Checks()
    sessions = {}

    def login(email):
        sessions[email] = Session(BASE_URL, email, config["passwords"][email])

    for email in (USER_A, SALES_MANAGER, SYSTEM_MANAGER):
        checks.run(f"real session {email}", lambda email=email: login(email))
    if len(sessions) != 3:
        return checks, None, None
    ordinary = sessions[USER_A]
    manager = sessions[SALES_MANAGER]
    system = sessions[SYSTEM_MANAGER]
    guest = Session.__new__(Session)
    guest.base_url = BASE_URL
    guest.email = "Guest"
    guest.csrf_token = None
    guest.cookies = http.cookiejar.CookieJar()
    guest.opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(guest.cookies)
    )

    def system_page():
        response = system.request("GET", "/resource-import")
        assert response.status == 200 and "六列资源导入" in response.text()

    def denied_pages():
        for session in (ordinary, manager):
            assert_safe_denial(session.request("GET", "/resource-import"))

    def anonymous_page():
        response = guest.request("GET", "/resource-import")
        assert response.status in (200, 403)
        text = response.text().lower()
        assert "login" in text and "csrf-token" not in text
        for marker in ("traceback", "organizations", "contacts", "custom_resource"):
            assert marker not in text

    token_holder = {}

    def system_preview():
        response = system.request(
            "POST", "/api/method/resource_import.api.preview", payload=payload_with()
        )
        assert response.status == 200, f"preview status {response.status}"
        message = response.json().get("message", {})
        token = message.get("token")
        assert isinstance(token, str) and len(token) == 64
        token_holder["token"] = token

    def denied_preview():
        for session in (ordinary, manager):
            response = session.request(
                "POST", "/api/method/resource_import.api.preview", payload=payload_with()
            )
            assert_safe_denial(response)
        assert_safe_denial(
            guest.request(
                "POST", "/api/method/resource_import.api.preview", payload=payload_with()
            ),
            allowed=(401, 403),
        )

    checks.run("M6 System Manager can open the import page", system_page)
    checks.run("Sales User and Sales Manager pages are safely denied", denied_pages)
    checks.run("anonymous page redirects without import data or CSRF", anonymous_page)
    checks.run("M6 System Manager preview issues a session-bound receipt", system_preview)
    checks.run("Sales User, Sales Manager and anonymous preview are safely denied", denied_preview)
    if "token" not in token_holder:
        return checks, sessions, token_holder.get("token")
    apply_payload = payload_with(token_holder["token"])

    def cross_user_apply():
        for session in (ordinary, manager):
            response = session.request(
                "POST", "/api/method/resource_import.api.apply", payload=apply_payload
            )
            assert_safe_denial(response)
        assert_safe_denial(
            guest.request(
                "POST", "/api/method/resource_import.api.apply", payload=apply_payload
            ),
            allowed=(401, 403),
        )

    def no_business_write():
        response = system.resource(
            "CRM Lead",
            fields=["name"],
            filters=[["CRM Lead", "first_name", "=", PERSON]],
        )
        assert response.status == 200 and response.json().get("data") == []

    checks.run("valid receipt cannot bypass cross-user or anonymous apply denial", cross_user_apply)
    checks.run("preview and denied apply created no M6/M7 business Lead", no_business_write)
    return checks, sessions, token_holder.get("token")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--container-action", choices=("configure", "set-enabled", "set-role"), help=argparse.SUPPRESS
    )
    parser.add_argument("--enabled", type=int, choices=(0, 1), help=argparse.SUPPRESS)
    parser.add_argument("--role", choices=("Sales User", "System Manager"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.container_action:
        try:
            container_action(args.container_action, args.enabled, args.role)
        except Exception as error:
            print(f"M6_M7_ERROR:{type(error).__name__}", file=sys.stderr)
            raise SystemExit(2) from None
        return
    config = run_container()
    checks, sessions, receipt = validate(config)
    if sessions and SYSTEM_MANAGER in sessions and receipt:
        system = sessions[SYSTEM_MANAGER]
        try:
            run_container("set-role", role="Sales User")

            def role_revoked_receipt():
                response = system.request(
                    "POST",
                    "/api/method/resource_import.api.apply",
                    payload=payload_with(receipt),
                )
                assert_safe_denial(response)

            checks.run("role revocation denies a valid receipt without a traceback", role_revoked_receipt)
        finally:
            run_container("set-role", role="System Manager")
        try:
            run_container("set-enabled", enabled=False)

            def revoked_receipt():
                response = system.request(
                    "POST",
                    "/api/method/resource_import.api.apply",
                    payload=payload_with(receipt),
                )
                assert_safe_denial(response, allowed=(401, 403, 417))

            checks.run("disabled account cannot apply with a valid receipt", revoked_receipt)
        finally:
            run_container("set-enabled", enabled=True)
    print(f"SUMMARY M7-negative pass={len(checks.passes)} fail={len(checks.failures)}")
    if checks.failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

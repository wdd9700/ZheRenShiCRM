import json
import os
import sys

import frappe


EXPECTED_APPS = ("frappe", "crm", "resource_import", "team_access", "team_schedule")
INSTALL_ORDER = ("resource_import", "team_access", "team_schedule")
SCHEDULE_TABLES = (
    "Team Schedule",
    "Team Schedule Member",
    "Team Schedule Busy Grant",
    "Team Schedule Source",
    "Team Schedule Source Item",
    "Team Schedule Request",
    "Team Schedule Audit",
)
INDEX_CONTRACT = {
    "Team Schedule Member": ("ts_member_user", ("parent", "user"), 0),
    "Team Schedule Busy Grant": ("ts_busy_pair", ("subject_user", "viewer_user"), 0),
    "Team Schedule Source Item": ("ts_source_uid", ("source", "uid_key"), 0),
    "Team Schedule Request": ("ts_request_owner", ("owner", "request_id"), 0),
    "Team Schedule": ("ts_start_name", ("start_utc", "name"), 1),
}


def verify_schedule_schema():
    for doctype in SCHEDULE_TABLES:
        if frappe.get_meta(doctype).module != "Team Schedule" or not frappe.db.table_exists(doctype):
            raise RuntimeError("team_schedule metadata or schema table is missing")
    if frappe.db.exists("DocShare", {"share_doctype": ["in", SCHEDULE_TABLES]}):
        raise RuntimeError("team_schedule DocShare rows are forbidden")
    for doctype in SCHEDULE_TABLES:
        if doctype not in INDEX_CONTRACT:
            continue
        index_name, expected_columns, expected_non_unique = INDEX_CONTRACT[doctype]
        rows = frappe.db.sql("SHOW INDEX FROM `tab" + doctype + "`", as_dict=True)
        matching = sorted((row for row in rows if row["Key_name"] == index_name), key=lambda row: row["Seq_in_index"])
        columns = [row["Column_name"] for row in matching]
        if columns != list(expected_columns) or any(int(row["Non_unique"]) != expected_non_unique for row in matching):
            raise RuntimeError("team_schedule index contract mismatch")
    for field in ("title", "description"):
        if frappe.db.get_column_type("Team Schedule", field) != "longtext":
            raise RuntimeError("team_schedule literal text schema mismatch")


def installed_apps():
    apps = frappe.get_installed_apps()
    if not isinstance(apps, list) or len(apps) != len(set(apps)) or any(not isinstance(app, str) for app in apps):
        raise RuntimeError("invalid installed apps result")
    return apps


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("missing", "verify", "maintenance"):
        raise RuntimeError("expected missing, verify or maintenance mode")
    mode = sys.argv[1]
    os.chdir("/home/frappe/frappe-bench/sites")
    frappe.init(site="crm.localhost", sites_path=".")
    frappe.connect()
    try:
        if mode == "maintenance":
            value = frappe.conf.get("maintenance_mode", 0)
            if value in (True, 1, "1"):
                enabled = True
            elif value in (False, 0, "0", None):
                enabled = False
            else:
                raise RuntimeError("unrecognized maintenance mode")
            print(json.dumps({"maintenance_mode": enabled}, separators=(",", ":")))
            return
        apps = installed_apps()
        if mode == "missing":
            if not {"frappe", "crm"}.issubset(apps) or not set(apps).issubset(EXPECTED_APPS):
                raise RuntimeError("unexpected installed app baseline")
            print(json.dumps({"missing": [app for app in INSTALL_ORDER if app not in apps]}, separators=(",", ":")))
            return
        if set(apps) != set(EXPECTED_APPS):
            raise RuntimeError("installed app set does not match the approved five apps")
        verify_schedule_schema()
        print("PASS: exact five installed apps and team_schedule schema verified")
    finally:
        frappe.destroy()


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError) as error:
        raise SystemExit("ERROR: candidate app/schema verification failed; preserve maintenance state: " + type(error).__name__)

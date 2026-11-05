import json
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


def installed_apps():
    apps = frappe.get_installed_apps()
    if not isinstance(apps, list) or len(apps) != len(set(apps)) or any(not isinstance(app, str) for app in apps):
        raise RuntimeError("invalid installed apps result")
    return apps


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("missing", "verify"):
        raise RuntimeError("expected missing or verify mode")
    mode = sys.argv[1]
    frappe.init(site="crm.localhost", sites_path="/home/frappe/frappe-bench/sites")
    frappe.connect()
    try:
        apps = installed_apps()
        if mode == "missing":
            if not {"frappe", "crm"}.issubset(apps) or not set(apps).issubset(EXPECTED_APPS):
                raise RuntimeError("unexpected installed app baseline")
            print(json.dumps({"missing": [app for app in INSTALL_ORDER if app not in apps]}, separators=(",", ":")))
            return
        if set(apps) != set(EXPECTED_APPS):
            raise RuntimeError("installed app set does not match the approved five apps")
        missing_tables = [doctype for doctype in SCHEDULE_TABLES if not frappe.db.table_exists(doctype)]
        if missing_tables:
            raise RuntimeError("team_schedule schema tables are missing")
        for field in ("title", "description"):
            if frappe.db.get_column_type("Team Schedule", field) != "longtext":
                raise RuntimeError("team_schedule literal text schema mismatch")
        print("PASS: exact five installed apps and team_schedule schema verified")
    finally:
        frappe.destroy()


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError) as error:
        raise SystemExit("ERROR: candidate app/schema verification failed; preserve maintenance state: " + type(error).__name__)

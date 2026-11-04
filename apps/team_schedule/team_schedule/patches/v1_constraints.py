import frappe

from team_schedule.permissions import assert_no_shares


def check_shares():
    if frappe.db.table_exists("DocShare"):
        assert_no_shares()


def execute():
    check_shares()
    for doctype, fields, name in (
        ("Team Schedule Member", ["parent", "user"], "ts_member_user"),
        ("Team Schedule Busy Grant", ["subject_user", "viewer_user"], "ts_busy_pair"),
        ("Team Schedule Source Item", ["source", "uid_key"], "ts_source_uid"),
        ("Team Schedule Request", ["owner", "request_id"], "ts_request_owner"),
    ):
        frappe.db.add_unique(doctype, fields, constraint_name=name)
    frappe.db.add_index("Team Schedule", ["start_utc", "name"], "ts_start_name")

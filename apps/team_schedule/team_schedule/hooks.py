app_name = "team_schedule"
app_title = "Team Schedule"
app_publisher = "CRM team"
app_description = "Private minute-level team scheduling"
app_email = "noreply@example.invalid"
app_license = "AGPL-3.0-or-later"
required_apps = ["frappe"]

before_migrate = "team_schedule.patches.v1_constraints.check_shares"
after_install = "team_schedule.patches.v1_constraints.execute"
after_migrate = "team_schedule.patches.v1_constraints.execute"

has_permission = {name: "team_schedule.permissions.has_permission" for name in (
    "Team Schedule", "Team Schedule Member", "Team Schedule Busy Grant",
    "Team Schedule Source", "Team Schedule Source Item", "Team Schedule Request", "Team Schedule Audit",
)}
permission_query_conditions = {
    "Team Schedule": "team_schedule.permissions.query_conditions",
    "Team Schedule Member": "team_schedule.permissions.member_query",
    "Team Schedule Busy Grant": "team_schedule.permissions.grant_query",
    "Team Schedule Source": "team_schedule.permissions.source_query",
    "Team Schedule Source Item": "team_schedule.permissions.source_item_query",
    "Team Schedule Request": "team_schedule.permissions.request_query",
    "Team Schedule Audit": "team_schedule.permissions.request_query",
}
doc_events = {
    "DocShare": {"before_insert": "team_schedule.permissions.reject_share", "before_validate": "team_schedule.permissions.reject_share", "validate": "team_schedule.permissions.reject_share"},
    **{name: {"before_insert": "team_schedule.permissions.reject_sidecar", "before_validate": "team_schedule.permissions.reject_sidecar"} for name in ("File", "Version", "Comment", "Communication", "ToDo", "Notification Log", "Report")},
}

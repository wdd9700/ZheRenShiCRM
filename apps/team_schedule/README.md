# Team Schedule

Private minute-level scheduling app for Frappe 15.125.0. This is an implementation candidate, not a deployment or completed L3 acceptance. The fixed implementation contract is `docs/SCHEDULING_L3.md` at contract commit `3e8aea6fd6222ae97b65fff720370a84827cafb0` (M23).

## Installation and verification

Package and app name: `team_schedule`; Python >=3.10. The app reuses Framework's `pytz`; it does not install dependencies or require a Node build. Install only on a new isolated synthetic site through the integration owner. Do not install on an existing source/recovery/production site for tests.

After standard bench app registration and editable package installation:

```sh
bench --site ISOLATED_SITE install-app team_schedule
bench --site ISOLATED_SITE migrate
bench --site ISOLATED_SITE migrate
bench --site ISOLATED_SITE set-config allow_tests true
bench --site ISOLATED_SITE run-tests --module team_schedule.tests.test_model_time
bench --site ISOLATED_SITE run-tests --module team_schedule.tests.test_model_service
bench --site ISOLATED_SITE run-tests --module team_schedule.tests.test_permissions_core
```

The service and permission tests use Framework's `FrappeTestCase`, real ORM/DB permissions and two newly created synthetic System Users with the existing CRM `Sales User` role. Thus the test candidate needs CRM installed, although the app itself depends only on Framework. No passwords or login sessions are printed. Welcome email is disabled. No scheduler is needed; leave it disabled. No external service calls, invitations or reminders are implemented. Test teardown rolls back each test's records; only isolated test data may be written. HTTP login/CSRF, concurrent transaction races, both CSV routes, search/docinfo/realtime and recovery still need separate integration evidence; direct Python calls are not HTTP acceptance.

Pure time tests may also run without Frappe:

```sh
PYTHONPATH=apps/team_schedule python -B -m unittest team_schedule.tests.test_model_time
```

## Data and access

Six app-owned DocTypes use the normal `team_schedule/team_schedule/doctype` module path. UTC instants are strict fixed-width minute strings, never site-timezone Datetime fields. Sources and cancellation tombstones are retained. Source UID is case-sensitive: `uid_key` is SHA256 of exact UTF-8 UID and `(source,uid_key)` is unique, avoiding MariaDB case-insensitive collation changing identity. Creation requests are unique per `(owner,request_id)` and store only the canonical payload digest and target ID.

App writes use Python-only ContextVar scope, live enabled-user/ACL checks and locked revision comparison. Standard ORM writes, deletions and app DocShare creation/update are rejected even when client flags are forged. Migration refuses pre-existing app DocShare rows; it never deletes them. Normal document changes do not create Version snapshots or realtime update broadcasts. Audit entries contain only actor/action/ID/revision plus logger time, not body or UID. No system timezone is changed.

All app RPC endpoints are POST only at `team_schedule.api.*`, use the existing Frappe session/CSRF machinery, reject token Authorization and unknown parameters, and return a real HTTP `Cache-Control: no-store` response. The response envelope is `{message: ...}`. `export_owned` returns a private attachment directly, never a File record.

## Internal interfaces for availability and ICS

- `timeutils`: `ScheduleError(code,status=400,details=None)`, `parse_utc`, `encode_utc`, `validate_window`, `validate_timezone`, `resolve_local`.
- `permissions`: `current_user`, `can_read`, `can_edit`, `is_maintenance`, `internal_write`, `assert_no_shares`.
- `service`: `detail`, `locked_schedule(name,expected_revision=None,mode='read')`, `create_schedule`, `mutate_schedule`, `assert_busy_access`.
- ICS: `create_source(label)`, `get_source(source_id,lock=False)`, `lock_source_item(source_id,uid)`, `save_source_item(source_id,uid,values)`, `save_import_schedule(source_id,payload,schedule_name=None,expected_revision=None)`.

`lock_source_item` first locks the source parent row, serializing absent as well as present UID mappings until commit. Import schedule updates preserve members. These interfaces do not commit: ICS must manage per-item savepoints, exact receipt-state checks, duplicate zero-write semantics and result classification. Frappe savepoints do not roll back Python after-commit callback registrations; callers must preserve/reset the callback queue when reverting an item. No HTTP endpoint exposes the internal write scope.

## Current verification boundary

Do not treat schema/import/static checks as completed permission acceptance. Administrator/System Manager maintenance is not ordinary-team acceptance. Framework's maintenance-role export shortcuts and standard entry points must be tested on the pinned runtime before opening this candidate to data. Backups/restores require a compatible app-bearing image. Disable new writes/navigation for rollback; do not uninstall or drop these schemas or security hooks.

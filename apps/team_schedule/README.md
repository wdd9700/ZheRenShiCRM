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
bench --site ISOLATED_SITE run-tests --module team_schedule.tests.test_model_transactions
bench --site ISOLATED_SITE run-tests --module team_schedule.tests.test_permissions_busy_locks
bench --site ISOLATED_SITE run-tests --module team_schedule.tests.test_permissions_identity
bench --site ISOLATED_SITE run-tests --module team_schedule.tests.test_model_storage
```

The storage module has two tests, uses four synthetic Users through `ScheduleCase`, and rolls back all its records (no explicit commit). It checks fresh DB literal round-trips, owner-only JSON/standard reads, the pinned server print macro's escaping, and pure-text required/length checks through create/update/import/controller paths. It does not send email or prove browser rendering.

The service and permission tests use Framework's `FrappeTestCase`, real ORM/DB permissions and two newly created synthetic System Users with the existing CRM `Sales User` role. Thus the test candidate needs CRM installed, although the app itself depends only on Framework. No passwords or login sessions are printed. Welcome email is disabled. No scheduler is needed; leave it disabled. No external service calls, invitations or reminders are implemented. Service/core-permission tests roll back their records. Transaction and busy-lock modules deliberately commit synthetic fixtures for two-connection checks. The identity module's two tests commit five new synthetic Users in total (four System Users and one separately created Website User) plus schedules; normal Administrator `User.save()` removes/restores desk roles for the downgrade/restore test and verifies persisted user_type. Those fixtures remain on the isolated site, so API errors can exercise real rollback without destroying the scenario. No existing data is deleted. These are direct API/ORM tests, not a claim of browser administration or fresh HTTP Website login acceptance. HTTP login/CSRF, truly simultaneous transaction races, both CSV routes, search/docinfo/realtime and recovery still need separate integration evidence; direct Python calls are not HTTP acceptance.

Pure time tests may also run without Frappe:

```sh
PYTHONPATH=apps/team_schedule python -B -m unittest team_schedule.tests.test_model_time
```

## Data and access

Seven app-owned DocTypes (including the tower-approved metadata-only internal Audit) use the normal `team_schedule/team_schedule/doctype` module path. UTC instants are strict fixed-width minute strings, never site-timezone Datetime fields. Sources and cancellation tombstones are retained. Source UID is case-sensitive: `uid_key` is SHA256 of exact UTF-8 UID and `(source,uid_key)` is unique, avoiding MariaDB case-insensitive collation changing identity. Creation requests are unique per `(owner,request_id)` and store only the canonical payload digest and target ID.

All business actors and app standard reads require an enabled `System User`. This is the R3 explicit team-membership boundary, not a regression caused by the shared-lock change. `Website User` accounts cannot create, read, list, edit, cancel, participate or export even when prior ownership or member ACL remains. Identity changes never delete schedules, member rows or grants; restoring an enabled System User restores access according to the retained ACL. App-local identity checks use current locking reads: business actors retain their selected exclusive/shared mode, while standard read/query/child checks take a shared User lock before owner/member/maintenance branches. Administrator/System Manager maintenance exceptions remain only for eligible identities and the explicitly supported operations; internal Request/Audit and standard write restrictions are unchanged. No global request or permission interception is installed.

App writes use Python-only ContextVar scope, live enabled-System-User/ACL checks and locked revision comparison. Standard ORM writes, deletions and app DocShare creation/update are rejected even when client flags are forged. Migration refuses pre-existing app DocShare rows; it never deletes them. Normal document changes do not create Version snapshots or realtime update broadcasts. Audit rows contain only actor/action/target type/ID/revision plus Framework creation time, not body or UID, and roll back with the business transaction. No system timezone is changed.

Schedule `title` and `description` are literal plain text, stored in native `Code` fields with no language/options. This is a field-level model choice, not an `ignore_xss_filter` flag or global sanitizer override: Framework's ordinary Data/Small Text HTML sanitization would otherwise change imported literal text. Every permitted create/update/import and internal document save still reaches the controller's `validate_schedule`: title must contain non-whitespace text and be at most 140 characters, description at most 4000. Title's metadata `reqd` is intentionally absent because Framework's mandatory check strips HTML before deciding emptiness, incorrectly rejecting a literal tag-only title. Standard writes remain forbidden.

Use normal `bench migrate` to sync the two existing columns to `longtext` (widening varchar/text, retaining field names and existing values); no destructive patch, rewriting old content or data/ACL deletion is needed. Do not roll back by narrowing columns or uninstalling. The pinned Framework's Code formatter escapes text in Desk, its default server print macro uses `|e` in a pre element, and ordinary print/email/export permissions and sidecar rejection are unchanged. App detail and owned attachment export are JSON, not HTML; clients must use textContent/input values, never HTML/Markdown execution or URL fetching for these fields. Custom privileged templates are not an authorized unescaped output route. Actual browser rendering and all standard bypasses still require integration evidence.

All app RPC endpoints are POST only at `team_schedule.api.*`, use the existing Frappe session/CSRF machinery, reject token Authorization and unknown parameters, and return a real HTTP `Cache-Control: no-store` response. The response envelope is `{message: ...}`. `export_owned` returns a private attachment directly, never a File record.

## Internal interfaces for availability and ICS

- `timeutils`: `ScheduleError(code,status=400,details=None)`, `parse_utc`, `encode_utc`, `validate_window`, `validate_timezone`, `resolve_local`.
- `permissions`: `current_user(*,lock_mode='exclusive')`, `can_read`, `can_edit`, `is_maintenance`, `internal_write`, `assert_no_shares`.
- `service`: `detail`, `locked_schedule(name,expected_revision=None,mode='read')`, `create_schedule`, `mutate_schedule`, `assert_busy_access(users)`, `confirm_busy_access(actor,users)`.
- ICS: `create_source(label)`, `get_source(source_id,lock=False)`, `lock_source_item(source_id,uid)`, `save_source_item(source_id,uid,values)`, `save_import_schedule(source_id,payload,schedule_name=None,expected_revision=None)`.

Busy query alone selects `parameters(...,identity_lock='shared')`; the internal enum accepts only `exclusive` and `shared`, and is not an HTTP parameter. All other endpoints and write services retain the default exclusive actor lock. Busy precheck takes only the actor's shared current-read lock; other User/grant checks there are ordinary snapshot reads. After scanning, callers must run `confirm_busy_access` before exposing results or scan-limit errors. It locks every deduplicated subject User (including actor) in sorted order with `LOCK IN SHARE MODE`, checks enabled/System User, then locks each required subject/viewer grant in sorted subject order. Invalid final identity, subject or grant produces only 403 `FORBIDDEN`. No helper commits. Shared actor locks avoid the reverse-subject reader X/S cycle; this is not a claim of global deadlock freedom. Lock failures reach the endpoint's generic 500 error and rollback path without data.

Locks last until the request transaction ends. On the pinned Framework, successful HTTP requests commit through `application`/`sync_database` after Response construction and before WSGI sends it; the endpoint wrapper rolls back errors, not successful calls. A direct test that already holds an exclusive actor lock from fixture writes is not a fresh shared-query transaction. The busy-lock module commits synthetic users/grants for its two-connection tests; those records remain only on the isolated site. Its overlapping reverse-subject transactions and bounded lock-timeout checks are not a substitute for simultaneous HTTP race acceptance.

`lock_source_item` first locks the source parent row, serializing absent as well as present UID mappings until commit. Import schedule updates preserve members. These interfaces do not commit: ICS must manage per-item savepoints, exact receipt-state checks, duplicate zero-write semantics and result classification. Metadata audit inserts occur in the same database transaction and naturally roll back with each item savepoint; callers do not manipulate Framework callback queues. No HTTP endpoint exposes the internal write scope.

## Current verification boundary

Do not treat schema/import/static checks as completed permission acceptance. Administrator/System Manager maintenance is not ordinary-team acceptance. Framework's maintenance-role export shortcuts and standard entry points must be tested on the pinned runtime before opening this candidate to data. Backups/restores require a compatible app-bearing image. Disable new writes/navigation for rollback; do not uninstall or drop these schemas or security hooks.

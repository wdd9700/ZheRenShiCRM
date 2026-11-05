# Team Schedule

Private minute-level scheduling app for Frappe 15.125.0. This is an implementation candidate, not a deployment or completed L3 acceptance. The fixed implementation contract is `docs/SCHEDULING_L3.md` at contract commit `3e8aea6fd6222ae97b65fff720370a84827cafb0` (M23).

## Installation and verification

Package and app name: `team_schedule`; Python >=3.10. The app reuses Framework's `pytz`; it does not install dependencies or require a Node build. Install only on a new isolated synthetic site through the integration owner. Do not install on an existing source/recovery/production site for tests.

After standard bench app registration and editable package installation:

```sh
bench --site ISOLATED_SITE install-app team_schedule
bench --site ISOLATED_SITE set-config allow_tests true
bench --site ISOLATED_SITE run-tests --module team_schedule.tests.test_model_patch_manifest
bench --site ISOLATED_SITE migrate
bench --site ISOLATED_SITE migrate
bench --site ISOLATED_SITE run-tests --module team_schedule.tests.test_model_patch_manifest
bench --site ISOLATED_SITE run-tests --module team_schedule.tests.test_model_time
bench --site ISOLATED_SITE run-tests --module team_schedule.tests.test_model_service
bench --site ISOLATED_SITE run-tests --module team_schedule.tests.test_permissions_core
bench --site ISOLATED_SITE run-tests --module team_schedule.tests.test_model_transactions
bench --site ISOLATED_SITE run-tests --module team_schedule.tests.test_permissions_busy_locks
bench --site ISOLATED_SITE run-tests --module team_schedule.tests.test_permissions_identity
bench --site ISOLATED_SITE run-tests --module team_schedule.tests.test_model_storage
bench --site ISOLATED_SITE run-tests --module team_schedule.tests.test_permissions_print
```

The storage module has two tests, uses four synthetic Users through `ScheduleCase`, and rolls back all its records (no explicit commit). It checks fresh DB literal round-trips, owner-only JSON/standard reads, the pinned server print macro's escaping, and pure-text required/length checks through create/update/import/controller paths. It does not send email or prove browser rendering.

The service and permission tests use Framework's `FrappeTestCase`, real ORM/DB permissions and two newly created synthetic System Users with the existing CRM `Sales User` role. Thus the test candidate needs CRM installed, although the app itself depends only on Framework. No passwords or login sessions are printed. Welcome email is disabled. No scheduler is needed; leave it disabled. No external service calls, invitations or reminders are implemented. Service/core-permission tests roll back their records. Transaction and busy-lock modules deliberately commit synthetic fixtures for two-connection checks. The identity module's two tests commit five new synthetic Users in total (four System Users and one separately created Website User) plus schedules; normal Administrator `User.save()` removes/restores desk roles for the downgrade/restore test and verifies persisted user_type. Those fixtures remain on the isolated site, so API errors can exercise real rollback without destroying the scenario. No existing data is deleted. These are direct API/ORM tests, not a claim of browser administration or fresh HTTP Website login acceptance. HTTP login/CSRF, truly simultaneous transaction races, both CSV routes, search/docinfo/realtime and recovery still need separate integration evidence; direct Python calls are not HTTP acceptance.

Pure time tests may also run without Frappe:

```sh
PYTHONPATH=apps/team_schedule python -B -m unittest team_schedule.tests.test_model_time
```

## Fresh-install discovery and partial-install continuation (M32)

On pinned [Frappe 15.125.0](https://github.com/frappe/frappe/blob/v15.125.0/frappe/installer.py#L273-L355), `install_app` runs `sync_for` before registering/committing the app, marking its patches completed, and calling `after_install`. Moving constraints to a later hook or skipping missing tables would hide an incomplete install, not fix it. The seven DocType JSONs, controllers, module name and package paths are valid; the failed candidate's existing 128-file build guard also checked those JSONs and `modules.txt` in the image.

The discovery gap is in [model/sync.py](https://github.com/frappe/frappe/blob/v15.125.0/frappe/model/sync.py): it iterates only `frappe.local.app_modules.get(app_name) or []`, silently importing nothing if a previously cached four-app module map omits the fifth app. Pinned `frappe.clear_cache()` clears site cache entries but does not rebuild the separate `local.app_modules`/`local.module_app` objects loaded at initialization. `before_install` now invalidates only the site-scoped `app_modules` key and calls the official `setup_module_map(include_all_apps=True)` before standard synchronization. No app schema is manually created, no global Redis flush is used, and `after_install`, post-model-sync patch and `after_migrate` still run all mandatory constraints and share checks unchanged.

M9's retained `m9-upgrade-22d94b0-r6/actual-five-app-upgrade.log` records `Installing team_schedule` followed by `after_install` failing on missing `tabTeam Schedule Member`, with no DocType progress output. Its exact failed process's module map and postfailure database snapshot were not captured. The stale-map mechanism is reproduced from pinned source and matches that log; it is not a claim that the failed process's memory or database was inspected. The Windows worker has no Frappe/MariaDB runtime and does not deploy, restore or rebuild images.

The existing `test_model_patch_manifest` module now checks standard module/JSON discovery, reproduces the stale-map zero-import case against Framework's actual `sync_for`, verifies all seven tables/metadata and the exact index columns/uniqueness **before** two constraint retries, then checks them again. Run it immediately after a fresh standard install, before any migration could mask an install defect, and again after the two standard migrations above. The discovery test mocks only import/commit/cache effects; it does not itself create tables. Pure contract/time/availability/parser/UI regression on Windows: 64 tests, 62 passed and two real-`vobject` tests skipped because that library is absent. A separate in-memory harness executed the pinned `setup_module_map` and `sync_for` functions: stale four-app discovery imported zero files; the new hook caused all seven JSONs to be discovered. These are not actual fresh-install or permission acceptance; M9 must run the real isolated-site install/migrate/schema and existing service/permission suites on the reviewed candidate.

For the preserved failed maintenance site, only M9 may execute an authorized continuation, subject to the deployment tool's state/lineage gates:

1. Keep maintenance and writer shutdown in force; retain the failed-generation metadata, locks, logs, volumes and readable with-files backup. Use a reviewed compatible image containing all five apps and this fix; do not simply restart the prior four-app image against a possibly five-app site. This README does not authorize a cross-generation deployment-tool bypass.
2. First observe actual `installed_apps`, seven DocType/table states, constraint states and app DocShare rows. The pinned installer commits registration and patch logs before the failed hook, so registration is expected to have persisted, but **the actual postfailure value remains unknown**. A failed CLI is not evidence of rollback.
3. If already registered, a normal non-force `install-app` returns "already installed" and cannot repair schema. Use the authorized standard `migrate` path: its setup clears/rebuilds module maps, standard schema sync creates missing tables, and `after_migrate` still enforces constraints even if the install already marked the patch completed. If not registered, use standard install first. Do not alter `installed_apps`/Patch Log, force-install, uninstall, drop tables, delete data/shares, restore a database, or call constraints directly before schema sync.
4. Before reopening, require seven tables/DocTypes with module `Team Schedule`; no app DocShare rows; and `SHOW INDEX` results matching the table below, ordered by `Seq_in_index`. Missing/incorrect constraints or duplicates must stop continuation, never trigger data cleanup or a skip. Repeat standard migrate and verify the same schema/constraints and retained data. Patch Log alone is insufficient evidence.

| DocType | Index name | Ordered columns | `Non_unique` |
|---|---|---|---|
| Team Schedule Member | `ts_member_user` | `parent, user` | 0 |
| Team Schedule Busy Grant | `ts_busy_pair` | `subject_user, viewer_user` | 0 |
| Team Schedule Source Item | `ts_source_uid` | `source, uid_key` | 0 |
| Team Schedule Request | `ts_request_owner` | `owner, request_id` | 0 |
| Team Schedule | `ts_start_name` | `start_utc, name` | 1 |

## Data and access

Seven app-owned DocTypes (including the tower-approved metadata-only internal Audit) use the normal `team_schedule/team_schedule/doctype` module path. UTC instants are strict fixed-width minute strings, never site-timezone Datetime fields. Sources and cancellation tombstones are retained. Source UID is case-sensitive: `uid_key` is SHA256 of exact UTF-8 UID and `(source,uid_key)` is unique, avoiding MariaDB case-insensitive collation changing identity. Creation requests are unique per `(owner,request_id)` and store only the canonical payload digest and target ID.

All business actors and app standard reads require an enabled `System User`. This is the R3 explicit team-membership boundary, not a regression caused by the shared-lock change. `Website User` accounts cannot create, read, list, edit, cancel, participate or export even when prior ownership or member ACL remains. Identity changes never delete schedules, member rows or grants; restoring an enabled System User restores access according to the retained ACL. App-local identity checks use current locking reads: business actors retain their selected exclusive/shared mode, while standard read/query/child checks take a shared User lock before owner/member/maintenance branches. Administrator/System Manager maintenance exceptions remain only for eligible identities and the explicitly supported operations; internal Request/Audit and standard write restrictions are unchanged. There is no global identity or read-permission interception. The app installs only the narrowly targeted standard-print request boundary described below.

App writes use Python-only ContextVar scope, live enabled-System-User/ACL checks and locked revision comparison. Standard ORM writes, deletions and app DocShare creation/update are rejected even when client flags are forged. Migration refuses pre-existing app DocShare rows; it never deletes them. Normal document changes do not create Version snapshots or realtime update broadcasts. Audit rows contain only actor/action/target type/ID/revision plus Framework creation time, not body or UID, and roll back with the business transaction. No system timezone is changed.

Schedule `title` and `description` are literal plain text, stored in native `Code` fields with no language/options. This is a field-level model choice, not an `ignore_xss_filter` flag or global sanitizer override: Framework's ordinary Data/Small Text HTML sanitization would otherwise change imported literal text. Every permitted create/update/import and internal document save still reaches the controller's `validate_schedule`: title must contain non-whitespace text and be at most 140 characters, description at most 4000. Title's metadata `reqd` is intentionally absent because Framework's mandatory check strips HTML before deciding emptiness, incorrectly rejecting a literal tag-only title. Standard writes remain forbidden.

Use normal `bench migrate` to sync the two existing columns to `longtext` (widening varchar/text, retaining field names and existing values); no destructive patch, rewriting old content or data/ACL deletion is needed. Do not roll back by narrowing columns or uninstalling. The pinned Framework's Code formatter escapes text in Desk, its default server print macro uses `|e` in a pre element, and ordinary print/email/export permissions and sidecar rejection are unchanged. App detail and owned attachment export are JSON, not HTML; clients must use textContent/input values, never HTML/Markdown execution or URL fetching for these fields. Custom privileged templates are not an authorized unescaped output route. Actual browser rendering and all standard bypasses still require integration evidence.

Standard app printing is explicitly forbidden, including owner, read-member and maintenance actors. Frappe 15.125.0's normal print validator accepts read OR print, so a false print-permission boolean alone is insufficient. An app `before_request` hook checks only `/printview` and seven fixed Framework print methods: HTML/style, raw commands, PDF, synchronous/asynchronous multi-PDF, server printer and WeasyPrint PDF. It checks exact structured DocTypes in `doctype` (including mixed multi-PDF dictionaries) and `doc` (including JSON), not body substrings. A mixed batch containing any app DocType is rejected as a whole before rendering or enqueueing. The check is method-independent (GET/POST), recognizes legacy `cmd` and API v1/v2 routes, and does not change JSON reads or owned export. Non-app targets pass through unchanged. All seven app DocTypes additionally reject `before_print` in the standard internal renderer, and controller print checks have no internal-write exception; the beta WeasyPrint route uses that print check. No upstream code or PDF dependency is modified. This is not a promise to control arbitrary privileged custom templates or printing a user's already-authorized JSON in their own browser; client-supplied HTML-to-PDF has no server document lookup and is not globally disabled.

The print test module contains one no-User request-shape/hook matrix and two real Framework renderer candidates (four synthetic User attempts, all rolled back). It checks owner/read-peer/Administrator denial, internal-write denial, no File/Communication/Email Queue rows from those renderer calls, JSON access preservation and a non-app User HTML positive control. The request-shape matrix is not HTTP acceptance or an asynchronous queue test. Integration must separately exercise actual HTTP print routes, mixed synchronous/asynchronous bulk before queueing, unauthorized/Website actors, and a real CRM non-app HTML positive control on the exact candidate image. A PDF-generator 500 is a failure, never a substitute for permission 403.

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

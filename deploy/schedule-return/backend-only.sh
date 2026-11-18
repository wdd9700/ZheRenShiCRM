#!/bin/bash
set -euo pipefail
umask 077

base=sha256:c2601699d018675f1e2fc87a13c7fa4963090182eccfc70a8e51ed5ccdfbe062
new=sha256:42f21f6359bd61aa4dd2a84b4ce50df96197a30688b1e0b298e5f8309d80318e
old_html=0bd3175203476a7c75fbf71e63a855e53adecf656900bb089660d8b710b496b5
new_html=cdb9e49ae2832574c231d4d9b4b0ee0b41abf6f8ed1e3b3e1c63a82f953a8f9f
project=crm-trial-c010400
runtime=/home/dev/crm-trial/deploy/remote/.runtime
tools=/home/dev/c1109-reviewed-https-64daf948/deploy/remote
stage=/home/dev/c1118-schedule-return-d4330d3
state=$runtime/site-update.state
mixed=$stage/backend-only
front=$project-frontend-1
back=$project-backend-1
html=/home/frappe/frappe-bench/apps/team_schedule/team_schedule/www/team-schedule.html
net=crm_trial_c010400_network
infra=(db redis-cache redis-queue)
apps=(frontend scheduler websocket queue-short queue-long configurator)

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
docker() { sudo -n docker "$@"; }
compose() { docker compose -p "$project" --env-file "$runtime/.env" --env-file "$runtime/image.env" -f "$tools/compose.yml" -f /etc/crm-https/compose.yml "$@"; }
trial() { CRM_TRIAL_RUNTIME_DIR="$runtime" CRM_TRIAL_DOCKER_SUDO=1 sh "$tools/trial.sh" "$@"; }
hash_is() { local actual; actual=$(sha256sum "$1") && [ "${actual%% *}" = "$2" ]; }
image_is() { [ "$(docker inspect --format '{{.Image}}' "$1")" = "$2" ]; }
html_is() { local actual; actual=$(docker exec "${2:-$back}" sha256sum "$html") && [ "${actual%% *}" = "$1" ]; }
backend_id() {
    local id
    id=$(docker inspect --format '{{.Id}}' "$back") && [[ $id =~ ^[0-9a-f]{64}$ ]] && printf '%s\n' "$id"
}
backend_matches() {
    local id=$1 image=$2 digest=$3
    [ "$(backend_id)" = "$id" ] && image_is "$id" "$image" && html_is "$digest" "$id" && [ "$(backend_id)" = "$id" ]
}
state_write() { local tmp; tmp=$(mktemp "$runtime/.s011.XXXXXXXX") && printf '%s\n' "$1" > "$tmp" && mv -T "$tmp" "$state"; }
restore_state() { local tmp; tmp=$(mktemp "$runtime/.s011.XXXXXXXX") && cp -- "$mixed/state.before" "$tmp" && mv -T "$tmp" "$state"; }
active_state() { [ -f "$state" ] && [ ! -L "$state" ] && [ "$(<"$state")" = "$1" ]; }
stable_dir() { [ -d "$1" ] && [ ! -L "$1" ] && [ "$(stat -c '%a %u' "$1")" = "700 $(id -u)" ]; }
backend_ip() { docker inspect --format '{{with index .NetworkSettings.Networks "crm_trial_c010400_network"}}{{.IPAddress}}{{end}}' "$back"; }
front_master() { docker exec "$front" sh -ec 'pid=$(cat /run/nginx.pid); [ "$pid" = 1 ]; awk '\''/^Uid:/{print $2}'\'' /proc/1/status; awk '\''{ print $22 }'\'' /proc/1/stat'; }

canonical_snapshot() {
    python3 -B -c '
import json, sys
for raw in sys.stdin:
    line = raw.rstrip("\n")
    if line.startswith("/"):
        prefix, sep, rest = line.partition(" [")
        if not sep:
            raise SystemExit("Missing mount array in container snapshot")
        mounts, end = json.JSONDecoder().raw_decode("[" + rest)
        canonical = sorted(json.dumps(mount, sort_keys=True, separators=(",", ":")) for mount in mounts)
        line = prefix + " [" + ",".join(canonical) + "]" + rest[end - 1:]
    print(line)
'
}

raw_non_target_snapshot() {
    local svc
    for svc in "${infra[@]}" "${apps[@]}"; do
        docker inspect --format '{{.Name}} {{.Id}} {{.Image}} {{.State.StartedAt}} {{.State.Status}} {{.State.Pid}} {{.State.ExitCode}} {{.RestartCount}} {{.State.OOMKilled}} {{index .Config.Labels "com.docker.compose.config-hash"}} {{json .Mounts}} {{json .NetworkSettings.Networks}}' "$project-$svc-1" || return 1
    done
    docker volume ls --filter "label=com.docker.compose.project=$project" --format '{{.Name}}' | sort || return 1
    docker network inspect "$net" --format '{{.Id}} {{json .IPAM.Config}}' || return 1
    front_master
}

non_target_snapshot() { raw_non_target_snapshot | canonical_snapshot; }

check_unchanged() {
    local snapshot=${1:-$mixed/non-target.before} now
    [ -f "$snapshot" ] && [ ! -L "$snapshot" ] || return 1
    now=$(non_target_snapshot) && [ "$now" = "$(<"$snapshot")" ] || return 1
    docker inspect --format '{{.Name}} {{.Id}} {{.State.StartedAt}} {{.Image}}' "$front"
}

stable_snapshot() {
    python3 -B -c '
import sys
lines = sys.stdin.read().splitlines()
names = sys.argv[1:]
if len(lines) < len(names) + 3 or not all(value.isdigit() for value in lines[-2:]):
    raise SystemExit("Malformed non-target snapshot")
for name, line in zip(names, lines):
    fields = line.split(" ", 10)
    if len(fields) != 11 or fields[0] != name or not fields[5].isdigit() or not fields[7].isdigit():
        raise SystemExit("Malformed container snapshot: " + name)
    for index in (3, 5, 7):  # StartedAt, host PID, RestartCount
        fields[index] = "-"
    print(" ".join(fields))
# Preserve volume names, network ID/IPAM, and nginx master UID. Only drop its start tick.
for line in lines[len(names):-1]:
    print(line)
' "$@"
}

non_targets_healthy() {
    local svc
    for svc in frontend "${infra[@]}"; do
        [ "$(docker inspect --format '{{.State.Health.Status}}' "$project-$svc-1")" = healthy ] || return 1
    done
    for svc in frontend scheduler websocket queue-short queue-long; do
        [ "$(docker inspect --format '{{.State.Status}} {{.State.OOMKilled}}' "$project-$svc-1")" = 'running false' ] || return 1
    done
    [ "$(docker inspect --format '{{.State.Status}} {{.State.ExitCode}} {{.State.OOMKilled}}' "$project-configurator-1")" = 'exited 0 false' ]
}

capture_rollback_window() {
    local original=$mixed/non-target.before snapshot=$mixed/rollback-window.before current old_stable new_stable svc tmp
    local names=()
    for svc in "${infra[@]}" "${apps[@]}"; do names+=("/$project-$svc-1"); done
    [ -f "$original" ] && [ ! -L "$original" ] && [ ! -e "$snapshot" ] && [ ! -L "$snapshot" ] || return 1
    non_targets_healthy && current=$(non_target_snapshot) || return 1
    old_stable=$(stable_snapshot "${names[@]}" < "$original") &&
        new_stable=$(printf '%s\n' "$current" | stable_snapshot "${names[@]}") || return 1
    if [ "$old_stable" != "$new_stable" ]; then
        printf 'ERROR: non-target stable identity differs from the release snapshot\n' >&2
        return 1
    fi
    tmp=$(mktemp "$mixed/.rollback-window.XXXXXXXX") && printf '%s\n' "$current" > "$tmp" &&
        ln -T -- "$tmp" "$snapshot" && rm -- "$tmp" || return 1
    printf 'PASS: non-target stable identity verified; captured strict planned rollback snapshot\n'
}

check_prereqs() {
    [ "$(hostname)" = iZuf6htx2n3srizz88227cZ ] || fail 'unexpected host'
    stable_dir "$stage" && stable_dir "$runtime" || fail 'unexpected staging or runtime ownership/mode'
    hash_is "$tools/trial.sh" 53d9eee8525efae3fb4ecd75cf1cbe87b62aa0a941ca9f06b4a8696dc89cc8d9 || fail 'trial tool drift'
    hash_is "$tools/compose.yml" d53236e4c83b936ca2864eb67f631047b68d1e953dcd25fe2cb0d3bd7b1b2980 || fail 'base Compose drift'
    hash_is /etc/crm-https/compose.yml 9ff19dd1dc09ff5cc8ed3a6b0f6c53a387ec26abaf333199584b339b3ba983a4 || fail 'HTTPS Compose drift'
    hash_is /etc/crm-https/prepare_inner.py 6770c12cce492d21b98f567596cd49260dda63dd15b8e7d2910a2955fa1aa406 || fail 'inner nginx launcher drift'
    hash_is "$runtime/release.env" b4b2cbcb5292da32561c63e4ab0289a3c274524e8a799fbc79f7569bd10c2818 || fail 'base release drift'
    hash_is "$runtime/image-rootfs-layers.txt" fb75287484298a947b53d7d2f3b8822fdeae478e8607ac6da3a4e317a2fda083 || fail 'base layers drift'
    [ "$(<"$runtime/image.env")" = "CRM_IMAGE=$base" ] || fail 'base image lock drift'
}

check_baseline() {
    local svc
    active_state "ready image=$base" || fail 'baseline is not ready'
    trial check
    for svc in backend "${apps[@]}"; do image_is "$project-$svc-1" "$base" || fail "$svc image drift"; done
    [ "$(docker inspect --format '{{.Id}}' "$front")" = 5aabd6045ef5004d028fbf188e6576e721d8eeb52ebf88d1ffb55986bf06892b ] || fail 'original frontend ID drift'
    for svc in backend frontend "${infra[@]}"; do
        [ "$(docker inspect --format '{{.State.Health.Status}}' "$project-$svc-1")" = healthy ] || fail "$svc not healthy"
    done
    html_is "$old_html" || fail 'live baseline HTML drift'
    docker exec "$back" sh -ec 'cd sites/crm.localhost/private/backups; for suffix in database.sql.gz files.tar private-files.tar site_config_backup.json; do f=20261110_170105-crm_localhost-$suffix; test -f "$f" && test -r "$f" && test -s "$f" || exit 1; done'
    [ "$(docker exec "$front" id -u)" = 1000 ] || fail 'nginx exec user drift'
    [ "$(front_master | sed -n '1p')" = 1000 ] || fail 'nginx master user drift'
    docker exec "$front" nginx -t
}

check_model() {
    python3 -B - "$tools" "$runtime" "$mixed/backend.yml" "$project" "$base" "$new" <<'PY'
import json, subprocess, sys
from pathlib import Path
tools, runtime, override, project, old, new = sys.argv[1:]
args = ['sudo', '-n', 'docker', 'compose', '-p', project, '--env-file', str(Path(runtime) / '.env'),
        '--env-file', str(Path(runtime) / 'image.env'), '-f', str(Path(tools) / 'compose.yml'),
        '-f', '/etc/crm-https/compose.yml']
a = json.loads(subprocess.check_output(args + ['config', '--format', 'json']))
b = json.loads(subprocess.check_output(args + ['-f', override, 'config', '--format', 'json']))
if a['services']['backend']['image'] != old or b['services']['backend']['image'] != new:
    raise SystemExit('Unexpected Compose image')
b['services']['backend']['image'] = old
if b != a:
    raise SystemExit('Override changes more than backend.image')
print('PASS: rendered override only changes backend.image')
PY
}

wait_backend() {
    local i health
    for ((i=0; i<45; i++)); do
        health=$(docker inspect --format '{{.State.Health.Status}}' "$back") || return 1
        if [ "$health" = healthy ]; then return 0; fi
        sleep 2
    done
    return 1
}

ping() {
    docker exec "$1" /home/frappe/frappe-bench/env/bin/python -c 'import json,sys,urllib.request; req=urllib.request.Request("http://127.0.0.1:"+sys.argv[1]+"/api/method/ping",headers={"Host":"crm.localhost"}); assert json.load(urllib.request.urlopen(req,timeout=5)).get("message")=="pong"' "$2"
}

dns_matches() {
    local actual
    actual=$(docker exec "$front" getent ahostsv4 backend | awk '{print $1}' | sort -u) && [ "$actual" = "$1" ];
}

fix_route() {
    local prior=$1 snapshot=${2:-$mixed/non-target.before} ip
    ip=$(backend_ip) && [ -n "$ip" ] && dns_matches "$ip" && ping "$back" 8000 || return 1
    printf 'Backend IP: %s -> %s\n' "$prior" "$ip"
    if [ "$prior" != "$ip" ] || ! ping "$front" 8080; then
        check_unchanged "$snapshot" && docker exec "$front" nginx -t && check_unchanged "$snapshot" &&
            docker exec "$front" nginx -s reload || return 1
        printf 'Original frontend nginx: graceful reload issued\n'
    fi
    local i
    for ((i=0; i<10; i++)); do
        if ping "$front" 8080 && dns_matches "$ip"; then return 0; fi
        sleep 1
    done
    return 1
}

replace() { compose "$@" up -d --no-deps --pull never --no-build --force-recreate backend; }

saved_base_state() {
    [ -f "$mixed/state.before" ] && [ ! -L "$mixed/state.before" ] &&
        [ "$(<"$mixed/state.before")" = "ready image=$base" ]
}

rollback() {
    local snapshot=$1 phase=$2 prior id
    saved_base_state && check_unchanged "$snapshot" && non_targets_healthy && trial check || return 1
    id=$(backend_id) && prior=$(backend_ip) && [ -n "$prior" ] || return 1
    if backend_matches "$id" "$new" "$new_html"; then
        state_write "backend-only $phase base=$base candidate=$new" && check_unchanged "$snapshot" &&
            backend_matches "$id" "$new" "$new_html" && replace && id=$(backend_id) || return 1
    elif ! backend_matches "$id" "$base" "$old_html"; then
        printf 'ERROR: live backend is neither the verified candidate nor the verified base\n' >&2
        return 1
    fi
    wait_backend && backend_matches "$id" "$base" "$old_html" && check_unchanged "$snapshot" &&
        fix_route "$prior" "$snapshot" && non_targets_healthy &&
        backend_matches "$id" "$base" "$old_html" && check_unchanged "$snapshot" || return 1
    state_write "backend-only $phase-awaiting-https base=$base candidate=$new" || return 1
    printf 'PASS: original backend and template restored; confirm direct HTTPS before restoring ready state\n'
}

planned_rollback() {
    local snapshot=$mixed/rollback-window.before id
    saved_base_state || fail 'invalid saved base state'
    if active_state "backend-only active base=$base candidate=$new override=$mixed/backend.yml"; then
        id=$(backend_id) && backend_matches "$id" "$new" "$new_html" && trial check ||
            fail 'candidate backend or base rollback image not confirmed'
        if [ -e "$snapshot" ] || [ -L "$snapshot" ]; then
            check_unchanged "$snapshot" || fail 'sealed planned rollback snapshot drifted; do not recapture it'
        else
            capture_rollback_window || fail 'cannot start planned rollback window; original state and evidence retained'
        fi
    elif ! active_state "backend-only rollback-planned base=$base candidate=$new" &&
        ! active_state "backend-only rollback-planned-failed base=$base candidate=$new"; then
        fail 'not in the active or interrupted planned rollback state'
    fi
    if ! rollback "$snapshot" rollback-planned; then
        state_write "backend-only rollback-planned-failed base=$base candidate=$new" || true
        fail 'planned rollback did not finish; preserve the window and inspect actual containers'
    fi
}

accept_rollback() {
    local snapshot=$1 phase=$2 id ip
    active_state "backend-only $phase-awaiting-https base=$base candidate=$new" && saved_base_state || return 1
    id=$(backend_id) && ip=$(backend_ip) && [ -n "$ip" ] && check_unchanged "$snapshot" && non_targets_healthy &&
        backend_matches "$id" "$base" "$old_html" && dns_matches "$ip" && ping "$back" 8000 && ping "$front" 8080 &&
        backend_matches "$id" "$base" "$old_html" && check_unchanged "$snapshot" && restore_state
}

switch_failed() {
    local rc=$?
    trap - EXIT HUP INT TERM
    if [ "$rc" != 0 ]; then
        if ! rollback "$mixed/non-target.before" rollback; then
            state_write "backend-only rollback-failed base=$base candidate=$new" || true
            printf 'ERROR: S011 rollback did not finish; preserve current state and escalate immediately\n' >&2
        fi
    fi
    exit "$rc"
}

dispatch() {
case "${1:-}" in
preflight)
    check_baseline
    [ -n "$(backend_ip)" ] && dns_matches "$(backend_ip)" && ping "$back" 8000 && ping "$front" 8080
    printf 'PASS: original image, four backup artifacts, frontend identity and route confirmed\n'
    ;;
switch)
    [ "${2:-}" = --confirm-exclusive ] || fail 'operator must confirm the exclusive maintenance window'
    check_baseline
    if [ "${3:-}" = --preserve-unapplied-first-attempt ]; then
        stable_dir "$mixed" || fail 'missing first attempt evidence'
        [ ! -e "$mixed/MAINTENANCE" ] && [ ! -L "$mixed/MAINTENANCE" ] || fail 'first attempt passed the mutation boundary'
        [ ! -e "$stage/backend-only.first-attempt" ] && [ ! -L "$stage/backend-only.first-attempt" ] || fail 'archive already exists'
        cmp -s "$state" "$mixed/state.before" || fail 'state differs from first attempt'
        first=$(canonical_snapshot < "$mixed/non-target.before")
        current=$(non_target_snapshot)
        [ "$first" = "$current" ] || fail 'non-target identity differs from first attempt'
        mv -T "$mixed" "$stage/backend-only.first-attempt"
        printf 'PASS: preserved first attempt; all canonical non-target fields unchanged\n'
    fi
    [ ! -e "$mixed" ] && [ ! -L "$mixed" ] || fail 'existing backend-only evidence; do not overwrite'
    mkdir "$mixed"
    cp -- "$state" "$mixed/state.before"
    non_target_snapshot > "$mixed/non-target.before"
    main_ip=$(backend_ip)
    [ -n "$main_ip" ] && dns_matches "$main_ip" && ping "$front" 8080 || fail 'baseline nginx route is not healthy'
    printf 'services:\n  backend:\n    image: %s\n' "$new" > "$mixed/backend.yml"
    check_model
    hash_is "$stage/release/release.env" 18bc73e1020a9e0b020e00995a4cf48dba2beb01bb8315d811c2d1772aaed60c || fail 'candidate release metadata drift'
    hash_is "$stage/release/image-rootfs-layers.txt" c423306310231e9d158f565e5580319fbbf52d49424c4eef567e0d2d801f2718 || fail 'candidate layer list drift'
    hash_is "$stage/release/image.tar" 52062d74bb73fea4118a932a99df5ea6de48877ef5aafa9d3780907a3c5e82d2 || fail 'candidate archive drift'
    docker load -i "$stage/release/image.tar"
    [ "$(docker image inspect "$new" --format '{{.Id}} {{.Os}}/{{.Architecture}}')" = "$new linux/amd64" ] || fail 'loaded candidate identity drift'
    [ "$(docker image inspect "$new" --format '{{range .RootFS.Layers}}{{println .}}{{end}}')" = "$(<"$stage/release/image-rootfs-layers.txt")" ] || fail 'loaded candidate diff_ids drift'
    check_baseline
    check_unchanged
    printf '%s\n' 'S011 mixed release: do not run trial.sh up/update-site-image/maintenance-stop/restore-old-lock. Before standard maintenance, perform single-service rollback plus direct HTTPS rollback confirmation, or use an independently reviewed integration; do not recreate frontend until authorized.' > "$mixed/MAINTENANCE"
    state_write "backend-only switching base=$base candidate=$new override=$mixed/backend.yml"
    trap switch_failed EXIT
    trap 'exit 129' HUP
    trap 'exit 130' INT
    trap 'exit 143' TERM
    replace -f "$mixed/backend.yml"
    wait_backend
    image_is "$back" "$new"
    html_is "$new_html"
    fix_route "$main_ip"
    check_unchanged
    state_write "backend-only awaiting-https base=$base candidate=$new override=$mixed/backend.yml"
    trap - EXIT HUP INT TERM
    printf 'PASS: unchanged frontend/non-target services, candidate backend and inner route healthy; awaiting direct authenticated HTTPS\n'
    ;;
accept)
    [ "${2:-}" = --confirm-authenticated-https ] || fail 'operator must confirm authenticated direct HTTPS and CRM reachability'
    active_state "backend-only awaiting-https base=$base candidate=$new override=$mixed/backend.yml" || fail 'not awaiting HTTPS'
    check_unchanged
    image_is "$back" "$new" && html_is "$new_html" && ping "$front" 8080 || fail 'candidate route or template drifted; roll back'
    state_write "backend-only active base=$base candidate=$new override=$mixed/backend.yml"
    ;;
rollback)
    stable_dir "$mixed" || fail 'missing backend-only records'
    if [ "${2:-}" = --confirm-exclusive ]; then
        planned_rollback
    else
        [ "$#" = 1 ] || fail 'unrecognized rollback option'
        if ! active_state "backend-only awaiting-https base=$base candidate=$new override=$mixed/backend.yml" &&
            ! active_state "backend-only switching base=$base candidate=$new override=$mixed/backend.yml" &&
            ! active_state "backend-only rollback base=$base candidate=$new" &&
            ! active_state "backend-only rollback-failed base=$base candidate=$new"; then
            fail 'not in the release window; planned rollback requires --confirm-exclusive and an active release'
        fi
        if ! rollback "$mixed/non-target.before" rollback; then
            state_write "backend-only rollback-failed base=$base candidate=$new" || true
            fail 'rollback did not finish; preserve current state'
        fi
    fi
    ;;
accept-rollback)
    stable_dir "$mixed" || fail 'missing backend-only records'
    [ "${2:-}" = --confirm-https ] || fail 'operator must confirm direct HTTPS after rollback'
    if active_state "backend-only rollback-planned-awaiting-https base=$base candidate=$new"; then
        accept_rollback "$mixed/rollback-window.before" rollback-planned || fail 'planned rollback identity or health changed; do not restore ready'
    else
        accept_rollback "$mixed/non-target.before" rollback || fail 'release-window rollback identity, state or health not confirmed; do not restore ready'
    fi
    ;;
*) fail 'specify preflight, switch, accept, rollback, or accept-rollback' ;;
esac
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
    check_prereqs
    [ ! -L "$stage/backend-only.lock" ] || fail 'release lock is a symlink'
    exec 9>> "$stage/backend-only.lock"
    flock -n 9 || fail 'S011 release lock is busy'
    check_prereqs
    dispatch "$@"
fi

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
html_is() { local actual; actual=$(docker exec "$back" sha256sum "$html") && [ "${actual%% *}" = "$1" ]; }
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
    local now
    now=$(non_target_snapshot) && [ "$now" = "$(<"$mixed/non-target.before")" ] || return 1
    docker inspect --format '{{.Name}} {{.Id}} {{.State.StartedAt}} {{.Image}}' "$front"
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
    local prior=$1 ip
    ip=$(backend_ip) && [ -n "$ip" ] && dns_matches "$ip" && ping "$back" 8000 || return 1
    printf 'Backend IP: %s -> %s\n' "$prior" "$ip"
    if [ "$prior" != "$ip" ] || ! ping "$front" 8080; then
        check_unchanged && docker exec "$front" nginx -t && docker exec "$front" nginx -s reload || return 1
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

rollback() {
    local prior
    prior=$(backend_ip 2>/dev/null) || prior=unknown
    state_write "backend-only rollback base=$base candidate=$new" || return 1
    check_unchanged && replace && wait_backend && image_is "$back" "$base" && html_is "$old_html" && fix_route "$prior" && check_unchanged || return 1
    trial check || return 1
    printf 'PASS: original backend and template restored; confirm direct HTTPS before restoring ready state\n'
    state_write "backend-only rollback-awaiting-https base=$base candidate=$new"
}

switch_failed() {
    local rc=$?
    trap - EXIT HUP INT TERM
    if [ "$rc" != 0 ]; then
        if ! rollback; then
            state_write "backend-only rollback-failed base=$base candidate=$new" || true
            printf 'ERROR: S011 rollback did not finish; preserve current state and escalate immediately\n' >&2
        fi
    fi
    exit "$rc"
}

check_prereqs
[ ! -L "$stage/backend-only.lock" ] || fail 'release lock is a symlink'
exec 9>> "$stage/backend-only.lock"
flock -n 9 || fail 'S011 release lock is busy'
check_prereqs

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
    case "$(<"$state")" in 'backend-only '*) ;; *) fail 'not in backend-only state' ;; esac
    if ! rollback; then
        state_write "backend-only rollback-failed base=$base candidate=$new" || true
        fail 'rollback did not finish; preserve current state'
    fi
    ;;
accept-rollback)
    [ "${2:-}" = --confirm-https ] || fail 'operator must confirm direct HTTPS after rollback'
    active_state "backend-only rollback-awaiting-https base=$base candidate=$new" || fail 'rollback not awaiting HTTPS'
    check_unchanged
    image_is "$back" "$base" && html_is "$old_html" && ping "$front" 8080 || fail 'original backend or route not confirmed'
    restore_state
    ;;
*) fail 'specify switch, accept, rollback, or accept-rollback' ;;
esac

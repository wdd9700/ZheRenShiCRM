#!/bin/sh
set -eu

REMOTE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$REMOTE/../.." && pwd)
RUNTIME=${CRM_TRIAL_RUNTIME_DIR:-$REMOTE/.runtime}
case "$RUNTIME" in
    /*) ;;
    *) printf 'ERROR: CRM_TRIAL_RUNTIME_DIR must be absolute\n' >&2; exit 1 ;;
esac
if [ -e "$RUNTIME" ] && { [ ! -d "$RUNTIME" ] || [ -L "$RUNTIME" ]; }; then
    printf 'ERROR: runtime must be a real non-symlink directory\n' >&2
    exit 1
fi
ENV_FILE=$RUNTIME/.env
IMAGE_FILE=$RUNTIME/image.env
PROJECT=crm-trial-c010400
SITE=crm.localhost
ACTION=${1:-}
[ "$#" -eq 0 ] || shift
IMAGE_ARCHIVE=
if [ "$ACTION" = load-image ]; then
    [ "$#" -gt 0 ] || { printf 'load-image requires an explicit archive path\n' >&2; exit 2; }
    IMAGE_ARCHIVE=$1
    shift
fi
UPDATE_RELEASE_DIR=
UPGRADE_APPS=0
RESUME_APPS=0
if [ "$ACTION" = update-site-image ] || [ "$ACTION" = upgrade-site-apps ] || [ "$ACTION" = resume-site-apps ]; then
    [ "$#" -ge 2 ] || { printf '%s requires a reviewed release directory and image archive\n' "$ACTION" >&2; exit 2; }
    UPDATE_RELEASE_DIR=$1
    IMAGE_ARCHIVE=$2
    shift 2
    if [ "$ACTION" = upgrade-site-apps ] || [ "$ACTION" = resume-site-apps ]; then
        UPGRADE_APPS=1
    fi
    if [ "$ACTION" = resume-site-apps ]; then
        RESUME_APPS=1
    fi
fi
CONFIRM=0
if [ "${1:-}" = "--confirm-synthetic-only" ]; then
    CONFIRM=1
    shift
fi
CONFIRM_CLASSIC=0
if [ "${1:-}" = "--confirm-classic-image-lock-migration" ]; then
    CONFIRM_CLASSIC=1
    shift
fi
CONFIRM_SITE_UPDATE=0
if [ "${1:-}" = "--confirm-site-image-update" ]; then
    CONFIRM_SITE_UPDATE=1
    shift
fi
CONFIRM_SITE_APP_UPGRADE=0
if [ "${1:-}" = "--confirm-site-app-upgrade" ]; then
    CONFIRM_SITE_APP_UPGRADE=1
    shift
fi

usage() {
    cat <<'EOF'
Usage: trial.sh ACTION [ARGS] [--confirm-synthetic-only] [--confirm-classic-image-lock-migration] [--confirm-site-image-update] [--confirm-site-app-upgrade]
Actions:
  verify-source                 Verify the 53 exact app/build source files
  init-env                     Generate new 0600 credentials; never overwrite
  load-image ARCHIVE           Load a verified image archive through the selected Docker mode
  check                        Check Compose, locked image identity, platform, labels and RootFS
  migrate-image-lock-to-config One-time exact index-to-config lock migration; requires classic confirmation
  update-site-image DIR TAR    Image-only reviewed update with backup and rollback; requires confirmation
  upgrade-site-apps DIR TAR    Controlled update to the approved five apps; requires app upgrade confirmation
  resume-site-apps DIR TAR     Resume the same failed app generation without repeating backup/init
  create-site                  One-time new site; requires synthetic confirmation
  up                           Start/wait all trial services
  install-extensions           One-time resource_import then team_access install; requires confirmation
  migrate                      Run two full migrations, then clear cache
  enable-import                Enable the import entry after its safety baseline; requires confirmation
  backup                       Native backup --with-files and four-file readability check
  versions                     Show image app versions and installed-site apps
  status                       Show retained project containers
  inspect-volumes              Inspect the four retained trial volumes
  maintenance-status           Show persistent update/maintenance state without metadata validation
  maintenance-stop             Stop without release metadata validation and record maintenance state
  restore-old-lock             Restore the retained old lock while stopped; requires confirmation
  stop                         Stop containers only; retain all volumes and resources
EOF
}
fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}
[ -n "$ACTION" ] || { usage >&2; exit 2; }
[ "$#" -eq 0 ] || { usage >&2; exit 2; }
[ -f "$REMOTE/release.env" ] || fail 'release.env is missing'
# shellcheck source=release.env
. "$REMOTE/release.env"
# shellcheck source=docker.sh
. "$REMOTE/docker.sh"
unset DB_PASSWORD ADMIN_PASSWORD FRAPPE_SITE_NAME CRM_TRIAL_SYNTHETIC_ONLY_ACK COMPOSE_PROJECT_NAME COMPOSE_FILE COMPOSE_PROFILES

require_docker() {
    command -v docker >/dev/null 2>&1 || fail 'Docker CLI is required; this script never installs it'
    DOCKER_CONTEXT_NAME=$(docker_cli context show 2>/dev/null) || fail 'Docker context query failed in the selected mode; sudo mode uses only sudo -n with no fallback'
    [ "$DOCKER_CONTEXT_NAME" = default ] || fail 'use only the default local Docker context'
    docker_cli compose version >/dev/null 2>&1 || fail 'Compose v2 or selected Docker access mode failed; no privilege fallback is attempted'
    docker_cli version --format '{{.Server.Version}}' >/dev/null 2>&1 || fail 'local Docker daemon access failed in the selected mode; sudo mode uses only sudo -n'
}
release_value() {
    awk -F= -v key="$1" '$1 == key {count++; value=substr($0, index($0, "=") + 1)} END {if (count != 1) exit 1; print value}' "$2"
}
require_runtime() {
    [ -f "$ENV_FILE" ] && [ ! -L "$ENV_FILE" ] || fail 'new trial credentials are missing; run init-env once, never reuse local credentials'
    [ -f "$IMAGE_FILE" ] && [ ! -L "$IMAGE_FILE" ] || fail 'trial image lock is missing'
    ACTIVE_RELEASE=$REMOTE/release.env
    ACTIVE_LAYERS=$REMOTE/image-rootfs-layers.txt
    if [ -e "$RUNTIME/release.env" ]; then
        [ -f "$RUNTIME/release.env" ] && [ ! -L "$RUNTIME/release.env" ] || fail 'runtime release metadata must be an ordinary non-symlink file'
        [ -f "$RUNTIME/image-rootfs-layers.txt" ] && [ ! -L "$RUNTIME/image-rootfs-layers.txt" ] || fail 'runtime RootFS metadata must be an ordinary non-symlink file'
        ACTIVE_RELEASE=$RUNTIME/release.env
        ACTIVE_LAYERS=$RUNTIME/image-rootfs-layers.txt
    fi
    CRM_IMAGE_CONFIG=$(release_value CRM_IMAGE_CONFIG "$ACTIVE_RELEASE")
    CRM_IMAGE_INDEX=$(release_value CRM_IMAGE_INDEX "$ACTIVE_RELEASE")
    CRM_RESOURCE_IMPORT_COMMIT=$(release_value CRM_RESOURCE_IMPORT_COMMIT "$ACTIVE_RELEASE")
    CRM_TEAM_ACCESS_COMMIT=$(release_value CRM_TEAM_ACCESS_COMMIT "$ACTIVE_RELEASE")
    CRM_UPSTREAM_CRM_COMMIT=$(release_value CRM_UPSTREAM_CRM_COMMIT "$ACTIVE_RELEASE")
    IMAGE_LOCK=$(cat "$IMAGE_FILE")
    case "$IMAGE_LOCK" in
        "CRM_IMAGE=$CRM_IMAGE_CONFIG")
            CRM_IMAGE=$CRM_IMAGE_CONFIG
            CRM_IMAGE_LOCK_KIND=classic-config
            ;;
        "CRM_IMAGE=$CRM_IMAGE_INDEX")
            CRM_IMAGE=$CRM_IMAGE_INDEX
            CRM_IMAGE_LOCK_KIND=containerd-index
            ;;
        *) fail 'trial image lock must exactly select the pinned config or index; no fallback is allowed' ;;
    esac
}
compose() {
    docker_cli compose -p "$PROJECT" --env-file "$ENV_FILE" --env-file "$IMAGE_FILE" -f "$REMOTE/compose.yml" "$@"
}
verify_source() {
    (cd "$ROOT" && sha256sum -c --status "$REMOTE/SOURCE_SHA256SUMS") || fail 'exact source verification failed; preserve the delivery and investigate'
    printf 'PASS: 53 exact app/build source files match M9 candidate sources\n'
}
init_env() {
    command -v openssl >/dev/null 2>&1 || fail 'openssl is required to generate independent secrets'
    [ ! -L "$RUNTIME" ] || fail 'runtime must not be a symbolic link'
    if [ -e "$RUNTIME" ]; then
        [ -d "$RUNTIME" ] || fail 'runtime exists but is not a directory'
    else
        (umask 077 && mkdir "$RUNTIME")
    fi
    [ ! -e "$ENV_FILE" ] && [ ! -L "$ENV_FILE" ] || fail 'credentials already exist; refuse to overwrite or regenerate'
    [ ! -e "$IMAGE_FILE" ] && [ ! -L "$IMAGE_FILE" ] || fail 'image lock already exists; refuse to overwrite'
    DB_GENERATED=$(openssl rand -hex 32)
    ADMIN_GENERATED=$(openssl rand -hex 32)
    (umask 077 && set -C && {
        printf 'DB_PASSWORD=%s\n' "$DB_GENERATED"
        printf 'ADMIN_PASSWORD=%s\n' "$ADMIN_GENERATED"
        printf 'FRAPPE_SITE_NAME=%s\n' "$SITE"
    } > "$ENV_FILE")
    (umask 077 && set -C && printf 'CRM_IMAGE=%s\n' "$CRM_IMAGE_CONFIG" > "$IMAGE_FILE")
    unset DB_GENERATED ADMIN_GENERATED
    printf 'PASS: independent trial credentials and classic-store config lock created with private permissions; values not printed\n'
}
verify_image_identity() {
    IMAGE=$1
    EXPECTED_ID=$2
    RESOURCE_REVISION=$3
    TEAM_REVISION=$4
    CRM_REVISION=$5
    LAYERS_FILE=$6
    ACTUAL=$(docker_cli image inspect "$IMAGE" --format '{{.Id}}') || fail "locked image is unavailable: $EXPECTED_ID"
    [ "$ACTUAL" = "$EXPECTED_ID" ] || fail "loaded image ID does not match the exact lock: $EXPECTED_ID"
    [ "$(docker_cli image inspect "$IMAGE" --format '{{.Os}}/{{.Architecture}}')" = linux/amd64 ] || fail 'candidate image platform mismatch'
    [ "$(docker_cli image inspect "$IMAGE" --format '{{index .Config.Labels "crm.resource-import.revision"}}')" = "$RESOURCE_REVISION" ] || fail 'resource_import revision label mismatch'
    [ "$(docker_cli image inspect "$IMAGE" --format '{{index .Config.Labels "crm.team-access.revision"}}')" = "$TEAM_REVISION" ] || fail 'team_access revision label mismatch'
    [ "$(docker_cli image inspect "$IMAGE" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')" = "$CRM_REVISION" ] || fail 'upstream CRM revision label mismatch'
    ACTUAL_LAYERS=$(docker_cli image inspect "$IMAGE" --format '{{range .RootFS.Layers}}{{println .}}{{end}}') || fail 'unable to read locked image RootFS layers'
    EXPECTED_LAYERS=$(cat "$LAYERS_FILE")
    [ "$ACTUAL_LAYERS" = "$EXPECTED_LAYERS" ] || fail 'image RootFS diff_ids differ from the pinned config content; labels are not identity proof'
}
check() {
    require_runtime
    require_docker
    compose --profile setup config -q
    verify_image_identity "$CRM_IMAGE" "$CRM_IMAGE" "$CRM_RESOURCE_IMPORT_COMMIT" "$CRM_TEAM_ACCESS_COMMIT" "$CRM_UPSTREAM_CRM_COMMIT" "$ACTIVE_LAYERS"
    printf 'PASS: Compose and %s image lock, linux/amd64, three labels and all RootFS diff_ids; runtime health not yet proven\n' "$CRM_IMAGE_LOCK_KIND"
}
mark() {
    (umask 077 && set -C && printf '%s\n' "$1" > "$RUNTIME/$1")
}
require_marker() {
    [ -f "$RUNTIME/$1" ] && [ ! -L "$RUNTIME/$1" ] || fail "required completed stage is missing: $1; do not skip deployment gates"
}
create_site() {
    [ "$CONFIRM" -eq 1 ] || fail 'create-site requires explicit --confirm-synthetic-only; no real customer data is permitted'
    require_runtime
    require_docker
    [ ! -e "$RUNTIME/site-created" ] && [ ! -L "$RUNTIME/site-created" ] || fail 'site-created marker exists; refuse to repeat initialization'
    CRM_TRIAL_DIR=$ROOT CRM_TRIAL_DOCKER_SUDO=$CRM_TRIAL_DOCKER_SUDO sh "$REMOTE/preflight.sh" --existing-dir
    compose --profile setup run -e CRM_TRIAL_SYNTHETIC_ONLY_ACK=confirmed-synthetic-only --name crm-trial-c010400-create-site create-site
    mark site-created
    printf 'PASS: create-site returned zero; CRM only was installed by new-site, extensions still require separate installation\n'
}
up() {
    require_runtime
    require_marker site-created
    require_docker
    compose up -d --wait
    printf 'PASS: Compose wait returned zero; HTTP/login/permissions/PWA acceptance is still required\n'
}
install_extensions() {
    [ "$CONFIRM" -eq 1 ] || fail 'extension installation requires explicit --confirm-synthetic-only'
    require_runtime
    require_marker site-created
    require_docker
    [ ! -e "$RUNTIME/extensions-installed" ] && [ ! -L "$RUNTIME/extensions-installed" ] || fail 'extensions-installed marker exists; do not blindly repeat installation'
    compose exec -T backend bench --site "$SITE" install-app resource_import
    compose exec -T backend bench --site "$SITE" install-app team_access
    mark extensions-installed
    printf 'PASS: both extension install commands returned zero; run two migrations next\n'
}
migrate() {
    require_runtime
    require_marker extensions-installed
    require_docker
    [ ! -e "$RUNTIME/migrated-twice" ] && [ ! -L "$RUNTIME/migrated-twice" ] || fail 'migrated-twice marker exists; do not blindly repeat migration'
    compose exec -T backend bench --site "$SITE" migrate
    compose exec -T backend bench --site "$SITE" migrate
    compose exec -T backend bench --site "$SITE" clear-cache
    mark migrated-twice
    printf 'PASS: two migrations and clear-cache returned zero; permission acceptance is separate\n'
}
enable_import() {
    [ "$CONFIRM" -eq 1 ] || fail 'enabling import requires explicit --confirm-synthetic-only after the HTTP safety baseline'
    require_runtime
    require_marker migrated-twice
    require_docker
    compose exec -T backend bench --site "$SITE" set-config -p resource_import_disabled 0
    compose exec -T backend bench --site "$SITE" clear-cache
    printf 'PASS: import entry enabled for authorized System Manager/Administrator synthetic use only\n'
}
backup() {
    require_runtime
    require_marker site-created
    require_docker
    BACKUP_STARTED=$(date +%s)
    compose exec -T backend bench --site "$SITE" backup --with-files
    compose exec -T backend /home/frappe/frappe-bench/env/bin/python - "$BACKUP_STARTED" < "$REMOTE/verify_backup.py"
}
versions() {
    require_runtime
    require_marker site-created
    require_docker
    compose exec -T backend bench version
    compose exec -T backend bench --site "$SITE" execute frappe.get_installed_apps
}
load_image() {
    case "$IMAGE_ARCHIVE" in
        /*) ;;
        *) fail 'load-image requires an absolute archive path' ;;
    esac
    [ -f "$IMAGE_ARCHIVE" ] && [ ! -L "$IMAGE_ARCHIVE" ] || fail 'load-image requires an ordinary existing archive file'
    ARCHIVE_HASH=$(sha256sum "$IMAGE_ARCHIVE")
    ARCHIVE_HASH=${ARCHIVE_HASH%% *}
    [ "$ARCHIVE_HASH" = "$CRM_IMAGE_ARCHIVE_SHA256" ] || fail 'image archive SHA256 differs from the pinned delivery; refuse to load an unverified chain'
    require_docker
    docker_cli load -i "$IMAGE_ARCHIVE"
    printf 'PASS: pinned archive loaded; classic store uses the config ID, containerd store uses the index ID; run check with the matching lock\n'
}
migrate_image_lock_to_config() {
    [ "$CONFIRM_CLASSIC" -eq 1 ] || fail 'exact index-to-config migration requires --confirm-classic-image-lock-migration'
    require_docker
    [ -f "$ENV_FILE" ] && [ ! -L "$ENV_FILE" ] || fail 'existing dev-owned .env is required and must not be a symlink'
    [ -f "$IMAGE_FILE" ] && [ ! -L "$IMAGE_FILE" ] || fail 'existing image lock must be an ordinary non-symlink file'
    [ "$(stat -c %a "$IMAGE_FILE")" = 600 ] || fail 'existing image lock must already be mode 0600; no permission change is attempted'
    OLD_LOCK=$(cat "$IMAGE_FILE")
    [ "$OLD_LOCK" = "CRM_IMAGE=$CRM_IMAGE_INDEX" ] || fail 'image lock migration only accepts the exact previous index lock'
    verify_image_identity "$CRM_IMAGE_CONFIG" "$CRM_IMAGE_CONFIG" "$CRM_RESOURCE_IMPORT_COMMIT" "$CRM_TEAM_ACCESS_COMMIT" "$CRM_UPSTREAM_CRM_COMMIT" "${ACTIVE_LAYERS:-$REMOTE/image-rootfs-layers.txt}"
    BACKUP="$RUNTIME/image.env.pre-c010400-config"
    TEMP="$RUNTIME/.image.env.c010400.tmp"
    [ ! -e "$BACKUP" ] && [ ! -L "$BACKUP" ] || fail 'previous lock backup already exists; preserve it and investigate'
    [ ! -e "$TEMP" ] && [ ! -L "$TEMP" ] || fail 'migration temporary path already exists; preserve it and investigate'
    (umask 077 && set -C && cat "$IMAGE_FILE" > "$BACKUP")
    [ "$(cat "$BACKUP")" = "$OLD_LOCK" ] || fail 'previous lock backup verification failed; original lock retained'
    (umask 077 && set -C && printf 'CRM_IMAGE=%s\n' "$CRM_IMAGE_CONFIG" > "$TEMP")
    [ "$(cat "$TEMP")" = "CRM_IMAGE=$CRM_IMAGE_CONFIG" ] && [ "$(stat -c %a "$TEMP")" = 600 ] || fail 'new lock verification failed before atomic rename'
    mv "$TEMP" "$IMAGE_FILE"
    [ "$(cat "$IMAGE_FILE")" = "CRM_IMAGE=$CRM_IMAGE_CONFIG" ] || fail 'atomic image lock replacement did not verify; previous backup retained'
    printf 'PASS: exact index lock migrated to config atomically; previous lock and .env retained unchanged\n'
}
valid_sha256() {
    printf '%s' "$1" | awk 'length == 71 && substr($0, 1, 7) == "sha256:" && substr($0, 8) ~ /^[0-9a-f]+$/ && length(substr($0, 8)) == 64 {ok=1} END {exit !ok}'
}
valid_revision() {
    printf '%s' "$1" | awk 'length == 40 && $0 ~ /^[0-9a-f]+$/ {ok=1} END {exit !ok}'
}
valid_hash64() {
    printf '%s' "$1" | awk 'length == 64 && $0 ~ /^[0-9a-f]+$/ {ok=1} END {exit !ok}'
}
require_compose_materials() {
    [ -f "$ENV_FILE" ] && [ ! -L "$ENV_FILE" ] || fail 'compose credentials file must be ordinary and non-symlink'
    [ -f "$IMAGE_FILE" ] && [ ! -L "$IMAGE_FILE" ] || fail 'compose image lock must be ordinary and non-symlink'
}
set_update_paths() {
    UPDATE_BACKUP="$RUNTIME/image.env.pre-site-update-$NEW_CONFIG"
    UPDATE_STATE_BACKUP="$RUNTIME/site-update.state.pre-$NEW_CONFIG"
    UPDATE_RELEASE_BACKUP="$RUNTIME/release.pre-$NEW_CONFIG.env"
    UPDATE_LAYERS_BACKUP="$RUNTIME/image-rootfs-layers.pre-$NEW_CONFIG.txt"
    FAILED_RELEASE="$RUNTIME/failed-release-$NEW_CONFIG.env"
    FAILED_LAYERS="$RUNTIME/failed-image-rootfs-layers-$NEW_CONFIG.txt"
    ROLLBACK_TEMP="$RUNTIME/.image.env.rollback-$NEW_CONFIG.tmp"
    UPDATE_CONTEXT="$RUNTIME/app-upgrade-context-$NEW_CONFIG"
    UPDATE_CONTEXT_TEMP="$RUNTIME/.app-upgrade-context-$NEW_CONFIG.tmp"
    BACKUP_PROOF="$RUNTIME/backup-ready-$NEW_CONFIG"
    BACKUP_PROOF_TEMP="$RUNTIME/.backup-ready-$NEW_CONFIG.tmp"
    REDIS_EVIDENCE="$RUNTIME/redis-replacement-$NEW_CONFIG"
    REDIS_EVIDENCE_TEMP="$RUNTIME/.redis-replacement-$NEW_CONFIG.tmp"
}
write_state() {
    STATE_TEMP="$RUNTIME/.site-update.state.${NEW_CONFIG:-manual}.$$.tmp"
    if (umask 077 && set -C && printf '%s\n' "$1" > "$STATE_TEMP") && mv "$STATE_TEMP" "$RUNTIME/site-update.state"; then
        return 0
    fi
    printf 'ERROR: unable to persist site update state; treat the update as interrupted\n' >&2
    return 1
}
stop_maintenance() {
    if compose stop; then
        STOP_RESULT=stopped
        return 0
    fi
    STOP_RESULT=stop-failed
    return 1
}
restore_previous_lock() {
    if [ ! -f "$UPDATE_BACKUP" ] || [ -L "$UPDATE_BACKUP" ] || [ -e "$ROLLBACK_TEMP" ]; then
        LOCK_RESULT=restore-failed
        return 1
    fi
    if (umask 077 && set -C && cat "$UPDATE_BACKUP" > "$ROLLBACK_TEMP") && mv "$ROLLBACK_TEMP" "$IMAGE_FILE"; then
        LOCK_RESULT=restored
        return 0
    fi
    LOCK_RESULT=restore-failed
    return 1
}
metadata_recovery_allowed() {
    ACTIVE=$1
    BACKUP=$2
    FAILED=$3
    [ ! -e "$FAILED" ] && [ ! -L "$FAILED" ] && return 0
    [ ! -e "$ACTIVE" ] && [ ! -L "$ACTIVE" ] && return 0
    [ -f "$ACTIVE" ] && [ ! -L "$ACTIVE" ] && [ -f "$BACKUP" ] && [ ! -L "$BACKUP" ] && cmp -s "$ACTIVE" "$BACKUP"
}
quarantine_metadata() {
    META_RESULT=quarantined
    FAILED_RELEASE=${FAILED_RELEASE:-$RUNTIME/failed-release.env}
    FAILED_LAYERS=${FAILED_LAYERS:-$RUNTIME/failed-image-rootfs-layers.txt}
    [ ! -L "$FAILED_RELEASE" ] && [ ! -L "$FAILED_LAYERS" ] || META_RESULT=quarantine-failed
    [ "$META_RESULT" = quarantined ] || return 1
    metadata_recovery_allowed "$RUNTIME/release.env" "$UPDATE_RELEASE_BACKUP" "$FAILED_RELEASE" || META_RESULT=quarantine-failed
    metadata_recovery_allowed "$RUNTIME/image-rootfs-layers.txt" "$UPDATE_LAYERS_BACKUP" "$FAILED_LAYERS" || META_RESULT=quarantine-failed
    [ "$META_RESULT" = quarantined ] || return 1
    if [ -e "$RUNTIME/release.env" ] && [ ! -e "$FAILED_RELEASE" ] && [ ! -L "$FAILED_RELEASE" ]; then
        mv "$RUNTIME/release.env" "$FAILED_RELEASE" || META_RESULT=quarantine-failed
    fi
    if [ -e "$RUNTIME/image-rootfs-layers.txt" ] && [ ! -e "$FAILED_LAYERS" ] && [ ! -L "$FAILED_LAYERS" ]; then
        mv "$RUNTIME/image-rootfs-layers.txt" "$FAILED_LAYERS" || META_RESULT=quarantine-failed
    fi
    [ "$META_RESULT" = quarantined ]
}
restore_previous_metadata() {
    [ "$META_RESULT" != quarantine-failed ] || return 1
    RESTORED_ANY=0
    if [ -e "$UPDATE_RELEASE_BACKUP" ]; then
        (umask 077 && set -C && cat "$UPDATE_RELEASE_BACKUP" > "$RUNTIME/.release.restore-$NEW_CONFIG.tmp") && mv "$RUNTIME/.release.restore-$NEW_CONFIG.tmp" "$RUNTIME/release.env" || META_RESULT=restore-failed
        RESTORED_ANY=1
    fi
    if [ -e "$UPDATE_LAYERS_BACKUP" ]; then
        (umask 077 && set -C && cat "$UPDATE_LAYERS_BACKUP" > "$RUNTIME/.layers.restore-$NEW_CONFIG.tmp") && mv "$RUNTIME/.layers.restore-$NEW_CONFIG.tmp" "$RUNTIME/image-rootfs-layers.txt" || META_RESULT=restore-failed
        RESTORED_ANY=1
    fi
    if [ "$RESTORED_ANY" = 1 ] && [ "$META_RESULT" = quarantined ]; then
        META_RESULT=restored
    fi
    [ "$META_RESULT" != restore-failed ]
}
fail_update() {
    REASON=$1
    UPDATE_ACTIVE=0
    STOP_RESULT=not-attempted
    LOCK_RESULT=not-attempted
    META_RESULT=not-attempted
    stop_maintenance || true
    restore_previous_lock || true
    quarantine_metadata || true
    if [ "$META_RESULT" != quarantine-failed ]; then
        restore_previous_metadata || true
    fi
    write_state "maintenance reason=$REASON image=$NEW_CONFIG stop=$STOP_RESULT lock=$LOCK_RESULT metadata=$META_RESULT"
    printf 'ERROR: site update failed (%s); stop=%s lock=%s metadata=%s; maintenance retained, no service is restarted and any app/schema changes are preserved\n' "$REASON" "$STOP_RESULT" "$LOCK_RESULT" "$META_RESULT" >&2
    exit 1
}
update_exit() {
    EXIT_CODE=$?
    if [ "${UPDATE_ACTIVE:-0}" = 1 ]; then
        fail_update "exit-$EXIT_CODE"
    fi
}
verify_running_app_images() {
    EXPECTED=$1
    for SERVICE in backend websocket frontend queue-short queue-long scheduler; do
        ACTUAL=$(docker_cli container inspect "$PROJECT-$SERVICE-1" --format '{{.Image}} {{.State.Status}}')
        [ "$ACTUAL" = "$EXPECTED running" ] || return 1
    done
    ACTUAL=$(docker_cli container inspect "$PROJECT-configurator-1" --format '{{.Image}} {{.State.Status}} {{.State.ExitCode}}')
    [ "$ACTUAL" = "$EXPECTED exited 0" ]
}
verify_infrastructure() {
    compose exec -T db healthcheck.sh --connect --innodb_initialized >/dev/null &&
      compose exec -T redis-cache redis-cli ping >/dev/null &&
      compose exec -T redis-queue redis-cli ping >/dev/null
}
verify_service_readiness() {
    verify_infrastructure &&
      compose exec -T backend /home/frappe/frappe-bench/env/bin/python -c 'import json,sys,urllib.request; response=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8000/api/method/ping",headers={"Host":sys.argv[1]}),timeout=5); raise SystemExit(0 if json.loads(response.read()).get("message") == "pong" else 1)' "$SITE" &&
      compose exec -T frontend /home/frappe/frappe-bench/env/bin/python -c 'import json,sys,urllib.request; response=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8080/api/method/ping",headers={"Host":sys.argv[1]}),timeout=5); raise SystemExit(0 if json.loads(response.read()).get("message") == "pong" else 1)' "$SITE"
}
candidate_apps() {
    compose run --no-deps -T --entrypoint /home/frappe/frappe-bench/env/bin/python backend - "$1" < "$REMOTE/verify_upgrade.py"
}
query_maintenance() {
    RAW=$(candidate_apps maintenance) || return 1
    printf '%s' "$RAW" | python3 -c 'import json,sys; value=json.load(sys.stdin); assert set(value)=={"maintenance_mode"} and type(value["maintenance_mode"]) is bool; print("1" if value["maintenance_mode"] else "0")'
}
site_config_fingerprint() {
    compose exec -T backend /home/frappe/frappe-bench/env/bin/python -c 'import hashlib,json; path="/home/frappe/frappe-bench/sites/crm.localhost/site_config.json"; data=json.load(open(path,encoding="utf-8")); data.pop("maintenance_mode",None); print(hashlib.sha256(json.dumps(data,sort_keys=True,separators=(",",":")).encode("utf-8")).hexdigest())'
}
verify_redis_contract() {
    PHASE=$1
    REDIS_IMAGE=public.ecr.aws/docker/library/redis@sha256:63d5174750e285bc3069c4519c53c8b6de6ebe70715140a6c9d21d6f04b77319
    CACHE_HASH_NEW=$(compose config --hash redis-cache | awk 'NR == 1 && $1 == "redis-cache" {print $2}')
    QUEUE_HASH_NEW=$(compose config --hash redis-queue | awk 'NR == 1 && $1 == "redis-queue" {print $2}')
    valid_hash64 "$CACHE_HASH_NEW" && valid_hash64 "$QUEUE_HASH_NEW" || return 1
    CACHE_HASH_CURRENT=$(docker_cli container inspect "$PROJECT-redis-cache-1" --format '{{index .Config.Labels "com.docker.compose.config-hash"}}')
    QUEUE_HASH_CURRENT=$(docker_cli container inspect "$PROJECT-redis-queue-1" --format '{{index .Config.Labels "com.docker.compose.config-hash"}}')
    valid_hash64 "$CACHE_HASH_CURRENT" && valid_hash64 "$QUEUE_HASH_CURRENT" || return 1
    if [ "$PHASE" = after ]; then
        [ "$CACHE_HASH_CURRENT" = "$CACHE_HASH_NEW" ] && [ "$QUEUE_HASH_CURRENT" = "$QUEUE_HASH_NEW" ] || return 1
    else
        [ "$CACHE_HASH_CURRENT" = "$CACHE_CONFIG_HASH_BEFORE" ] || [ "$CACHE_HASH_CURRENT" = "$CACHE_HASH_NEW" ] || return 1
        [ "$QUEUE_HASH_CURRENT" = "$QUEUE_CONFIG_HASH_BEFORE" ] || [ "$QUEUE_HASH_CURRENT" = "$QUEUE_HASH_NEW" ] || return 1
    fi
    [ "$(docker_cli container inspect "$PROJECT-redis-cache-1" --format '{{.Config.Image}}')" = "$REDIS_IMAGE" ] || return 1
    [ "$(docker_cli container inspect "$PROJECT-redis-queue-1" --format '{{.Config.Image}}')" = "$REDIS_IMAGE" ] || return 1
    QUEUE_MOUNT=$(docker_cli container inspect "$PROJECT-redis-queue-1" --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Type}}:{{.Name}}:{{.Destination}}:{{.RW}}{{end}}{{end}}')
    [ "$QUEUE_MOUNT" = volume:crm_trial_c010400_redis:/data:true ]
}
resume_infrastructure() {
    verify_redis_contract before || return 1
    compose up -d --wait db redis-cache redis-queue || return 1
    verify_infrastructure
}
write_redis_evidence() {
    CACHE_AFTER=$(docker_cli container inspect "$PROJECT-redis-cache-1" --format '{{.Id}}')
    QUEUE_AFTER=$(docker_cli container inspect "$PROJECT-redis-queue-1" --format '{{.Id}}')
    valid_hash64 "$CACHE_AFTER" && valid_hash64 "$QUEUE_AFTER" || return 1
    if [ "$CACHE_CONFIG_HASH_BEFORE" = "$CACHE_HASH_NEW" ]; then
        [ "$CACHE_AFTER" = "$CACHE_BEFORE" ] || return 1
    fi
    if [ "$QUEUE_CONFIG_HASH_BEFORE" = "$QUEUE_HASH_NEW" ]; then
        [ "$QUEUE_AFTER" = "$QUEUE_BEFORE" ] || return 1
    fi
    EXPECTED="cache_old=$CACHE_BEFORE cache_new=$CACHE_AFTER hash=$CACHE_HASH_NEW
queue_old=$QUEUE_BEFORE queue_new=$QUEUE_AFTER hash=$QUEUE_HASH_NEW"
    if [ -e "$REDIS_EVIDENCE" ] || [ -L "$REDIS_EVIDENCE" ]; then
        [ -f "$REDIS_EVIDENCE" ] && [ ! -L "$REDIS_EVIDENCE" ] && [ "$(cat "$REDIS_EVIDENCE")" = "$EXPECTED" ]
        return
    fi
    (umask 077 && set -C && printf '%s\n' "$EXPECTED" > "$REDIS_EVIDENCE_TEMP") && mv "$REDIS_EVIDENCE_TEMP" "$REDIS_EVIDENCE"
}
write_app_context() {
    (umask 077 && set -C && printf '%s\n' \
      "ENV_SHA256=$ENV_BEFORE" \
      "DB_CONTAINER_ID=$DB_BEFORE" \
      "CACHE_CONTAINER_ID=$CACHE_BEFORE" \
      "CACHE_CONFIG_HASH=$CACHE_CONFIG_HASH_BEFORE" \
      "QUEUE_CONTAINER_ID=$QUEUE_BEFORE" \
      "QUEUE_CONFIG_HASH=$QUEUE_CONFIG_HASH_BEFORE" \
      "SITE_CONFIG_SHA256=$SITE_CONFIG_BEFORE" \
      "SITE_CONFIG_FINGERPRINT=$SITE_CONFIG_FINGERPRINT" \
      "MAINTENANCE_MODE=$MAINTENANCE_BEFORE" > "$UPDATE_CONTEXT_TEMP") && mv "$UPDATE_CONTEXT_TEMP" "$UPDATE_CONTEXT"
}
load_app_context() {
    ENV_BEFORE=$(release_value ENV_SHA256 "$UPDATE_CONTEXT")
    DB_BEFORE=$(release_value DB_CONTAINER_ID "$UPDATE_CONTEXT")
    CACHE_BEFORE=$(release_value CACHE_CONTAINER_ID "$UPDATE_CONTEXT")
    CACHE_CONFIG_HASH_BEFORE=$(release_value CACHE_CONFIG_HASH "$UPDATE_CONTEXT")
    QUEUE_BEFORE=$(release_value QUEUE_CONTAINER_ID "$UPDATE_CONTEXT")
    QUEUE_CONFIG_HASH_BEFORE=$(release_value QUEUE_CONFIG_HASH "$UPDATE_CONTEXT")
    SITE_CONFIG_BEFORE=$(release_value SITE_CONFIG_SHA256 "$UPDATE_CONTEXT")
    SITE_CONFIG_FINGERPRINT=$(release_value SITE_CONFIG_FINGERPRINT "$UPDATE_CONTEXT")
    MAINTENANCE_BEFORE=$(release_value MAINTENANCE_MODE "$UPDATE_CONTEXT")
    valid_hash64 "$DB_BEFORE" && valid_hash64 "$CACHE_BEFORE" && valid_hash64 "$QUEUE_BEFORE" &&
      valid_hash64 "$CACHE_CONFIG_HASH_BEFORE" && valid_hash64 "$QUEUE_CONFIG_HASH_BEFORE" &&
      valid_hash64 "$SITE_CONFIG_FINGERPRINT" || return 1
    [ "$MAINTENANCE_BEFORE" = 0 ] || [ "$MAINTENANCE_BEFORE" = 1 ]
}
failed_metadata_allowed() {
    FAILED=$1
    CANDIDATE=$2
    BACKUP=$3
    [ -f "$FAILED" ] && [ ! -L "$FAILED" ] || return 1
    cmp -s "$FAILED" "$CANDIDATE" && return 0
    [ -f "$BACKUP" ] && [ ! -L "$BACKUP" ] && cmp -s "$FAILED" "$BACKUP"
}
resume_preflight() {
    [ -f "$RUNTIME/site-update.state" ] && [ ! -L "$RUNTIME/site-update.state" ] || fail 'app resume requires retained maintenance state'
    STATE=$(cat "$RUNTIME/site-update.state")
    case "$STATE" in
        maintenance\ reason=*" image=$NEW_CONFIG"*) ;;
        *) fail 'app resume only accepts maintenance for the same reviewed generation' ;;
    esac
    for REQUIRED in "$UPDATE_CONTEXT" "$BACKUP_PROOF" "$UPDATE_BACKUP"; do
        [ -f "$REQUIRED" ] && [ ! -L "$REQUIRED" ] || fail "app resume evidence is missing or unsafe: $REQUIRED"
    done
    [ "$(cat "$UPDATE_BACKUP")" = "$(cat "$IMAGE_FILE")" ] || fail 'app resume current lock does not match the retained previous lock'
    [ "$(cat "$BACKUP_PROOF")" = "backup-four-readable image=$NEW_CONFIG" ] || fail 'app resume backup proof does not match this generation'
    for EVIDENCE in "$UPDATE_STATE_BACKUP" "$UPDATE_RELEASE_BACKUP" "$UPDATE_LAYERS_BACKUP" "$REDIS_EVIDENCE"; do
        if [ -e "$EVIDENCE" ] || [ -L "$EVIDENCE" ]; then
            [ -f "$EVIDENCE" ] && [ ! -L "$EVIDENCE" ] || fail "app resume evidence must be ordinary and non-symlink: $EVIDENCE"
        fi
    done
    if [ -e "$FAILED_RELEASE" ] || [ -L "$FAILED_RELEASE" ]; then
        failed_metadata_allowed "$FAILED_RELEASE" "$NEW_RELEASE" "$UPDATE_RELEASE_BACKUP" || fail 'failed release evidence is neither the reviewed candidate nor the retained previous generation'
    fi
    if [ -e "$FAILED_LAYERS" ] || [ -L "$FAILED_LAYERS" ]; then
        failed_metadata_allowed "$FAILED_LAYERS" "$NEW_LAYERS" "$UPDATE_LAYERS_BACKUP" || fail 'failed layer evidence is neither the reviewed candidate nor the retained previous generation'
    fi
    if [ -e "$RUNTIME/.image.env.site-update-$NEW_CONFIG.tmp" ]; then
        [ "$(cat "$RUNTIME/.image.env.site-update-$NEW_CONFIG.tmp")" = "CRM_IMAGE=$NEW_CONFIG" ] || fail 'resume lock temporary content mismatch'
    fi
    if [ -e "$RUNTIME/.release.env.site-update-$NEW_CONFIG.tmp" ]; then
        cmp -s "$RUNTIME/.release.env.site-update-$NEW_CONFIG.tmp" "$NEW_RELEASE" || fail 'resume release temporary content mismatch'
    fi
    if [ -e "$RUNTIME/.image-rootfs-layers.site-update-$NEW_CONFIG.tmp" ]; then
        cmp -s "$RUNTIME/.image-rootfs-layers.site-update-$NEW_CONFIG.tmp" "$NEW_LAYERS" || fail 'resume layer temporary content mismatch'
    fi
    for CONFLICT in "$UPDATE_CONTEXT_TEMP" "$BACKUP_PROOF_TEMP" "$REDIS_EVIDENCE_TEMP" "$ROLLBACK_TEMP" \
      "$RUNTIME/.release.restore-$NEW_CONFIG.tmp" "$RUNTIME/.layers.restore-$NEW_CONFIG.tmp"; do
        [ ! -e "$CONFLICT" ] && [ ! -L "$CONFLICT" ] || fail "app resume temporary conflict: $CONFLICT"
    done
}
update_site_image() {
    if [ "$UPGRADE_APPS" -eq 1 ]; then
        [ "$CONFIRM_SITE_APP_UPGRADE" -eq 1 ] || fail 'site app upgrade requires --confirm-site-app-upgrade'
    else
        [ "$CONFIRM_SITE_UPDATE" -eq 1 ] || fail 'site image update requires --confirm-site-image-update'
    fi
    case "$UPDATE_RELEASE_DIR" in /*) ;; *) fail 'reviewed release directory must be absolute' ;; esac
    case "$IMAGE_ARCHIVE" in /*) ;; *) fail 'reviewed image archive must be absolute' ;; esac
    [ -d "$UPDATE_RELEASE_DIR" ] && [ ! -L "$UPDATE_RELEASE_DIR" ] || fail 'reviewed release directory must be real and non-symlink'
    NEW_RELEASE=$UPDATE_RELEASE_DIR/release.env
    NEW_LAYERS=$UPDATE_RELEASE_DIR/image-rootfs-layers.txt
    [ -f "$NEW_RELEASE" ] && [ ! -L "$NEW_RELEASE" ] || fail 'reviewed release.env is required'
    [ -f "$NEW_LAYERS" ] && [ ! -L "$NEW_LAYERS" ] || fail 'reviewed RootFS layer list is required'
    [ -f "$IMAGE_ARCHIVE" ] && [ ! -L "$IMAGE_ARCHIVE" ] || fail 'reviewed image archive must be an ordinary non-symlink file'
    NEW_CONFIG=$(release_value CRM_IMAGE_CONFIG "$NEW_RELEASE")
    NEW_INDEX=$(release_value CRM_IMAGE_INDEX "$NEW_RELEASE")
    NEW_MANIFEST=$(release_value CRM_IMAGE_PLATFORM_MANIFEST "$NEW_RELEASE")
    NEW_ARCHIVE_SHA=$(release_value CRM_IMAGE_ARCHIVE_SHA256 "$NEW_RELEASE")
    NEW_RESOURCE=$(release_value CRM_RESOURCE_IMPORT_COMMIT "$NEW_RELEASE")
    NEW_TEAM=$(release_value CRM_TEAM_ACCESS_COMMIT "$NEW_RELEASE")
    NEW_CRM=$(release_value CRM_UPSTREAM_CRM_COMMIT "$NEW_RELEASE")
    for DIGEST in "$NEW_CONFIG" "$NEW_INDEX" "$NEW_MANIFEST" "$NEW_ARCHIVE_SHA"; do
        valid_sha256 "$DIGEST" || fail 'reviewed release contains an invalid digest'
    done
    for REVISION in "$NEW_RESOURCE" "$NEW_TEAM" "$NEW_CRM"; do
        valid_revision "$REVISION" || fail 'reviewed release contains an invalid source revision'
    done
    awk 'substr($0, 1, 7) != "sha256:" || length($0) != 71 || substr($0, 8) !~ /^[0-9a-f]+$/ {bad=1} {count++} END {exit bad || count < 1}' "$NEW_LAYERS" || fail 'reviewed RootFS layer list is empty or invalid'
    ARCHIVE_HASH=$(sha256sum "$IMAGE_ARCHIVE")
    ARCHIVE_HASH=sha256:${ARCHIVE_HASH%% *}
    [ "$ARCHIVE_HASH" = "$NEW_ARCHIVE_SHA" ] || fail 'reviewed image archive SHA mismatch'
    command -v python3 >/dev/null 2>&1 || fail 'Python 3 standard library is required for offline archive chain verification'
    python3 "$REMOTE/verify_image_archive.py" "$IMAGE_ARCHIVE" "$NEW_RELEASE" "$NEW_LAYERS" || fail 'reviewed archive digest chain verification failed'
    set_update_paths
    [ ! -L "$RUNTIME/site-update.state" ] || fail 'site-update.state must not be a symlink; refuse any update write'
    if [ "$RESUME_APPS" -eq 1 ]; then
        resume_preflight
    else
        if [ -e "$RUNTIME/site-update.state" ]; then
            CURRENT_LOCK=$(cat "$IMAGE_FILE")
            [ "$(cat "$RUNTIME/site-update.state")" = ready ] || [ "$(cat "$RUNTIME/site-update.state")" = "ready image=${CURRENT_LOCK#CRM_IMAGE=}" ] || fail 'repeat update requires a clean ready state matching the current lock; do not edit or delete maintenance state to bypass it'
        else
            for EVIDENCE in "$RUNTIME/release.env" "$RUNTIME/image-rootfs-layers.txt" \
              "$RUNTIME/image.env.pre-site-update" "$RUNTIME/failed-release.env" "$RUNTIME/failed-image-rootfs-layers.txt" \
              "$RUNTIME"/image.env.pre-site-update-* "$RUNTIME"/site-update.state.pre-* \
              "$RUNTIME"/release.pre-* "$RUNTIME"/image-rootfs-layers.pre-* \
              "$RUNTIME"/failed-release-* "$RUNTIME"/failed-image-rootfs-layers-* \
              "$RUNTIME"/app-upgrade-context-* "$RUNTIME"/backup-ready-* "$RUNTIME"/redis-replacement-*; do
                [ ! -e "$EVIDENCE" ] && [ ! -L "$EVIDENCE" ] || fail "update evidence exists without state; refuse first-only bypass: $EVIDENCE"
            done
        fi
        for CONFLICT in "$UPDATE_BACKUP" "$UPDATE_STATE_BACKUP" "$UPDATE_RELEASE_BACKUP" "$UPDATE_LAYERS_BACKUP" \
          "$FAILED_RELEASE" "$FAILED_LAYERS" "$ROLLBACK_TEMP" \
          "$UPDATE_CONTEXT" "$UPDATE_CONTEXT_TEMP" "$BACKUP_PROOF" "$BACKUP_PROOF_TEMP" "$REDIS_EVIDENCE" "$REDIS_EVIDENCE_TEMP" \
          "$RUNTIME/.image.env.site-update-$NEW_CONFIG.tmp" \
          "$RUNTIME/.release.env.site-update-$NEW_CONFIG.tmp" "$RUNTIME/.image-rootfs-layers.site-update-$NEW_CONFIG.tmp" \
          "$RUNTIME/.release.restore-$NEW_CONFIG.tmp" "$RUNTIME/.layers.restore-$NEW_CONFIG.tmp" \
          "$RUNTIME/.site-update.state.$NEW_CONFIG.tmp"; do
            [ ! -e "$CONFLICT" ] && [ ! -L "$CONFLICT" ] || fail "site update generation target/temporary/backup conflict must be resolved before any runtime change: $CONFLICT"
        done
    fi
    require_runtime
    [ "$CRM_IMAGE" = "$CRM_IMAGE_CONFIG" ] || fail 'running-site update only accepts the existing classic config lock'
    [ "$NEW_CONFIG" != "$CRM_IMAGE_CONFIG" ] || fail 'reviewed update must select a different config; no-op update refused'
    require_marker migrated-twice
    require_docker
    if [ "$RESUME_APPS" -eq 1 ]; then
        load_app_context || fail 'retained app upgrade context is invalid'
        [ "$ENV_BEFORE" = "$(sha256sum "$ENV_FILE")" ] || fail 'credentials changed since the retained app upgrade context'
        [ "$DB_BEFORE" = "$(docker_cli container inspect "$PROJECT-db-1" --format '{{.Id}}')" ] || fail 'DB identity changed since the retained app upgrade context'
        resume_infrastructure || fail 'unable to restore only DB/Redis for app resume; no old application service or configurator was started'
    else
        verify_running_app_images "$CRM_IMAGE" || fail 'current application image drift detected; refuse backup/load/update without any runtime change'
        verify_infrastructure || fail 'current DB/Redis are not healthy; refuse update before stopping writers'
        if [ -e "$RUNTIME/release.env" ]; then
            (umask 077 && set -C && cat "$RUNTIME/release.env" > "$UPDATE_RELEASE_BACKUP")
        fi
        if [ -e "$RUNTIME/image-rootfs-layers.txt" ]; then
            (umask 077 && set -C && cat "$RUNTIME/image-rootfs-layers.txt" > "$UPDATE_LAYERS_BACKUP")
        fi
        if [ -e "$RUNTIME/site-update.state" ]; then
            (umask 077 && set -C && cat "$RUNTIME/site-update.state" > "$UPDATE_STATE_BACKUP")
        fi
        ENV_BEFORE=$(sha256sum "$ENV_FILE")
        DB_BEFORE=$(docker_cli container inspect "$PROJECT-db-1" --format '{{.Id}}')
        CACHE_BEFORE=$(docker_cli container inspect "$PROJECT-redis-cache-1" --format '{{.Id}}')
        QUEUE_BEFORE=$(docker_cli container inspect "$PROJECT-redis-queue-1" --format '{{.Id}}')
        CACHE_CONFIG_HASH_BEFORE=$(docker_cli container inspect "$PROJECT-redis-cache-1" --format '{{index .Config.Labels "com.docker.compose.config-hash"}}')
        QUEUE_CONFIG_HASH_BEFORE=$(docker_cli container inspect "$PROJECT-redis-queue-1" --format '{{index .Config.Labels "com.docker.compose.config-hash"}}')
        SITE_CONFIG_BEFORE=$(compose exec -T backend sha256sum /home/frappe/frappe-bench/sites/crm.localhost/site_config.json)
        if [ "$UPGRADE_APPS" -eq 1 ]; then
            candidate_apps missing >/dev/null || fail 'current site/app baseline is invalid; HTTP readiness is not required for maintenance entry'
            MAINTENANCE_BEFORE=$(query_maintenance) || fail 'unable to classify current maintenance mode safely'
            SITE_CONFIG_FINGERPRINT=$(site_config_fingerprint) || fail 'unable to fingerprint site configuration without exposing values'
        fi
    fi
    if [ "$RESUME_APPS" -eq 0 ]; then
        verify_redis_contract before || fail 'Redis image/config-hash/volume contract mismatch before update'
    fi
    if [ "$RESUME_APPS" -eq 0 ]; then
        (umask 077 && set -C && cat "$NEW_RELEASE" > "$RUNTIME/.release.env.site-update-$NEW_CONFIG.tmp")
        (umask 077 && set -C && cat "$NEW_LAYERS" > "$RUNTIME/.image-rootfs-layers.site-update-$NEW_CONFIG.tmp")
        (umask 077 && set -C && cat "$IMAGE_FILE" > "$UPDATE_BACKUP")
        (umask 077 && set -C && printf 'CRM_IMAGE=%s\n' "$NEW_CONFIG" > "$RUNTIME/.image.env.site-update-$NEW_CONFIG.tmp")
    else
        [ ! -L "$RUNTIME/.release.env.site-update-$NEW_CONFIG.tmp" ] && [ ! -L "$RUNTIME/.image-rootfs-layers.site-update-$NEW_CONFIG.tmp" ] && [ ! -L "$RUNTIME/.image.env.site-update-$NEW_CONFIG.tmp" ] || fail 'resume metadata temporary must not be a symlink'
        if [ ! -e "$RUNTIME/.release.env.site-update-$NEW_CONFIG.tmp" ]; then
            (umask 077 && set -C && cat "$NEW_RELEASE" > "$RUNTIME/.release.env.site-update-$NEW_CONFIG.tmp")
        fi
        if [ ! -e "$RUNTIME/.image-rootfs-layers.site-update-$NEW_CONFIG.tmp" ]; then
            (umask 077 && set -C && cat "$NEW_LAYERS" > "$RUNTIME/.image-rootfs-layers.site-update-$NEW_CONFIG.tmp")
        fi
        if [ ! -e "$RUNTIME/.image.env.site-update-$NEW_CONFIG.tmp" ]; then
            (umask 077 && set -C && printf 'CRM_IMAGE=%s\n' "$NEW_CONFIG" > "$RUNTIME/.image.env.site-update-$NEW_CONFIG.tmp")
        fi
    fi
    UPDATE_MODE=image-only
    [ "$UPGRADE_APPS" -eq 0 ] || UPDATE_MODE=apps
    [ "$RESUME_APPS" -eq 0 ] || UPDATE_MODE=apps-resume
    write_state "updating image=$NEW_CONFIG mode=$UPDATE_MODE" || fail 'unable to record update start; no runtime action was taken'
    UPDATE_ACTIVE=1
    trap update_exit EXIT
    trap 'fail_update signal-hup' HUP
    trap 'fail_update signal-int' INT
    trap 'fail_update signal-term' TERM
    if [ "$UPGRADE_APPS" -eq 1 ] && [ "$RESUME_APPS" -eq 0 ]; then
        write_app_context || fail_update context-write-failed
    fi
    compose stop frontend websocket queue-short queue-long scheduler || fail_update stop-writers-failed
    if [ "$RESUME_APPS" -eq 0 ]; then
        backup
        if [ "$UPGRADE_APPS" -eq 1 ]; then
            (umask 077 && set -C && printf 'backup-four-readable image=%s\n' "$NEW_CONFIG" > "$BACKUP_PROOF_TEMP") && mv "$BACKUP_PROOF_TEMP" "$BACKUP_PROOF" || fail_update backup-proof-write-failed
        fi
    fi
    compose stop backend || fail_update stop-backend-failed
    docker_cli load -i "$IMAGE_ARCHIVE"
    verify_image_identity "$NEW_CONFIG" "$NEW_CONFIG" "$NEW_RESOURCE" "$NEW_TEAM" "$NEW_CRM" "$NEW_LAYERS"
    mv "$RUNTIME/.image.env.site-update-$NEW_CONFIG.tmp" "$IMAGE_FILE" || fail_update lock-rename-failed
    if [ "$UPGRADE_APPS" -eq 1 ]; then
        compose run --no-deps -T configurator || fail_update candidate-configurator-failed
        MISSING_JSON=$(candidate_apps missing) || fail_update candidate-app-query-failed
        MISSING_APPS=$(printf '%s' "$MISSING_JSON" | python3 -c 'import json,sys; value=json.load(sys.stdin); missing=value.get("missing"); assert set(value)=={"missing"} and isinstance(missing,list); assert all(app in ("resource_import","team_access","team_schedule") for app in missing); print(" ".join(missing))') || fail_update candidate-app-list-invalid
        for APP in $MISSING_APPS; do
            compose run --no-deps -T backend bench --site "$SITE" install-app "$APP" || fail_update "install-$APP-failed"
        done
        compose run --no-deps -T backend bench --site "$SITE" migrate || fail_update migrate-failed
        candidate_apps verify || fail_update schema-verification-failed
        MAINTENANCE_CURRENT=$(query_maintenance) || fail_update maintenance-query-failed
        if [ "$MAINTENANCE_CURRENT" != "$MAINTENANCE_BEFORE" ]; then
            [ "$MAINTENANCE_BEFORE" = 1 ] && [ "$MAINTENANCE_CURRENT" = 0 ] || fail_update maintenance-state-drift
        fi
        if [ "$MAINTENANCE_CURRENT" = 1 ]; then
            compose run --no-deps -T backend bench --site "$SITE" set-config maintenance_mode 0 || fail_update maintenance-resume-failed
            [ "$(query_maintenance)" = 0 ] || fail_update maintenance-resume-verification-failed
        fi
    fi
    compose up -d --wait || fail_update recreate-failed
    verify_running_app_images "$NEW_CONFIG" || fail_update application-image-mismatch
    verify_redis_contract after || fail_update redis-contract-changed
    write_redis_evidence || fail_update redis-evidence-changed
    verify_service_readiness || fail_update application-readiness-failed
    [ "$DB_BEFORE" = "$(docker_cli container inspect "$PROJECT-db-1" --format '{{.Id}}')" ] || fail_update db-container-changed
    [ "$ENV_BEFORE" = "$(sha256sum "$ENV_FILE")" ] || fail_update env-changed
    if [ "$UPGRADE_APPS" -eq 1 ]; then
        [ "$SITE_CONFIG_FINGERPRINT" = "$(site_config_fingerprint)" ] || fail_update site-config-changed
        if [ "$MAINTENANCE_BEFORE" = 0 ]; then
            [ "$SITE_CONFIG_BEFORE" = "$(compose exec -T backend sha256sum /home/frappe/frappe-bench/sites/crm.localhost/site_config.json)" ] || fail_update site-config-changed
        fi
    else
        [ "$SITE_CONFIG_BEFORE" = "$(compose exec -T backend sha256sum /home/frappe/frappe-bench/sites/crm.localhost/site_config.json)" ] || fail_update site-config-changed
    fi
    mv "$RUNTIME/.release.env.site-update-$NEW_CONFIG.tmp" "$RUNTIME/release.env" || fail_update release-rename-failed
    mv "$RUNTIME/.image-rootfs-layers.site-update-$NEW_CONFIG.tmp" "$RUNTIME/image-rootfs-layers.txt" || fail_update layers-rename-failed
    write_state "ready image=$NEW_CONFIG" || fail_update ready-state-write-failed
    UPDATE_ACTIVE=0
    trap - EXIT HUP INT TERM
    if [ "$UPGRADE_APPS" -eq 1 ]; then
        printf 'PASS: approved five apps, schema and service readiness verified; backup/old image/old lock retained; run check and business regression\n'
    else
        printf 'PASS: reviewed image loaded, all application services recreated consistently, backup/old image/old lock retained; run check and business regression\n'
    fi
}
maintenance_status() {
    if [ -f "$RUNTIME/site-update.state" ]; then
        cat "$RUNTIME/site-update.state"
    else
        printf 'no-persistent-site-update-state\n'
    fi
    if [ -f "$IMAGE_FILE" ]; then
        cat "$IMAGE_FILE"
    fi
}
maintenance_stop() {
    require_compose_materials
    require_docker
    STOP_RESULT=not-attempted
    if stop_maintenance; then
        STOP_RESULT=stopped
    else
        STOP_RESULT=stop-failed
    fi
    STATE_IMAGE=
    if [ -f "$RUNTIME/site-update.state" ]; then
        STATE_IMAGE=$(sed -n 's/.*image=\(sha256:[0-9a-f][0-9a-f]*\).*/\1/p' "$RUNTIME/site-update.state")
    fi
    if [ -z "$STATE_IMAGE" ]; then
        MANUAL_IMAGE=$(cat "$IMAGE_FILE")
        STATE_IMAGE=${MANUAL_IMAGE#CRM_IMAGE=}
    fi
    write_state "maintenance reason=manual-stop image=$STATE_IMAGE stop=$STOP_RESULT lock=unchanged metadata=unchanged" || fail "maintenance stop=$STOP_RESULT but state write failed; no persistence is claimed"
    [ "$STOP_RESULT" = stopped ] || fail 'maintenance stop failed; failure state was recorded, preserve resources'
    printf 'PASS: project stopped without requiring release metadata validation\n'
}
restore_old_lock() {
    [ "$CONFIRM_SITE_UPDATE" -eq 1 ] || fail 'maintenance lock recovery requires --confirm-site-image-update'
    require_compose_materials
    require_docker
    NEW_CONFIG=
    if [ -f "$RUNTIME/site-update.state" ]; then
        NEW_CONFIG=$(sed -n 's/.*image=\(sha256:[0-9a-f][0-9a-f]*\).*/\1/p' "$RUNTIME/site-update.state")
    fi
    if [ -n "$NEW_CONFIG" ]; then
        set_update_paths
    else
        UPDATE_BACKUP="$RUNTIME/image.env.pre-site-update"
        UPDATE_RELEASE_BACKUP="$RUNTIME/.no-previous-release"
        UPDATE_LAYERS_BACKUP="$RUNTIME/.no-previous-layers"
        FAILED_RELEASE="$RUNTIME/failed-release.env"
        FAILED_LAYERS="$RUNTIME/failed-image-rootfs-layers.txt"
        ROLLBACK_TEMP="$RUNTIME/.image.env.rollback.tmp"
    fi
    STOP_RESULT=not-attempted
    LOCK_RESULT=not-attempted
    META_RESULT=not-attempted
    stop_maintenance || true
    restore_previous_lock || true
    quarantine_metadata || true
    if [ "$META_RESULT" != quarantine-failed ]; then
        restore_previous_metadata || true
    fi
    write_state "maintenance reason=manual-old-lock-recovery image=${NEW_CONFIG:-legacy} stop=$STOP_RESULT lock=$LOCK_RESULT metadata=$META_RESULT"
    [ "$STOP_RESULT" = stopped ] && [ "$LOCK_RESULT" = restored ] && [ "$META_RESULT" != restore-failed ] && [ "$META_RESULT" != quarantine-failed ] || fail 'maintenance recovery incomplete; inspect maintenance-status and preserve resources'
    printf 'PASS: previous lock and current-generation metadata restored with project stopped; no old service was started\n'
}
inspect_volumes() {
    require_docker
    docker_cli volume inspect crm_trial_c010400_db crm_trial_c010400_redis crm_trial_c010400_sites crm_trial_c010400_logs
}

case "$ACTION" in
    verify-source) verify_source ;;
    init-env) init_env ;;
    load-image) load_image ;;
    check) check ;;
    migrate-image-lock-to-config) migrate_image_lock_to_config ;;
    update-site-image) update_site_image ;;
    upgrade-site-apps) update_site_image ;;
    resume-site-apps) update_site_image ;;
    create-site) create_site ;;
    up) up ;;
    install-extensions) install_extensions ;;
    migrate) migrate ;;
    enable-import) enable_import ;;
    backup) backup ;;
    versions) versions ;;
    status) require_runtime; require_docker; compose ps -a ;;
    inspect-volumes) inspect_volumes ;;
    maintenance-status) maintenance_status ;;
    maintenance-stop) maintenance_stop ;;
    restore-old-lock) restore_old_lock ;;
    stop) require_compose_materials; require_docker; compose stop; printf 'PASS: project stopped without release metadata validation; containers, image, network and all volumes retained\n' ;;
    -h|--help|help) usage ;;
    *) usage >&2; exit 2 ;;
esac

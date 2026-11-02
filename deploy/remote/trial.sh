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
if [ "$ACTION" = update-site-image ]; then
    [ "$#" -ge 2 ] || { printf 'update-site-image requires a reviewed release directory and image archive\n' >&2; exit 2; }
    UPDATE_RELEASE_DIR=$1
    IMAGE_ARCHIVE=$2
    shift 2
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

usage() {
    cat <<'EOF'
Usage: trial.sh ACTION [ARGS] [--confirm-synthetic-only] [--confirm-classic-image-lock-migration] [--confirm-site-image-update]
Actions:
  verify-source                 Verify the 53 exact app/build source files
  init-env                     Generate new 0600 credentials; never overwrite
  load-image ARCHIVE           Load a verified image archive through the selected Docker mode
  check                        Check Compose, locked image identity, platform, labels and RootFS
  migrate-image-lock-to-config One-time exact index-to-config lock migration; requires classic confirmation
  update-site-image DIR TAR    One-time reviewed image update with backup and rollback; requires confirmation
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
quarantine_metadata() {
    META_RESULT=quarantined
    FAILED_RELEASE=${FAILED_RELEASE:-$RUNTIME/failed-release.env}
    FAILED_LAYERS=${FAILED_LAYERS:-$RUNTIME/failed-image-rootfs-layers.txt}
    if [ -e "$RUNTIME/release.env" ] && [ ! -e "$FAILED_RELEASE" ] && [ ! -L "$FAILED_RELEASE" ]; then
        mv "$RUNTIME/release.env" "$FAILED_RELEASE" || META_RESULT=quarantine-failed
    fi
    if [ -e "$RUNTIME/image-rootfs-layers.txt" ] && [ ! -e "$FAILED_LAYERS" ] && [ ! -L "$FAILED_LAYERS" ]; then
        mv "$RUNTIME/image-rootfs-layers.txt" "$FAILED_LAYERS" || META_RESULT=quarantine-failed
    fi
    [ "$META_RESULT" = quarantined ]
}
restore_previous_metadata() {
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
    restore_previous_metadata || true
    write_state "maintenance reason=$REASON image=$NEW_CONFIG stop=$STOP_RESULT lock=$LOCK_RESULT metadata=$META_RESULT"
    printf 'ERROR: site update failed (%s); stop=%s lock=%s metadata=%s; do not resume the known-broken permission version\n' "$REASON" "$STOP_RESULT" "$LOCK_RESULT" "$META_RESULT" >&2
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
update_site_image() {
    [ "$CONFIRM_SITE_UPDATE" -eq 1 ] || fail 'site image update requires --confirm-site-image-update'
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
    if [ -e "$RUNTIME/site-update.state" ]; then
        CURRENT_LOCK=$(cat "$IMAGE_FILE")
        [ "$(cat "$RUNTIME/site-update.state")" = ready ] || [ "$(cat "$RUNTIME/site-update.state")" = "ready image=${CURRENT_LOCK#CRM_IMAGE=}" ] || fail 'repeat update requires a clean ready state matching the current lock; do not edit or delete maintenance state to bypass it'
    else
        for EVIDENCE in "$RUNTIME/release.env" "$RUNTIME/image-rootfs-layers.txt" \
          "$RUNTIME/image.env.pre-site-update" "$RUNTIME/failed-release.env" "$RUNTIME/failed-image-rootfs-layers.txt" \
          "$RUNTIME"/image.env.pre-site-update-* "$RUNTIME"/site-update.state.pre-* \
          "$RUNTIME"/release.pre-* "$RUNTIME"/image-rootfs-layers.pre-* \
          "$RUNTIME"/failed-release-* "$RUNTIME"/failed-image-rootfs-layers-*; do
            [ ! -e "$EVIDENCE" ] && [ ! -L "$EVIDENCE" ] || fail "update evidence exists without state; refuse first-only bypass: $EVIDENCE"
        done
    fi
    for CONFLICT in "$UPDATE_BACKUP" "$UPDATE_STATE_BACKUP" "$UPDATE_RELEASE_BACKUP" "$UPDATE_LAYERS_BACKUP" \
      "$FAILED_RELEASE" "$FAILED_LAYERS" "$ROLLBACK_TEMP" \
      "$RUNTIME/.image.env.site-update-$NEW_CONFIG.tmp" \
      "$RUNTIME/.release.env.site-update-$NEW_CONFIG.tmp" "$RUNTIME/.image-rootfs-layers.site-update-$NEW_CONFIG.tmp" \
      "$RUNTIME/.release.restore-$NEW_CONFIG.tmp" "$RUNTIME/.layers.restore-$NEW_CONFIG.tmp" \
      "$RUNTIME/.site-update.state.$NEW_CONFIG.tmp"; do
        [ ! -e "$CONFLICT" ] && [ ! -L "$CONFLICT" ] || fail "site update generation target/temporary/backup conflict must be resolved before any runtime change: $CONFLICT"
    done
    require_runtime
    [ "$CRM_IMAGE" = "$CRM_IMAGE_CONFIG" ] || fail 'running-site update only accepts the existing classic config lock'
    [ "$NEW_CONFIG" != "$CRM_IMAGE_CONFIG" ] || fail 'reviewed update must select a different config; no-op update refused'
    require_marker migrated-twice
    require_docker
    verify_running_app_images "$CRM_IMAGE" || fail 'current application image drift detected; refuse backup/load/update without any runtime change'
    if [ -e "$RUNTIME/release.env" ]; then
        (umask 077 && set -C && cat "$RUNTIME/release.env" > "$UPDATE_RELEASE_BACKUP")
    fi
    if [ -e "$RUNTIME/image-rootfs-layers.txt" ]; then
        (umask 077 && set -C && cat "$RUNTIME/image-rootfs-layers.txt" > "$UPDATE_LAYERS_BACKUP")
    fi
    if [ -e "$RUNTIME/site-update.state" ]; then
        (umask 077 && set -C && cat "$RUNTIME/site-update.state" > "$UPDATE_STATE_BACKUP")
    fi
    (umask 077 && set -C && cat "$NEW_RELEASE" > "$RUNTIME/.release.env.site-update-$NEW_CONFIG.tmp")
    (umask 077 && set -C && cat "$NEW_LAYERS" > "$RUNTIME/.image-rootfs-layers.site-update-$NEW_CONFIG.tmp")
    ENV_BEFORE=$(sha256sum "$ENV_FILE")
    DB_BEFORE=$(docker_cli container inspect "$PROJECT-db-1" --format '{{.Id}}')
    CACHE_BEFORE=$(docker_cli container inspect "$PROJECT-redis-cache-1" --format '{{.Id}}')
    QUEUE_BEFORE=$(docker_cli container inspect "$PROJECT-redis-queue-1" --format '{{.Id}}')
    SITE_CONFIG_BEFORE=$(compose exec -T backend sha256sum /home/frappe/frappe-bench/sites/crm.localhost/site_config.json)
    backup
    (umask 077 && set -C && cat "$IMAGE_FILE" > "$UPDATE_BACKUP")
    (umask 077 && set -C && printf 'CRM_IMAGE=%s\n' "$NEW_CONFIG" > "$RUNTIME/.image.env.site-update-$NEW_CONFIG.tmp")
    write_state "updating image=$NEW_CONFIG" || fail 'unable to record update start; no runtime action was taken'
    UPDATE_ACTIVE=1
    trap update_exit EXIT
    trap 'fail_update signal-hup' HUP
    trap 'fail_update signal-int' INT
    trap 'fail_update signal-term' TERM
    docker_cli load -i "$IMAGE_ARCHIVE"
    verify_image_identity "$NEW_CONFIG" "$NEW_CONFIG" "$NEW_RESOURCE" "$NEW_TEAM" "$NEW_CRM" "$NEW_LAYERS"
    mv "$RUNTIME/.image.env.site-update-$NEW_CONFIG.tmp" "$IMAGE_FILE" || fail_update lock-rename-failed
    compose up -d --wait || fail_update recreate-failed
    verify_running_app_images "$NEW_CONFIG" || fail_update application-image-mismatch
    [ "$DB_BEFORE" = "$(docker_cli container inspect "$PROJECT-db-1" --format '{{.Id}}')" ] || fail_update db-container-changed
    [ "$CACHE_BEFORE" = "$(docker_cli container inspect "$PROJECT-redis-cache-1" --format '{{.Id}}')" ] || fail_update redis-cache-container-changed
    [ "$QUEUE_BEFORE" = "$(docker_cli container inspect "$PROJECT-redis-queue-1" --format '{{.Id}}')" ] || fail_update redis-queue-container-changed
    [ "$ENV_BEFORE" = "$(sha256sum "$ENV_FILE")" ] || fail_update env-changed
    [ "$SITE_CONFIG_BEFORE" = "$(compose exec -T backend sha256sum /home/frappe/frappe-bench/sites/crm.localhost/site_config.json)" ] || fail_update site-config-changed
    mv "$RUNTIME/.release.env.site-update-$NEW_CONFIG.tmp" "$RUNTIME/release.env" || fail_update release-rename-failed
    mv "$RUNTIME/.image-rootfs-layers.site-update-$NEW_CONFIG.tmp" "$RUNTIME/image-rootfs-layers.txt" || fail_update layers-rename-failed
    write_state "ready image=$NEW_CONFIG" || fail_update ready-state-write-failed
    UPDATE_ACTIVE=0
    trap - EXIT HUP INT TERM
    printf 'PASS: reviewed image loaded, all application services recreated consistently, backup/old image/old lock retained; run check and business regression\n'
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
    restore_previous_metadata || true
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

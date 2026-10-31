#!/bin/sh
set -eu

REMOTE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$REMOTE/../.." && pwd)
RUNTIME=$REMOTE/.runtime
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

usage() {
    cat <<'EOF'
Usage: trial.sh ACTION [ARCHIVE] [--confirm-synthetic-only] [--confirm-classic-image-lock-migration]
Actions:
  verify-source                 Verify the 53 exact app/build source files
  init-env                     Generate new 0600 credentials; never overwrite
  load-image ARCHIVE           Load a verified image archive through the selected Docker mode
  check                        Check Compose, locked image identity, platform, labels and RootFS
  migrate-image-lock-to-config One-time exact index-to-config lock migration; requires classic confirmation
  create-site                  One-time new site; requires synthetic confirmation
  up                           Start/wait all trial services
  install-extensions           One-time resource_import then team_access install; requires confirmation
  migrate                      Run two full migrations, then clear cache
  enable-import                Enable the import entry after its safety baseline; requires confirmation
  backup                       Native backup --with-files and four-file readability check
  versions                     Show image app versions and installed-site apps
  status                       Show retained project containers
  inspect-volumes              Inspect the four retained trial volumes
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
require_runtime() {
    [ -f "$ENV_FILE" ] && [ ! -L "$ENV_FILE" ] || fail 'new trial credentials are missing; run init-env once, never reuse local credentials'
    [ -f "$IMAGE_FILE" ] && [ ! -L "$IMAGE_FILE" ] || fail 'trial image lock is missing'
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
    ACTUAL=$(docker_cli image inspect "$IMAGE" --format '{{.Id}}') || fail "locked image is unavailable: $EXPECTED_ID"
    [ "$ACTUAL" = "$EXPECTED_ID" ] || fail "loaded image ID does not match the exact lock: $EXPECTED_ID"
    [ "$(docker_cli image inspect "$IMAGE" --format '{{.Os}}/{{.Architecture}}')" = linux/amd64 ] || fail 'candidate image platform mismatch'
    [ "$(docker_cli image inspect "$IMAGE" --format '{{index .Config.Labels "crm.resource-import.revision"}}')" = "$CRM_RESOURCE_IMPORT_COMMIT" ] || fail 'resource_import revision label mismatch'
    [ "$(docker_cli image inspect "$IMAGE" --format '{{index .Config.Labels "crm.team-access.revision"}}')" = "$CRM_TEAM_ACCESS_COMMIT" ] || fail 'team_access revision label mismatch'
    [ "$(docker_cli image inspect "$IMAGE" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')" = "$CRM_UPSTREAM_CRM_COMMIT" ] || fail 'upstream CRM revision label mismatch'
    ACTUAL_LAYERS=$(docker_cli image inspect "$IMAGE" --format '{{range .RootFS.Layers}}{{println .}}{{end}}') || fail 'unable to read locked image RootFS layers'
    EXPECTED_LAYERS=$(cat "$REMOTE/image-rootfs-layers.txt")
    [ "$ACTUAL_LAYERS" = "$EXPECTED_LAYERS" ] || fail 'image RootFS diff_ids differ from the pinned config content; labels are not identity proof'
}
check() {
    require_runtime
    require_docker
    compose --profile setup config -q
    verify_image_identity "$CRM_IMAGE" "$CRM_IMAGE"
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
    verify_image_identity "$CRM_IMAGE_CONFIG" "$CRM_IMAGE_CONFIG"
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
    create-site) create_site ;;
    up) up ;;
    install-extensions) install_extensions ;;
    migrate) migrate ;;
    enable-import) enable_import ;;
    backup) backup ;;
    versions) versions ;;
    status) require_runtime; require_docker; compose ps -a ;;
    inspect-volumes) inspect_volumes ;;
    stop) require_runtime; require_docker; compose stop; printf 'PASS: project stopped; containers, image, network and all volumes retained\n' ;;
    -h|--help|help) usage ;;
    *) usage >&2; exit 2 ;;
esac

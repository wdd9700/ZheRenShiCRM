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
CONFIRM=0
if [ "${1:-}" = "--confirm-synthetic-only" ]; then
    CONFIRM=1
    shift
fi

usage() {
    cat <<'EOF'
Usage: trial.sh ACTION [--confirm-synthetic-only]
Actions:
  verify-source                 Verify the 53 exact app/build source files
  init-env                     Generate new 0600 credentials; never overwrite
  check                        Check Compose, loaded image ID and source labels
  create-site                  One-time new site; requires synthetic confirmation
  up                           Start/wait all trial services
  install-extensions           One-time resource_import then team_access install; requires confirmation
  migrate                      Run two full migrations, then clear cache
  enable-import                Enable the import entry after its safety baseline; requires confirmation
  backup                       Native backup --with-files and four-file readability check
  versions                     Show image app versions and installed-site apps
  status                       Show retained project containers
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
unset DB_PASSWORD ADMIN_PASSWORD FRAPPE_SITE_NAME CRM_TRIAL_SYNTHETIC_ONLY_ACK COMPOSE_PROJECT_NAME COMPOSE_FILE COMPOSE_PROFILES

require_docker() {
    [ -z "${DOCKER_HOST:-}" ] || fail 'DOCKER_HOST must be unset for the local trial daemon'
    command -v docker >/dev/null 2>&1 || fail 'Docker CLI is required; this script never installs it'
    [ "$(docker context show 2>/dev/null || printf unknown)" = default ] || fail 'use only the default local Docker context'
    docker compose version >/dev/null 2>&1 || fail 'Compose v2 is required'
    docker version --format '{{.Server.Version}}' >/dev/null 2>&1 || fail 'current user cannot access the local Docker daemon'
}
require_runtime() {
    [ -f "$ENV_FILE" ] && [ ! -L "$ENV_FILE" ] || fail 'new trial credentials are missing; run init-env once, never reuse local credentials'
    [ -f "$IMAGE_FILE" ] && [ ! -L "$IMAGE_FILE" ] || fail 'trial image lock is missing'
    [ "$(cat "$IMAGE_FILE")" = "CRM_IMAGE=$CRM_IMAGE" ] || fail 'trial image lock differs from release.env'
}
compose() {
    docker compose -p "$PROJECT" --env-file "$ENV_FILE" --env-file "$IMAGE_FILE" -f "$REMOTE/compose.yml" "$@"
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
    (umask 077 && set -C && printf 'CRM_IMAGE=%s\n' "$CRM_IMAGE" > "$IMAGE_FILE")
    unset DB_GENERATED ADMIN_GENERATED
    printf 'PASS: independent trial credentials and image lock created with private permissions; values not printed\n'
}
check() {
    require_runtime
    require_docker
    compose --profile setup config -q
    ACTUAL=$(docker image inspect "$CRM_IMAGE" --format '{{.Id}}') || fail 'exact candidate image is not loaded'
    [ "$ACTUAL" = "$CRM_IMAGE" ] || fail 'loaded image ID mismatch'
    [ "$(docker image inspect "$CRM_IMAGE" --format '{{.Os}}/{{.Architecture}}')" = linux/amd64 ] || fail 'candidate image platform mismatch'
    [ "$(docker image inspect "$CRM_IMAGE" --format '{{index .Config.Labels "crm.resource-import.revision"}}')" = "$CRM_RESOURCE_IMPORT_COMMIT" ] || fail 'resource_import revision label mismatch'
    [ "$(docker image inspect "$CRM_IMAGE" --format '{{index .Config.Labels "crm.team-access.revision"}}')" = "$CRM_TEAM_ACCESS_COMMIT" ] || fail 'team_access revision label mismatch'
    [ "$(docker image inspect "$CRM_IMAGE" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')" = "$CRM_UPSTREAM_CRM_COMMIT" ] || fail 'upstream CRM revision label mismatch'
    printf 'PASS: Compose, exact linux/amd64 image ID and three source revision labels; runtime health not yet proven\n'
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
    CRM_TRIAL_DIR=$ROOT sh "$REMOTE/preflight.sh" --existing-dir
    CRM_TRIAL_SYNTHETIC_ONLY_ACK=confirmed-synthetic-only
    export CRM_TRIAL_SYNTHETIC_ONLY_ACK
    compose --profile setup run --name crm-trial-c010400-create-site create-site
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

case "$ACTION" in
    verify-source) verify_source ;;
    init-env) init_env ;;
    check) check ;;
    create-site) create_site ;;
    up) up ;;
    install-extensions) install_extensions ;;
    migrate) migrate ;;
    enable-import) enable_import ;;
    backup) backup ;;
    versions) versions ;;
    status) require_runtime; require_docker; compose ps -a ;;
    stop) require_runtime; require_docker; compose stop; printf 'PASS: project stopped; containers, image, network and all volumes retained\n' ;;
    -h|--help|help) usage ;;
    *) usage >&2; exit 2 ;;
esac

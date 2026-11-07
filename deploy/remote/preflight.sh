#!/bin/sh
set -eu

TRIAL_DIR=${CRM_TRIAL_DIR:-$HOME/crm-trial}
PROJECT=crm-trial-c010400
FAILURES=0

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    FAILURES=$((FAILURES + 1))
}
warn() {
    printf 'WARN: %s\n' "$*" >&2
}
pass() {
    printf 'PASS: %s\n' "$*"
}

if [ "${1:-}" = "--help" ]; then
    printf 'Usage: preflight.sh [--existing-dir]\nRead-only checks; never installs software or creates resources.\n'
    exit 0
fi
EXISTING_DIR=0
if [ "${1:-}" = "--existing-dir" ]; then
    EXISTING_DIR=1
    shift
fi
[ "$#" -eq 0 ] || { printf 'Usage: preflight.sh [--existing-dir]\n' >&2; exit 2; }
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=docker.sh
. "$SCRIPT_DIR/docker.sh"

printf 'INFO: trial directory=%s project=%s; no changes will be made\n' "$TRIAL_DIR" "$PROJECT"
[ "$(uname -m)" = "x86_64" ] && pass 'x86_64 architecture' || fail 'the pinned image requires x86_64/linux'
if [ -r /etc/os-release ]; then
    OS_ID=$( ( . /etc/os-release; printf '%s' "${ID:-unknown}" ) )
    OS_VERSION=$( ( . /etc/os-release; printf '%s' "${VERSION_ID:-unknown}" ) )
    [ "$OS_ID" = "alinux" ] && [ "$OS_VERSION" = "3" ] && pass 'Alibaba Cloud Linux 3' || fail "expected Alibaba Cloud Linux 3, found $OS_ID $OS_VERSION"
else
    fail '/etc/os-release is unavailable'
fi

MEM_TOTAL=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo 2>/dev/null || printf 0)
MEM_AVAILABLE=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo 2>/dev/null || printf 0)
SWAP_TOTAL=$(awk '/^SwapTotal:/ {print $2}' /proc/meminfo 2>/dev/null || printf 0)
MEM_TOTAL=${MEM_TOTAL:-0}
MEM_AVAILABLE=${MEM_AVAILABLE:-0}
SWAP_TOTAL=${SWAP_TOTAL:-0}
printf 'INFO: MemTotal=%sKiB MemAvailable=%sKiB SwapTotal=%sKiB\n' "$MEM_TOTAL" "$MEM_AVAILABLE" "$SWAP_TOTAL"
[ "$MEM_TOTAL" -ge 1572864 ] && pass 'at least 1.5GiB RAM detected' || fail 'less than 1.5GiB RAM; do not start this stack'
[ "$MEM_AVAILABLE" -ge 1048576 ] || warn 'less than 1GiB currently available or readable; OOM risk remains, stop other workload only through an authorized administrator'
[ "$SWAP_TOTAL" -gt 0 ] || warn 'no swap; this package will not add swap and cannot guarantee stability on a 1.8GiB host'
HOME_FREE=$(df -Pk "$HOME" | awk 'NR==2 {print $4}')
printf 'INFO: free space on home filesystem=%sKiB\n' "$HOME_FREE"
[ "$HOME_FREE" -ge 8388608 ] && pass 'at least 8GiB free on the home filesystem' || fail 'less than 8GiB free; retain headroom for image save/load, DB and backups'

for COMMAND in openssl sha256sum tar ss awk df; do
    command -v "$COMMAND" >/dev/null 2>&1 && pass "command $COMMAND" || fail "required command missing: $COMMAND"
done
if command -v python3 >/dev/null 2>&1 && PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))' 2>/dev/null); then
    printf 'INFO: host Python=%s; application Python remains inside the pinned image\n' "$PYTHON_VERSION"
    python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' || warn 'host Python is below 3.9 and is not suitable for M9 manage.py; remote shell tools do not require it'
else
    warn 'host Python is absent or unusable; remote shell tools do not require it, M9 manage.py is not used'
fi

if [ -e "$TRIAL_DIR" ] || [ -L "$TRIAL_DIR" ]; then
    if [ "$EXISTING_DIR" -eq 1 ] && [ -d "$TRIAL_DIR" ] && [ ! -L "$TRIAL_DIR" ]; then
        pass 'existing real trial directory accepted only for the create-site resource guard'
    else
        fail "trial path already exists; preserve it and investigate instead of overwriting: $TRIAL_DIR"
    fi
else
    pass 'trial path is absent'
fi

if ! command -v docker >/dev/null 2>&1; then
    fail 'Docker CLI is absent; administrator installation is still required'
else
    pass 'Docker CLI exists'
    if docker_cli compose version >/dev/null 2>&1; then
        docker_cli compose version
        pass 'Compose v2 exists in the selected access mode'
    else
        fail 'Compose v2 or selected Docker access failed; no privilege fallback is attempted'
    fi
    if [ "$(docker_cli context show 2>/dev/null || printf unknown)" = default ]; then
        pass 'default local Docker context'
    else
        fail 'Docker context is not default; refuse to target an ambiguous daemon'
    fi
    if docker_cli version --format '{{.Server.Version}}' >/dev/null 2>&1; then
        pass 'selected mode can access the local Docker daemon'
        DOCKER_ROOT=$(docker_cli info --format '{{.DockerRootDir}}')
        ROOT_FREE=$(df -Pk "$DOCKER_ROOT" | awk 'NR==2 {print $4}')
        printf 'INFO: DockerRootDir=%s free=%sKiB\n' "$DOCKER_ROOT" "$ROOT_FREE"
        [ "$ROOT_FREE" -ge 8388608 ] || fail 'less than 8GiB free on the Docker filesystem'
        for VOLUME in crm_trial_c010400_db crm_trial_c010400_redis crm_trial_c010400_sites crm_trial_c010400_logs; do
            if docker_cli volume inspect "$VOLUME" >/dev/null 2>&1; then
                fail "volume already exists and will be preserved: $VOLUME"
            else
                pass "volume absent: $VOLUME"
            fi
        done
        if docker_cli network inspect crm_trial_c010400_network >/dev/null 2>&1; then
            fail 'trial network already exists and will be preserved'
        else
            pass 'trial network absent'
        fi
        if docker_cli container inspect crm-trial-c010400-create-site >/dev/null 2>&1; then
            fail 'retained create-site container already exists; do not rerun initialization'
        else
            pass 'create-site container absent'
        fi
        EXISTING=$(docker_cli ps -a --filter "label=com.docker.compose.project=$PROJECT" --format '{{.Names}}')
        [ -z "$EXISTING" ] && pass 'no containers in the trial Compose project' || fail "trial project already has containers: $EXISTING"
    else
        fail 'local Docker daemon access failed in the selected mode; no privilege fallback or group change is attempted'
    fi
fi

if command -v ss >/dev/null 2>&1; then
    if ss -ltnH '( sport = :8088 )' | awk 'NF {found=1} END {exit !found}'; then
        fail 'TCP port 8088 is already listening; identify the owner instead of replacing it'
    else
        pass 'TCP port 8088 is free'
    fi
fi

if [ "$FAILURES" -ne 0 ]; then
    printf 'PREFLIGHT NOT READY: %s failure(s); no software, directory, container, volume or system setting was changed\n' "$FAILURES" >&2
    exit 1
fi
printf 'PREFLIGHT READY: proceed only after authorization; 1.8GiB/no-swap stability and all runtime acceptance remain unverified\n'

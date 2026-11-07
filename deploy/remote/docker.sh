CRM_TRIAL_DOCKER_SUDO=${CRM_TRIAL_DOCKER_SUDO:-0}
case "$CRM_TRIAL_DOCKER_SUDO" in
    0|1) ;;
    *)
        printf 'ERROR: CRM_TRIAL_DOCKER_SUDO must be exactly 0 or 1\n' >&2
        exit 2
        ;;
esac
if [ -n "${DOCKER_HOST:-}" ] || [ -n "${DOCKER_CONTEXT:-}" ]; then
    printf 'ERROR: DOCKER_HOST and DOCKER_CONTEXT must be unset; only the default local daemon is allowed\n' >&2
    exit 1
fi
if [ "$CRM_TRIAL_DOCKER_SUDO" = 1 ] && ! command -v sudo >/dev/null 2>&1; then
    printf 'ERROR: CRM_TRIAL_DOCKER_SUDO=1 requires sudo -n; no privilege fallback is attempted\n' >&2
    exit 1
fi

docker_cli() {
    if [ "$CRM_TRIAL_DOCKER_SUDO" = 1 ]; then
        sudo -n docker "$@"
    else
        docker "$@"
    fi
}

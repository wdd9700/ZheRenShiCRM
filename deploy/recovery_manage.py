import argparse
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
PROJECT = "crm-recovery-b010200"
SOURCE = "crm-mvp-v15-backend-1"
VOLUMES = ["crm_recovery_b010200_" + suffix for suffix in ("db", "sites", "redis", "logs", "bundle", "keys", "receive_sites", "receive_logs")]
NETWORK = "crm_recovery_b010200_network"
RECEIVER = PROJECT + "-receive"
RESTORE = PROJECT + "-restore"


def run(*args, **kwargs):
    return subprocess.run(list(args), check=True, **kwargs)


def output(*args):
    return subprocess.check_output(list(args), text=True).strip()


def compose_command(image, confirm_synthetic_only=False):
    if not shutil.which("docker"):
        raise RuntimeError("Existing Docker CLI and Compose v2 are required")
    environment = {key: value for key, value in os.environ.items() if not key.startswith("COMPOSE_") and key not in ("CRM_IMAGE", "DB_PASSWORD", "ADMIN_PASSWORD", "CRM_RECOVERY_SYNTHETIC_ONLY_ACK")}
    environment["CRM_IMAGE"] = image
    environment["CRM_RECOVERY_SYNTHETIC_ONLY_ACK"] = "confirmed-synthetic-only" if confirm_synthetic_only else "not-confirmed"
    command = ["docker", "compose", "-p", PROJECT, "--env-file", os.devnull, "-f", str(ROOT / "compose.recovery.yml")]
    return command, environment


def check_config(image, confirm_synthetic_only=False):
    command, environment = compose_command(image, confirm_synthetic_only)
    result = subprocess.run(command + ["--profile", "setup", "config", "--format", "json"], env=environment, capture_output=True, text=True, check=True)
    config = json.loads(result.stdout)
    services = config["services"]
    if set(services) != {"recovery-db", "recovery-cache", "recovery-queue", "restore", "backend", "websocket", "frontend"}:
        raise RuntimeError("Recovery service allowlist changed; no scheduler/workers/integrations may run")
    infra = {
        "recovery-db": "public.ecr.aws/docker/library/mariadb@sha256:f1c56f035ed268a0d7c2c2e06dc879f6319b997cb434cf822a4cfd72a7aa184d",
        "recovery-cache": "public.ecr.aws/docker/library/redis@sha256:63d5174750e285bc3069c4519c53c8b6de6ebe70715140a6c9d21d6f04b77319",
        "recovery-queue": "public.ecr.aws/docker/library/redis@sha256:63d5174750e285bc3069c4519c53c8b6de6ebe70715140a6c9d21d6f04b77319",
    }
    app_mounts = {
        ("recovery_sites", "/home/frappe/frappe-bench/sites", False),
        ("recovery_logs", "/home/frappe/frappe-bench/logs", False),
    }
    mounts = {
        "recovery-db": {("recovery_db", "/var/lib/mysql", False), ("recovery_keys", "/run/recovery-keys", True)},
        "recovery-cache": set(), "recovery-queue": {("recovery_redis", "/data", False)},
        "backend": app_mounts, "websocket": app_mounts, "frontend": app_mounts,
        "restore": app_mounts | {("recovery_bundle", "/restore", True), ("recovery_keys", "/run/recovery-keys", True), (str(ROOT / "recovery_site.py"), "/opt/recovery_site.py", True)},
    }
    for name, service in services.items():
        if service["image"] != infra.get(name, image):
            raise RuntimeError("Recovery image differs from its fixed same-version source")
        labels = service.get("labels", {})
        if labels.get("crm.recovery.mission") != "M9" or labels.get("crm.recovery.run_id") != environment.get("CRM_RECOVERY_RUN_ID", "planning"):
            raise RuntimeError("Recovery service run labels changed")
        if set(service.get("networks", {})) != {"recovery"} or service.get("network_mode") or service.get("privileged") or service.get("cap_add"):
            raise RuntimeError("Recovery service must be confined to its own internal network without elevated privileges")
        actual = set()
        for volume in service.get("volumes", []):
            if volume["type"] not in ("volume", "bind"):
                raise RuntimeError("Recovery refuses an unexpected mount type")
            source = str(Path(volume["source"]).resolve()) if volume["type"] == "bind" else volume["source"]
            actual.add((source, volume["target"], bool(volume.get("read_only"))))
        if actual != mounts[name]:
            raise RuntimeError("Recovery service mount source/target/read-only allowlist changed")
        if name != "frontend" and service.get("ports"):
            raise RuntimeError("Only recovery frontend may publish a port")
    if services["restore"].get("environment", {}).get("CRM_RECOVERY_SYNTHETIC_ONLY_ACK") != environment["CRM_RECOVERY_SYNTHETIC_ONLY_ACK"]:
        raise RuntimeError("Recovery restore synthetic-only acknowledgement transport changed")
    ports = services["frontend"]["ports"]
    if len(ports) != 1 or ports[0].get("host_ip") != "127.0.0.1" or str(ports[0].get("published")) != "8089" or ports[0].get("target") != 8080:
        raise RuntimeError("Recovery must publish only loopback port 8089 to its frontend")
    if set(config["networks"]) != {"recovery"} or config["networks"]["recovery"].get("name") != NETWORK or not config["networks"]["recovery"].get("internal"):
        raise RuntimeError("Recovery network must prevent outbound integration traffic")
    expected_volumes = {"recovery_" + suffix: "crm_recovery_b010200_" + suffix for suffix in ("db", "sites", "redis", "logs", "bundle", "keys")}
    if {key: value["name"] for key, value in config["volumes"].items()} != expected_volumes:
        raise RuntimeError("Recovery must use only its exact isolated volume names")
    if any(value.get("driver_opts") for value in config["volumes"].values()):
        raise RuntimeError("Recovery refuses host/external storage driver overrides")
    print("PASS: local Compose isolation, image consistency, no background jobs, internal network and declared loopback port; runtime ingress still requires verification")
    return command, environment


def absent(kind, name):
    result = subprocess.run(["docker", kind, "inspect", name], capture_output=True, text=True)
    if result.returncode == 0:
        raise RuntimeError("Recovery refuses existing resources; preserve them and coordinate before retrying")
    message = result.stderr.lower()
    if not any(text in message for text in ("no such", "not found", "does not exist")):
        raise RuntimeError("Cannot safely determine whether recovery resources already exist")


def port_free():
    with socket.socket() as sock:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        sock.bind(("127.0.0.1", 8089))


def run_id():
    value = os.environ.get("CRM_RECOVERY_RUN_ID", "")
    if not re.fullmatch(r"[0-9a-f]{32}", value):
        raise RuntimeError("Runtime recovery requires a fresh explicit 32-hex CRM_RECOVERY_RUN_ID marker")
    return value


def owned(kind, name):
    data = json.loads(output("docker", kind, "inspect", name))[0]
    labels = data.get("Labels", {}) if kind in ("volume", "network") else data.get("Config", {}).get("Labels", {})
    if labels.get("com.docker.compose.project") != PROJECT or labels.get("crm.recovery.run_id") != run_id() or labels.get("crm.recovery.mission") != "M9":
        raise RuntimeError("Recovery resource labels/project/run marker mismatch; preserve conflicting resources")
    return data


def new_volumes():
    for name in VOLUMES:
        logical = "recovery_" + name.removeprefix("crm_recovery_b010200_")
        output("docker", "volume", "create", "--label", "com.docker.compose.project=" + PROJECT,
               "--label", "com.docker.compose.volume=" + logical, "--label", "crm.recovery.mission=M9",
               "--label", "crm.recovery.run_id=" + run_id(), name)
        owned("volume", name)


def receive(image, stem, source_project="crm-mvp-v15"):
    if source_project not in ("crm-mvp-v15", "crm-m9-source-c1102"):
        raise RuntimeError("Recovery accepts only the original project or the explicit isolated synthetic source")
    SOURCE = source_project + "-backend-1"
    if os.name == "nt":
        raise RuntimeError("Runtime recovery operations must run in the authorized first Ubuntu, not the Windows Docker daemon")
    run_id()
    if not re.fullmatch(r"[0-9]{8}_[0-9]{6}-crm_localhost", stem or ""):
        raise RuntimeError("Receive requires the exact timestamped crm.localhost backup stem")
    output("docker", "version", "--format", "{{.Server.Version}}")
    for name in VOLUMES:
        absent("volume", name)
    absent("network", NETWORK)
    for name in (RECEIVER, RESTORE, *(PROJECT + "-" + service + "-1" for service in ("backend", "frontend", "websocket", "recovery-db", "recovery-cache", "recovery-queue"))):
        absent("container", name)
    port_free()
    source_image = output("docker", "inspect", SOURCE, "--format", "{{.Image}}")
    labels = json.loads(output("docker", "inspect", SOURCE, "--format", "{{json .Config.Labels}}"))
    if source_image != image or labels.get("com.docker.compose.project") != source_project or labels.get("com.docker.compose.service") != "backend":
        raise RuntimeError("Recovery backup source project/service/security image mismatch")
    if source_project == "crm-m9-source-c1102" and (labels.get("crm.recovery.mission") != "M9" or labels.get("crm.recovery.run_id") != "b4a562ef23334fc0bdc41f3b90996a2d"):
        raise RuntimeError("Isolated synthetic source identity marker mismatch")
    versions = output("docker", "exec", SOURCE, "bench", "version")
    for line in ("frappe 15.125.0", "crm 1.90.0", "resource_import 0.1.0", "team_access 0.1.0"):
        if line not in versions.splitlines():
            raise RuntimeError("Source app versions do not match recovery target")
    apps = output("docker", "exec", SOURCE, "bench", "--site", "crm.localhost", "execute", "frappe.get_installed_apps")
    if set(json.loads(apps)) != {"frappe", "crm", "resource_import", "team_access"}:
        raise RuntimeError("Source must have both extension apps installed before recovery backup")
    if source_project == "crm-m9-source-c1102":
        check = "import json; from pathlib import Path; c=json.loads(Path('sites/crm.localhost/site_config.json').read_text()); print('confirmed' if type(c.get('team_access_synthetic_only')) is int and c['team_access_synthetic_only']==1 and c.get('resource_import_disabled')==1 and c.get('mute_emails')==1 and c.get('pause_scheduler')==1 else 'refused')"
        if output("docker", "exec", SOURCE, "env/bin/python", "-c", check) != "confirmed":
            raise RuntimeError("Isolated source must retain its explicit synthetic-only and disabled integration settings")
    new_volumes()
    names = {"database": stem + "-database.sql.gz", "public": stem + "-files.tar", "private": stem + "-private-files.tar", "config": stem + "-site_config_backup.json"}
    command = ["docker", "run", "-i", "--name", RECEIVER, "--network", "none", "--user", "0",
               "--label", "com.docker.compose.project=" + PROJECT, "--label", "crm.recovery.mission=M9", "--label", "crm.recovery.run_id=" + run_id()]
    for source, target in (("bundle", "/restore"), ("keys", "/run/recovery-keys"), ("receive_sites", "/home/frappe/frappe-bench/sites"), ("receive_logs", "/home/frappe/frappe-bench/logs")):
        command += ["--mount", f"type=volume,source=crm_recovery_b010200_{source},target={target}"]
    command += ["--mount", f"type=bind,source={ROOT / 'receive_recovery.py'},target=/opt/receive_recovery.py,readonly", "--entrypoint", "/home/frappe/frappe-bench/env/bin/python", image, "/opt/receive_recovery.py", "--image", image, "--run-id", run_id()]
    for kind, name in names.items():
        command += ["--" + kind, name]
    source = subprocess.Popen(["docker", "exec", SOURCE, "tar", "-C", "/home/frappe/frappe-bench/sites/crm.localhost/private/backups", "-cf", "-", *names.values()], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        receiver = subprocess.run(command, stdin=source.stdout, capture_output=True, text=True)
        source.stdout.close()
        _, error = source.communicate()
        if receiver.returncode or source.returncode:
            raise RuntimeError("Selected backup transfer failed; preserve all source/receiver resources")
    finally:
        if source.poll() is None:
            source.stdout.close()
            source.wait()
    import io
    import tarfile

    backup_dir = "/home/frappe/frappe-bench/sites/crm.localhost/private/backups"
    source_hashes = output("docker", "exec", "-w", backup_dir, SOURCE, "sha256sum", *names.values())
    expected = {line.split(maxsplit=1)[1].lstrip(" *"): line.split(maxsplit=1)[0] for line in source_hashes.splitlines()}
    manifest_tar = subprocess.check_output(["docker", "cp", RECEIVER + ":/restore/manifest.json", "-"])
    with tarfile.open(fileobj=io.BytesIO(manifest_tar)) as archive:
        members = archive.getmembers()
        if len(members) != 1 or not members[0].isfile():
            raise RuntimeError("Receiver manifest could not be verified privately")
        with archive.extractfile(members[0]) as stream:
            manifest = json.load(stream)
    for kind, name in names.items():
        target = {"database": "database.sql.gz", "public": "public-files.tar", "private": "private-files.tar", "config": "site-config.json"}[kind]
        if manifest["files"][target] != expected.get(name):
            raise RuntimeError("Source/receiver backup file checksum mismatch; preserve all resources")
    if manifest.get("run_id") != run_id() or manifest.get("image") != image:
        raise RuntimeError("Receiver run/source image marker mismatch")
    print("PASS: selected source/receiver backup bytes match; private bundle and source originals retained")


def verify_started(services, image):
    network = owned("network", NETWORK)
    if not network.get("Internal"):
        raise RuntimeError("Running recovery network is not internal")
    for service in services:
        data = owned("container", PROJECT + "-" + service + "-1")
        if data["Config"]["Labels"].get("com.docker.compose.service") != service or data["State"]["Status"] != "running":
            raise RuntimeError("Recovery service identity/state mismatch")
        if set(data["NetworkSettings"]["Networks"]) != {NETWORK}:
            raise RuntimeError("Recovery service attached to an unexpected network")
        if service in ("backend", "frontend", "websocket") and data["Image"] != image:
            raise RuntimeError("Running recovery app security image mismatch")


def restore(command, environment):
    if environment.get("CRM_RECOVERY_SYNTHETIC_ONLY_ACK") != "confirmed-synthetic-only":
        raise RuntimeError("Recovery requires the operator's explicit synthetic-only acknowledgement before runtime actions")
    if os.name == "nt":
        raise RuntimeError("Run runtime recovery only in the authorized first Ubuntu")
    run_id()
    image = environment["CRM_IMAGE"]
    for name in (RESTORE, *(PROJECT + "-" + service + "-1" for service in ("backend", "frontend", "websocket", "recovery-db", "recovery-cache", "recovery-queue"))):
        absent("container", name)
    receiver = owned("container", RECEIVER)
    if receiver["State"]["Status"] != "exited" or receiver["State"]["ExitCode"] != 0 or receiver["Image"] != image or receiver["HostConfig"]["NetworkMode"] != "none":
        raise RuntimeError("Recovery receiver must have completed this run/security image offline; do not retry partial attempts")
    for name in VOLUMES:
        owned("volume", name)
    absent("network", NETWORK)
    port_free()
    infra = ("recovery-db", "recovery-cache", "recovery-queue")
    run(*command, "up", "-d", "--wait", *infra, env=environment)
    verify_started(infra, image)
    run(*command, "--profile", "setup", "run", "--no-deps", "--name", RESTORE, "restore", env=environment)
    restored = owned("container", RESTORE)
    if restored["Image"] != image or restored["State"]["Status"] != "exited" or restored["State"]["ExitCode"] != 0 or set(restored["NetworkSettings"]["Networks"]) != {NETWORK}:
        raise RuntimeError("Retained recovery restore image/state/network mismatch")
    apps = ("backend", "websocket", "frontend")
    run(*command, "up", "-d", "--wait", *apps, env=environment)
    verify_started((*infra, *apps), image)
    print("PASS: isolated restore command and recovery services started; HTTP/business/permissions still require acceptance")


def main():
    parser = argparse.ArgumentParser(description="Non-destructive same-version isolated recovery; runtime actions require a tower window")
    parser.add_argument("action", choices=("check", "receive", "restore", "up", "stop", "status"))
    parser.add_argument("--image", required=True, help="Exact source security image ID, never an old image lacking either app")
    parser.add_argument("--backup-stem")
    parser.add_argument("--source-project", choices=("crm-mvp-v15", "crm-m9-source-c1102"), default="crm-mvp-v15", help="receive only: exact original or isolated synthetic source project")
    parser.add_argument("--confirm-isolated-recovery-window", action="store_true")
    parser.add_argument("--confirm-synthetic-only-data", action="store_true", help="restore only: explicitly acknowledge this run contains reviewed synthetic data only; not a data authenticity check")
    args = parser.parse_args()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", args.image):
        parser.error("--image must be an immutable SHA256 image ID")
    if args.action != "receive" and (args.backup_stem or args.source_project != "crm-mvp-v15"):
        parser.error("--backup-stem and --source-project apply only to receive")
    if args.confirm_synthetic_only_data and args.action != "restore":
        parser.error("--confirm-synthetic-only-data applies only to restore")
    if args.action == "restore" and not args.confirm_synthetic_only_data:
        parser.error("restore requires --confirm-synthetic-only-data for this reviewed synthetic-only run")
    command, environment = check_config(args.image, args.confirm_synthetic_only_data)
    if args.action == "check":
        return
    if not args.confirm_isolated_recovery_window:
        parser.error("Runtime actions require explicit --confirm-isolated-recovery-window and tower coordination")
    if args.action == "receive":
        receive(args.image, args.backup_stem, args.source_project)
    elif args.action == "restore":
        restore(command, environment)
    else:
        if os.name == "nt":
            raise RuntimeError("Run runtime recovery only in the authorized first Ubuntu")
        run_id()
        for name in VOLUMES:
            owned("volume", name)
        owned("network", NETWORK)
        ids = subprocess.check_output(command + ["ps", "-aq"], env=environment, text=True).split()
        for identifier in ids:
            data = owned("container", identifier)
            service = data["Config"]["Labels"].get("com.docker.compose.service")
            if service in ("restore", "backend", "websocket", "frontend") and data["Image"] != args.image:
                raise RuntimeError("Recovery app image changed; do not recreate an unverified target")
        if args.action == "up":
            restored = owned("container", RESTORE)
            if restored["State"]["Status"] != "exited" or restored["State"]["ExitCode"] != 0 or restored["Image"] != args.image:
                raise RuntimeError("A successful retained same-run/security-image restore container is required before recovery up")
            run(*command, "up", "-d", "--wait", "recovery-db", "recovery-cache", "recovery-queue", "backend", "websocket", "frontend", env=environment)
        elif args.action == "stop":
            run(*command, "stop", env=environment)
        else:
            run(*command, "ps", "-a", env=environment)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"ERROR: {type(error).__name__}; recovery stage not accepted; preserve all resources", file=sys.stderr)
        if isinstance(error, RuntimeError):
            print(str(error), file=sys.stderr)
        sys.exit(1)

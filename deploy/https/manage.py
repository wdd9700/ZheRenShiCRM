#!/usr/bin/python3
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import socket
import ssl
import subprocess
import sys
import tempfile

IP = "8.133.190.46"
NAME = "crm-public-ip"
SOURCE = Path(__file__).resolve().parent
CONFIG = Path("/etc/nginx/conf.d/crm-public-ip.conf")
STATE = Path("/var/lib/crm-acme")
LINEAGE = Path("/etc/crm-acme/production/live") / NAME
PYTHON = Path("/usr/bin/python3")
DOCKER = "/usr/bin/docker"
CERTBOT_MANIFEST = "certbot/certbot@sha256:1dc5b4a99cce916f154c706569baf062600d7dea13e0711e7d7e1461d6230e39"
CERTBOT_IMAGE = "sha256:f0cfa0056d76325c6a2d3f4dc4dc41449763a9ee1000ed11caf8dc180450144d"
CERTBOT_LAYERS = [
    "sha256:994456c4fd7b2b87346a81961efb4ce945a39592d32e0762b38768bca7c7d085",
    "sha256:742e38c37a3df8d7685f163c146ab948120a81e39dd97817addae56e878b6f1a",
    "sha256:7b7e15815a1df5e94833097b7f662b81e9d1395b4c874b79ff8001d05fae55a5",
    "sha256:dbb969ba5eafbfe83869528a067a90aae0fca8d7a8f6e9eed106d7298bce9402",
    "sha256:c6edf5fd8cce3ac362994993752f4cfc493faef52e67d9a2e0c4cf3c40323399",
    "sha256:955248e74edeeb0e5f3158014be92bfde37d3487cfe30992b90810e13eb9f370",
    "sha256:95262b5f9b6be14381302bad083cd05468d03a9cf0d709a86955e4612cbbfc3e",
    "sha256:8e0dba8acab96fd5dcf39e9e06e01f06b35333f2a1675cfb8a56b1d124e8eb70",
    "sha256:3ea642b31d7e4e8e2e03584c3b10ffb6816aa4bf911484dc58a12aaf6416e791",
    "sha256:76baeec31c5481e8560d00897997b8fe6509cb1a2e4192ab0c9b63c1eaba97c9",
    "sha256:308bc0f313206400ce42f8b82f39f14c5b68330c522e38f8d97bf3404d06b523",
]
TOOL = "/usr/local/lib/crm-https/manage.py"
MARKER = "# Managed by crm-https H010\n"


def run(*args, capture=False):
    result = subprocess.run([str(arg) for arg in args], check=True,
                            stdout=subprocess.PIPE if capture else None,
                            stderr=subprocess.STDOUT if capture else None)
    return result.stdout if capture else None


def check_runtime():
    if sys.version_info < (3, 6) or Path(sys.executable) != PYTHON:
        raise RuntimeError("run with /usr/bin/python3 (>=3.6); do not replace the system Python")


def check_nginx():
    version = run("nginx", "-v", capture=True).decode()
    match = re.search(r"nginx/(\d+)\.(\d+)\.(\d+)", version)
    if not match or tuple(map(int, match.groups())) < (1, 19, 3):
        raise RuntimeError("Nginx >=1.19.3 required; retain all TLS/cookie directives")


def private_directory(path):
    if path.is_symlink():
        raise RuntimeError("refusing symlink directory: {}".format(path))
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.stat().st_uid != 0:
        raise RuntimeError("directory is not root-owned: {}".format(path))
    path.chmod(0o700)


def container_args(network="bridge"):
    return [DOCKER, "--host", "unix:///var/run/docker.sock", "run", "--rm", "--pull=never",
            "--platform", "linux/amd64", "--user", "0:0", "--read-only",
            "--cap-drop=ALL", "--security-opt=no-new-privileges", "--network", network,
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m", "--env", "PYTHONDONTWRITEBYTECODE=1"]


def verified_image():
    inspected = json.loads(run(DOCKER, "--host", "unix:///var/run/docker.sock",
                               "image", "inspect", CERTBOT_IMAGE, capture=True).decode())
    if not isinstance(inspected, list) or len(inspected) != 1 or not isinstance(inspected[0], dict):
        raise RuntimeError("expected exactly one pinned Certbot image")
    image = inspected[0]
    if (image.get("Id") != CERTBOT_IMAGE or image.get("Os") != "linux"
            or image.get("Architecture") != "amd64"
            or image.get("RootFS") != {"Type": "layers", "Layers": CERTBOT_LAYERS}):
        raise RuntimeError("Certbot image differs from the reviewed official config/platform/RootFS")
    return CERTBOT_IMAGE


def check_certbot():
    image = verified_image()
    args = container_args("none")
    for target in ("/etc/letsencrypt", "/var/lib/letsencrypt", "/var/log/letsencrypt"):
        args += ["--mount", "type=tmpfs,destination=" + target]
    command = ("import sys; assert sys.version_info >= (3,10); "
               "print('Python ' + sys.version.split()[0], flush=True); "
               "from certbot.main import main; sys.exit(main(['--version']))")
    version = run(*(args + ["--entrypoint", "/usr/local/bin/python", image, "-c", command]), capture=True).decode()
    match = re.search(r"certbot (\d+)\.(\d+)", version)
    if not match or tuple(map(int, match.groups())) < (5, 4):
        raise RuntimeError("Certbot >=5.4 required for IP webroot")
    print(version.strip())


def certbot_args(environment):
    if environment not in ("staging", "production"):
        raise ValueError("invalid ACME environment")
    mounts = (("/etc/crm-acme/" + environment, "/etc/letsencrypt"),
              (str(STATE / environment), "/var/lib/letsencrypt"),
              ("/var/log/crm-acme/" + environment, "/var/log/letsencrypt"),
              (str(STATE / "webroot"), "/var/www/certbot"))
    args = container_args()
    for source, target in mounts:
        args += ["--mount", "type=bind,src={},dst={}".format(source, target)]
    return args + [verified_image(), "--config", "/dev/null", "--non-interactive",
                   "--config-dir", "/etc/letsencrypt", "--work-dir", "/var/lib/letsencrypt",
                   "--logs-dir", "/var/log/letsencrypt", "--server",
                   "https://acme-" + ("staging-" if environment == "staging" else "")
                   + "v02.api.letsencrypt.org/directory", "--cert-name", NAME]


def state_directory():
    private_directory(STATE)
    STATE.chmod(0o711)


def prepare_acme(environment):
    state_directory()
    private_directory(STATE / environment)
    for path in (Path("/etc/crm-acme"), Path("/var/log/crm-acme")):
        private_directory(path)
        private_directory(path / environment)


def certificate_check(minimum_seconds=172800):
    key = LINEAGE / "privkey.pem"
    mode = key.stat()
    if mode.st_uid != 0 or mode.st_mode & 0o077:
        raise RuntimeError("private key must be root-owned and not group/world accessible")
    run("openssl", "verify", "-purpose", "sslserver", "-verify_ip", IP,
        "-CApath", "/etc/ssl/certs", "-untrusted", LINEAGE / "chain.pem", LINEAGE / "cert.pem")
    run("openssl", "x509", "-in", LINEAGE / "cert.pem", "-noout", "-checkend", minimum_seconds)
    dates = run("openssl", "x509", "-in", LINEAGE / "cert.pem", "-noout", "-dates", capture=True).decode()
    values = [dt.datetime.strptime(line.split("=", 1)[1], "%b %d %H:%M:%S %Y %Z")
              for line in dates.strip().splitlines()]
    if len(values) != 2 or not 0 < (values[1] - values[0]).total_seconds() <= 160 * 3600 + 60:
        raise RuntimeError("certificate must use the <=160-hour shortlived profile")
    public_cert = run("openssl", "x509", "-in", LINEAGE / "cert.pem", "-pubkey", "-noout", capture=True)
    public_key = run("openssl", "pkey", "-in", key, "-pubout", capture=True)
    if public_cert != public_key:
        raise RuntimeError("certificate/key mismatch")


def served_check():
    import time

    expected = run("openssl", "x509", "-in", LINEAGE / "cert.pem", "-outform", "DER", capture=True)
    for attempt in range(6):
        with socket.create_connection(("127.0.0.1", 443), timeout=10) as connection:
            with ssl.create_default_context().wrap_socket(connection, server_hostname=IP) as tls:
                if tls.getpeercert(binary_form=True) == expected:
                    return
        if attempt < 5:
            time.sleep(1)
    raise RuntimeError("nginx is not serving the current production certificate")


def reload_nginx():
    certificate_check(86400)
    run("nginx", "-t")
    run("systemctl", "reload", "nginx")
    served_check()


def config_install(tls):
    if CONFIG.is_symlink():
        raise RuntimeError("refusing symlink config")
    previous = CONFIG.read_bytes() if CONFIG.exists() else None
    if previous is not None and not previous.startswith(MARKER.encode()):
        raise RuntimeError("refusing to overwrite unmanaged nginx configuration")
    content = MARKER + (SOURCE / "http.conf").read_text()
    if tls:
        content += "\n" + (SOURCE / "tls.conf").read_text()
    state_directory()
    backup = STATE / "rollback.conf"
    if previous is not None:
        if backup.is_symlink():
            raise RuntimeError("refusing symlink backup")
        backup.write_bytes(previous)
        backup.chmod(0o600)
    fd, temporary = tempfile.mkstemp(prefix=".crm-ip-", dir=CONFIG.parent)
    reload_attempted = False
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(content)
        os.chmod(temporary, 0o644)
        os.replace(temporary, CONFIG)
        try:
            run("nginx", "-t")
            if run("systemctl", "is-active", "nginx", capture=True).strip() != b"active":
                raise RuntimeError("nginx must already be active")
            reload_attempted = True
            run("systemctl", "reload", "nginx")
            if tls:
                served_check()
        except Exception:
            if previous is None:
                CONFIG.unlink()
            else:
                CONFIG.write_bytes(previous)
                CONFIG.chmod(0o644)
            if reload_attempted:
                run("nginx", "-t")
                run("systemctl", "reload", "nginx")
            raise
    finally:
        if Path(temporary).exists():
            Path(temporary).unlink()


def deploy_production():
    if CONFIG.exists() and "listen 443 ssl" in CONFIG.read_text():
        reload_nginx()
    else:
        certificate_check(86400)
        print("Production certificate ready; HTTPS activation remains a separate step")


def issue(environment, email=None, without_email=False):
    if bool(email) == bool(without_email) or (email and "@" not in email):
        raise ValueError("choose --email or --register-unsafely-without-email, never both")
    check_certbot()
    prepare_acme(environment)
    registration = ["--register-unsafely-without-email"] if without_email else ["--email", email]
    args = certbot_args(environment) + ["certonly", "--agree-tos"] + registration + [
        "--webroot", "--webroot-path", "/var/www/certbot",
        "--ip-address", IP, "--required-profile", "shortlived", "--preferred-challenges", "http-01",
        "--keep-until-expiring"]
    run(*args)
    if environment == "production":
        deploy_production()


def renew():
    check_certbot()
    run(*(certbot_args("production") + ["renew"]))
    certificate_check()
    try:
        served_check()
    except (RuntimeError, OSError):
        reload_nginx()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("preflight", "bootstrap", "issue-staging", "issue-production", "activate", "renew", "check"))
    registration = parser.add_mutually_exclusive_group()
    registration.add_argument("--email")
    registration.add_argument("--register-unsafely-without-email", action="store_true")
    args = parser.parse_args()
    if args.action.startswith("issue-"):
        if bool(args.email) == args.register_unsafely_without_email or (args.email and "@" not in args.email):
            parser.error("choose --email or --register-unsafely-without-email")
    elif args.email or args.register_unsafely_without_email:
        parser.error("registration options apply only to issue-staging/issue-production")
    check_runtime()
    if os.geteuid() != 0:
        parser.error("run as root on the server; no local forwarding is used")
    check_nginx()
    os.umask(0o077)
    if args.action == "preflight":
        check_certbot()
    elif args.action == "bootstrap":
        state_directory()
        webroot = STATE / "webroot"
        private_directory(webroot)
        webroot.chmod(0o755)
        config_install(False)
    elif args.action.startswith("issue-"):
        issue(args.action[len("issue-"):], args.email, args.register_unsafely_without_email)
    elif args.action == "activate":
        certificate_check(86400)
        config_install(True)
    elif args.action == "renew":
        renew()
    elif args.action == "check":
        certificate_check()
        served_check()
        run("systemctl", "is-active", "crm-ip-renew.timer")
        run("systemctl", "is-enabled", "crm-ip-renew.timer")
    print("crm-https {}: OK".format(args.action))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("crm-https FAILED: {}".format(error), file=sys.stderr)
        sys.exit(1)

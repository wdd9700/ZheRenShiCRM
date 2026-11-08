#!/usr/bin/env python3
import argparse
import datetime as dt
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
CERTBOT = Path("/opt/crm-certbot/bin/certbot")
TOOL = "/usr/local/lib/crm-https/manage.py"
MARKER = "# Managed by crm-https H010\n"


def run(*args, capture=False):
    result = subprocess.run([str(arg) for arg in args], check=True,
                            stdout=subprocess.PIPE if capture else None)
    return result.stdout if capture else None


def private_directory(path):
    if path.is_symlink():
        raise RuntimeError(f"refusing symlink directory: {path}")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.stat().st_uid != 0:
        raise RuntimeError(f"directory is not root-owned: {path}")
    path.chmod(0o700)


def check_certbot():
    version = run(CERTBOT, "--version", capture=True).decode()
    match = re.search(r"certbot (\d+)\.(\d+)", version)
    if not match or tuple(map(int, match.groups())) < (5, 4):
        raise RuntimeError("Certbot >=5.4 required for IP webroot")


def certbot_args(environment):
    if environment not in ("staging", "production"):
        raise ValueError("invalid ACME environment")
    return [str(CERTBOT), "--config", "/dev/null", "--non-interactive",
            "--config-dir", f"/etc/crm-acme/{environment}",
            "--work-dir", str(STATE / environment),
            "--logs-dir", f"/var/log/crm-acme/{environment}",
            "--server", "https://acme-" + ("staging-" if environment == "staging" else "")
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


def issue(environment, email):
    check_certbot()
    prepare_acme(environment)
    args = certbot_args(environment) + ["certonly", "--agree-tos", "--email", email,
        "--webroot", "--webroot-path", str(STATE / "webroot"),
        "--ip-address", IP, "--required-profile", "shortlived", "--preferred-challenges", "http-01",
        "--keep-until-expiring"]
    if environment == "production":
        args += ["--deploy-hook", f"{TOOL} deploy-hook"]
    run(*args)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("bootstrap", "issue-staging", "issue-production", "activate", "deploy-hook", "renew", "check"))
    parser.add_argument("--email")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("run as root on the server; no local forwarding is used")
    if args.action.startswith("issue-") and (not args.email or "@" not in args.email):
        parser.error("--email is required for the ACME account")
    os.umask(0o077)
    if args.action == "bootstrap":
        state_directory()
        webroot = STATE / "webroot"
        private_directory(webroot)
        webroot.chmod(0o755)
        config_install(False)
    elif args.action.startswith("issue-"):
        issue(args.action.removeprefix("issue-"), args.email)
    elif args.action == "activate":
        certificate_check(86400)
        config_install(True)
    elif args.action == "deploy-hook":
        if os.environ.get("RENEWED_LINEAGE") != str(LINEAGE):
            raise RuntimeError("unexpected renewal lineage; refusing reload")
        if CONFIG.exists() and "listen 443 ssl" in CONFIG.read_text():
            reload_nginx()
        else:
            certificate_check(86400)
            print("Production certificate ready; HTTPS activation remains a separate step")
    elif args.action == "renew":
        check_certbot()
        run(*(certbot_args("production") + ["renew", "--deploy-hook", f"{TOOL} deploy-hook"]))
        certificate_check()
        served_check()
    elif args.action == "check":
        certificate_check()
        served_check()
        run("systemctl", "is-active", "crm-ip-renew.timer")
        run("systemctl", "is-enabled", "crm-ip-renew.timer")
    print(f"crm-https {args.action}: OK")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"crm-https FAILED: {error}", file=sys.stderr)
        sys.exit(1)

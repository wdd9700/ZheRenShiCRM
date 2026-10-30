import argparse
import http.cookiejar
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parent
ENV = ROOT / ".env"
SITE = "crm.localhost"
BASE_URL = "http://127.0.0.1:8088"


def read_env():
    if not ENV.is_file():
        raise RuntimeError("Run init-env first; deploy/.env is missing")
    values = {}
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    for key in ("DB_PASSWORD", "ADMIN_PASSWORD"):
        value = values.get(key, "")
        if len(value) < 24 or value.startswith("replace-"):
            raise RuntimeError(f"Set a locally generated random {key} (24+ characters)")
    if values.get("FRAPPE_SITE_NAME") != SITE:
        raise RuntimeError(f"This local sandbox requires FRAPPE_SITE_NAME={SITE}")
    return values


def compose(*args):
    docker = shutil.which("docker")
    if docker and subprocess.run(
        [docker, "compose", "version"], capture_output=True
    ).returncode == 0:
        command = [docker, "compose"]
    elif shutil.which("docker-compose"):
        command = [shutil.which("docker-compose")]
    else:
        raise RuntimeError("Docker Compose is required; this script never installs it")
    image_lock = ROOT / ".runtime" / "image.env"
    if not image_lock.is_file():
        raise RuntimeError("Run build first; verified derived image lock is missing")
    image = image_lock.read_text(encoding="utf-8").strip().removeprefix("CRM_IMAGE=")
    if not image.startswith("sha256:") or len(image) != 71:
        raise RuntimeError("Derived image lock is invalid; run build again")
    environment = os.environ.copy()
    for key in ("DB_PASSWORD", "ADMIN_PASSWORD", "FRAPPE_SITE_NAME", "CRM_IMAGE"):
        environment.pop(key, None)
    return subprocess.run(
        command + ["-p", "crm-mvp-v15", "--env-file", str(ENV), "--env-file", str(image_lock), "-f", str(ROOT / "compose.yml"), *args],
        cwd=ROOT,
        env=environment,
        check=True,
    )


def build_image(proxy):
    command = ["docker", "build", "--network", "host", "--progress", "plain"]
    if proxy:
        address = urllib.parse.urlsplit(proxy)
        if address.hostname not in ("127.0.0.1", "localhost") or address.username or address.password:
            raise RuntimeError("Build proxy must be an authorized credential-free loopback endpoint")
        command += ["--build-arg", f"HTTP_PROXY={proxy}", "--build-arg", f"HTTPS_PROXY={proxy}", "--build-arg", "NO_PROXY=localhost,127.0.0.1"]
    command += ["-t", "crm-local:v1.90.0-r1", "-f", str(ROOT / "Dockerfile"), str(ROOT)]
    subprocess.run(command, check=True)
    image = subprocess.check_output(
        ["docker", "image", "inspect", "crm-local:v1.90.0-r1", "--format", "{{.Id}}"],
        text=True,
    ).strip()
    if not image.startswith("sha256:") or len(image) != 71:
        raise RuntimeError("Docker did not return an immutable derived image ID")
    runtime = ROOT / ".runtime"
    runtime.mkdir(exist_ok=True)
    (runtime / "image.env").write_text(f"CRM_IMAGE={image}\n", encoding="utf-8")
    print(f"Locked locally built CRM image: {image}")


def init_env():
    content = (
        f"DB_PASSWORD={secrets.token_urlsafe(32)}\n"
        f"ADMIN_PASSWORD={secrets.token_urlsafe(32)}\n"
        f"FRAPPE_SITE_NAME={SITE}\n"
    )
    descriptor = os.open(ENV, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
    print("Created deploy/.env with fresh local secrets; values are not printed")


def smoke(values, write_synthetic=False):
    cookies = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(cookies)
    )

    def request(path, data=None):
        return opener.open(
            urllib.request.Request(
                BASE_URL + path, data=data, headers={"Host": SITE}
            ),
            timeout=30,
        )

    with request("/api/method/ping") as response:
        if json.load(response).get("message") != "pong":
            raise RuntimeError("Health endpoint did not return pong")
    credentials = urllib.parse.urlencode(
        {"usr": "Administrator", "pwd": values["ADMIN_PASSWORD"]}
    ).encode()
    with request("/api/method/login", credentials) as response:
        if json.load(response).get("message") != "Logged In":
            raise RuntimeError("Login endpoint did not confirm Logged In")
    with request("/api/method/frappe.auth.get_logged_user") as response:
        if json.load(response).get("message") != "Administrator":
            raise RuntimeError("Authenticated session identity mismatch")
    with request("/crm") as response:
        html = response.read().decode("utf-8")
        if response.status != 200 or "<html" not in html.lower():
            raise RuntimeError("CRM HTML page was not served")
    import re

    assets = re.findall(r'src=["\'](/assets/crm/[^"\']+\.js)["\']', html)
    if not assets:
        raise RuntimeError("CRM HTML did not reference its built JavaScript asset")
    for asset in assets:
        with request(asset) as response:
            if response.status != 200 or "javascript" not in response.headers.get("Content-Type", ""):
                raise RuntimeError("CRM JavaScript asset was not served")
    print("PASS: pong, Administrator login/session, CRM HTML/JS assets (not full MVP acceptance)")
    if write_synthetic:
        query = urllib.parse.urlencode({"filters": json.dumps({"email": "bootstrap-smoke@example.invalid"})})
        with request("/api/resource/CRM%20Lead?" + query) as response:
            existing = json.load(response)["data"]
        if existing:
            name = existing[0]["name"]
        else:
            with request("/api/resource/CRM%20Lead%20Status?limit_page_length=1") as response:
                statuses = json.load(response)["data"]
            if not statuses:
                raise RuntimeError("CRM Lead Status seed data is missing")
            token = next((cookie.value for cookie in cookies if cookie.name == "csrf_token"), None)
            if not token:
                token_match = re.search(r'csrf_token["\'\]]*\s*[:=]\s*["\']([^"\']+)', html)
                token = token_match.group(1) if token_match else None
            if not token:
                raise RuntimeError("CRM session did not expose a CSRF token")
            payload = json.dumps({"first_name": "部署烟测合成人员", "organization": "合成公司（非真实客户）", "email": "bootstrap-smoke@example.invalid", "status": statuses[0]["name"]}).encode("utf-8")
            with opener.open(urllib.request.Request(BASE_URL + "/api/resource/CRM%20Lead", data=payload, headers={"Host": SITE, "Content-Type": "application/json", "X-Frappe-CSRF-Token": token}), timeout=30) as response:
                name = json.load(response)["data"]["name"]
        with request("/api/resource/CRM%20Lead/" + urllib.parse.quote(name, safe="")) as response:
            lead = json.load(response)["data"]
        if lead.get("first_name") != "部署烟测合成人员" or lead.get("email") != "bootstrap-smoke@example.invalid":
            raise RuntimeError("Synthetic Lead read-back mismatch")
        print(f"PASS: synthetic CRM Lead create/read {name}; retained, no delete performed")


def main():
    parser = argparse.ArgumentParser(description="Isolated, loopback-only Frappe CRM sandbox")
    parser.add_argument(
        "action",
        choices=("init-env", "build", "check", "pull", "create-site", "install-app", "up", "status", "stop", "smoke", "smoke-data"),
    )
    parser.add_argument("--proxy", help="Authorized credential-free loopback build proxy")
    args = parser.parse_args()
    action = args.action
    if action == "init-env":
        init_env()
        return
    if action == "build":
        build_image(args.proxy)
        return
    values = read_env()
    commands = {
        "check": ("--profile", "setup", "config", "-q"),
        "pull": ("pull", "db", "redis-cache", "redis-queue"),
        "create-site": ("--profile", "setup", "run", "--name", "crm-mvp-v15-create-site", "create-site"),
        "install-app": ("run", "--no-deps", "--name", "crm-mvp-v15-install-crm", "backend", "bench", "--site", SITE, "install-app", "crm"),
        "up": ("up", "-d", "--wait"),
        "status": ("ps", "-a"),
        "stop": ("stop",),
    }
    if action in ("smoke", "smoke-data"):
        smoke(values, write_synthetic=action == "smoke-data")
    else:
        compose(*commands[action])


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, urllib.error.URLError, subprocess.CalledProcessError) as error:
        print(f"ERROR: {type(error).__name__}; operation did not pass", file=sys.stderr)
        if isinstance(error, RuntimeError):
            print(str(error), file=sys.stderr)
        sys.exit(1)

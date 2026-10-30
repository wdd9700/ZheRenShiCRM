import argparse
import hashlib
import http.cookiejar
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import secrets
import stat
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parent
RUNTIME = Path(os.environ.get("CRM_DEPLOY_RUNTIME_DIR", ROOT / ".runtime"))
if not RUNTIME.is_absolute():
    raise RuntimeError("CRM_DEPLOY_RUNTIME_DIR must be an explicit absolute runtime directory")
ENV = RUNTIME / ".env"
if not ENV.exists() and "CRM_DEPLOY_RUNTIME_DIR" not in os.environ:
    ENV = ROOT / ".env"
SITE = "crm.localhost"
BASE_URL = "http://127.0.0.1:8088"


def plain_path(path, file=False):
    for component in (path, *path.parents):
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise RuntimeError("Runtime handoff refuses symlinks and reparse points")
    if file:
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise RuntimeError("Runtime handoff requires ordinary, non-hardlinked files")


def handoff_runtime(target_dir, secure_runtime_dir):
    if os.name != "nt":
        raise RuntimeError("Run runtime handoff with native Windows Python/PowerShell for Windows ACL enforcement; not through WSL/DrvFS")
    target = Path(target_dir)
    if not target.is_absolute() or ".." in target.parts or target.drive.startswith("\\\\"):
        raise RuntimeError("Runtime handoff requires an explicit absolute local deploy directory")
    plain_path(target)
    if not target.is_dir() or target.name != "deploy" or target.resolve() == ROOT:
        raise RuntimeError("Target must be another checkout's existing deploy directory")
    git = shutil.which("git")
    powershell = shutil.which("powershell.exe")
    if not git or not powershell:
        raise RuntimeError("Runtime handoff requires existing Git and Windows PowerShell")

    def git_result(*args):
        return subprocess.run([git, "-C", str(target.parent), *args], capture_output=True, text=True)

    root = git_result("rev-parse", "--show-toplevel")
    if root.returncode or Path(root.stdout.strip()).resolve() != target.parent.resolve():
        raise RuntimeError("Target deploy directory must be directly inside a Git checkout root")
    for name in ("manage.py", "compose.yml", "handoff-runtime.ps1"):
        path = target / name
        plain_path(path, file=True)
        tracked = git_result("ls-files", "--error-unmatch", "--", f"deploy/{name}")
        if tracked.returncode or hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).digest() != hashlib.sha256((ROOT / name).read_bytes().replace(b"\r\n", b"\n")).digest():
            raise RuntimeError("Target deployment code must already be tracked and match this handoff version; merge first")
    if (target / ".env").exists() or (target / ".env").is_symlink():
        raise RuntimeError("Target has a legacy deploy/.env; stop and reconcile existing materials explicitly, without overwriting")
    for relative in (".runtime/.env", ".runtime/image.env"):
        if git_result("check-ignore", "--quiet", "--no-index", "--", f"deploy/{relative}").returncode:
            raise RuntimeError("Each target runtime path must be Git-ignored before handoff")
        if git_result("ls-files", "--error-unmatch", "--", f"deploy/{relative}").returncode != 1:
            raise RuntimeError("Target runtime materials must not be tracked")
        path = target / relative
        plain_path(path)
        if path.exists():
            plain_path(path, file=True)
    for path in (ENV, ROOT / ".runtime" / "image.env"):
        plain_path(path, file=True)
    command = [powershell, "-NoProfile", "-NonInteractive", "-File", str(ROOT / "handoff-runtime.ps1"), "-SourceDir", str(ROOT), "-SourceEnv", str(ENV), "-TargetDir", str(target)]
    if secure_runtime_dir:
        command.append("-SecureRuntimeDir")
    copied = subprocess.run(command, capture_output=True, text=True)
    if copied.returncode:
        raise RuntimeError("Runtime handoff path/ACL/content check or exclusive copy failed; no source removed or existing file overwritten; retain partial targets for investigation")
    for action in ("check", "smoke"):
        result = subprocess.run([sys.executable, str(target / "manage.py"), action], cwd=target.parent, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f"Runtime copied privately but target {action} failed; do not clean source worktree or reinitialize the site")
        print(f"PASS: target {action}")
    print("PASS: runtime handoff verified from target; source retained; no credential text or digest logged")


def validate_runtime_override():
    if "CRM_DEPLOY_RUNTIME_DIR" not in os.environ:
        return
    if ".." in RUNTIME.parts or RUNTIME.name != ".runtime" or RUNTIME.parent.name != "deploy":
        raise RuntimeError("Runtime override must identify a checkout deploy/.runtime directory")
    plain_path(RUNTIME)
    plain_path(ENV, file=True)
    plain_path(RUNTIME / "image.env", file=True)
    checkout = RUNTIME.parent.parent
    git = shutil.which("git")
    if not git:
        raise RuntimeError("Git is required to validate a runtime override")
    def git_value(path, *args):
        result = subprocess.run([git, "-C", str(path), *args], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError("Runtime override checkout validation failed")
        return result.stdout.strip()
    if Path(git_value(checkout, "rev-parse", "--show-toplevel")).resolve() != checkout.resolve():
        raise RuntimeError("Runtime override must be directly inside a Git checkout")
    registered_roots = []
    for line in git_value(checkout, "-c", "core.quotePath=false", "worktree", "list", "--porcelain").splitlines():
        if not line.startswith("worktree "):
            continue
        path = line.removeprefix("worktree ")
        if os.name != "nt" and len(path) > 2 and path[1] == ":":
            wslpath = shutil.which("wslpath")
            if not wslpath:
                raise RuntimeError("Windows worktree paths require trusted wslpath normalization")
            converted = subprocess.run([wslpath, "-u", path], capture_output=True, text=True)
            if converted.returncode:
                raise RuntimeError("Windows worktree path normalization failed")
            path = converted.stdout.strip()
        registered_roots.append(Path(path).resolve())
    if ROOT.parent.resolve() not in registered_roots:
        raise RuntimeError("Runtime override must belong to this repository's registered worktree")
    for relative in ("deploy/.runtime/.env", "deploy/.runtime/image.env"):
        git_value(checkout, "check-ignore", "--no-index", "--", relative)
        if git_value(checkout, "ls-files", "--", relative):
            raise RuntimeError("Runtime override materials must be ignored and untracked")


def read_env():
    validate_runtime_override()
    if not ENV.is_file():
        raise RuntimeError("Local credentials missing; hand off existing runtime materials for an existing site, never regenerate its passwords")
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
    image_lock = RUNTIME / "image.env"
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
    command += ["-t", "crm-local:v1.90.0-resource-import-0.1.0", "-f", str(ROOT / "Dockerfile"), str(ROOT.parent)]
    subprocess.run(command, check=True)
    image = subprocess.check_output(
        ["docker", "image", "inspect", "crm-local:v1.90.0-resource-import-0.1.0", "--format", "{{.Id}}"],
        text=True,
    ).strip()
    if not image.startswith("sha256:") or len(image) != 71:
        raise RuntimeError("Docker did not return an immutable derived image ID")
    runtime = RUNTIME
    runtime.mkdir(parents=True, exist_ok=True)
    content = f"CRM_IMAGE={image}\n"
    (runtime / "built-image.env").write_text(content, encoding="utf-8")
    try:
        with (runtime / "image.env").open("x", encoding="utf-8") as stream:
            stream.write(content)
    except FileExistsError:
        print("Existing active image lock retained; coordinate backup/deployment before activating built-image.env")
    print(f"Built CRM candidate image: {image}")


def init_env():
    if "CRM_DEPLOY_RUNTIME_DIR" in os.environ:
        raise RuntimeError("Runtime override only reuses existing materials; init-env is forbidden")
    content = (
        f"DB_PASSWORD={secrets.token_urlsafe(32)}\n"
        f"ADMIN_PASSWORD={secrets.token_urlsafe(32)}\n"
        f"FRAPPE_SITE_NAME={SITE}\n"
    )
    descriptor = os.open(ENV, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
    print("Created deploy/.env with fresh local secrets; values are not printed")


class LoginAssets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and attrs.get("src"):
            self.paths.append((attrs["src"], "javascript"))
        elif tag == "link" and "stylesheet" in attrs.get("rel", "").split() and attrs.get("href"):
            self.paths.append((attrs["href"], "text/css"))


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
    with request("/login") as response:
        login_html = response.read().decode("utf-8")
        if response.status != 200 or "<html" not in login_html.lower():
            raise RuntimeError("Login HTML page was not served")
    login_assets = LoginAssets()
    login_assets.feed(login_html)
    required = (
        ("/assets/frappe/dist/js/frappe-web.bundle.", ".js"),
        ("/assets/frappe/dist/css/website.bundle.", ".css"),
        ("/assets/frappe/dist/css/login.bundle.", ".css"),
    )
    for prefix, suffix in required:
        if not any(
            path.startswith(prefix) and path.endswith(suffix) and len(path) > len(prefix) + len(suffix)
            for path, _ in login_assets.paths
        ):
            raise RuntimeError("Login HTML is missing a mapped Framework bundle")
    for asset, content_type in login_assets.paths:
        if not asset.startswith("/") or asset.startswith("//"):
            raise RuntimeError("Login asset must be served from this site")
        with request(asset) as response:
            if response.status != 200 or content_type not in response.headers.get("Content-Type", ""):
                raise RuntimeError("Login JavaScript or CSS asset was not served")
    print("PASS: guest login HTML and mapped Framework JS/CSS assets (browser form login still requires acceptance)")
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
        choices=("init-env", "build", "check", "pull", "create-site", "install-app", "up", "status", "stop", "smoke", "smoke-data", "handoff-runtime"),
    )
    parser.add_argument("--proxy", help="Authorized credential-free loopback build proxy")
    parser.add_argument("--target-dir", help="Absolute target checkout deploy directory; handoff-runtime only")
    parser.add_argument("--secure-runtime-dir", action="store_true", help="Explicitly restrict only an existing target .runtime directory ACL; no recursive ACL changes")
    args = parser.parse_args()
    action = args.action
    if action == "handoff-runtime":
        if not args.target_dir:
            parser.error("handoff-runtime requires --target-dir")
        handoff_runtime(args.target_dir, args.secure_runtime_dir)
        return
    if args.target_dir or args.secure_runtime_dir:
        parser.error("handoff options are only valid with handoff-runtime")
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

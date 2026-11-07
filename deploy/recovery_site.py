import contextlib
import gzip
import hashlib
import importlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import sys
import tarfile


SITE = "recovery.localhost"
DB_NAME = "_crm_recovery_b010200"
BUNDLE = Path("/restore")
FILES = {"database.sql.gz", "public-files.tar", "private-files.tar", "site-config.json"}
VERSIONS = {"frappe": "15.125.0", "crm": "1.90.0", "resource_import": "0.1.0", "team_access": "0.1.0"}


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def archive_files(path, folder, source_site):
    result = {}
    seen = {}
    with tarfile.open(path, "r:*") as archive:
        for member in archive:
            raw = member.name.rstrip("/").split("/")
            if raw[:4] != [".", source_site, folder, "files"] or any(part in ("", "..") for part in raw):
                raise RuntimeError("Unexpected backup archive path; native restore strip semantics must be reviewed")
            if not (member.isdir() or member.isfile()):
                raise RuntimeError("Recovery refuses archive links and special files")
            relative = PurePosixPath(*raw[2:]).as_posix()
            if relative in seen and not (seen[relative] and member.isdir()):
                raise RuntimeError("Duplicate or conflicting normalized path in backup archive")
            seen[relative] = member.isdir()
            if member.isfile():
                value = hashlib.sha256()
                with archive.extractfile(member) as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        value.update(chunk)
                result[relative] = value.hexdigest()
    return result


def validate_bundle():
    manifest = json.loads((BUNDLE / "manifest.json").read_text())
    if manifest.get("format") != "crm-recovery-v1" or manifest.get("site") != "crm.localhost":
        raise RuntimeError("Recovery bundle format/site mismatch")
    run_id = os.environ.get("CRM_RECOVERY_RUN_ID", "")
    if not re.fullmatch(r"[0-9a-f]{32}", run_id) or manifest.get("run_id") != run_id or (Path("/run/recovery-keys") / "run-id").read_text().strip() != run_id:
        raise RuntimeError("Recovery bundle/key/new-run marker mismatch")
    image = os.environ.get("CRM_IMAGE", "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image) or manifest.get("image") != image:
        raise RuntimeError("Recovery must use the same immutable security image as its source backup")
    if manifest.get("apps") != VERSIONS or set(manifest.get("files", {})) != FILES:
        raise RuntimeError("Recovery bundle apps/file manifest mismatch")
    for app, version in VERSIONS.items():
        if importlib.import_module(app).__version__ != version:
            raise RuntimeError("Recovery app version mismatch")
    for name, expected in manifest["files"].items():
        path = BUNDLE / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0 or digest(path) != expected:
            raise RuntimeError("Recovery bundle integrity validation failed")
    with gzip.open(BUNDLE / "database.sql.gz", "rb") as stream:
        for _ in iter(lambda: stream.read(1024 * 1024), b""):
            pass
    files = {}
    files.update(archive_files(BUNDLE / "public-files.tar", "public", manifest["site"]))
    files.update(archive_files(BUNDLE / "private-files.tar", "private", manifest["site"]))
    source_config = json.loads((BUNDLE / "site-config.json").read_text())
    if source_config.get("db_type", "mariadb") != "mariadb":
        raise RuntimeError("Recovery only supports the fixed MariaDB source")
    return source_config, files


def synthetic_only_value(source, acknowledgement):
    if acknowledgement != "confirmed-synthetic-only":
        raise RuntimeError("Recovery requires the operator's explicit synthetic-only acknowledgement for this run")
    if not isinstance(source, dict) or type(source.get("team_access_synthetic_only")) is not int or source["team_access_synthetic_only"] != 1:
        raise RuntimeError("Recovery source configuration must contain the reviewed synthetic-only integer acknowledgement; no default is allowed")
    return source["team_access_synthetic_only"]


def write_new(path, value):
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def main():
    if Path.cwd() != Path("/home/frappe/frappe-bench"):
        raise RuntimeError("Recovery must run only in the isolated bench image")
    password_file = Path("/run/recovery-keys/db-root-password")
    if password_file.is_symlink() or not password_file.is_file():
        raise RuntimeError("Recovery requires its own protected database root password file")
    root_password = password_file.read_text().strip()
    if len(root_password) < 24:
        raise RuntimeError("Recovery requires its own high-entropy database root password")
    source, files = validate_bundle()
    synthetic_only = synthetic_only_value(source, os.environ.get("CRM_RECOVERY_SYNTHETIC_ONLY_ACK"))
    sites = Path("sites")
    site = sites / SITE
    if site.exists() or site.is_symlink():
        raise RuntimeError("Recovery refuses an existing target site; preserve it and coordinate a new attempt")
    if any(path.is_dir() and (path / "site_config.json").exists() for path in sites.iterdir()):
        raise RuntimeError("Recovery sites volume must not contain any other configured site")
    import frappe
    from frappe.commands.site import _restore

    common = {
        "db_host": "recovery-db", "db_port": 3306,
        "redis_cache": "redis://recovery-cache:6379", "redis_queue": "redis://recovery-queue:6379",
        "redis_socketio": "redis://recovery-queue:6379", "socketio_port": 9000,
        "server_script_enabled": 0, "pause_scheduler": 1, "mute_emails": 1,
    }
    common_path = sites / "common_site_config.json"
    if common_path.is_symlink():
        raise RuntimeError("Recovery common config must not be a link")
    if common_path.exists():
        existing = json.loads(common_path.read_text())
        if existing and existing != common:
            raise RuntimeError("Recovery refuses preconfigured connection targets")
        common_path.write_text(json.dumps(common, sort_keys=True) + "\n")
    else:
        write_new(common_path, common)
    site.mkdir(mode=0o700)
    config = {
        "db_name": DB_NAME, "db_password": secrets.token_urlsafe(32), "db_type": "mariadb",
        "db_host": "recovery-db", "db_port": 3306, "mute_emails": 1, "pause_scheduler": 1,
        "maintenance_mode": 1, "server_script_enabled": 0, "host_name": "http://127.0.0.1:8089",
        "team_access_synthetic_only": synthetic_only,
    }
    for key in ("encryption_key", "backup_encryption_key", "resource_import_disabled"):
        if key in source:
            config[key] = source[key]
    write_new(site / "site_config.json", config)
    (sites / "apps.txt").write_text("\n".join(VERSIONS) + "\n")
    os.chdir(sites)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        frappe.init(site=SITE, sites_path=".")
        try:
            _restore(
                site=SITE, sql_file_path=str(BUNDLE / "database.sql.gz"),
                db_root_username="root", db_root_password=root_password,
                verbose=False, install_app=(), admin_password=None, force=False,
                with_public_files=str(BUNDLE / "public-files.tar"),
                with_private_files=str(BUNDLE / "private-files.tar"),
            )
        finally:
            frappe.destroy()
        frappe.init(site=SITE, sites_path=".")
        try:
            from frappe.database.mariadb.setup_db import get_root_connection

            if frappe.conf.db_name != "_crm_recovery_b010200" or frappe.conf.db_host != "recovery-db":
                raise RuntimeError("Recovery-only database authorization target mismatch")
            root = get_root_connection("root", root_password)
            try:
                root.sql("CREATE USER %s@%s IDENTIFIED BY %s", (DB_NAME, "%", config["db_password"]))
                root.sql(r"GRANT ALL PRIVILEGES ON `\_crm\_recovery\_b010200`.* TO %s@%s", (DB_NAME, "%"))
                root.sql("FLUSH PRIVILEGES")
                grants = root.sql("SHOW GRANTS FOR %s@%s", (DB_NAME, "%"))
                permitted = ("GRANT USAGE ON *.* TO ", r"GRANT ALL PRIVILEGES ON `\_crm\_recovery\_b010200`.* TO ")
                if len(grants) != 2 or any("WITH GRANT OPTION" in row[0] or not row[0].startswith(permitted) for row in grants) or any(sum(row[0].startswith(prefix) for row in grants) != 1 for prefix in permitted):
                    raise RuntimeError("Recovery account grants differ from its exact isolated database allowlist")
            finally:
                root.close()
            frappe.connect()
            if set(frappe.get_installed_apps()) != set(VERSIONS):
                raise RuntimeError("Restored installed apps mismatch")
            from team_access.install import preflight
            preflight()
        finally:
            frappe.destroy()
    os.chdir("..")
    for relative, expected in files.items():
        path = site.joinpath(*PurePosixPath(relative).parts)
        if not path.is_file() or path.is_symlink() or digest(path) != expected:
            raise RuntimeError("Restored public/private file content mismatch")
    actual = set()
    for folder in ("public", "private"):
        for path in (site / folder / "files").rglob("*"):
            if path.is_symlink():
                raise RuntimeError("Unexpected restored file link")
            if path.is_file():
                actual.add(path.relative_to(site).as_posix())
    if actual != set(files):
        raise RuntimeError("Restored public/private file inventory mismatch")
    config["maintenance_mode"] = 0
    config_path = site / "site_config.json"
    current = json.loads(config_path.read_text())
    if current != {**config, "maintenance_mode": 1}:
        raise RuntimeError("Restore unexpectedly changed isolated site configuration")
    config_path.write_text(json.dumps(config, sort_keys=True) + "\n")
    print(f"PASS: native database/public/private restore and file inventory ({len(files)} files); source bundle retained")
    print("NOT VERIFIED: business graph, HTTP login/write, dual-user permissions or source restart")


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        print(f"ERROR: {type(error).__name__}; isolated restore not accepted; preserve all resources", file=sys.stderr)
        sys.exit(1)

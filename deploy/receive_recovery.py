import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sys
import tarfile


BUNDLE = Path("/restore")
KEYS = Path("/run/recovery-keys")
VERSIONS = {"frappe": "15.125.0", "crm": "1.90.0", "resource_import": "0.1.0", "team_access": "0.1.0"}


def private_file(path, data):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
    os.chown(path, 1000, 1000)


def main():
    parser = argparse.ArgumentParser(description="Receive only four selected backup files into new isolated Docker volumes")
    for kind in ("database", "public", "private", "config", "image", "run-id"):
        parser.add_argument("--" + kind, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{32}", args.run_id):
        raise RuntimeError("Recovery receiver requires a fresh explicit run marker")
    if os.geteuid() != 0 or not re.fullmatch(r"sha256:[0-9a-f]{64}", args.image):
        raise RuntimeError("Recovery receiver requires root in its isolated container and an immutable source image")
    mapping = {
        args.database: "database.sql.gz", args.public: "public-files.tar",
        args.private: "private-files.tar", args.config: "site-config.json",
    }
    if len(mapping) != 4 or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or ".." in name for name in mapping):
        raise RuntimeError("Receiver requires four distinct ordinary backup basenames")
    for directory in (BUNDLE, KEYS):
        if directory.is_symlink() or not directory.is_dir() or any(directory.iterdir()):
            raise RuntimeError("Recovery bundle and key volumes must be empty; preserve existing attempts")
        directory.chmod(0o700)
        os.chown(directory, 1000, 1000)
    files = {}
    with tarfile.open(fileobj=sys.stdin.buffer, mode="r|*") as archive:
        for member in archive:
            if member.name not in mapping or not member.isfile() or member.size <= 0:
                raise RuntimeError("Unexpected backup stream member")
            name = mapping[member.name]
            if name in files:
                raise RuntimeError("Duplicate backup stream member")
            target = BUNDLE / name
            value = hashlib.sha256()
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as output, archive.extractfile(member) as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    output.write(chunk)
                    value.update(chunk)
            os.chown(target, 1000, 1000)
            if target.stat().st_size != member.size:
                raise RuntimeError("Incomplete backup stream member")
            files[name] = value.hexdigest()
    if set(files) != set(mapping.values()):
        raise RuntimeError("Backup stream was incomplete")
    with gzip.open(BUNDLE / "database.sql.gz", "rb") as stream:
        for _ in iter(lambda: stream.read(1024 * 1024), b""):
            pass
    for name in ("public-files.tar", "private-files.tar"):
        with tarfile.open(BUNDLE / name, "r:*") as archive:
            for member in archive:
                if not (member.isdir() or member.isfile()):
                    raise RuntimeError("Backup archive contains links or special files")
    source_config = json.loads((BUNDLE / "site-config.json").read_text())
    if not isinstance(source_config, dict) or not source_config.get("db_name"):
        raise RuntimeError("Site configuration backup is invalid")
    manifest = {"format": "crm-recovery-v1", "site": "crm.localhost", "image": args.image, "run_id": args.run_id, "apps": VERSIONS, "files": files}
    private_file(BUNDLE / "manifest.json", (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode())
    private_file(KEYS / "db-root-password", (secrets.token_urlsafe(32) + "\n").encode())
    (KEYS / "db-root-password").chmod(0o400)
    private_file(KEYS / "run-id", (args.run_id + "\n").encode())
    print("PASS: four backup files received with SHA256/gzip/tar/config validation into private isolated volumes; no secret printed")


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        print(f"ERROR: {type(error).__name__}; preserve partial bundle/key volumes; receiver failed", file=sys.stderr)
        sys.exit(1)

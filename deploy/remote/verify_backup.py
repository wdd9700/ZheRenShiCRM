import gzip
import json
from pathlib import Path
import sys
import tarfile


BACKUPS = Path("/home/frappe/frappe-bench/sites/crm.localhost/private/backups")
SUFFIXES = {
    "database": "-database.sql.gz",
    "public": "-files.tar",
    "private": "-private-files.tar",
    "config": "-site_config_backup.json",
}


def main():
    if len(sys.argv) != 2:
        raise RuntimeError("Backup verification requires the command start timestamp")
    started = float(sys.argv[1])
    candidates = list(BACKUPS.glob("*-database.sql.gz"))
    if not candidates:
        raise RuntimeError("No database backup was created")
    database = max(candidates, key=lambda path: path.stat().st_mtime_ns)
    if database.stat().st_mtime < started:
        raise RuntimeError("Latest database backup predates this command; refuse to accept a stale backup")
    stem = database.name[:-len(SUFFIXES["database"])]
    paths = {kind: BACKUPS / (stem + suffix) for kind, suffix in SUFFIXES.items()}
    for path in paths.values():
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError("Backup set is incomplete or not ordinary non-empty files")
    with gzip.open(paths["database"], "rb") as stream:
        for _ in iter(lambda: stream.read(1024 * 1024), b""):
            pass
    for kind in ("public", "private"):
        with tarfile.open(paths[kind], "r:*") as archive:
            for member in archive:
                if not (member.isfile() or member.isdir()):
                    raise RuntimeError("Backup archive contains a link or special file")
    with paths["config"].open("r", encoding="utf-8") as stream:
        if not isinstance(json.load(stream), dict):
            raise RuntimeError("Backup site configuration is not a JSON object")
    print("PASS: latest four-file backup readable; source and backup retained; restore not tested: " + stem)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, tarfile.TarError, gzip.BadGzipFile) as error:
        raise SystemExit("ERROR: backup verification failed; preserve all resources: " + type(error).__name__)

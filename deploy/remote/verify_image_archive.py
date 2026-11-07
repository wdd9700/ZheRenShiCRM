import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import tarfile


def fail(message):
    raise RuntimeError(message)


def values(path):
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or key in result:
            fail("release metadata contains a duplicate or invalid entry")
        result[key] = value
    return result


def main():
    archive_path = Path(sys.argv[1])
    release = values(Path(sys.argv[2]))
    expected_layers = Path(sys.argv[3]).read_text(encoding="utf-8").splitlines()
    expected_index = release["CRM_IMAGE_INDEX"]
    expected_manifest = release["CRM_IMAGE_PLATFORM_MANIFEST"]
    expected_config = release["CRM_IMAGE_CONFIG"]
    blobs = {}
    names = {}
    with tarfile.open(str(archive_path), "r:") as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                fail("archive contains an unsafe path")
            if member.isdir():
                continue
            if not member.isfile() or member.name in blobs:
                fail("archive contains a link, special file or duplicate path")
            stream = archive.extractfile(member)
            digest = hashlib.sha256()
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
            hex_digest = "sha256:" + digest.hexdigest()
            if member.name.startswith("blobs/sha256/") and path.name != hex_digest.split(":", 1)[1]:
                fail("blob filename and content digest differ")
            blobs[member.name] = hex_digest
            names[hex_digest] = member.name
            if member.name == "index.json" or member.name.endswith("manifest.json") or hex_digest in (expected_index, expected_manifest, expected_config):
                stream.seek(0)
                blobs[member.name] = (hex_digest, stream.read())
    if "index.json" not in blobs:
        fail("archive index.json is missing")
    top = json.loads(blobs["index.json"][1].decode("utf-8"))
    if len(top.get("manifests", [])) != 1 or top["manifests"][0]["digest"] != expected_index:
        fail("top-level index does not select the reviewed OCI index")
    if expected_index not in names:
        fail("reviewed OCI index blob is missing")
    outer = json.loads(blobs[names[expected_index]][1].decode("utf-8"))
    if outer.get("mediaType") != "application/vnd.oci.image.index.v1+json":
        fail("reviewed OCI index mediaType mismatch")
    candidates = [item for item in outer.get("manifests", []) if item.get("platform", {}).get("os") == "linux" and item.get("platform", {}).get("architecture") == "amd64"]
    if len(candidates) != 1 or candidates[0]["digest"] != expected_manifest:
        fail("reviewed linux/amd64 platform manifest mismatch")
    if expected_manifest not in names:
        fail("reviewed platform manifest blob is missing")
    manifest = json.loads(blobs[names[expected_manifest]][1].decode("utf-8"))
    if manifest.get("mediaType") != "application/vnd.oci.image.manifest.v1+json" or manifest.get("config", {}).get("digest") != expected_config:
        fail("platform manifest does not select the reviewed config")
    if expected_config not in names:
        fail("reviewed config blob is missing")
    config = json.loads(blobs[names[expected_config]][1].decode("utf-8"))
    if config.get("os") != "linux" or config.get("architecture") != "amd64":
        fail("config platform mismatch")
    actual_layers = []
    with tarfile.open(str(archive_path), "r:") as archive:
        for descriptor in manifest.get("layers", []):
            digest = descriptor["digest"]
            if digest not in names:
                fail("manifest layer blob is missing")
            stream = archive.extractfile(names[digest])
            decompressed = hashlib.sha256()
            with gzip.GzipFile(fileobj=stream) as layer:
                while True:
                    chunk = layer.read(1024 * 1024)
                    if not chunk:
                        break
                    decompressed.update(chunk)
            actual_layers.append("sha256:" + decompressed.hexdigest())
    if actual_layers != expected_layers or actual_layers != config.get("rootfs", {}).get("diff_ids"):
        fail("decompressed layers differ from reviewed/config diff_ids")
    print("PASS: archive index -> linux/amd64 manifest -> config and every decompressed diff_id match reviewed metadata")


if __name__ == "__main__":
    try:
        main()
    except (KeyError, IndexError, ValueError, OSError, RuntimeError, tarfile.TarError) as error:
        raise SystemExit("ERROR: reviewed archive verification failed: " + type(error).__name__)

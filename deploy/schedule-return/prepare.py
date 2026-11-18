"""Package the reviewed S011 HTML as a single layer over the archived e14b6 release."""

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile


BASE_INDEX = "sha256:e14b6cce43cf861f92ffaf4f55935434897ed156efea04f8eacc56311e39a4dd"
BASE_CONFIG = "sha256:c2601699d018675f1e2fc87a13c7fa4963090182eccfc70a8e51ed5ccdfbe062"
BASE_ARCHIVE = "sha256:0a91cbcc298ef599de35f46b0ab09ab696bc389fc0697c6d1feedaf163441679"
BASE_RELEASE = "sha256:b4b2cbcb5292da32561c63e4ab0289a3c274524e8a799fbc79f7569bd10c2818"
BASE_LAYERS = "sha256:fb75287484298a947b53d7d2f3b8822fdeae478e8607ac6da3a4e317a2fda083"
HTML_DIGEST = "sha256:cdb9e49ae2832574c231d4d9b4b0ee0b41abf6f8ed1e3b3e1c63a82f953a8f9f"
HTML_PATH = "home/frappe/frappe-bench/apps/team_schedule/team_schedule/www/team-schedule.html"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def file_digest(path):
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
    return "sha256:" + checksum.hexdigest()


def blob(value):
    return "blobs/sha256/" + value.split(":", 1)[1]


def encode(data):
    return json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")


def read(source, name):
    member = source.getmember(name)
    require(member.isfile(), "not a regular file: " + name)
    with source.extractfile(member) as stream:
        return stream.read()


def add(target, path, data, uid=0, mode=0o644):
    member = tarfile.TarInfo(path)
    member.uid = uid
    member.mode = mode
    member.size = len(data)
    target.addfile(member, io.BytesIO(data))


def add_layer(html):
    uncompressed = io.BytesIO()
    with tarfile.open(fileobj=uncompressed, mode="w", format=tarfile.USTAR_FORMAT) as layer:
        add(layer, HTML_PATH, html, uid=1000)
    raw = uncompressed.getvalue()
    compressed = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=compressed, mtime=0) as stream:
        stream.write(raw)
    return compressed.getvalue(), digest(raw)


def replace_descriptor(descriptor, data):
    return dict(descriptor, digest=digest(data), size=len(data))


def pack(source, target, html, release, expected_layers):
    # The attestation in the old OCI index refers to the old manifest, not this derivative.
    top = json.loads(read(source, "index.json"))
    require(len(top["manifests"]) == 1 and top["manifests"][0]["digest"] == BASE_INDEX,
            "unexpected top-level OCI index")
    outer = json.loads(read(source, blob(BASE_INDEX)))
    image = [item for item in outer["manifests"] if item.get("platform") == {"os": "linux", "architecture": "amd64"}]
    require(len(image) == 1 and image[0]["digest"] == release["CRM_IMAGE_PLATFORM_MANIFEST"],
            "unexpected original platform manifest")
    manifest = json.loads(read(source, blob(image[0]["digest"])))
    require(manifest["config"]["digest"] == BASE_CONFIG, "unexpected original config")
    config = json.loads(read(source, blob(BASE_CONFIG)))
    require(config["rootfs"]["diff_ids"] == expected_layers, "original diff_ids differ")
    require(len(manifest["layers"]) == len(expected_layers), "original layer count differs")
    legacy = json.loads(read(source, "manifest.json"))
    old_layer_paths = [blob(item["digest"]) for item in manifest["layers"]]
    require(legacy == [{"Config": blob(BASE_CONFIG), "RepoTags": None, "Layers": old_layer_paths}],
            "unexpected Docker load manifest")

    compressed, diff_id = add_layer(html)
    config["rootfs"]["diff_ids"].append(diff_id)
    config["history"].append({"created_by": "S011: d4330d3 team-schedule.html only"})
    new_config = encode(config)
    manifest["config"] = replace_descriptor(manifest["config"], new_config)
    layer = replace_descriptor({"mediaType": "application/vnd.oci.image.layer.v1.tar+gzip"}, compressed)
    manifest["layers"].append(layer)
    new_manifest = encode(manifest)
    outer["manifests"] = [replace_descriptor(image[0], new_manifest)]
    new_index = encode(outer)
    top["manifests"] = [replace_descriptor(top["manifests"][0], new_index)]
    legacy[0]["Config"] = blob(digest(new_config))
    legacy[0]["Layers"].append(blob(layer["digest"]))

    for name in dict.fromkeys(old_layer_paths):
        member = source.getmember(name)
        require(member.isfile(), "base layer must be a regular file")
        with source.extractfile(member) as stream:
            target.addfile(member, stream)
    for data in (compressed, new_config, new_manifest, new_index):
        add(target, blob(digest(data)), data)
    add(target, "oci-layout", read(source, "oci-layout"))
    add(target, "index.json", encode(top))
    add(target, "manifest.json", encode(legacy))
    return (digest(new_index), digest(new_manifest), digest(new_config)), diff_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path, help="retained e14b6 candidate-release")
    parser.add_argument("html", type=Path, help="raw d4330d3 Git blob (not a checkout copy)")
    parser.add_argument("output", type=Path, help="new directory; never overwritten")
    args = parser.parse_args()
    html = args.html.read_bytes()
    require(digest(html) == HTML_DIGEST, "wrong d4330d3 Git template bytes")
    base_archive = args.base / "image.tar"
    base_release = args.base / "release.env"
    base_layers = args.base / "image-rootfs-layers.txt"
    for path, expected in ((base_release, BASE_RELEASE), (base_layers, BASE_LAYERS), (base_archive, BASE_ARCHIVE)):
        require(file_digest(path) == expected, "unexpected e14b6 source: " + path.name)
    release = dict(line.split("=", 1) for line in base_release.read_text(encoding="utf-8").splitlines())
    expected_layers = base_layers.read_text(encoding="utf-8").splitlines()
    args.output.mkdir(mode=0o700)
    archive = args.output / "image.tar"
    with tarfile.open(str(base_archive), "r:") as source:
        with tarfile.open(str(archive), "x:") as target:
            ids, diff_id = pack(source, target, html, release, expected_layers)
    for key, value in zip(("CRM_IMAGE_INDEX", "CRM_IMAGE_PLATFORM_MANIFEST", "CRM_IMAGE_CONFIG"), ids):
        release[key] = value
    release["CRM_IMAGE_ARCHIVE_SHA256"] = file_digest(archive)
    (args.output / "image-rootfs-layers.txt").write_text("\n".join(expected_layers + [diff_id]) + "\n", encoding="utf-8")
    (args.output / "release.env").write_text("".join("{}={}\n".format(key, release[key]) for key in sorted(release)), encoding="utf-8")
    print("Prepared S011: index={}, manifest={}, config={}, layer={}, archive={}".format(
        *ids, diff_id, release["CRM_IMAGE_ARCHIVE_SHA256"]))


if __name__ == "__main__":
    main()

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


CRM_COMMIT = "36bd8859f2a6345a620477bc708d0546e8c3f08a"
PATCH_FILES = frozenset({
    "apply.py", "manifest.json", "check_apply.py", "controlled.test.mjs", "vitest-bridge.test.js",
    "payload/main.js", "payload/session.js", "payload/resources/accountBoundary.js",
    "payload/resources/documentResource.js", "payload/resources/listResource.js",
    "payload/resources/local.ts", "payload/resources/resources.js",
})
CONSUMER_FIXTURES = frozenset({"consumer-fixtures/router.js", "consumer-fixtures/users.js", "consumer-fixtures/views.js"})


def patch_file_set(paths):
    actual = set(paths)
    if actual not in (PATCH_FILES, PATCH_FILES | CONSUMER_FIXTURES):
        raise RuntimeError("Frontend patch source differs from the exact file whitelist")
    return actual


TARGETS = {
    "frontend/node_modules/frappe-ui/src/resources/accountBoundary.js": "resources/accountBoundary.js",
    "frontend/node_modules/frappe-ui/src/resources/documentResource.js": "resources/documentResource.js",
    "frontend/node_modules/frappe-ui/src/resources/listResource.js": "resources/listResource.js",
    "frontend/node_modules/frappe-ui/src/resources/local.ts": "resources/local.ts",
    "frontend/node_modules/frappe-ui/src/resources/resources.js": "resources/resources.js",
    "frontend/src/main.js": "main.js",
    "frontend/src/stores/session.js": "session.js",
    "frontend/package.json": None,
    "frontend/yarn.lock": None,
    "frontend/node_modules/frappe-ui/package.json": None,
    "frontend/node_modules/frappe-ui/src/utils/request.ts": None,
    "frontend/node_modules/frappe-ui/src/utils/frappeRequest.ts": None,
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_manifest(patch):
    entries = json.loads((patch / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(entries, list) or len(entries) != len(TARGETS):
        raise RuntimeError("Frontend patch manifest has an unexpected target count")
    seen = set()
    for entry in entries:
        target = entry.get("target")
        if target not in TARGETS or target in seen or entry.get("payload") != TARGETS[target]:
            raise RuntimeError("Frontend patch manifest targets differ from the whitelist")
        seen.add(target)
        for field in ("before", "after") if entry.get("payload") else ("before",):
            value = entry.get(field)
            if field == "before" and target.endswith("/accountBoundary.js") and value is None:
                continue
            if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise RuntimeError("Frontend patch manifest contains an invalid SHA256")
        if entry.get("payload") and digest((patch / "payload" / entry["payload"]).read_bytes()) != entry["after"]:
            raise RuntimeError("Frontend patch payload differs from its manifest")
    return entries


def verify(root, patch):
    root = root.resolve(strict=True)
    if subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip() != CRM_COMMIT:
        raise RuntimeError("Patched CRM HEAD differs from the fixed upstream commit")
    for entry in read_manifest(patch):
        target = root / entry["target"]
        if target.is_symlink() or not target.parent.resolve(strict=True).is_relative_to(root):
            raise RuntimeError("Patched frontend target escapes CRM or is linked")
        if target.stat().st_nlink != 1:
            raise RuntimeError("Patched frontend target is hard linked")
        expected = entry["after"] if entry.get("payload") else entry["before"]
        if digest(target.read_bytes()) != expected:
            raise RuntimeError("Patched frontend source or dependency guard changed: " + entry["target"])
    print("PASS: fixed CRM HEAD, seven patched files and five dependency/source guards")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("crm_root", type=Path)
    parser.add_argument("patch_root", type=Path)
    args = parser.parse_args()
    verify(args.crm_root, args.patch_root)

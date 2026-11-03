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
INITIALIZATION_TESTS = frozenset({"initialization.test.mjs", "real-runtime.test.mjs"})
RESUME_FILES = PATCH_FILES | CONSUMER_FIXTURES | INITIALIZATION_TESTS | frozenset({
    "resume.test.mjs", "source_edits.py", "payload/safeResume.js", "payload/resumeRuntime.js",
})


def patch_file_set(paths):
    actual = set(paths)
    if actual not in (PATCH_FILES, PATCH_FILES | CONSUMER_FIXTURES, PATCH_FILES | CONSUMER_FIXTURES | INITIALIZATION_TESTS, RESUME_FILES):
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


RESUME_EDITS = frozenset({
    "frontend/node_modules/frappe-ui/src/utils/frappeRequest.ts",
    "frontend/src/data/document.js", "frontend/src/data/script.js", "frontend/src/stores/meta.js",
    "frontend/src/components/ViewControls.vue", "frontend/src/pages/Lead.vue", "frontend/src/pages/Deal.vue",
    "frontend/src/pages/Leads.vue", "frontend/src/pages/Deals.vue", "frontend/src/stores/notifications.js",
    "frontend/src/stores/settings.js", "frontend/src/composables/telephony.js", "frontend/src/composables/whatsapp.js",
    "frontend/src/composables/erpnext.js", "frontend/src/composables/useCommandPalette.js",
    "frontend/src/composables/doctypeModal.js", "frontend/src/composables/document.js", "frontend/src/composables/noteView.ts",
    "frontend/src/utils/renderFieldLayoutDialog.js", "frontend/src/utils/dialogs.jsx", "frontend/src/composables/modals.js",
    "frontend/src/composables/useVisitedRecords.ts", "frontend/src/components/Layouts/AppSidebar.vue",
    "frontend/src/components/Activities/Activities.vue", "frontend/src/stores/users.js", "frontend/src/stores/views.js",
    "frontend/src/components/CommunicationArea.vue",
})
RESUME_TARGETS = dict(TARGETS, **{
    "frontend/src/data/safeResume.js": "safeResume.js",
    "frontend/src/resumeRuntime.js": "resumeRuntime.js",
    "frontend/src/components/EmailEditor.vue": None,
})
RESUME_TARGETS.update({target: None for target in RESUME_EDITS})
NEW_TARGETS = frozenset({
    "frontend/node_modules/frappe-ui/src/resources/accountBoundary.js",
    "frontend/src/data/safeResume.js", "frontend/src/resumeRuntime.js",
})


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_manifest(patch):
    entries = json.loads((patch / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
        raise RuntimeError("Frontend patch manifest must contain objects")
    resume = (patch / "source_edits.py").is_file()
    targets = RESUME_TARGETS if resume else TARGETS
    edits = RESUME_EDITS if resume else frozenset()
    if len(entries) != len(targets):
        raise RuntimeError("Frontend patch manifest has an unexpected target count")
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise RuntimeError("Frontend patch manifest entry must be an object")
        target = entry.get("target")
        edited = target in edits
        if target not in targets or target in seen or entry.get("payload") != targets[target]:
            raise RuntimeError("Frontend patch manifest targets differ from the whitelist")
        expected_keys = {"target", "before"}
        if targets[target]:
            expected_keys |= {"payload", "after"}
        elif edited:
            expected_keys |= {"edits", "after"}
        if set(entry) != expected_keys or (edited and entry.get("edits") is not True):
            raise RuntimeError("Frontend patch manifest entry schema differs from the whitelist")
        seen.add(target)
        for field in ("before", "after") if entry.get("payload") or edited else ("before",):
            value = entry.get(field)
            if field == "before" and target in NEW_TARGETS and value is None:
                continue
            if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise RuntimeError("Frontend patch manifest contains an invalid SHA256")
        if target in NEW_TARGETS and entry["before"] is not None:
            raise RuntimeError("New frontend target must not exist in the baseline")
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
        expected = entry["after"] if entry.get("payload") or entry.get("edits") else entry["before"]
        if digest(target.read_bytes()) != expected:
            raise RuntimeError("Patched frontend source or dependency guard changed: " + entry["target"])
    entries = read_manifest(patch)
    changed = sum(bool(entry.get("payload") or entry.get("edits")) for entry in entries)
    print(f"PASS: fixed CRM HEAD, {changed} patched files and {len(entries) - changed} dependency/source guards")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("crm_root", type=Path)
    parser.add_argument("patch_root", type=Path)
    args = parser.parse_args()
    verify(args.crm_root, args.patch_root)

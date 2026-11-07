import importlib
import json
from pathlib import Path
import subprocess


versions = {}
for app, version in (("frappe", "15.125.0"), ("crm", "1.90.0"), ("resource_import", "0.1.0"), ("team_access", "0.1.0")):
    module = importlib.import_module(app)
    assert module.__version__ == version, f"Unexpected {app} version"
    versions[app] = version
assert set(Path("sites/apps.txt").read_text().split()) == set(versions), "Image apps registry mismatch"
manifests = []
for directory in ("assets", "sites/assets"):
    manifest = json.loads((Path(directory) / "assets.json").read_text())
    assert len(manifest) >= 32, "Framework asset manifest was truncated"
    manifests.append(manifest)
    for bundle in ("frappe-web.bundle.js", "website.bundle.css", "login.bundle.css", "desk.bundle.js"):
        target = manifest.get(bundle)
        assert isinstance(target, str) and target.startswith("/assets/frappe/dist/"), "Framework asset mapping missing"
    for target in manifest.values():
        assert isinstance(target, str) and target.startswith("/assets/"), "Unexpected mapped asset path"
        assert (Path(directory) / target.removeprefix("/assets/")).is_file(), "Mapped asset file missing"
assert manifests[0] == manifests[1], "Image/sites asset manifests differ"
for filename in ("access.js", "page.js"):
    path = Path("assets/team_access") / filename
    site_path = Path("sites/assets/team_access") / filename
    assert path.is_file() and path.stat().st_size > 0 and site_path.read_bytes() == path.read_bytes(), "Team Access image/sites static asset missing or changed"
    subprocess.run(["node", "--check", str(path)], check=True)
if Path("/home/frappe/c011000").exists():
    subprocess.run(["env/bin/python", "/home/frappe/verify_frontend_patch.py", "apps/crm", "/home/frappe/c011000"], check=True)
subprocess.run(["bench", "version"], check=True)
subprocess.run(["bench", "--site", "recovery.localhost", "restore", "--help"], check=True)
print("PASS: exact app versions/registry, image static assets, JavaScript syntax and offline restore CLI")
print("NOT VERIFIED: installed site, migrations, HTTP/UI permissions, restore or persistence")

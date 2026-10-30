import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import uuid


ROOT = Path(__file__).resolve().parent
CHECKOUT = ROOT.parent


def git(*args):
    return subprocess.check_output(["git", "-C", str(CHECKOUT), *args])


def ordinary_path(path):
    for item in (path, *path.parents):
        if item.is_symlink() or (item.exists() and getattr(item.lstat(), "st_file_attributes", 0) & 0x400):
            raise RuntimeError("Build context refuses links and reparse points")


def export_app(commit, app, context):
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise RuntimeError("Candidate source requires a full lowercase 40-character commit")
    if git("rev-parse", f"{commit}^{{commit}}").decode().strip() != commit:
        raise RuntimeError("Candidate source must identify an exact commit")
    prefix = f"apps/{app}/"
    entries = git("ls-tree", "-rz", commit, "--", prefix).split(b"\0")
    manifest = {}
    for entry in filter(None, entries):
        metadata, raw_path = entry.split(b"\t", 1)
        mode, kind, object_id = metadata.decode("ascii").split()
        path = raw_path.decode("utf-8")
        parts = PurePosixPath(path).parts
        if mode not in ("100644", "100755") or kind != "blob" or not path.startswith(prefix):
            raise RuntimeError("Only ordinary committed app files may enter the build context")
        if ".." in parts or "\\" in path or any(part in (".local", ".env", "__pycache__", ".runtime", ".tower") for part in parts):
            raise RuntimeError("App source contains a forbidden build-context path")
        content = git("cat-file", "blob", object_id)
        target = context.joinpath(*parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(content)
        if mode == "100755":
            target.chmod(0o755)
        manifest[path] = hashlib.sha256(content).hexdigest()
    for relative in (f"{prefix}pyproject.toml", f"{prefix}{app}/__init__.py", f"{prefix}{app}/hooks.py"):
        if relative not in manifest:
            raise RuntimeError("Candidate app source is incomplete")
    return manifest


def prepare(resource_commit, access_commit=None):
    runtime = ROOT / ".runtime"
    ordinary_path(runtime)
    runtime.mkdir(exist_ok=True)
    probe = "deploy/.runtime/context-probe"
    if subprocess.run(["git", "-C", str(CHECKOUT), "check-ignore", "--quiet", "--no-index", "--", probe]).returncode:
        raise RuntimeError("Build contexts must be Git-ignored")
    context = runtime / f"integration-{uuid.uuid4().hex}"
    context.mkdir()
    files = export_app(resource_commit, "resource_import", context)
    if access_commit:
        files.update(export_app(access_commit, "team_access", context))
    (context / "deploy").mkdir()
    for name in ("Dockerfile", "Dockerfile.dockerignore"):
        if access_commit:
            source = ROOT / name
            ordinary_path(source)
            content = source.read_bytes().replace(b"\r\n", b"\n")
        else:
            content = git("show", f"{resource_commit}:deploy/{name}")
        with (context / "deploy" / name).open("xb") as stream:
            stream.write(content)
        files[f"deploy/{name}"] = hashlib.sha256(content).hexdigest()
    manifest = {"resource_import": resource_commit, "files": files}
    if access_commit:
        manifest["team_access"] = access_commit
    else:
        manifest["deployment"] = resource_commit
    with (context / "source-manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(f"Prepared exact committed source context: {context}")
    print(f"App/source files: {len(files)}; no runtime materials or uncommitted app files copied")
    return context, manifest


def build(context, manifest, proxy):
    command = ["docker", "build", "--network", "host", "--progress", "plain"]
    if proxy:
        from urllib.parse import urlsplit
        address = urlsplit(proxy)
        if address.scheme != "http" or address.hostname not in ("127.0.0.1", "localhost") or address.username or address.password:
            raise RuntimeError("Build proxy must be an authorized credential-free HTTP loopback endpoint")
        command += ["--build-arg", f"HTTP_PROXY={proxy}", "--build-arg", f"HTTPS_PROXY={proxy}", "--build-arg", "NO_PROXY=localhost,127.0.0.1"]
    for app, argument in (("resource_import", "RESOURCE_IMPORT_REVISION"), ("team_access", "TEAM_ACCESS_REVISION")):
        if app in manifest and f"ARG {argument}" in (context / "deploy" / "Dockerfile").read_text():
            command += ["--build-arg", f"{argument}={manifest[app]}"]
    tag = f"crm-local:integration-{context.name.removeprefix('integration-')}"
    command += ["-t", tag, "-f", str(context / "deploy" / "Dockerfile"), str(context)]
    subprocess.run(command, check=True)
    image = subprocess.check_output(["docker", "image", "inspect", tag, "--format", "{{.Id}}"], text=True).strip()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise RuntimeError("Build did not return an immutable image ID")
    if "team_access" in manifest:
        labels = json.loads(subprocess.check_output(["docker", "image", "inspect", image, "--format", "{{json .Config.Labels}}"], text=True))
        for app, label in (("resource_import", "crm.resource-import.revision"), ("team_access", "crm.team-access.revision")):
            if labels.get(label) != manifest[app]:
                raise RuntimeError("Built image app revision labels differ from its exact source manifest")
    with (context / "candidate-image.env").open("x", encoding="utf-8") as stream:
        stream.write(f"CRM_IMAGE={image}\n")
    manifest["image"] = image
    with (context / "build-result.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(f"PASS: candidate image {image}; active runtime image lock was not modified")


def load_context(value):
    context = Path(value)
    ordinary_path(context)
    if not context.is_absolute() or context.parent.resolve() != (ROOT / ".runtime").resolve() or not re.fullmatch(r"integration-[0-9a-f]{32}", context.name):
        raise RuntimeError("Existing context must be this checkout's absolute prepared integration directory")
    manifest = json.loads((context / "source-manifest.json").read_text(encoding="utf-8"))
    for app in ("resource_import", "team_access", "deployment"):
        if app != "resource_import" and app not in manifest:
            continue
        if not re.fullmatch(r"[0-9a-f]{40}", manifest[app]):
            raise RuntimeError("Prepared context source revision is invalid")
    if ("team_access" in manifest) == ("deployment" in manifest):
        raise RuntimeError("Prepared context must be either an integration or an exact resource-only deployment")
    files = manifest["files"]
    if not isinstance(files, dict) or not files:
        raise RuntimeError("Prepared context manifest is empty")
    actual = set()
    for path in context.rglob("*"):
        ordinary_path(path)
        if path.is_file():
            actual.add(path.relative_to(context).as_posix())
    if actual != set(files) | {"source-manifest.json"}:
        raise RuntimeError("Prepared context contains unmanifested files or previous build results")
    for relative, digest in files.items():
        path = PurePosixPath(relative)
        if ".." in path.parts or path.is_absolute() or "\\" in relative:
            raise RuntimeError("Invalid prepared context path")
        if not (relative in ("deploy/Dockerfile", "deploy/Dockerfile.dockerignore") or relative.startswith(("apps/resource_import/", "apps/team_access/"))):
            raise RuntimeError("Prepared context path is outside the source whitelist")
        if hashlib.sha256(context.joinpath(*path.parts).read_bytes()).hexdigest() != digest:
            raise RuntimeError("Prepared source content changed after export")
    return context, manifest


def main():
    parser = argparse.ArgumentParser(description="Prepare exact committed integration candidates without merging mission branches")
    parser.add_argument("--resource-commit")
    parser.add_argument("--access-commit")
    parser.add_argument("--resource-only-commit", help="Export both deploy files and resource_import from one exact committed M7 revision")
    parser.add_argument("--context", help="Absolute prepared context; supports Windows preparation followed by WSL build")
    parser.add_argument("--build", action="store_true", help="Requires a tower Docker build window; never activates the image")
    parser.add_argument("--proxy")
    args = parser.parse_args()
    if args.proxy and not args.build:
        parser.error("--proxy requires --build")
    if args.context:
        if args.resource_commit or args.access_commit or args.resource_only_commit:
            parser.error("--context cannot be combined with source revisions")
        context, manifest = load_context(args.context)
    else:
        if not shutil.which("git"):
            raise RuntimeError("Existing Git is required")
        if args.resource_only_commit:
            if args.resource_commit or args.access_commit:
                parser.error("--resource-only-commit cannot be combined with integration revisions")
            context, manifest = prepare(args.resource_only_commit)
        else:
            if not args.resource_commit or not args.access_commit:
                parser.error("both exact integration revisions or --resource-only-commit are required")
            context, manifest = prepare(args.resource_commit, args.access_commit)
    if args.build:
        build(context, manifest, args.proxy)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"ERROR: {type(error).__name__}; candidate preparation/build did not pass", file=sys.stderr)
        if isinstance(error, RuntimeError):
            print(str(error), file=sys.stderr)
        sys.exit(1)

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


FRONTEND_PREFIX = "frontend-patches/c011000/"
FRONTEND_DEPLOY = frozenset({"deploy/Dockerfile.frontend", "deploy/Dockerfile.frontend.dockerignore", "deploy/verify_frontend_patch.py"})
REVISION_ARGUMENTS = (
    ("resource_import", "RESOURCE_IMPORT_REVISION", "crm.resource-import.revision"),
    ("team_access", "TEAM_ACCESS_REVISION", "crm.team-access.revision"),
    ("frontend_cache", "FRONTEND_CACHE_REVISION", "crm.frontend-cache.revision"),
    ("deployment", "DEPLOYMENT_REVISION", "crm.deployment.revision"),
)


def committed_files(commit, prefix):
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise RuntimeError("Candidate source requires a full lowercase 40-character commit")
    if git("rev-parse", f"{commit}^{{commit}}").decode().strip() != commit:
        raise RuntimeError("Candidate source must identify an exact commit")
    entries = git("ls-tree", "-rz", commit, "--", prefix).split(b"\0")
    files = {}
    for entry in filter(None, entries):
        metadata, raw_path = entry.split(b"\t", 1)
        mode, kind, object_id = metadata.decode("ascii").split()
        path = raw_path.decode("utf-8")
        parts = PurePosixPath(path).parts
        if mode not in ("100644", "100755") or kind != "blob" or not path.startswith(prefix):
            raise RuntimeError("Only ordinary committed source files may enter the build context")
        if ".." in parts or "\\" in path or any(part in (".local", ".env", "__pycache__", ".runtime", ".tower") for part in parts):
            raise RuntimeError("Source contains a forbidden build-context path")
        files[path] = (mode, git("cat-file", "blob", object_id))
    return files


def write_sources(files, context):
    manifest = {}
    for path, (mode, content) in files.items():
        target = context.joinpath(*PurePosixPath(path).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(content)
        if mode == "100755":
            target.chmod(0o755)
        manifest[path] = hashlib.sha256(content).hexdigest()
    return manifest


def export_app(commit, app, context):
    prefix = f"apps/{app}/"
    files = committed_files(commit, prefix)
    for relative in (f"{prefix}pyproject.toml", f"{prefix}{app}/__init__.py", f"{prefix}{app}/hooks.py"):
        if relative not in files:
            raise RuntimeError("Candidate app source is incomplete")
    return write_sources(files, context)


def prepare(resource_commit, access_commit=None, frontend_commit=None, deployment_commit=None):
    if bool(frontend_commit) != bool(deployment_commit) or (frontend_commit and not access_commit):
        raise RuntimeError("Frontend integration requires exact resource, access, frontend and deployment commits")
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
    if frontend_commit:
        from verify_frontend_patch import patch_file_set, read_manifest
        patch_files = committed_files(frontend_commit, FRONTEND_PREFIX)
        patch_file_set(path.removeprefix(FRONTEND_PREFIX) for path in patch_files)
        files.update(write_sources(patch_files, context))
        read_manifest(context / FRONTEND_PREFIX)
        deployment_files = committed_files(deployment_commit, "deploy/")
        if not FRONTEND_DEPLOY <= set(deployment_files):
            raise RuntimeError("Frontend deployment source is incomplete")
        files.update(write_sources({path: deployment_files[path] for path in FRONTEND_DEPLOY}, context))
    else:
        (context / "deploy").mkdir()
        for name in ("Dockerfile", "Dockerfile.dockerignore"):
            if access_commit:
                source = ROOT / name
                ordinary_path(source)
                content = source.read_bytes().replace(b"\r\n", b"\n")
            else:
                content = git("show", f"{resource_commit}:deploy/{name}")
            files.update(write_sources({f"deploy/{name}": ("100644", content)}, context))
    manifest = {"resource_import": resource_commit, "files": files}
    if access_commit:
        manifest["team_access"] = access_commit
    else:
        manifest["deployment"] = resource_commit
    if frontend_commit:
        manifest.update(frontend_cache=frontend_commit, deployment=deployment_commit)
    with (context / "source-manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(f"Prepared exact committed source context: {context}")
    print(f"App/source files: {len(files)}; no runtime materials or uncommitted app files copied")
    return context, manifest


def build(context, manifest, proxy, manifest_sha256=None):
    context, validated = load_context(str(context), manifest_sha256)
    if validated != manifest:
        raise RuntimeError("Build manifest differs from the validated prepared context")
    dockerfile = context / "deploy" / ("Dockerfile.frontend" if "frontend_cache" in manifest else "Dockerfile")
    recipe = dockerfile.read_text(encoding="utf-8")
    command = ["docker", "build", "--network", "host", "--progress", "plain"]
    if proxy:
        from urllib.parse import urlsplit
        address = urlsplit(proxy)
        if address.scheme != "http" or address.hostname not in ("127.0.0.1", "localhost") or address.username or address.password:
            raise RuntimeError("Build proxy must be an authorized credential-free HTTP loopback endpoint")
        command += ["--build-arg", f"HTTP_PROXY={proxy}", "--build-arg", f"HTTPS_PROXY={proxy}", "--build-arg", "NO_PROXY=localhost,127.0.0.1"]
    for app, argument, label in REVISION_ARGUMENTS:
        if app in manifest and f"ARG {argument}" in recipe:
            command += ["--build-arg", f"{argument}={manifest[app]}"]
    tag = f"crm-local:integration-{context.name.removeprefix('integration-')}"
    command += ["-t", tag, "-f", str(dockerfile), str(context)]
    subprocess.run(command, check=True)
    image = subprocess.check_output(["docker", "image", "inspect", tag, "--format", "{{.Id}}"], text=True).strip()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise RuntimeError("Build did not return an immutable image ID")
    if "team_access" in manifest:
        labels = json.loads(subprocess.check_output(["docker", "image", "inspect", image, "--format", "{{json .Config.Labels}}"], text=True))
        for app, argument, label in REVISION_ARGUMENTS:
            if app in manifest and f"ARG {argument}" in recipe and labels.get(label) != manifest[app]:
                raise RuntimeError("Built image revision labels differ from its exact source manifest")
    with (context / "candidate-image.env").open("x", encoding="utf-8") as stream:
        stream.write(f"CRM_IMAGE={image}\n")
    result = dict(manifest, image=image, source_manifest_sha256=hashlib.sha256((context / "source-manifest.json").read_bytes()).hexdigest())
    with (context / "build-result.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(f"PASS: candidate image {image}; active runtime image lock was not modified")


def load_context(value, expected_sha256=None):
    context = Path(value)
    ordinary_path(context)
    if not context.is_absolute() or context.parent.resolve() != (ROOT / ".runtime").resolve() or not re.fullmatch(r"integration-[0-9a-f]{32}", context.name):
        raise RuntimeError("Existing context must be this checkout's absolute prepared integration directory")
    ordinary_path(context / "source-manifest.json")
    raw_manifest = (context / "source-manifest.json").read_bytes()
    if expected_sha256 is not None and (not re.fullmatch(r"[0-9a-f]{64}", expected_sha256) or hashlib.sha256(raw_manifest).hexdigest() != expected_sha256):
        raise RuntimeError("Prepared context manifest SHA256 differs from the preparation receipt")
    manifest = json.loads(raw_manifest)
    allowed_keys = {"resource_import", "files", "team_access", "deployment", "frontend_cache"}
    if not isinstance(manifest, dict) or not {"resource_import", "files"} <= set(manifest) or set(manifest) - allowed_keys:
        raise RuntimeError("Prepared context manifest schema is invalid")
    for app in allowed_keys - {"files"}:
        if app in manifest and (not isinstance(manifest[app], str) or not re.fullmatch(r"[0-9a-f]{40}", manifest[app])):
            raise RuntimeError("Prepared context source revision is invalid")
    files = manifest["files"]
    if not isinstance(files, dict) or not files:
        raise RuntimeError("Prepared context manifest is empty")
    frontend = "frontend_cache" in manifest
    if frontend:
        if not {"team_access", "deployment"} <= set(manifest) or expected_sha256 is None:
            raise RuntimeError("Frontend context requires four exact revisions and the preparation manifest SHA256")
        from verify_frontend_patch import patch_file_set, read_manifest
        patch_paths = {path for path in files if path.startswith(FRONTEND_PREFIX)}
        patch_file_set(path.removeprefix(FRONTEND_PREFIX) for path in patch_paths)
        deploy_paths = FRONTEND_DEPLOY
    else:
        if ("team_access" in manifest) == ("deployment" in manifest):
            raise RuntimeError("Prepared context must be either an integration or an exact resource-only deployment")
        patch_paths = set()
        deploy_paths = {"deploy/Dockerfile", "deploy/Dockerfile.dockerignore"}
    if not (deploy_paths | patch_paths) <= set(files):
        raise RuntimeError("Prepared context manifest is missing required sources")
    for app in ("resource_import", "team_access"):
        if app in manifest:
            for name in ("pyproject.toml", f"{app}/__init__.py", f"{app}/hooks.py"):
                if f"apps/{app}/{name}" not in files:
                    raise RuntimeError("Prepared context app source is incomplete")
    actual = set()
    for path in context.rglob("*"):
        ordinary_path(path)
        if path.is_file():
            if path.stat().st_nlink != 1:
                raise RuntimeError("Prepared context refuses hard linked sources")
            actual.add(path.relative_to(context).as_posix())
    if actual != set(files) | {"source-manifest.json"}:
        raise RuntimeError("Prepared context contains unmanifested files or previous build results")
    app_prefixes = tuple(f"apps/{app}/" for app in ("resource_import", "team_access") if app in manifest)
    for relative, digest in files.items():
        path = PurePosixPath(relative)
        if ".." in path.parts or path.is_absolute() or "\\" in relative or ":" in relative or path.as_posix() != relative:
            raise RuntimeError("Invalid prepared context path")
        if not (relative in deploy_paths | patch_paths or relative.startswith(app_prefixes)):
            raise RuntimeError("Prepared context path is outside the source whitelist")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest) or hashlib.sha256(context.joinpath(*path.parts).read_bytes()).hexdigest() != digest:
            raise RuntimeError("Prepared source content changed after export")
    if frontend:
        read_manifest(context / FRONTEND_PREFIX)
    return context, manifest


def main():
    parser = argparse.ArgumentParser(description="Prepare exact committed integration candidates without merging mission branches")
    parser.add_argument("--resource-commit")
    parser.add_argument("--access-commit")
    parser.add_argument("--frontend-commit", help="Exact independently reviewed C011000 patch commit; never a moving branch or worktree")
    parser.add_argument("--deployment-commit", help="Exact reviewed deploy commit; required with --frontend-commit")
    parser.add_argument("--resource-only-commit", help="Export both deploy files and resource_import from one exact committed M7 revision")
    parser.add_argument("--context", help="Absolute prepared context; supports Windows preparation followed by WSL build")
    parser.add_argument("--context-sha256", help="Preparation source-manifest.json SHA256; required when reusing a frontend context")
    parser.add_argument("--build", action="store_true", help="Requires a tower Docker build window; never activates the image")
    parser.add_argument("--proxy")
    args = parser.parse_args()
    if args.proxy and not args.build:
        parser.error("--proxy requires --build")
    if args.context:
        if args.resource_commit or args.access_commit or args.resource_only_commit or args.frontend_commit or args.deployment_commit:
            parser.error("--context cannot be combined with source revisions")
        context, manifest = load_context(args.context, args.context_sha256)
        manifest_sha256 = args.context_sha256
    else:
        if args.context_sha256:
            parser.error("--context-sha256 requires --context")
        if not shutil.which("git"):
            raise RuntimeError("Existing Git is required")
        if args.resource_only_commit:
            if args.resource_commit or args.access_commit or args.frontend_commit or args.deployment_commit:
                parser.error("--resource-only-commit cannot be combined with integration revisions")
            context, manifest = prepare(args.resource_only_commit)
        else:
            if not args.resource_commit or not args.access_commit:
                parser.error("both exact integration revisions or --resource-only-commit are required")
            context, manifest = prepare(args.resource_commit, args.access_commit, args.frontend_commit, args.deployment_commit)
        manifest_sha256 = hashlib.sha256((context / "source-manifest.json").read_bytes()).hexdigest()
        print(f"Source manifest SHA256: {manifest_sha256}")
        load_context(str(context), manifest_sha256)
    if args.build:
        build(context, manifest, args.proxy, manifest_sha256)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"ERROR: {type(error).__name__}; candidate preparation/build did not pass", file=sys.stderr)
        if isinstance(error, RuntimeError):
            print(str(error), file=sys.stderr)
        sys.exit(1)

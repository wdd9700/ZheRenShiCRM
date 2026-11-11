#!/usr/bin/env python3
import argparse
import os
from pathlib import Path
import re
import shutil
import tempfile


def patch(content):
    if not re.search(r"map\s+\$http_x_forwarded_proto\s+\$proxy_x_forwarded_proto\s*\{[^}]*https\s+https;", content, re.S):
        raise ValueError("expected HTTPS forwarding map missing")
    for expected in ("${NGINX_LISTEN_PORT}", "backend-server", "socketio-server",
                     "proxy_set_header X-Frappe-Site-Name ${FRAPPE_SITE_NAME_HEADER};"):
        if expected not in content:
            raise ValueError(f"unexpected inner template: missing {expected}")
    replacements = (
        (r"(proxy_set_header\s+Origin\s+)\$proxy_x_forwarded_proto://\$\{FRAPPE_SITE_NAME_HEADER\};", r"\g<1>$proxy_x_forwarded_proto://$http_host;"),
        (r"(proxy_set_header\s+X-Forwarded-For\s+)\$remote_addr;", r"\g<1>$http_x_forwarded_for;"),
    )
    for before, after in replacements:
        content, count = re.subn(before, after, content)
        if count != 1:
            raise ValueError(f"expected exactly one inner header match, found {count}")
    return content


def launch(template=Path("/templates/nginx/frappe.conf.template")):
    entrypoint = shutil.which("nginx-entrypoint.sh")
    if not entrypoint:
        raise RuntimeError("image nginx-entrypoint.sh missing")
    content = patch(template.read_text())
    script = Path(entrypoint).read_text()
    source = "/templates/nginx/frappe.conf.template"
    start = "nginx -g 'daemon off;'"
    if script.count(source) != 1 or script.count(start) != 1:
        raise RuntimeError("image nginx entrypoint contract changed; review before startup")
    directory = Path(tempfile.mkdtemp(prefix="crm-https-"))
    (directory / "frappe.conf.template").write_text(content)
    script = script.replace(source, str(directory / "frappe.conf.template"))
    script = script.replace(start, "nginx -t\nexec " + start)
    target = directory / "nginx-entrypoint.sh"
    target.write_text(script)
    os.execv("/bin/bash", ["/bin/bash", str(target)])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--launch", action="store_true")
    parser.add_argument("captured_template", type=Path, nargs="?")
    parser.add_argument("output", type=Path, nargs="?")
    args = parser.parse_args()
    if args.launch:
        launch()
    else:
        if not args.captured_template or not args.output:
            parser.error("captured_template and output required without --launch")
        result = patch(args.captured_template.read_text())
        with args.output.open("x") as handle:
            handle.write(result)
        print("Inner template prepared: only Socket.IO Origin and backend client IP changed")


if __name__ == "__main__":
    main()

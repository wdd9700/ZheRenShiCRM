from contextlib import ExitStack
from functools import wraps
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import sys
import tempfile
import types
from unittest.mock import patch


def run(h, website_source, request_source, jinja_source):
    from jinja2 import DictLoader
    from werkzeug.test import EnvironBuilder
    from werkzeug.wrappers import Request

    expected = {
        website_source / "base_template_page.py": "99776444e1a5d1effc873cdbf5b35bb04e1094953faf65f01ccc3c6cbe6a8e66",
        website_source / "web.html": "8f41d331f388bf43e56cab694eda77408e13abc1ef2cf7c4560cbe9833e9b94d",
        website_source / "base.html": "558c5831574b7f051ca6249b0465e5d9e6e53d41914bc1a694bf81ce95f96b85",
        request_source / "auth.py": "792e09201cb5f37ba649e3167254714e01804d2138f26137a912a4d729ec42ad",
        request_source / "exceptions.py": "c7b8b577e94c1d8130828028fbe9f96e88c17ee7f1028b5afc66db6f06870313",
        request_source / "sessions.py": "f7c6ea4d3d507ecf10cecc43022ecc6bafcbb0865e54c40dd689abec61e4e99b",
        jinja_source / "jinja.py": "be5a0e1cd43d2be13afb8eb16178818b4d4c1a15d9b39477c7b84362ad6edfa1",
        jinja_source / "utils.py": "495808a8895afa379c26e0362ab153b2b1e0c15e3b3c7439341ea8d44192db66",
    }
    for path, digest in expected.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    app_path = Path(__file__).with_name("team_access").resolve()
    templates = {
        "www/team-activities.html": (app_path / "www/team-activities.html").read_text(encoding="utf-8"),
        "templates/web.html": (website_source / "web.html").read_text(encoding="utf-8"),
        "templates/base.html": (website_source / "base.html").read_text(encoding="utf-8"),
    }
    for name in ("templates/includes/meta_block.html", "templates/includes/head.html", "public/icons/timeless/icons.svg", "public/icons/espresso/icons.svg", "templates/includes/breadcrumbs.html", "templates/includes/web_sidebar.html"):
        templates[name] = ""
    frappe = h.frappe
    namespace = {"frappe": frappe, "os": os, "wraps": wraps, "_": lambda text: text, "UNSAFE_HTTP_METHODS": frozenset(("POST", "PUT", "DELETE", "PATCH"))}
    h.load_native(website_source / "template_page.py", {"set_pymodule"}, namespace, "TemplatePage")
    h.load_native(website_source / "base_template_page.py", {"add_csrf_token"}, namespace, "BaseTemplatePage")
    h.load_native(request_source / "exceptions.py", {"CSRFTokenError"}, namespace)
    h.load_native(request_source / "auth.py", {"validate_csrf_token"}, namespace, "HTTPRequest")
    h.load_native(request_source / "sessions.py", {"get_csrf_token", "generate_csrf_token"}, namespace)
    h.load_native(jinja_source / "utils.py", {"can_cache", "cache_html"}, namespace)
    safe_exec = types.ModuleType("frappe.utils.safe_exec")
    safe_exec.UNSAFE_ATTRIBUTES = set()
    safe_exec.is_render_exec_enabled = lambda: False
    safe_exec.get_safe_globals = lambda: {"frappe": frappe, "web_block": lambda *args, **kwargs: "", "include_script": lambda *args, **kwargs: ""}
    safe_exec.render_safe_globals = safe_exec.get_safe_globals
    utils = types.ModuleType("frappe.utils")
    utils.__path__ = []
    utils.safe_exec = safe_exec
    namespace.update(get_jloader=lambda: DictLoader(templates), set_filters=lambda env: env.filters.update({"json": json.dumps, "abs_url": lambda value: value}), get_jinja_hooks=lambda: ({}, {}))
    h.load_native(jinja_source / "jinja.py", {"get_jenv"}, namespace)

    class RootParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.roots = []

        def handle_starttag(self, tag, attrs):
            values = dict(attrs)
            if values.get("id") == "team-activities":
                self.roots.append(values)

    def root(html):
        parser = RootParser()
        parser.feed(html)
        assert len(parser.roots) == 1
        return parser.roots[0]

    generated, persisted, rendered = [], [], []
    cache_rows = {}
    cache = types.SimpleNamespace(hget=lambda table, key: cache_rows.get((table, key)), hset=lambda table, key, value: cache_rows.__setitem__((table, key), value))
    local = h.Doc(lang="en", response=h.Doc(), no_cache=False, session_obj=types.SimpleNamespace(update=lambda **kwargs: persisted.append(kwargs)))
    session = h.Doc(user="a", data=h.Doc(csrf_token=None))
    local.session = session
    sessions = types.SimpleNamespace(get_csrf_token=namespace["get_csrf_token"])

    def generate_hash():
        generated.append(session.user)
        return "synthetic-generated-session-token"

    def throw(message, exc):
        raise exc()

    with ExitStack() as stack:
        replacements = {"local": local, "session": session, "sessions": sessions, "flags": h.Doc(in_test=False, force_website_cache=False), "conf": h.Doc(ignore_csrf=False, disable_website_cache=False, developer_mode=False), "utils": utils, "cache": cache, "generate_hash": generate_hash, "throw": throw, "CSRFTokenError": namespace["CSRFTokenError"], "request": None, "get_request_header": lambda name: frappe.request.headers.get(name)}
        for name, value in replacements.items():
            stack.enter_context(patch.object(frappe, name, value, create=True))
        stack.enter_context(patch.dict(sys.modules, {"frappe.utils": utils, "frappe.utils.safe_exec": safe_exec}))
        controller = sys.modules["team_access.www.team_activities"]

        def render(page):
            rendered.append(page.pymodule_name)
            page.context = h.Doc(base_template_path="templates/base.html", boot=h.Doc(lang="en", sysdefaults={}), dev_server="false", web_include_js=[], path="team-activities", route="team-activities", name="team-activities", pathname="team-activities", user=session.user)
            if page.pymodule_name:
                page.context.no_cache = controller.no_cache
                controller.get_context(page.context)
            page.context._context_dict = page.context
            return namespace["get_jenv"]().get_template("www/team-activities.html").render(page.context)

        def validate(token):
            frappe.request = Request(EnvironBuilder(path="/api/method/team_access.api.save_activity", method="POST", headers={"X-Frappe-CSRF-Token": token}).get_environ())
            namespace["validate_csrf_token"](None)

        with tempfile.TemporaryDirectory(prefix="website-layout-", dir=Path(__file__).parent) as directory:
            old_path = Path(directory)
            (old_path / "www").mkdir()
            (old_path / "www/team-activities.py").write_bytes((app_path / "www/team_activities.py").read_bytes())
            old = types.SimpleNamespace(app="team_access", app_path=str(old_path), template_path=os.path.join("www", "team-activities.html"), path="team-activities")
            new = types.SimpleNamespace(app="team_access", app_path=str(app_path), template_path=os.path.join("www", "team-activities.html"), path="team-activities")
            for page in (old, new):
                namespace["set_pymodule"](page)
            assert old.pymodule_name is None and new.pymodule_name == "team_access.www.team_activities"
            for user in ("a", "Administrator"):
                session.user = user
                for initial in (None, "synthetic-existing-session-token"):
                    session.data.csrf_token = initial
                    before = len(generated)
                    old_html = namespace["add_csrf_token"](old, render(old))
                    old_token = root(old_html)["data-csrf"]
                    assert old_token == "{{ csrf_token }}" and len(generated) == before
                    assert old.context.no_cache is None
                    if initial:
                        try:
                            validate(old_token)
                        except frappe.CSRFTokenError as error:
                            assert error.http_status_code == 400 and frappe.flags.disable_traceback
                        else:
                            raise AssertionError("Existing-session CSRF must reject the unresolved template placeholder")
                    else:
                        validate(old_token)
                    new_html = namespace["add_csrf_token"](new, render(new))
                    new_root = root(new_html)
                    assert new_root["data-csrf"] == session.data.csrf_token and new_root["data-user"] == user
                    assert new_root["data-csrf"] != old_token and new.context.no_cache == 1
                    assert len(generated) == before + (initial is None)
                    validate(new_root["data-csrf"])
            assert generated == ["a", "Administrator"] and persisted == [{"force": True}, {"force": True}]
            cached_render = namespace["cache_html"](render)
            session.data.csrf_token = "synthetic-existing-session-token"
            old_cached = cached_render(old)
            calls = len(rendered)
            assert cached_render(new) == old_cached and len(rendered) == calls
            cache_rows.clear()
            assert root(cached_render(new))["data-csrf"] == session.data.csrf_token
            assert not cache_rows and len(rendered) == calls + 1
    print("PASS fixed Jinja get_jenv + actual base/web/activity HTML + native controller/session-token/CSRF chain: old layout renders literal placeholder; empty saved-token skips, existing saved-token yields 400; renamed A/Admin context generates/preserves matching token and passes; old cached HTML bypass and fresh no_cache demonstrated in memory")

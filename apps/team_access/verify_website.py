import ast
import hashlib
import importlib
import os
from pathlib import Path
import types


def run(h, source_root=None):
    app_path = Path(__file__).with_name("team_access").resolve()
    page = types.SimpleNamespace(app="team_access", app_path=str(app_path), template_path=os.path.join("www", "team-activities.html"), context=h.Doc())
    namespace = None
    if source_root:
        path = source_root / "template_page.py"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == "86c4ed3a1bd00328a3bc3a47f01142623f72e6a0d3bde0db36f668650ffad144"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        properties = next(node.value for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "WEBPAGE_PY_MODULE_PROPERTIES" for target in node.targets))
        namespace = {"os": os, "WEBPAGE_PY_MODULE_PROPERTIES": ast.literal_eval(properties)}
        h.load_native(path, {"set_pymodule", "set_pymodule_properties", "run_pymodule_method"}, namespace, "TemplatePage")
        namespace["set_pymodule"](page)
        assert Path(page.pymodule_path) == Path("www/team_activities.py")
        assert page.pymodule_name == "team_access.www.team_activities", "Native website loader did not discover the activity controller"
        controller = importlib.import_module(page.pymodule_name)
        page.pymodule = controller
        namespace["set_pymodule_properties"](page)
        assert page.context.no_cache == 1
    else:
        controller = importlib.import_module("team_access.www.team_activities")
    assert controller.no_cache == 1
    assert not (app_path / "www/team-activities.py").exists()
    assert (app_path / "www/team-activities.html").is_file()
    frappe = h.frappe
    previous_user = frappe.session.user
    previous_sessions = getattr(frappe, "sessions", None)
    tokens = []

    def csrf_token():
        tokens.append(frappe.session.user)
        return "synthetic-current-session-token"

    frappe.sessions = types.SimpleNamespace(get_csrf_token=csrf_token)
    try:
        for user in ("a", "Administrator"):
            frappe.session.user = user
            page.context = h.Doc()
            if namespace:
                namespace["set_pymodule_properties"](page)
                namespace["run_pymodule_method"](page, "get_context")
                assert page.context.no_cache == 1
            else:
                controller.get_context(page.context)
            assert page.context.csrf_token == "synthetic-current-session-token"
            assert page.context.user == user
        assert tokens == ["a", "Administrator"]
        frappe.session.user = "Guest"
        h.forbidden(lambda: controller.get_context(h.Doc()))
        assert tokens == ["a", "Administrator"]
    finally:
        frappe.session.user = previous_user
        if previous_sessions is None:
            del frappe.sessions
        else:
            frappe.sessions = previous_sessions
    mode = "fixed native route-to-controller discovery/properties/invocation" if namespace else "controller module contract"
    print(f"PASS activity website {mode}: hyphen URL resolves underscore Python module, no_cache=1, A/Admin current-session token and user, Guest denied before token lookup; session source is simulated")

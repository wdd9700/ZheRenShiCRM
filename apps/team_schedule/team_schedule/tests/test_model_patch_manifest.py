import configparser
import importlib
import json
import runpy
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


PACKAGE = Path(__file__).resolve().parents[1]


class TestInstallContract(unittest.TestCase):
    def test_module_manifest_resolves_all_seven_standard_doctypes(self):
        modules = (PACKAGE / "modules.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(modules, ["Team Schedule"])
        module = importlib.import_module("team_schedule.team_schedule")
        folder = Path(module.__file__).parent
        files = list(folder.glob("doctype/*/*.json"))
        self.assertEqual(len(files), 7)
        for path in files:
            doc = json.loads(path.read_text(encoding="utf-8"))
            with self.subTest(doctype=doc["name"]):
                self.assertEqual(doc["doctype"], "DocType")
                self.assertEqual(doc["module"], modules[0])
                self.assertEqual(path.stem, doc["name"].lower().replace(" ", "_"))
                self.assertEqual(path.parent.name, path.stem)
                self.assertTrue(path.with_suffix(".py").is_file())

    def test_before_install_invalidates_only_discovery_cache_then_rebuilds(self):
        from team_schedule import hooks

        self.assertEqual(hooks.before_install, "team_schedule.install.before_install")
        calls = Mock()
        fake = SimpleNamespace(cache=SimpleNamespace(delete_value=calls.delete_value), setup_module_map=calls.setup_module_map)
        with patch.dict("sys.modules", {"frappe": fake}):
            install = runpy.run_path(str(PACKAGE / "install.py"))
            install["before_install"]()
        self.assertEqual(calls.mock_calls, [
            unittest.mock.call.delete_value("app_modules"),
            unittest.mock.call.setup_module_map(include_all_apps=True),
        ])

    def test_constraints_fail_closed_on_shares_and_missing_tables(self):
        for failure in ("shares", "table"):
            with self.subTest(failure=failure):
                db = Mock()
                db.table_exists.return_value = True
                no_shares = Mock(side_effect=RuntimeError("shares") if failure == "shares" else None)
                if failure == "table":
                    db.add_unique.side_effect = RuntimeError("table")
                with patch.dict("sys.modules", {
                    "frappe": SimpleNamespace(db=db),
                    "team_schedule.permissions": SimpleNamespace(assert_no_shares=no_shares),
                }):
                    constraints = runpy.run_path(str(PACKAGE / "patches" / "v1_constraints.py"))
                    with self.assertRaisesRegex(RuntimeError, failure):
                        constraints["execute"]()
                no_shares.assert_called_once_with()
                if failure == "shares":
                    db.add_unique.assert_not_called()
                else:
                    db.add_unique.assert_called_once_with("Team Schedule Member", ["parent", "user"], constraint_name="ts_member_user")
                db.add_index.assert_not_called()


class TestModelPatchManifest(unittest.TestCase):
    def test_both_frappe_patch_sections_and_constraint_phase(self):
        manifest = PACKAGE / "patches.txt"
        parser = configparser.ConfigParser(allow_no_value=True, delimiters="\n")
        parser.optionxform = str
        parser.read(manifest, encoding="utf-8")
        self.assertEqual(parser.sections(), ["pre_model_sync", "post_model_sync"])
        self.assertEqual(list(parser["pre_model_sync"]), [])
        self.assertEqual(list(parser["post_model_sync"]), ["team_schedule.patches.v1_constraints"])
        self.assertEqual(list(parser["pre_model_sync"]) + list(parser["post_model_sync"]), ["team_schedule.patches.v1_constraints"])

    def test_pinned_frappe_parser_install_and_migrate_modes(self):
        from frappe.modules.patch_handler import PatchType, parse_as_configfile

        manifest = str(PACKAGE / "patches.txt")
        self.assertEqual(parse_as_configfile(manifest), ["team_schedule.patches.v1_constraints"])
        self.assertEqual(parse_as_configfile(manifest, PatchType.pre_model_sync), [])
        self.assertEqual(parse_as_configfile(manifest, PatchType.post_model_sync), ["team_schedule.patches.v1_constraints"])

    def test_pinned_sync_discovers_doctypes_after_stale_four_app_map(self):
        import frappe
        from frappe.model.sync import sync_for
        from team_schedule.install import before_install

        old_modules, old_reverse = frappe.local.app_modules, frappe.local.module_app
        stale = {app: modules for app, modules in old_modules.items() if app != "team_schedule"}
        cache = {"app_modules": stale}
        try:
            frappe.local.app_modules = stale
            frappe.local.module_app = {module: app for module, app in old_reverse.items() if app != "team_schedule"}
            with patch.object(frappe.cache, "get_value", side_effect=lambda key: cache.get(key)), \
                 patch.object(frappe.cache, "delete_value", side_effect=lambda key: cache.pop(key, None)), \
                 patch.object(frappe.cache, "set_value", side_effect=lambda key, value: cache.update({key: value})), \
                 patch("frappe.model.sync.import_file_by_path") as import_file, \
                 patch.object(frappe.db, "commit"):
                sync_for("team_schedule", reset_permissions=True)
                import_file.assert_not_called()
                before_install()
                self.assertEqual(frappe.local.app_modules["team_schedule"], ["team_schedule"])
                self.assertEqual(frappe.local.module_app["team_schedule"], "team_schedule")
                sync_for("team_schedule", reset_permissions=True)
            discovered = {Path(call.args[0]).resolve() for call in import_file.call_args_list}
            self.assertEqual(discovered, {path.resolve() for path in (PACKAGE / "team_schedule" / "doctype").glob("*/*.json")})
            self.assertEqual(import_file.call_count, 7)
        finally:
            frappe.local.app_modules, frappe.local.module_app = old_modules, old_reverse

    def test_installed_constraints_and_lifecycle_hooks(self):
        import frappe
        from team_schedule import hooks
        from team_schedule.patches.v1_constraints import execute

        expected = "team_schedule.patches.v1_constraints.execute"
        self.assertEqual(hooks.before_install, "team_schedule.install.before_install")
        self.assertEqual(hooks.after_install, expected)
        self.assertEqual(hooks.after_migrate, expected)
        self.assertEqual(hooks.before_migrate, "team_schedule.patches.v1_constraints.check_shares")
        for attempt in range(3):
            if attempt:
                execute()
            for doctype, index, fields, non_unique in (
                ("Team Schedule Member", "ts_member_user", ["parent", "user"], 0),
                ("Team Schedule Busy Grant", "ts_busy_pair", ["subject_user", "viewer_user"], 0),
                ("Team Schedule Source Item", "ts_source_uid", ["source", "uid_key"], 0),
                ("Team Schedule Request", "ts_request_owner", ["owner", "request_id"], 0),
                ("Team Schedule", "ts_start_name", ["start_utc", "name"], 1),
            ):
                with self.subTest(attempt=attempt, doctype=doctype):
                    self.assertTrue(frappe.db.table_exists(doctype))
                    self.assertTrue(frappe.db.has_index("tab" + doctype, index))
                    rows = frappe.db.sql(f"SHOW INDEX FROM `tab{doctype}` WHERE Key_name=%s", (index,), as_dict=True)
                    rows.sort(key=lambda row: row.Seq_in_index)
                    self.assertEqual([row.Column_name for row in rows], fields)
                    self.assertTrue(all(row.Non_unique == non_unique for row in rows))
            for path in (PACKAGE / "team_schedule" / "doctype").glob("*/*.json"):
                doc = json.loads(path.read_text(encoding="utf-8"))
                self.assertTrue(frappe.db.table_exists(doc["name"]))
                self.assertEqual(frappe.db.get_value("DocType", doc["name"], "module"), "Team Schedule")


if __name__ == "__main__":
    unittest.main()

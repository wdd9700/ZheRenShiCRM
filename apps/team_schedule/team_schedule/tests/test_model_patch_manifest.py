import configparser
import unittest
from pathlib import Path


class TestModelPatchManifest(unittest.TestCase):
    def test_both_frappe_patch_sections_and_constraint_phase(self):
        manifest = Path(__file__).resolve().parents[1] / "patches.txt"
        parser = configparser.ConfigParser(allow_no_value=True, delimiters="\n")
        parser.optionxform = str
        parser.read(manifest, encoding="utf-8")
        self.assertEqual(parser.sections(), ["pre_model_sync", "post_model_sync"])
        self.assertEqual(list(parser["pre_model_sync"]), [])
        self.assertEqual(list(parser["post_model_sync"]), ["team_schedule.patches.v1_constraints"])
        self.assertEqual(list(parser["pre_model_sync"]) + list(parser["post_model_sync"]), ["team_schedule.patches.v1_constraints"])

    def test_pinned_frappe_parser_install_and_migrate_modes(self):
        from frappe.modules.patch_handler import PatchType, parse_as_configfile

        manifest = str(Path(__file__).resolve().parents[1] / "patches.txt")
        self.assertEqual(parse_as_configfile(manifest), ["team_schedule.patches.v1_constraints"])
        self.assertEqual(parse_as_configfile(manifest, PatchType.pre_model_sync), [])
        self.assertEqual(parse_as_configfile(manifest, PatchType.post_model_sync), ["team_schedule.patches.v1_constraints"])

    def test_installed_constraints_and_lifecycle_hooks(self):
        import frappe
        from team_schedule import hooks

        expected = "team_schedule.patches.v1_constraints.execute"
        self.assertEqual(hooks.after_install, expected)
        self.assertEqual(hooks.after_migrate, expected)
        self.assertEqual(hooks.before_migrate, "team_schedule.patches.v1_constraints.check_shares")
        for doctype, index in (
            ("Team Schedule Member", "ts_member_user"),
            ("Team Schedule Busy Grant", "ts_busy_pair"),
            ("Team Schedule Source Item", "ts_source_uid"),
            ("Team Schedule Request", "ts_request_owner"),
            ("Team Schedule", "ts_start_name"),
        ):
            with self.subTest(doctype=doctype):
                self.assertTrue(frappe.db.has_index("tab" + doctype, index))


if __name__ == "__main__":
    unittest.main()

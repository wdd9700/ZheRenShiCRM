from uuid import uuid4

import frappe
from frappe import client

from team_schedule import api, permissions, service
from team_schedule.tests.test_model_service import ScheduleCase, payload


TITLE = "<script>SYNTHETIC-ICS-TITLE-CANARY</script>"
DESCRIPTION = '<img src="https://example.invalid/not-fetched">& literal text'
WINDOW = {"start_utc": "2026-11-04T00:00:00Z", "end_utc": "2026-11-05T00:00:00Z"}


class TestModelStorage(ScheduleCase):
    def assert_literal(self, document, title, description):
        document.reload()
        self.assertEqual((document.title, document.description), (title, description))
        self.assertEqual(frappe.db.get_value("Team Schedule", document.name, ["title", "description"]), (title, description))

    def test_literal_storage_json_standard_reads_and_server_rendering(self):
        response = api.create(**{**payload(), "title": TITLE, "description": DESCRIPTION}, request_id=str(uuid4()))
        self.assertEqual(response.status_code, 200)
        name = response.get_json()["message"]["schedule"]["name"]
        document = frappe.get_doc("Team Schedule", name)
        self.assert_literal(document, TITLE, DESCRIPTION)
        for field in ("title", "description"):
            definition = frappe.get_meta("Team Schedule").get_field(field)
            self.assertEqual(definition.fieldtype, "Code")
            self.assertFalse(definition.options)
            self.assertFalse(definition.get("ignore_xss_filter"))
            self.assertEqual(frappe.db.get_column_type("Team Schedule", field), "longtext")
        self.assertFalse(frappe.get_meta("Team Schedule").get_field("title").reqd)
        value = client.get("Team Schedule", name=name)
        self.assertEqual((value["title"], value["description"]), (TITLE, DESCRIPTION))
        rows = frappe.get_list("Team Schedule", fields=["title", "description"], filters={"name": name})
        self.assertEqual((rows[0].title, rows[0].description), (TITLE, DESCRIPTION))
        detail = api.get(name=name)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.mimetype, "application/json")
        self.assertEqual(detail.headers["Cache-Control"], "no-store")
        self.assertEqual(detail.get_json()["message"]["schedule"]["title"], TITLE)
        exported = api.export_owned(**WINDOW)
        self.assertEqual(exported.status_code, 200)
        self.assertEqual(exported.mimetype, "application/json")
        self.assertEqual(exported.headers["Cache-Control"], "no-store")
        self.assertIn("attachment", exported.headers["Content-Disposition"])
        exported_row = next(row for row in exported.get_json()["schedules"] if row["name"] == name)
        self.assertEqual((exported_row["title"], exported_row["description"]), (TITLE, DESCRIPTION))
        template = '{% from "templates/print_formats/standard_macros.html" import render_field with context %}{{ render_field(df, doc) }}'
        rendered = "".join(frappe.render_template(template, {"df": document.meta.get_field(field), "doc": document}) for field in ("title", "description"))
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn("&lt;img", rendered)
        self.assertNotIn("<script", rendered)
        self.assertNotIn("<img", rendered)
        for operation in ("print", "email", "export"):
            self.assertFalse(frappe.has_permission("Team Schedule", operation, document))
        changed = service.mutate_schedule(name, 1, {"title": DESCRIPTION, "description": TITLE})
        self.assert_literal(changed, DESCRIPTION, TITLE)
        frappe.set_user(self.users[1])
        self.assertFalse(permissions.can_read(document))
        self.assertEqual(frappe.get_list("Team Schedule", filters={"name": name}), [])
        with self.assertRaises(frappe.PermissionError):
            client.get("Team Schedule", name=name)

    def test_plaintext_required_limits_and_import_controller_paths(self):
        source = service.create_source("synthetic literal storage source")
        literal_title = '<img src="https://example.invalid/not-fetched">'
        import_payload = {key: value for key, value in payload().items() if key != "members"}
        imported = service.save_import_schedule(source.name, {**import_payload, "title": literal_title, "description": DESCRIPTION})
        self.assert_literal(imported, literal_title, DESCRIPTION)
        updated = service.save_import_schedule(source.name, {"title": TITLE, "description": DESCRIPTION}, imported.name, 1)
        self.assert_literal(updated, TITLE, DESCRIPTION)
        boundary = service.create_schedule({**payload(), "title": "T" * 140, "description": "D" * 4000}, str(uuid4()))
        self.assert_literal(boundary, "T" * 140, "D" * 4000)
        for changes in ({"title": ""}, {"title": " \n\t"}, {"title": "T" * 141}, {"description": "D" * 4001}):
            for entry in ("create", "update", "import_create", "import_update", "controller"):
                with self.subTest(changes=changes, entry=entry):
                    frappe.db.savepoint("literal_invalid")
                    try:
                        if entry == "create":
                            self.assert_code("INVALID_INPUT", service.create_schedule, {**payload(), **changes}, str(uuid4()))
                        elif entry == "update":
                            self.assert_code("INVALID_INPUT", service.mutate_schedule, boundary.name, 1, changes)
                        elif entry == "import_create":
                            self.assert_code("INVALID_INPUT", service.save_import_schedule, source.name, {**import_payload, **changes})
                        elif entry == "import_update":
                            self.assert_code("INVALID_INPUT", service.save_import_schedule, source.name, changes, imported.name, 2)
                        else:
                            document = frappe.get_doc("Team Schedule", boundary.name)
                            document.update(changes)
                            with permissions.internal_write():
                                self.assert_code("INVALID_INPUT", document.save)
                    finally:
                        frappe.db.rollback(save_point="literal_invalid")
        document = frappe.get_doc("Team Schedule", boundary.name)
        document.title = literal_title
        with self.assertRaises(frappe.PermissionError):
            document.save()
        self.assertEqual(frappe.db.get_value("Team Schedule", boundary.name, "title"), "T" * 140)

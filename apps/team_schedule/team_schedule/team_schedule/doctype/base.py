import secrets

import frappe
from frappe.model.document import Document

from team_schedule.permissions import current_user, writing


class ScheduleDocument(Document):
    def autoname(self):
        self.name = secrets.token_hex(16)

    def check_permission(self, permtype="read", permlevel=None):
        if permtype not in ("read", "select") and not writing():
            frappe.throw("FORBIDDEN", frappe.PermissionError)
        return super().check_permission(permtype, permlevel)

    def before_insert(self):
        self.require_service()
        if self.owner != current_user():
            frappe.throw("FORBIDDEN", frappe.PermissionError)

    def require_service(self):
        if not writing():
            frappe.throw("FORBIDDEN", frappe.PermissionError)
        current_user()

    def validate(self):
        self.require_service()
        old = self.get_doc_before_save()
        if old and old.owner != self.owner:
            frappe.throw("FORBIDDEN", frappe.PermissionError)
        if self.doctype == "Team Schedule":
            from team_schedule.service import validate_schedule
            validate_schedule(self)

    def on_trash(self):
        frappe.throw("FORBIDDEN", frappe.PermissionError)

    def notify_update(self):
        pass

import frappe
from crm.fcrm.doctype.crm_call_log.crm_call_log import CRMCallLog
from crm.fcrm.doctype.crm_notification.crm_notification import CRMNotification
from crm.fcrm.doctype.crm_task.crm_task import CRMTask
from crm.fcrm.doctype.fcrm_note.fcrm_note import FCRMNote
from frappe.core.doctype.comment.comment import Comment
from frappe.core.doctype.communication.communication import Communication
from frappe.core.doctype.version.version import Version
from frappe.desk.doctype.notification_log.notification_log import NotificationLog
from frappe.desk.doctype.todo.todo import ToDo

from team_access.permissions import PRIVATE_TYPES, deny, get_record
from team_access.references import private_roots


def private_document(doc):
    if doc.doctype in PRIVATE_TYPES:
        return True
    try:
        if doc.doctype == "File":
            from team_access.files import activity_roots

            return bool(activity_roots(doc))
        return bool(private_roots(doc=doc))
    except (frappe.PermissionError, frappe.DoesNotExistError):
        return True


class PrivateUpdate:
    @property
    def no_feed_on_delete(self):
        return private_document(self) or getattr(super(), "no_feed_on_delete", False)

    def on_trash(self):
        from team_access.events import prevent_private_deletion

        prevent_private_deletion(self)
        method = getattr(super(), "on_trash", None)
        if method:
            return method()

    def notify_update(self):
        if not getattr(frappe.local, "team_access_private_communication_update", False) and not private_document(self):
            return super().notify_update()


class ActivityNote(PrivateUpdate, FCRMNote):
    pass


class ActivityTask(PrivateUpdate, CRMTask):
    def validate(self):
        old = self.get_doc_before_save()
        if old and self.assigned_to and old.assigned_to != self.assigned_to:
            self.unassign_from_previous_user(old.assigned_to)

    def on_update(self):
        old = self.get_doc_before_save()
        if old and self.assigned_to and old.assigned_to != self.assigned_to:
            self.assign_to()


class ActivityComment(PrivateUpdate, Comment):
    def notify_change(self, action):
        if not private_document(self):
            return super().notify_change(action)


class ActivityCommunication(PrivateUpdate, Communication):
    def on_update(self):
        if not private_document(self):
            return super().on_update()
        from team_access.hooks import override_doctype_class

        if self.get("reference_doctype") and self.reference_doctype not in override_doctype_class:
            raise frappe.PermissionError("Private communications require a reviewed parent controller")
        previous = getattr(frappe.local, "team_access_private_communication_update", False)
        frappe.local.team_access_private_communication_update = True
        try:
            return super().on_update()
        finally:
            frappe.local.team_access_private_communication_update = previous

    def notify_change(self, action):
        if not private_document(self):
            return super().notify_change(action)

    def after_insert(self):
        if self.get("communication_type") in ("Chat", "Notification") and private_document(self):
            if self.get("reference_doctype") == "Communication" and self.get("reference_name") and self.get("sent_or_received") == "Sent":
                frappe.db.set_value("Communication", self.reference_name, "status", "Replied")
            return
        return super().after_insert()


class ActivityToDo(PrivateUpdate, ToDo):
    pass


class ActivityVersion(PrivateUpdate, Version):
    pass


class ActivityNotification(PrivateUpdate, CRMNotification):
    pass


class ActivityNotificationLog(PrivateUpdate, NotificationLog):
    pass


class ActivityCall(PrivateUpdate, CRMCallLog):
    pass


@frappe.whitelist(allow_guest=True)
def can_subscribe_doc(doctype: str, docname: str):
    from frappe.realtime import can_subscribe_doc as original

    result = original(doctype, docname)
    record = get_record(doctype, docname)
    if record and private_document(record):
        deny()
    return result

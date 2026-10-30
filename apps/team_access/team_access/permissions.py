import frappe

PRIVATE_TYPES = ("FCRM Note", "CRM Task")
PARENTS = ("CRM Lead", "CRM Deal")
PROTECTED = PRIVATE_TYPES + (
    "CRM Call Log", "Comment", "Communication", "File", "Version",
    "CRM Notification", "Notification Log", "ToDo", "Dynamic Link", "Deleted Document",
)
MAX_ROWS = 2000
READ_TYPES = (None, "read", "select", "print", "email", "export", "report")


def deny():
    raise frappe.PermissionError("Activity access denied")


def get_record(doctype, name):
    if not name or not frappe.db.exists(doctype, str(name)):
        return None
    return frappe.get_doc(doctype, str(name))


def can_reference(doctype, name, user, seen=()):
    if not doctype or not name:
        return False
    key = (doctype, str(name))
    if key in seen or len(seen) >= 12:
        return False
    try:
        doc = get_record(doctype, name)
        if not doc:
            return False
        if doctype in PROTECTED and not permitted(doc, user, "read", seen):
            return False
        return bool(frappe.has_permission(doctype, "read", doc=doc, user=user, raise_exception=False))
    except (frappe.PermissionError, frappe.DoesNotExistError, ImportError):
        return False


def can_contribute(doctype, name, user, seen=()):
    if doctype in PRIVATE_TYPES:
        target = get_record(doctype, name)
        return bool(target and permitted(target, user, "write", seen) and frappe.has_permission(doctype, "write", doc=target, user=user, raise_exception=False))
    return can_reference(doctype, name, user, seen)


def private_links_permitted(doc, user, seen=()):
    from team_access.references import history_permitted

    return history_permitted(doc, user, seen)


def parent_readable(doc, user, seen=()):
    dt, name = doc.get("reference_doctype"), doc.get("reference_docname")
    if not dt and not name:
        return True
    return dt in PARENTS and bool(name) and can_reference(dt, name, user, seen)


def permitted(doc, user=None, ptype="read", seen=()):
    user = user or frappe.session.user
    if doc.doctype == "Deleted Document":
        from team_access.deleted import permitted_snapshot

        return bool(user and user != "Guest" and permitted_snapshot(doc, user))
    if user == "Administrator":
        return True
    if not user or user == "Guest":
        return False
    dt = doc.doctype
    key = (dt, str(doc.get("name")))
    if key in seen or len(seen) >= 12:
        return False
    seen = (*seen, key)
    reading = ptype in READ_TYPES
    from team_access.references import GRAPH_TYPES, history_permitted

    if dt in GRAPH_TYPES and not history_permitted(doc, user, seen):
        return False
    if dt in PRIVATE_TYPES:
        if not parent_readable(doc, user, seen):
            return False
        collaborator = user == doc.get("custom_team_collaborator")
        assignee = dt == "CRM Task" and user == doc.get("assigned_to")
        personal = user == doc.get("owner") or collaborator or assignee
        if ptype in ("share", "delete"):
            return user == doc.get("owner")
        if personal:
            return True
        return bool(reading and doc.get("custom_team_visibility") == "Shared" and doc.get("reference_doctype") in PARENTS and doc.get("reference_docname"))
    if dt == "CRM Call Log":
        refs = [(doc.get("reference_doctype"), doc.get("reference_docname"))]
        refs += [(link.get("link_doctype"), link.get("link_name")) for link in doc.get("links", [])]
        if doc.get("note"):
            refs.append(("FCRM Note", doc.note))
        refs = [(d, n) for d, n in refs if d or n]
        if not refs:
            return user == doc.get("owner")
        if not all(d in (*PARENTS, *PRIVATE_TYPES, "Contact", "CRM Organization") and can_reference(d, n, user, seen) for d, n in refs):
            return False
        return reading or user in (doc.get("owner"), doc.get("caller"), doc.get("receiver"))
    if dt == "File":
        from team_access.files import activity_roots

        dt_ref, name = doc.get("attached_to_doctype"), doc.get("attached_to_name")
        for root in activity_roots(doc):
            if not can_contribute(*root, user, seen):
                return False
        if dt_ref or name:
            return can_reference(dt_ref, name, user, seen) and (reading or user == doc.get("owner"))
        return user == doc.get("owner") or (reading and not doc.get("is_private"))
    if dt == "Version":
        target_dt, target_name = doc.get("ref_doctype"), doc.get("docname")
        if target_dt in PRIVATE_TYPES:
            target = get_record(target_dt, target_name)
            return bool(reading and target and permitted(target, user, "write", seen))
        return reading and can_reference(target_dt, target_name, user, seen)
    if dt in ("CRM Notification", "Notification Log"):
        recipient = doc.get("to_user") or doc.get("for_user")
        if recipient != user:
            return False
        target_dt = doc.get("notification_type_doctype") or doc.get("document_type") or doc.get("reference_doctype")
        target_name = doc.get("notification_type_doc") or doc.get("document_name") or doc.get("reference_name")
        if target_dt in PRIVATE_TYPES:
            target = get_record(target_dt, target_name)
            return bool(target and permitted(target, user, "write", seen))
        return can_reference(target_dt, target_name, user, seen) if target_dt or target_name else True
    if dt == "Dynamic Link":
        return can_reference(doc.get("parenttype"), doc.get("parent"), user, seen) and can_reference(doc.get("link_doctype"), doc.get("link_name"), user, seen)
    if dt == "ToDo":
        if user not in (doc.get("owner"), doc.get("allocated_to"), doc.get("assigned_by")):
            return False
        dt_ref, name = doc.get("reference_type"), doc.get("reference_name")
    else:
        dt_ref, name = doc.get("reference_doctype"), doc.get("reference_name")
    if not dt_ref and not name:
        return user == doc.get("owner")
    if dt in ("Comment", "Communication") and dt_ref in PRIVATE_TYPES:
        return can_contribute(dt_ref, name, user, seen) and (reading or user == doc.get("owner"))
    return can_reference(dt_ref, name, user, seen) and (reading or user == doc.get("owner"))


def has_permission(doc, ptype=None, user=None, **kwargs):
    if doc.doctype not in PROTECTED or ((user or frappe.session.user) == "Administrator" and doc.doctype != "Deleted Document"):
        return None
    if ptype == "create":
        if doc.doctype in PRIVATE_TYPES and not parent_readable(doc, user or frappe.session.user):
            deny()
        return None
    stored = get_record(doc.doctype, doc.get("name")) if doc.get("name") else None
    if not permitted(stored or doc, user, ptype):
        if doc.doctype == "Comment" and not doc.get("name") and ptype == "read":
            return False
        deny()
    return None


def allowed_names(doctype, user=None):
    user = user or frappe.session.user
    records = frappe.get_all(doctype, fields=["name"], limit_page_length=MAX_ROWS + 1, order_by="name")
    if len(records) > MAX_ROWS:
        frappe.local.response["team_access_limit"] = MAX_ROWS
        raise frappe.PermissionError("Team Access scan limit reached; a reviewed scalable policy is required")
    return [str(row.name) for row in records if permitted(frappe.get_doc(doctype, row.name), user)]


def query_condition(user=None, doctype=None):
    if doctype not in PROTECTED or ((user or frappe.session.user) == "Administrator" and doctype != "Deleted Document"):
        return ""
    names = allowed_names(doctype, user)
    if not names:
        return "1=0"
    return f"`tab{doctype}`.`name` in ({', '.join(frappe.db.escape(n, percent=False) for n in names)})"


def append_filter(doctype, filters=None, user=None):
    filters = frappe.parse_json(filters) if isinstance(filters, str) else filters
    if isinstance(filters, dict):
        result = []
        for key, value in filters.items():
            if isinstance(value, (list, tuple)) and len(value) == 2:
                result.append([doctype, key, value[0], value[1]])
            else:
                result.append([doctype, key, "=", value])
    elif isinstance(filters, list):
        result = list(filters)
    elif filters is None:
        result = []
    else:
        raise frappe.ValidationError("Invalid activity filters")
    result.append([doctype, "name", "in", allowed_names(doctype, user)])
    return result

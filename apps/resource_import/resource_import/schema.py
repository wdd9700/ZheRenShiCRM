import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


FIELDS = {
    "CRM Lead": [
        {"fieldname": "custom_resource_import_key", "label": "Resource Import Key v1", "fieldtype": "Data", "unique": 1, "read_only": 1, "no_copy": 1},
        {"fieldname": "custom_resource_requirement", "label": "需求原文", "fieldtype": "Long Text"},
        {"fieldname": "custom_resource_offering", "label": "产品服务原文", "fieldtype": "Long Text"},
        {"fieldname": "custom_resource_contact_raw", "label": "联系方式原文", "fieldtype": "Long Text"},
        {"fieldname": "custom_resource_source", "label": "导入来源 JSON", "fieldtype": "Long Text", "read_only": 1, "no_copy": 1},
        {"fieldname": "custom_resource_snapshot", "label": "六列原文 JSON", "fieldtype": "Long Text", "read_only": 1, "no_copy": 1},
        {"fieldname": "custom_resource_contact", "label": "导入联系人", "fieldtype": "Link", "options": "Contact"},
        {"fieldname": "custom_resource_organization", "label": "导入企业", "fieldtype": "Link", "options": "CRM Organization"},
        {"fieldname": "custom_resource_requirement_verbatim", "label": "需求原文（未清洗）", "fieldtype": "Code"},
        {"fieldname": "custom_resource_offering_verbatim", "label": "产品原文（未清洗）", "fieldtype": "Code"},
        {"fieldname": "custom_resource_contact_verbatim", "label": "联系方式原文（未清洗）", "fieldtype": "Code"},
        {"fieldname": "custom_resource_source_verbatim", "label": "来源原文 JSON", "fieldtype": "Code", "options": "JSON", "read_only": 1, "no_copy": 1},
        {"fieldname": "custom_resource_snapshot_verbatim", "label": "六列原文 JSON（未清洗）", "fieldtype": "Code", "options": "JSON", "read_only": 1, "no_copy": 1},
    ],
    "Contact": [
        {"fieldname": "custom_resource_contact_key", "label": "Resource Contact Key v1", "fieldtype": "Data", "unique": 1, "read_only": 1, "no_copy": 1},
    ],
}


def install():
    missing = {}
    for doctype, fields in FIELDS.items():
        meta = frappe.get_meta(doctype)
        for field in fields:
            existing = meta.get_field(field["fieldname"])
            if existing:
                for key in ("fieldtype", "options", "unique", "read_only", "no_copy"):
                    if (existing.get(key) or 0) != (field.get(key) or 0):
                        raise RuntimeError("Resource import schema conflict; reconcile without deleting fields")
            else:
                missing.setdefault(doctype, []).append(field)
    if missing:
        create_custom_fields(missing, update=False)
    for doctype, fields in FIELDS.items():
        for field in fields:
            if field.get("unique"):
                frappe.db.add_unique(doctype, [field["fieldname"]])

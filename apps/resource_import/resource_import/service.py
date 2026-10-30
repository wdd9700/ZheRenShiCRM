import hashlib
import json
import secrets
from urllib.parse import quote

import frappe

from resource_import.parser import InputError, digest, identities

DOCTYPES = ("CRM Organization", "Contact", "CRM Lead")


def authorize():
    if frappe.local.conf.get("resource_import_disabled") or frappe.session.user == "Guest" or "System Manager" not in frappe.get_roles():
        raise frappe.PermissionError("无资源导入权限")
    for doctype in DOCTYPES:
        if not frappe.has_permission(doctype, "read") or not frappe.has_permission(doctype, "create"):
            raise frappe.PermissionError("缺少导入所需实体权限")


def visible(doctype, filters):
    rows = frappe.get_list(doctype, filters=filters, fields=["name"], page_length=21, order_by="name asc")
    return [r.name for r in rows if frappe.has_permission(doctype, "read", doc=frappe.get_doc(doctype, r.name))]


def contact_key(raw):
    return digest(["resource-contact-v1", raw["姓名"].strip(), raw["公司名称"].strip(), raw["联系方式"]])


def candidates(raw):
    org = raw["公司名称"].strip()
    names = set(visible("Contact", {"first_name": raw["姓名"].strip(), "company_name": org}))
    names.update(visible("Contact", {"custom_resource_contact_key": contact_key(raw)}))
    phones, mails = identities(raw["联系方式"])
    for doctype, field, values in (("Contact Phone", "phone", phones), ("Contact Email", "email_id", mails)):
        if values:
            names.update(visible("Contact", [[doctype, field, "in", values]]))
    if len(names) > 20:
        raise InputError("候选过多，请在原生CRM整理后重试")
    result = []
    for name in sorted(names):
        doc = frappe.get_doc("Contact", name)
        linked = any(link.link_doctype == "CRM Organization" and link.link_name == org for link in doc.links)
        result.append({"name": name, "label": doc.full_name or name, "company": doc.company_name or "", "compatible": bool(linked and doc.company_name == org)})
    return result


def plan_record(record):
    row = {**record, "organizations": [], "contacts": [], "lead": None}
    if row["errors"]:
        row["state"] = "错误"
        return row
    previous = visible("CRM Lead", {"custom_resource_import_key": record["key"]})
    if previous:
        doc = frappe.get_doc("CRM Lead", previous[0])
        if not doc.custom_resource_snapshot_verbatim:
            row.update(state="历史资料待核验", lead=previous[0], errors=["历史导入可能经过HTML清洗，须人工核对/确认修复原文；本次不覆盖"])
        else:
            row.update(state="已导入", lead=previous[0])
        return row
    raw = record["raw"]
    row["organizations"] = visible("CRM Organization", {"organization_name": raw["公司名称"].strip()})
    row["contacts"] = candidates(raw)
    row["state"] = "待消歧" if row["organizations"] or row["contacts"] else "新建"
    return row


def plan(records):
    rows = []
    seen = set()
    for record in records:
        try:
            row = plan_record(record)
        except InputError as exc:
            row = {**record, "state": "错误", "errors": [str(exc)], "organizations": [], "contacts": [], "lead": None}
        if record["key"] in seen and not row["errors"]:
            row["state"] = "文件内重复"
        seen.add(record["key"])
        rows.append(row)
    return rows


def preview_binding(csv_text, source):
    return ["preview-v2", frappe.session.user, frappe.session.sid, source, digest(csv_text), True]


def preview_token(csv_text, source):
    token = secrets.token_hex(32)
    frappe.cache.set_value("resource_import:preview:" + token, preview_binding(csv_text, source), expires_in_sec=900)
    return token


def check_token(token, csv_text, source):
    if not isinstance(token, str) or len(token) != 64 or any(c not in "0123456789abcdef" for c in token):
        raise InputError("预览已过期或文件/会话改变，请重新预览")
    stored = frappe.cache.get_value("resource_import:preview:" + token)
    if stored != preview_binding(csv_text, source):
        raise InputError("预览已过期或文件/会话改变，请重新预览")


def links(lead, org=None, contact=None):
    result = {}
    for key, doctype, name, route in (("lead", "CRM Lead", lead, "leads"), ("organization", "CRM Organization", org, "organizations"), ("contact", "Contact", contact, "contacts")):
        if name and frappe.has_permission(doctype, "read", doc=frappe.get_doc(doctype, name)):
            result[key] = {"name": name, "url": "/crm/" + route + "/" + quote(name, safe="")}
    return result


def write_row(record, choice, created_contacts, created_orgs):
    row = plan_record(record)
    if row["errors"]:
        raise InputError("；".join(row["errors"]))
    if row["lead"]:
        doc = frappe.get_doc("CRM Lead", row["lead"])
        return {"state": "已导入", "links": links(doc.name, doc.custom_resource_organization, doc.custom_resource_contact)}
    if choice.get("skip"):
        raise InputError("用户跳过此行")
    raw = record["raw"]
    org_name = raw["公司名称"].strip()
    org_choice = choice.get("organization")
    if row["organizations"]:
        if org_choice not in row["organizations"] and org_name not in created_orgs:
            raise InputError("企业候选已存在或改变，请重新预览并显式选择")
        org = row["organizations"][0] if org_name in created_orgs else org_choice
    else:
        if org_choice not in (None, "", "__new__"):
            raise InputError("企业候选已改变，请重新预览")
        org = None
    key = contact_key(raw)
    contact_choice = choice.get("contact")
    contact = created_contacts.get(key)
    if not contact and row["contacts"]:
        selected = next((c for c in row["contacts"] if c["name"] == contact_choice and c["compatible"]), None)
        if not selected:
            raise InputError("请选择与该企业已关联的联系人；关联不明请在原生CRM整理后重新预览")
        contact = selected["name"]
    elif not contact and contact_choice not in (None, "", "__new__"):
        raise InputError("联系人候选已改变，请重新预览")
    new_org = False
    new_contact = False
    if not org:
        doc = frappe.get_doc({"doctype": "CRM Organization", "organization_name": org_name})
        doc.insert()
        org = doc.name
        new_org = True
    if not contact:
        doc = frappe.get_doc({"doctype": "Contact", "first_name": raw["姓名"].strip(), "company_name": org_name, "custom_resource_contact_key": key, "links": [{"link_doctype": "CRM Organization", "link_name": org}]})
        phones, mails = identities(raw["联系方式"])
        if phones:
            doc.append("phone_nos", {"phone": phones[0], "is_primary_mobile_no": 1})
        if mails:
            doc.append("email_ids", {"email_id": mails[0], "is_primary": 1})
        doc.insert()
        contact = doc.name
        new_contact = True
    doc = frappe.get_doc({
        "doctype": "CRM Lead", "first_name": raw["姓名"].strip(), "organization": org_name,
        "status": "New", "lead_owner": frappe.session.user,
        "custom_resource_import_key": record["key"], "custom_resource_contact": contact,
        "custom_resource_organization": org, "custom_resource_requirement_verbatim": raw["需要的产品、服务"],
        "custom_resource_offering_verbatim": raw["公司产品、服务"], "custom_resource_contact_verbatim": raw["联系方式"],
        "custom_resource_source_verbatim": json.dumps({"file": choice["source"], "line": record["line"], "serial": raw["序号"]}, ensure_ascii=False),
        "custom_resource_snapshot_verbatim": json.dumps(raw, ensure_ascii=False),
    })
    doc.insert()
    result = {"state": "成功", "links": links(doc.name, org, contact)}
    if new_org:
        created_orgs.add(org_name)
    if new_contact:
        created_contacts[key] = contact
    return result


def apply(records, choices, source):
    lock_name = "resource_import:" + hashlib.sha256(frappe.local.site.encode()).hexdigest()[:40]
    locked = frappe.db.sql("SELECT GET_LOCK(%s, 10)", (lock_name,))[0][0]
    if locked != 1:
        raise InputError("导入繁忙，请稍后重新确认")
    try:
        frappe.db.rollback()
        created_contacts, created_orgs, results = {}, set(), []
        for index, record in enumerate(records):
            savepoint = "resource_import_row_" + str(index)
            callbacks = {name: list(getattr(frappe.db, name)._functions) for name in ("before_commit", "after_commit", "before_rollback", "after_rollback")}
            realtime = list(frappe.local._realtime_log) if hasattr(frappe.local, "_realtime_log") else None
            saving = list(frappe.flags.currently_saving or [])
            frappe.db.savepoint(savepoint)
            try:
                choice = choices.get(str(record["line"]), {})
                if not isinstance(choice, dict):
                    raise InputError("无效行选择")
                outcome = write_row(record, {**choice, "source": source}, created_contacts, created_orgs)
            except Exception as exc:
                frappe.db.rollback(save_point=savepoint)
                for name, functions in callbacks.items():
                    manager = getattr(frappe.db, name)
                    manager.reset()
                    for function in functions:
                        manager.add(function)
                if realtime is None:
                    if hasattr(frappe.local, "_realtime_log"):
                        del frappe.local._realtime_log
                else:
                    frappe.local._realtime_log = realtime
                frappe.flags.currently_saving = saving
                message = str(exc) if isinstance(exc, InputError) else "该行未写入，请检查输入及对象权限后重新预览；必要时联系管理员"
                outcome = {"state": "失败", "error": message}
                frappe.local.message_log = []
            frappe.db.release_savepoint(savepoint)
            results.append({"line": record["line"], "raw": record["raw"], **outcome})
        frappe.db.commit()
        return results
    except Exception:
        frappe.db.rollback()
        raise
    finally:
        frappe.db.sql("SELECT RELEASE_LOCK(%s)", (lock_name,))

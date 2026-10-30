import json

import frappe

from resource_import import service
from resource_import.parser import InputError, parse


def failure(message, status):
    frappe.local.message_log = []
    frappe.local.response.http_status_code = status
    return {"error": message}


def inputs(csv_text, source, shared_consent):
    frappe.local.flags.disable_traceback = True
    service.authorize()
    if shared_consent not in (True, 1, "1", "true"):
        raise InputError("当前仅支持共享企业/联系人导入，须独立确认其将对现有Sales User角色开放；仅私域Lead模式尚未支持")
    return parse(csv_text, source)


@frappe.whitelist(methods=["POST"])
def preview(csv_text, source, shared_consent=False):
    try:
        records = inputs(csv_text, source, shared_consent)
        return {"rows": service.plan(records), "token": service.preview_token(csv_text, source)}
    except frappe.PermissionError:
        return failure("无资源导入权限", 403)
    except InputError as exc:
        return failure(str(exc), 422)
    except Exception:
        return failure("无法预览，请联系管理员检查应用版本及配置", 500)


@frappe.whitelist(methods=["POST"])
def apply(csv_text, source, token, confirm=False, choices=None, shared_consent=False):
    try:
        records = inputs(csv_text, source, shared_consent)
        if confirm not in (True, 1, "1", "true"):
            raise InputError("必须显式确认导入")
        service.check_token(token, csv_text, source)
        if isinstance(choices, str) and len(choices) > 200000:
            raise InputError("无效行选择")
        choices = json.loads(choices) if isinstance(choices, str) else choices or {}
        if not isinstance(choices, dict) or len(choices) > 500:
            raise InputError("无效行选择")
        return {"rows": service.apply(records, choices, source)}
    except frappe.PermissionError:
        return failure("无资源导入权限", 403)
    except (InputError, json.JSONDecodeError) as exc:
        return failure(str(exc) if isinstance(exc, InputError) else "无效行选择", 422)
    except Exception:
        frappe.db.rollback()
        return failure("导入未完成，请重新预览后重试；必要时联系管理员", 500)

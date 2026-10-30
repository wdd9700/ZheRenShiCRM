"""M5 业务闭环演示：导入结果 → 两个独立商机 → 沟通事件 → 截止跟进 → 阶段演进 → 时间线。

**仅合成数据**：只操作企业名以 `M5样例` 开头、姓名以 `样例` 开头的记录，否则拒绝执行
（M6 已证实 FCRM Note 私密 detail/PUT 跨用户 200、activities 泄漏未共享 note，真实资料不得进入本路径）。

在 bench 容器内运行（不删除、不改用户与权限）：

    cd /home/frappe/frappe-bench/sites
    ../env/bin/python /tmp/m5/m5_workflow_demo.py            # 只读检查
    ../env/bin/python /tmp/m5/m5_workflow_demo.py --confirm   # 真实写入

前置：先执行 M5 合成导入（tools/crm/m5_import.py apply --confirm）。
幂等：商机按 lead 复用、评论/任务按内容与标题复用、阶段只在当前值不够/未达目标时推进。
"""

import argparse
import json
import sys

import frappe

SYNTHETIC_ORG_PREFIX = "M5样例"
SYNTHETIC_PERSON_PREFIX = "样例"

DEAL_A_REQUIREMENT = "质检环节数字化与不良率追溯"
DEAL_B_REQUIREMENT = "冷链仓储温控监控"
FOLLOW_UP_A = "M5跟进：给样例企业甲发送质检试点方案与报价"
FOLLOW_UP_B = "M5跟进：确认样例企业乙冷链温控现场勘查时间"


def lead_for(requirement):
	notes = frappe.get_all(
		"FCRM Note",
		filters={
			"reference_doctype": "CRM Lead",
			"title": ["like", f"需求线索（导入）：{requirement}%"],
		},
		fields=["reference_docname"],
		limit=1,
	)
	return notes[0].reference_docname if notes else None


def deal_for_lead(lead):
	return frappe.db.get_value("CRM Deal", {"lead": lead}, "name")


def comment_exists(reference_doctype, reference_docname, content):
	return bool(
		frappe.db.exists(
			"Comment",
			{
				"reference_doctype": reference_doctype,
				"reference_name": reference_docname,
				"content": content,
			},
		)
	)


def ensure_comment(reference_doctype, reference_docname, content, apply):
	if comment_exists(reference_doctype, reference_docname, content):
		return "已存在"
	if not apply:
		return "将新建"
	user = frappe.session.user
	frappe.get_doc(
		{
			"doctype": "Comment",
			"comment_type": "Comment",
			"reference_doctype": reference_doctype,
			"reference_name": reference_docname,
			"content": content,
			"comment_by": user,
			"comment_email": frappe.db.get_value("User", user, "email"),
		}
	).insert(ignore_permissions=True)
	return "新建"


def ensure_task(title, reference_docname, due_date, priority, description, apply):
	existing = frappe.db.get_value(
		"CRM Task",
		{"title": title, "reference_doctype": "CRM Deal", "reference_docname": reference_docname},
		"name",
	)
	if existing:
		return existing, "已存在"
	if not apply:
		return None, "将新建"
	task = frappe.get_doc(
		{
			"doctype": "CRM Task",
			"title": title,
			"status": "Todo",
			"priority": priority,
			"due_date": due_date,
			"reference_doctype": "CRM Deal",
			"reference_docname": reference_docname,
			"assigned_to": frappe.session.user,
			"description": description,
		}
	)
	task.insert(ignore_permissions=True)
	return task.name, "新建"


STAGE_ORDER = ["Qualification", "Demo/Making", "Proposal/Quotation", "Negotiation", "Ready to Close"]
STAGE_RANK = {status: index for index, status in enumerate(STAGE_ORDER)}


def shift_status(deal_name, statuses, apply):
	"""只向前推进阶段：目标阶段必须晚于当前阶段，重复执行不会回退或重复推进。"""
	doc = frappe.get_doc("CRM Deal", deal_name)
	current_rank = STAGE_RANK.get(doc.status, -1)
	applied = []
	for status in sorted(statuses, key=lambda s: STAGE_RANK.get(s, -1)):
		if STAGE_RANK.get(status, -1) <= current_rank:
			continue
		if not apply:
			applied.append(f"将推进到 {status}")
			continue
		doc.status = status
		doc.save()
		current_rank = STAGE_RANK.get(status, current_rank)
		applied.append(f"推进到 {status}")
	return applied


def timeline(deal_name):
	from crm.api.activities import get_activities

	activities, calls, notes, tasks, attachments = get_activities(deal_name)
	kinds = {}
	for activity in activities:
		kinds[activity["activity_type"]] = kinds.get(activity["activity_type"], 0) + 1
	return {
		"activity_count": len(activities),
		"activity_kinds": kinds,
		"status_changes": [
			a["data"] for a in activities if a["activity_type"] == "changed" and a["data"].get("field") == "status"
		],
		"comments": [a["content"] for a in activities if a["activity_type"] == "comment"],
		"notes": [n.get("title") for n in notes],
		"tasks": [{"title": t.get("title"), "status": t.get("status"), "due_date": str(t.get("due_date"))} for t in tasks],
		"attachments": len(attachments),
	}


def main(argv=None):
	parser = argparse.ArgumentParser(description="M5 业务闭环演示")
	parser.add_argument("--confirm", action="store_true", help="真实写入；缺省只读检查")
	parser.add_argument("--site", default="crm.localhost")
	parser.add_argument("--sites-path", default=".")
	args = parser.parse_args(argv)
	apply = args.confirm

	frappe.init(site=args.site, sites_path=args.sites_path)
	frappe.connect()
	report = {"mode": "apply" if apply else "dry-run", "steps": {}}
	exit_code = 0
	try:
		lead_a = lead_for(DEAL_A_REQUIREMENT)
		lead_b = lead_for(DEAL_B_REQUIREMENT)
		report["steps"]["leads"] = {"A": lead_a, "B": lead_b}
		if not lead_a or not lead_b:
			report["error"] = "未找到导入产生的需求线索，请先运行 m5_import.py apply --confirm"
			print(json.dumps(report, ensure_ascii=False, indent=1))
			return 1

		non_synthetic = []
		for lead in (lead_a, lead_b):
			org, person = frappe.db.get_value("CRM Lead", lead, ["organization", "first_name"])
			if not (org or "").startswith(SYNTHETIC_ORG_PREFIX) or not (person or "").startswith(
				SYNTHETIC_PERSON_PREFIX
			):
				non_synthetic.append({"lead": lead, "organization": org, "first_name": person})
		if non_synthetic:
			report["error"] = "拒绝执行：目标线索不是合成数据（企业名须以 M5样例 开头、姓名须以 样例 开头）"
			report["non_synthetic"] = non_synthetic
			print(json.dumps(report, ensure_ascii=False, indent=1))
			return 1

		deals = {}
		for label, lead in (("A", lead_a), ("B", lead_b)):
			existing = deal_for_lead(lead)
			if existing:
				deals[label] = (existing, "已存在")
				continue
			if not apply:
				deals[label] = (None, "将转换")
				continue
			doc = frappe.get_doc("CRM Lead", lead)
			doc.flags.ignore_permissions = True
			deals[label] = (doc.convert_to_deal(), "转换为商机")
			frappe.db.commit()
		report["steps"]["deals"] = {k: {"name": v[0], "state": v[1]} for k, v in deals.items()}
		if not apply:
			print(json.dumps(report, ensure_ascii=False, indent=1))
			return 0

		deal_a, deal_b = deals["A"][0], deals["B"][0]

		# 商机字段：金额、预计成交、下一步（只在空值时写入，避免覆盖人工修改）
		for deal_name, values in (
			(deal_a, {"expected_deal_value": 120000, "expected_closure_date": "2026-12-15", "next_step": "提交质检试点方案"}),
			(deal_b, {"expected_deal_value": 86000, "expected_closure_date": "2026-11-30", "next_step": "安排现场温控勘查"}),
		):
			doc = frappe.get_doc("CRM Deal", deal_name)
			changed = {}
			for field, value in values.items():
				if not doc.get(field):
					doc.set(field, value)
					changed[field] = value
			if changed:
				doc.save()
				frappe.db.commit()
			report["steps"].setdefault("deal_fields", {})[deal_name] = changed or "已有值，未覆盖"

		# 沟通事件（评论进入 CRM 时间线）
		events = [
			(deal_a, "2026-10-28 电话沟通：样例张一确认质检场景，关注不良率追溯与报表导出。"),
			(deal_a, "2026-10-30 现场拜访：产线两处检测工位，要求先做 4 周试点。"),
			(deal_b, "2026-10-29 微信沟通：样例王三反馈冷库温控数据分散在两家供应商系统。"),
			(lead_b, "2026-10-27 电话初次接触：客户提到冷链仓储温控监控需求，尚未立项。"),
		]
		report["steps"]["communication_events"] = []
		for reference, content in events:
			doctype = "CRM Deal" if frappe.db.exists("CRM Deal", reference) else "CRM Lead"
			state = ensure_comment(doctype, reference, content, apply)
			report["steps"]["communication_events"].append({"reference": reference, "state": state})
		frappe.db.commit()

		# 截止跟进任务
		task_a, state_a = ensure_task(
			FOLLOW_UP_A, deal_a, "2026-11-03 10:00:00", "High", "准备试点范围、验收指标与报价；客户要求 11 月第一周给答复。", apply
		)
		task_b, state_b = ensure_task(
			FOLLOW_UP_B, deal_b, "2026-11-05 15:00:00", "Medium", "与客户确认勘查时间与进厂手续。", apply
		)
		report["steps"]["follow_ups"] = [
			{"task": task_a, "state": state_a, "due": "2026-11-03 10:00:00"},
			{"task": task_b, "state": state_b, "due": "2026-11-05 15:00:00"},
		]
		frappe.db.commit()

		# 阶段演进
		report["steps"]["stage_changes"] = {
			deal_a: shift_status(deal_a, ["Demo/Making", "Negotiation"], apply),
			deal_b: shift_status(deal_b, ["Proposal/Quotation"], apply),
		}
		frappe.db.commit()

		# 查询与修改验证：联系人职位、需求线索状态
		contact = frappe.db.get_value("Contact", {"first_name": "样例李二"}, "name")
		contact_change = "未找到联系人"
		if contact:
			doc = frappe.get_doc("Contact", contact)
			if doc.designation != "生产经理":
				doc.designation = "生产经理"
				doc.save()
				frappe.db.commit()
				contact_change = "已更新为生产经理"
			else:
				contact_change = "已是生产经理"
		lead_b_doc = frappe.get_doc("CRM Lead", lead_b)

		report["steps"]["modifications"] = {
			"contact": contact,
			"designation": contact_change,
			"lead_status_after_conversion": lead_b_doc.status,
			"lead_converted": lead_b_doc.converted,
		}

		# 验证：对象关系、查询、时间线
		verification = {}
		for label, deal_name in (("A", deal_a), ("B", deal_b)):
			deal = frappe.get_doc("CRM Deal", deal_name)
			verification[deal_name] = {
				"organization": deal.organization,
				"lead": deal.lead,
				"contacts": [c.contact for c in deal.contacts],
				"status": deal.status,
				"probability": deal.probability,
				"expected_deal_value": deal.expected_deal_value,
				"expected_closure_date": str(deal.expected_closure_date),
				"next_step": deal.next_step,
				"open_follow_ups": frappe.get_all(
					"CRM Task",
					filters={
						"reference_doctype": "CRM Deal",
						"reference_docname": deal_name,
						"status": ["in", ["Backlog", "Todo", "In Progress"]],
					},
					fields=["name", "title", "due_date", "priority", "status"],
				),
				"timeline": timeline(deal_name),
				"stage_history": [
					{
						"from": row.get("from"),
						"to_status": row.to,
						"from_date": str(row.from_date) if row.from_date else None,
						"to_date": str(row.to_date) if row.to_date else None,
						"duration": row.duration,
					}
					for row in deal.status_change_log
				],
			}
		report["verification"] = verification

		org_links = {}
		for org in ("M5样例企业甲 智能制造", "M5样例企业乙 食品加工"):
			org_links[org] = {
				"deals": frappe.get_all("CRM Deal", filters={"organization": org}, pluck="name"),
				"contacts": frappe.get_all(
					"Dynamic Link",
					filters={"link_doctype": "CRM Organization", "link_name": org, "parenttype": "Contact"},
					pluck="parent",
				),
				"leads": frappe.get_all("CRM Lead", filters={"organization": org}, pluck="name"),
			}
		report["cross_object_queries"] = {
			"by_organization": org_links,
			"leads_by_contact_phone": frappe.get_all(
				"CRM Lead", filters={"mobile_no": "13800000001"}, fields=["name", "first_name", "organization", "status"]
			),
		}

		checks = {
			"两个独立商机不同": deal_a != deal_b,
			"商机A有企业/需求/联系人": bool(
				verification[deal_a]["organization"] and verification[deal_a]["lead"] and verification[deal_a]["contacts"]
			),
			"商机B有企业/需求/联系人": bool(
				verification[deal_b]["organization"] and verification[deal_b]["lead"] and verification[deal_b]["contacts"]
			),
			"两商机各有未完成跟进": bool(verification[deal_a]["open_follow_ups"]) and bool(verification[deal_b]["open_follow_ups"]),
			"商机A阶段变更记录": len(verification[deal_a]["stage_history"]) >= 2,
			"商机B阶段变更记录": len(verification[deal_b]["stage_history"]) >= 1,
			"时间线含阶段变更": bool(verification[deal_a]["timeline"]["status_changes"])
			and bool(verification[deal_b]["timeline"]["status_changes"]),
			"时间线含沟通评论": bool(verification[deal_a]["timeline"]["comments"]) and bool(verification[deal_b]["timeline"]["comments"]),
			"需求线索转商机后状态": frappe.db.get_value("CRM Lead", lead_a, "converted") == 1,
		}
		report["checks"] = checks
		if not all(checks.values()):
			exit_code = 3
		print(json.dumps(report, ensure_ascii=False, indent=1, default=str))
		return exit_code
	finally:
		frappe.destroy()


if __name__ == "__main__":
	sys.exit(main())

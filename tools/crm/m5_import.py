"""M5 六列企业资源 CSV 的预览→确认导入适配器。

在 bench 容器内运行（标准库 + 已安装的 frappe，不引入新依赖）：

    cd /home/frappe/frappe-bench/sites
    ../env/bin/python /tmp/m5/m5_import.py preview --csv /tmp/m5/m5-synthetic-six-columns.csv
    ../env/bin/python /tmp/m5/m5_import.py apply --csv /tmp/m5/m5-synthetic-six-columns.csv --confirm

行为边界：
- 企业→CRM Organization（docname 即 organization_name，天然去重键）
- 联系人→Contact（按手机号/邮箱/姓名+企业去重，追加企业 Dynamic Link）
- 需求→CRM Lead（每条需求一条 Lead，状态 New；绝不创建商机）
- 联系方式原文与来源行写入 FCRM Note，不覆盖解析后的字段
- 只写入、不删除；重复执行同文件不产生重复记录
"""

import argparse
import csv
import hashlib
import html
import json
import re
import sys

import frappe

COLUMNS = ["序号", "姓名", "公司名称", "联系方式", "公司产品、服务", "需要的产品、服务"]
IMPORT_SOURCE = "M5导入样例"
KEY_MARKER = "m5-import-key:"

EXIT_OK = 0
EXIT_FATAL = 1
EXIT_ROW_ERRORS = 2


def norm_text(value):
	return re.sub(r"\s+", " ", (value or "").replace("\u3000", " ")).strip()


def phone_candidates(raw):
	found = []
	for chunk in re.findall(r"\+?[\d][\d\s\-()]{4,}[\d]", raw or ""):
		digits = re.sub(r"\D", "", chunk)
		if len(digits) < 6:
			continue
		found.append(digits)
		if digits.startswith("86") and len(digits) > 11:
			found.append(digits[2:])
	return list(dict.fromkeys(found))


def emails(raw):
	return [e.strip().lower() for e in re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", raw or "")]


def import_key(org, person, phone, email, requirement):
	identity = phone or email or f"{org}|{person}"
	payload = "|".join([org, person, identity, requirement])
	return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def read_rows(path):
	with open(path, encoding="utf-8-sig", newline="") as handle:
		reader = csv.reader(handle)
		rows = []
		for index, row in enumerate(reader):
			rows.append((index, row))
	return rows


def parse_file(path):
	rows = read_rows(path)
	if not rows:
		raise SystemExit("CSV 为空")
	header_index, header = rows[0]
	header = [norm_text(c) for c in header]
	missing = [c for c in COLUMNS if c not in header]
	if missing:
		raise SystemExit(f"表头缺少列：{'、'.join(missing)}；实际表头：{header}")
	position = {name: header.index(name) for name in COLUMNS}
	parsed = []
	for line_index, row in rows[1:]:
		if not any(norm_text(cell) for cell in row):
			continue
		record = {name: norm_text(row[position[name]]) if position[name] < len(row) else "" for name in COLUMNS}
		record["line"] = line_index + 1
		parsed.append(record)
	return parsed


def validate(record):
	problems = []
	if not record["姓名"]:
		problems.append("缺少姓名")
	if not record["公司名称"]:
		problems.append("缺少公司名称")
	if not record["需要的产品、服务"]:
		problems.append("缺少需求内容")
	phones = phone_candidates(record["联系方式"])
	mails = emails(record["联系方式"])
	if not phones and not mails:
		problems.append("联系方式无法识别（无手机号或邮箱），不能建立可去重的联系人")
	return problems, phones, mails


def build_contact_index(exclude_deleted=True):
	by_phone, by_email, by_name_company = {}, {}, {}
	filters = {"parenttype": "Contact"} if exclude_deleted else {}
	for row in frappe.get_all("Contact Phone", filters=filters, fields=["parent", "phone"], limit=0):
		for digits in phone_candidates(row.phone or ""):
			by_phone.setdefault(digits, row.parent)
	for row in frappe.get_all("Contact Email", filters=filters, fields=["parent", "email_id"], limit=0):
		key = (row.email_id or "").strip().lower()
		if key:
			by_email.setdefault(key, row.parent)
	for row in frappe.get_all("Contact", fields=["name", "first_name", "company_name"], limit=0):
		by_name_company.setdefault((norm_text(row.first_name).lower(), norm_text(row.company_name)), row.name)
	return {"phone": by_phone, "email": by_email, "name_company": by_name_company}


def find_contact(index, person, org, phones, mails):
	for phone in phones:
		if phone in index["phone"]:
			return index["phone"][phone], "手机号"
	for mail in mails:
		if mail in index["email"]:
			return index["email"][mail], "邮箱"
	key = (person.lower(), org)
	if key in index["name_company"]:
		return index["name_company"][key], "姓名+企业"
	return None, None


def find_lead(key):
	notes = frappe.get_all(
		"FCRM Note",
		filters={"reference_doctype": "CRM Lead", "content": ["like", f"%{KEY_MARKER}{key}%"]},
		fields=["reference_docname"],
		limit=1,
	)
	return notes[0].reference_docname if notes else None


def plan(records):
	index = build_contact_index()
	plan_rows = []
	seen_keys = set()
	seen_orgs = set()
	for record in records:
		problems, phones, mails = validate(record)
		row = {"record": record, "problems": problems, "phones": phones, "mails": mails}
		if not problems:
			org = record["公司名称"]
			person = record["姓名"]
			key = import_key(org, person, phones[0] if phones else "", mails[0] if mails else "", record["需要的产品、服务"])
			row["key"] = key
			row["org_new"] = not (bool(frappe.db.exists("CRM Organization", org)) or org in seen_orgs)
			row["org_exists"] = not row["org_new"]
			seen_orgs.add(org)
			contact, matched_by = find_contact(index, person, org, phones, mails)
			row["contact"], row["matched_by"] = contact, matched_by
			if key in seen_keys:
				row["lead"], row["lead_state"] = None, "文件内重复"
			else:
				existing = find_lead(key)
				row["lead"], row["lead_state"] = existing, ("已导入" if existing else "新建")
			seen_keys.add(key)
			if not contact:
				row["contact_state"] = "新建"
				index["name_company"].setdefault((person.lower(), org), f"<new:{key[:8]}>")
				for phone in phones:
					index["phone"][phone] = f"<new:{key[:8]}>"
				for mail in mails:
					index["email"][mail] = f"<new:{key[:8]}>"
			else:
				row["contact_state"] = f"复用({matched_by})"
		plan_rows.append(row)
	return plan_rows


def preview_output(plan_rows):
	lines = []
	lines.append("行\t序号\t企业\t联系人\t需求")
	for row in plan_rows:
		record = row["record"]
		if row["problems"]:
			lines.append(
				f"{record['line']}\t{record['序号']}\t错误\t{record['姓名'] or '-'}\t{'；'.join(row['problems'])}"
			)
			continue
		org_state = "复用" if row["org_exists"] else "新建"
		lines.append(
			f"{record['line']}\t{record['序号']}\t{org_state}:{record['公司名称']}\t"
			f"{row['contact_state']}:{record['姓名']}\t需求{row['lead_state']}"
		)
	return "\n".join(lines)


def ensure_source():
	name = IMPORT_SOURCE
	if not frappe.db.exists("CRM Lead Source", name):
		frappe.get_doc({"doctype": "CRM Lead Source", "source_name": name}).insert(ignore_permissions=True)
	return name


def note_exists(reference_doctype, reference_docname, key):
	return bool(
		frappe.db.exists(
			"FCRM Note",
			{
				"reference_doctype": reference_doctype,
				"reference_docname": reference_docname,
				"content": ["like", f"%{KEY_MARKER}{key}%"],
			},
		)
	)


def make_note(title, body_lines, reference_doctype, reference_docname, key):
	if note_exists(reference_doctype, reference_docname, key):
		return None
	content = "".join(f"<p>{line}</p>" for line in body_lines)
	content += f"<!-- {KEY_MARKER}{key} -->"
	note = frappe.new_doc("FCRM Note")
	note.title = title
	note.content = content
	note.reference_doctype = reference_doctype
	note.reference_docname = reference_docname
	note.insert(ignore_permissions=True)
	return note.name


def apply_row(row, source, csv_name, owner):
	record = row["record"]
	org_name = record["公司名称"]
	org = org_name if frappe.db.exists("CRM Organization", org_name) else None
	if not org:
		doc = frappe.new_doc("CRM Organization")
		doc.organization_name = org_name
		if record["公司产品、服务"]:
			doc.company_description = record["公司产品、服务"]
		doc.insert(ignore_permissions=True)
		org = doc.name

	index = build_contact_index()
	contact, _ = find_contact(index, record["姓名"], org_name, row["phones"], row["mails"])
	contact_created = False
	if not contact:
		doc = frappe.new_doc("Contact")
		doc.first_name = record["姓名"]
		doc.company_name = org_name
		for phone in row["phones"][:1]:
			doc.append("phone_nos", {"phone": phone, "is_primary_mobile_no": 1})
		for mail in row["mails"][:1]:
			doc.append("email_ids", {"email_id": mail, "is_primary": 1})
		doc.append("links", {"link_doctype": "CRM Organization", "link_name": org})
		doc.insert(ignore_permissions=True)
		contact = doc.name
		contact_created = True

	provenance = [
		f"<strong>联系方式原文：</strong>{html.escape(record['联系方式'] or '未提供')}",
		f"<strong>来源文件：</strong>{html.escape(csv_name)} 第 {record['line']} 行（序号 {html.escape(record['序号'] or '-')}）",
		f"<strong>企业：</strong>{html.escape(org)}　<strong>联系人：</strong>{html.escape(contact)}",
	]
	contact_note = None
	if contact_created:
		contact_note = make_note(
			f"导入来源：{record['姓名']}",
			provenance,
			"Contact",
			contact,
			row["key"],
		)

	lead = find_lead(row["key"])
	lead_state = "已存在" if lead else "新建"
	if not lead:
		doc = frappe.new_doc("CRM Lead")
		doc.first_name = record["姓名"]
		doc.organization = org_name
		if row["phones"]:
			doc.mobile_no = row["phones"][0]
		if row["mails"]:
			doc.email = row["mails"][0]
		doc.status = "New"
		doc.source = source
		if owner:
			doc.lead_owner = owner
		doc.insert(ignore_permissions=True)
		lead = doc.name

	requirement = record["需要的产品、服务"]
	lead_note = make_note(
		f"需求线索（导入）：{requirement[:40]}",
		[
			f"<strong>需求原文：</strong>{html.escape(requirement)}",
			f"<strong>企业提供：</strong>{html.escape(record['公司产品、服务'] or '未提供')}",
		]
		+ provenance
		+ ["<strong>说明：</strong>本记录是需求线索，未升级为商机；升级需人工确认。"],
		"CRM Lead",
		lead,
		row["key"],
	)

	return {"org": org, "contact": contact, "contact_note": contact_note, "lead": lead, "lead_state": lead_state, "lead_note": lead_note}


def main(argv=None):
	parser = argparse.ArgumentParser(description="M5 六列企业资源 CSV 预览/确认导入")
	parser.add_argument("command", choices=["preview", "apply"])
	parser.add_argument("--csv", required=True)
	parser.add_argument("--site", default="crm.localhost")
	parser.add_argument("--sites-path", default=".")
	parser.add_argument("--confirm", action="store_true", help="apply 必需：确认写入")
	parser.add_argument("--owner", default=None, help="写入 Lead 的负责人，默认当前登录用户")
	args = parser.parse_args(argv)

	if args.command == "apply" and not args.confirm:
		print("apply 需要 --confirm 才会写库；先运行 preview 检查计划。")
		return EXIT_FATAL

	frappe.init(site=args.site, sites_path=args.sites_path)
	frappe.connect()
	try:
		records = parse_file(args.csv)
		if not records:
			print("CSV 没有数据行")
			return EXIT_FATAL
		plan_rows = plan(records)
		print(preview_output(plan_rows))
		error_rows = [row for row in plan_rows if row["problems"]]
		creates = {
			"企业": sum(1 for row in plan_rows if not row["problems"] and row["org_new"]),
			"联系人": sum(1 for row in plan_rows if not row["problems"] and row["contact_state"] == "新建"),
			"需求": sum(1 for row in plan_rows if not row["problems"] and row["lead_state"] == "新建"),
			"需求跳过": sum(1 for row in plan_rows if not row["problems"] and row["lead_state"] != "新建"),
			"错误行": len(error_rows),
		}
		print("\n计划汇总：" + "，".join(f"{k}={v}" for k, v in creates.items()))

		if args.command == "preview":
			return EXIT_ROW_ERRORS if error_rows else EXIT_OK

		source = ensure_source()
		owner = args.owner or frappe.session.user
		results = []
		for row in plan_rows:
			record = row["record"]
			if row["problems"]:
				results.append({"line": record["line"], "序号": record["序号"], "状态": "失败", "原因": "；".join(row["problems"])})
				continue
			try:
				result = apply_row(row, source, args.csv.split("/")[-1], owner)
				frappe.db.commit()
				results.append({"line": record["line"], "序号": record["序号"], "状态": "成功", **result})
			except Exception as exc:
				frappe.db.rollback()
				results.append({"line": record["line"], "序号": record["序号"], "状态": "失败", "原因": f"{type(exc).__name__}: {exc}"})
		print("\n写入结果：")
		print(json.dumps(results, ensure_ascii=False, indent=1, default=str))
		failed = [r for r in results if r["状态"] == "失败"]
		print(
			f"\n完成：成功 {len(results) - len(failed)} 行，失败 {len(failed)} 行；"
			f"企业 {len({r.get('org') for r in results if r.get('org')})} 个、"
			f"联系人 {len({r.get('contact') for r in results if r.get('contact')})} 个、"
			f"需求 {len({r.get('lead') for r in results if r.get('lead')})} 条。"
		)
		return EXIT_ROW_ERRORS if failed else EXIT_OK
	finally:
		frappe.destroy()


if __name__ == "__main__":
	sys.exit(main())

"""合成数据防护（仅标准库，不导入 frappe）。

M5 的脚本只用于**合成数据**验证。M6 已通过两个真实 Sales User 的 HTTP 请求证实：
FCRM Note 的私密 detail/PUT 均返回 200（跨用户越权），activities 也会泄漏未共享的 note。
因此这些脚本写入的联系方式原文/来源备注**不得承载真实客户资料**，生产导入入口属于 M7。

防护是内容级的、默认生效、没有旁路开关：任何一行的企业名不以 `M5` 开头，
或姓名不以 `样例` 开头，就直接拒绝执行并列出违规行。
"""

SYNTHETIC_COMPANY_PREFIX = "M5"
SYNTHETIC_PERSON_PREFIX = "样例"

BANNER = "仅合成数据：企业名须以 M5 开头、姓名须以 样例 开头；真实客户资料请使用 M7 导入入口。"


class SyntheticInputError(ValueError):
	pass


def check_rows(rows):
	"""返回违规列表 [(行号, 原因)]；空值不算违规（交由正常校验报"缺字段"）。"""
	violations = []
	for row in rows:
		line = row.get("line")
		company = (row.get("公司名称") or "").strip()
		person = (row.get("姓名") or "").strip()
		if company and not company.startswith(SYNTHETIC_COMPANY_PREFIX):
			violations.append((line, f"企业名 {company!r} 未以 {SYNTHETIC_COMPANY_PREFIX} 开头"))
		if person and not person.startswith(SYNTHETIC_PERSON_PREFIX):
			violations.append((line, f"姓名 {person!r} 未以 {SYNTHETIC_PERSON_PREFIX} 开头"))
	return violations


def require_synthetic(rows):
	violations = check_rows(rows)
	if violations:
		detail = "；".join(f"第 {line} 行：{reason}" for line, reason in violations[:10])
		more = "" if len(violations) <= 10 else f"（共 {len(violations)} 条）"
		raise SyntheticInputError(
			"拒绝执行：输入不是合成数据。"
			f"{detail}{more}。{BANNER}"
		)

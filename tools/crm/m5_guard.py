"""合成数据防护（仅标准库，不导入 frappe）。

M5 的脚本只是**历史合成验证工具**，不是真实资料导入路径。M6 已用两个真实 Sales User 的
HTTP 请求证实：FCRM Note 私密 detail/PUT 均返回 200（跨用户越权读写），activities 也会
返回未共享的 note —— 所以这些脚本写入的原文备注不得承载真实客户资料。

防护分两层，且**没有旁路开关、不接受调用方自报摘要**：

1. **可信摘要闸门（主）**：`apply` 只接受与仓库固定合成样例*完全一致*的文件内容。
   摘要清单来自本文件的 `TRUSTED_SAMPLES` 常量（仓库内容），不读取任何用户提供的哈希值。
   任何改动过的联系方式、产品、需求或来源都会改变摘要而被拒绝。
2. **行级合成标记（辅）**：企业名须以 `M5` 开头、姓名须以 `样例` 开头，违规则拒绝。

`preview` 同样走这两层，且输出明确标注"仅解析演示、不是真实数据导入路径"。
"""

import hashlib
from pathlib import Path

# 仓库内固定合成样例的 SHA-256（按 LF 归一化、去 BOM 后的字节计算）。
# 新增样例必须先在仓库提交，再把摘要写死在这里，禁止运行时由用户文件自证。
TRUSTED_SAMPLES = {
	"m5-synthetic-six-columns.csv": "fd6b9b8e363ea83d210265dcc801c3fb0723421b146bdb76eaeb6903d6493bd3",
}

SYNTHETIC_COMPANY_PREFIX = "M5"
SYNTHETIC_PERSON_PREFIX = "样例"

BANNER = (
	"仅合成数据：本工具只接受仓库固定合成样例的精确内容（企业名以 M5 开头、姓名以 样例 开头）；"
	"真实客户资料请使用 M7 导入入口。"
)
PREVIEW_NOTE = "预览仅是解析演示，不是真实数据导入路径；写入同样只接受可信清单内的合成样例。"


class SyntheticInputError(ValueError):
	pass


def normalized_digest(path):
	data = Path(path).read_bytes()
	if data.startswith(b"\xef\xbb\xbf"):
		data = data[3:]
	return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def trusted_sample_name(path):
	digest = normalized_digest(path)
	for name, expected in TRUSTED_SAMPLES.items():
		if digest == expected:
			return name
	return None


def check_rows(rows):
	"""行级合成标记检查，返回违规列表 [(行号, 原因)]；空值交由正式校验报"缺字段"。"""
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
		raise SyntheticInputError(f"拒绝执行：输入不是合成数据。{detail}{more}。{BANNER}")


def require_trusted_sample(path, rows):
	"""两层校验：先比对仓库可信摘要，再校验行级合成标记。"""
	name = trusted_sample_name(path)
	if not name:
		digest = normalized_digest(path)
		allowed = "、".join(sorted(TRUSTED_SAMPLES))
		raise SyntheticInputError(
			"拒绝执行：该文件内容不在仓库可信合成样例清单内"
			f"（摘要 {digest[:12]}…；允许：{allowed}）。"
			"任何修改过的联系方式/产品/需求/来源都会被拒绝；真实资料请用 M7 导入入口。"
		)
	require_synthetic(rows)
	return name

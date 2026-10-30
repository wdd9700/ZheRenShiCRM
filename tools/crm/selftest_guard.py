"""合成数据防护的本地静态自检（不连实例、不导入 frappe）。

    python tools/crm/selftest_guard.py

覆盖：样例 CSV 必须通过；像真实公司的输入必须被拒绝；缺字段的空值不算违规。
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from m5_guard import SyntheticInputError, check_rows, require_synthetic

SAMPLE = Path(__file__).resolve().parents[2] / "samples" / "m5-synthetic-six-columns.csv"
COLUMNS = ["序号", "姓名", "公司名称"]


def load(path):
	rows = []
	with path.open(encoding="utf-8-sig", newline="") as handle:
		reader = csv.DictReader(handle)
		for index, raw in enumerate(reader, start=2):
			row = {name: (raw.get(name) or "").strip() for name in COLUMNS}
			row["line"] = index
			rows.append(row)
	return rows


def main():
	rows = load(SAMPLE)
	violations = check_rows(rows)
	assert violations == [], f"样例 CSV 不应违规，实际：{violations}"

	real_like = [
		{"line": 2, "姓名": "张三", "公司名称": "某科技有限公司"},
		{"line": 3, "姓名": "样例李四", "公司名称": "M5样例企业甲 智能制造"},
	]
	caught = check_rows(real_like)
	assert len(caught) == 2, f"应拒绝 2 处，实际：{caught}"
	assert caught[0][0] == 2
	raised = False
	try:
		require_synthetic(real_like)
	except SyntheticInputError as exc:
		raised = "拒绝执行" in str(exc)
	assert raised, "require_synthetic 应抛出拒绝"

	partial = [
		{"line": 4, "姓名": "", "公司名称": "M5样例企业甲 智能制造"},
		{"line": 5, "姓名": "样例王五", "公司名称": ""},
	]
	assert check_rows(partial) == [], "缺字段空值应交由正式校验，不算合成违规"

	print("PASS: 样例通过；真实样式输入被拒（含行号）；缺字段空值不误报")
	return 0


if __name__ == "__main__":
	sys.exit(main())

"""合成数据防护与历史键的本地静态自检（不连实例、不导入 frappe）。

    python tools/crm/selftest_guard.py

覆盖：
1. 仓库样例摘要必须命中可信清单；`require_trusted_sample` 接受它；
2. 合法名字前缀 + 真实样式联系方式/需求（评审探针）必须被拒绝；
3. 只改一个手机号数字的样例副本必须被拒绝；
4. CRLF/BOM 变体（内容一致）必须被接受（摘要按 LF 归一化）；
5. 历史幂等键保持 16 位（不得悄悄改成 40 位，否则旧合成数据会重插）；
6. `apply_row` 内部调用 `ensure_source`（避免首行失败回滚后级联）。
"""

import ast
import csv
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from m5_guard import (
	TRUSTED_SAMPLES,
	SyntheticInputError,
	check_rows,
	normalized_digest,
	require_synthetic,
	require_trusted_sample,
	trusted_sample_name,
)

HERE = Path(__file__).resolve().parent
SAMPLE = HERE.parents[1] / "samples" / "m5-synthetic-six-columns.csv"
IMPORT_SCRIPT = HERE / "m5_import.py"
COLUMNS = ["序号", "姓名", "公司名称"]


def load(path):
	rows = []
	with path.open(encoding="utf-8-sig", newline="") as handle:
		for index, raw in enumerate(csv.DictReader(handle), start=2):
			row = {name: (raw.get(name) or "").strip() for name in COLUMNS}
			row["line"] = index
			rows.append(row)
	return rows


def expect_rejected(path, rows, label):
	try:
		require_trusted_sample(path, rows)
	except SyntheticInputError as exc:
		assert "拒绝执行" in str(exc), f"{label}: 拒绝信息不明确：{exc}"
		return
	raise AssertionError(f"{label}: 应被拒绝但被接受")


def main():
	# 1. 三个仓库样例都必须命中可信清单，且清单里的文件都在仓库里
	samples_dir = SAMPLE.parent
	assert len(TRUSTED_SAMPLES) == 3, f"可信清单数量异常：{TRUSTED_SAMPLES}"
	for name, expected in TRUSTED_SAMPLES.items():
		path = samples_dir / name
		assert path.is_file(), f"可信清单指向不存在的文件：{name}"
		assert normalized_digest(path) == expected, f"摘要与清单不符：{name}"
		assert require_trusted_sample(path, load(path)) == name
	digest = normalized_digest(SAMPLE)
	assert digest in TRUSTED_SAMPLES.values(), f"样例摘要未在可信清单：{digest}"
	assert trusted_sample_name(SAMPLE) == "m5-synthetic-six-columns.csv"
	rows = load(SAMPLE)
	assert check_rows(rows) == []
	assert require_trusted_sample(SAMPLE, rows) == "m5-synthetic-six-columns.csv"

	with tempfile.TemporaryDirectory() as tmp:
		tmp = Path(tmp)

		# 2. 评审探针：合法前缀 + 真实样式联系方式/需求 → 必须拒绝
		probe = tmp / "probe.csv"
		probe.write_text(
			"序号,姓名,公司名称,联系方式,公司产品、服务,需要的产品、服务\n"
			"P-1,样例张三,M5真实客户企业,13812345678 / 微信 zhangsan_real,真实主营,真实未公开需求\n",
			encoding="utf-8",
		)
		expect_rejected(probe, load(probe), "真实样式载荷（前缀合法）")

		# 3. 改一个手机号数字的样例副本 → 摘要失配
		altered = (SAMPLE.read_text(encoding="utf-8")).replace("13800000001", "13800000009")
		altered_path = tmp / "altered.csv"
		altered_path.write_text(altered, encoding="utf-8")
		expect_rejected(altered_path, load(altered_path), "改动手机号")

		# 4. 归一化：CRLF + BOM 的同内容样例应被接受
		crlf = tmp / "crlf.csv"
		crlf.write_bytes(b"\xef\xbb\xbf" + SAMPLE.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
		assert require_trusted_sample(crlf, load(crlf)) == "m5-synthetic-six-columns.csv"

	# 5. 历史键保持 16 位
	source = IMPORT_SCRIPT.read_text(encoding="utf-8")
	tree = ast.parse(source)
	key_fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "import_key")
	return_expr = ast.unparse(key_fn.body[-1].value)
	assert return_expr.endswith("[:16]"), f"import_key 必须保持 16 位历史算法，实际：{return_expr}"

	# 6. apply_row 自己确保 Source（避免首行失败回滚后级联）
	apply_fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "apply_row")
	called = {node.func.id for node in ast.walk(apply_fn) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
	assert "ensure_source" in called, "apply_row 内必须调用 ensure_source"

	# 行级标记仍作为第二层
	real_like = [
		{"line": 2, "姓名": "张三", "公司名称": "某科技有限公司"},
		{"line": 3, "姓名": "样例李四", "公司名称": "M5样例企业甲 智能制造"},
	]
	assert len(check_rows(real_like)) == 2
	try:
		require_synthetic(real_like)
	except SyntheticInputError:
		pass
	else:
		raise AssertionError("require_synthetic 应抛错")

	print(
		"PASS: 三个可信样例摘要命中；真实样式载荷/单点改动被拒；CRLF+BOM 归一；"
		"16 位历史键未变；apply_row 自保 Source；行级标记仍生效"
	)
	return 0


if __name__ == "__main__":
	sys.exit(main())

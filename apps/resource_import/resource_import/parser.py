import csv
import hashlib
import io
import json
import re

COLUMNS = ["序号", "姓名", "公司名称", "联系方式", "公司产品、服务", "需要的产品、服务"]
MAX_BYTES = 1024 * 1024
MAX_ROWS = 500


class InputError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def parse(csv_text, source):
    if not isinstance(csv_text, str) or len(csv_text.encode("utf-8")) > MAX_BYTES:
        raise InputError("文件必须是最多1MiB的UTF-8 CSV")
    if not isinstance(source, str) or not source.strip() or len(source) > 200 or any(c in source for c in "\r\n\x00"):
        raise InputError("来源文件名须为1至200字符且不含换行")
    try:
        reader = csv.reader(io.StringIO(csv_text.removeprefix("\ufeff"), newline=""), strict=True)
        header = next(reader)
        if len(header) != 6 or set(header) != set(COLUMNS):
            raise InputError("CSV表头须恰好包含六列：" + "、".join(COLUMNS))
        records = []
        for values in reader:
            if not any(values):
                continue
            if len(records) >= MAX_ROWS:
                raise InputError("最多500数据行")
            errors = []
            if len(values) != 6:
                errors.append("列数必须为6")
            if any(len(value) > 10000 or "\x00" in value for value in values):
                errors.append("每格最多10000字符且不得含空字符")
            raw = dict(zip(header, (values + [""] * 6)[:6]))
            for column in ("姓名", "公司名称", "需要的产品、服务"):
                if not raw[column].strip():
                    errors.append("缺少" + column)
            for column in ("姓名", "公司名称"):
                if len(raw[column].strip()) > 100:
                    errors.append(column + "最多100字符")
            if not raw["联系方式"].strip():
                errors.append("缺少联系方式")
            records.append({"line": reader.line_num, "raw": raw, "errors": errors, "key": digest(["resource-import-v1"] + [raw[c] for c in COLUMNS[1:]])})
        if not records:
            raise InputError("CSV没有数据行")
        return records
    except (csv.Error, StopIteration) as exc:
        raise InputError("CSV格式错误或文件为空") from exc


def identities(raw):
    phones = list(dict.fromkeys(re.sub(r"\D", "", p) for p in re.findall(r"\+?\d[\d ()-]{4,}\d", raw)))
    phones = [p for p in phones if 6 <= len(p) <= 15]
    mails = list(dict.fromkeys(m.lower() for m in re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", raw)))
    return phones, mails

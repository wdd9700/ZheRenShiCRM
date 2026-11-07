import argparse
import csv
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import re
import sys


DOCTYPES = (
    "CRM Organization", "Contact", "CRM Lead", "CRM Deal", "CRM Task", "FCRM Note",
    "Comment", "Communication", "File", "Version", "DocShare", "Custom Field",
)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def csv_cell(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        value = canonical(value)
    if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        value = "'" + value
    return value


def write_new(path, content):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
        stream.write(content)


def collect(frappe):
    records = {}
    for doctype in DOCTYPES:
        names = frappe.get_all(doctype, pluck="name", order_by="name asc", limit_page_length=0)
        records[doctype] = [json.loads(frappe.as_json(frappe.get_doc(doctype, name).as_dict())) for name in names]
    exported = {doctype: {row["name"] for row in rows} for doctype, rows in records.items()}
    edges = []
    cache = {}

    def reference(doctype, name):
        key = (doctype, str(name))
        if key not in cache:
            cache[key] = bool(frappe.db.exists(doctype, name))
        return cache[key]

    def walk(source_type, source_name, row, doctype, prefix=""):
        for field in frappe.get_meta(doctype).fields:
            value = row.get(field.fieldname)
            if not value:
                continue
            path = prefix + field.fieldname
            if field.fieldtype in ("Table", "Table MultiSelect"):
                for index, child in enumerate(value):
                    walk(source_type, source_name, child, field.options, f"{path}[{index}].")
            elif field.fieldtype in ("Link", "Dynamic Link"):
                target_type = field.options if field.fieldtype == "Link" else row.get(field.options)
                if target_type:
                    edges.append({
                        "source_type": source_type, "source_id": source_name, "field": path,
                        "target_type": target_type, "target_id": str(value),
                        "exists": reference(target_type, value), "in_export": str(value) in exported.get(target_type, set()),
                    })

    for doctype, rows in records.items():
        for row in rows:
            walk(doctype, row["name"], row, doctype)
    edges.sort(key=canonical)
    summary = {
        "format": "crm-state-v1",
        "apps": {app: importlib.import_module(app).__version__ for app in ("frappe", "crm", "resource_import", "team_access")},
        "doctypes": {doctype: {"count": len(rows), "sha256": digest(rows)} for doctype, rows in records.items()},
        "references": {"count": len(edges), "missing": sum(not edge["exists"] for edge in edges), "sha256": digest(edges)},
    }
    summary["state_sha256"] = digest(summary)
    return records, edges, summary


def export(site, run, records, edges, summary):
    parent = Path(site) / "private" / "recovery-exports"
    for path in (parent, *parent.parents):
        if path.is_symlink():
            raise RuntimeError("Controlled export refuses linked paths")
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = parent / run
    target.mkdir(mode=0o700)
    payload = {"format": "crm-controlled-export-v1", "site": site, "summary": summary, "records": records, "references": edges}
    write_new(target / "records-and-relations.json", canonical(payload) + "\n")
    for doctype, rows in records.items():
        columns = sorted({key for row in rows for key in row})
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: csv_cell(row.get(key)) for key in columns})
        write_new(target / (doctype.replace(" ", "_") + ".csv"), stream.getvalue())
    decoded = json.loads((target / "records-and-relations.json").read_text(encoding="utf-8"))
    if decoded["records"] != records or decoded["references"] != edges or decoded["summary"] != summary:
        raise RuntimeError("Controlled export readback mismatch")
    for doctype, rows in records.items():
        with (target / (doctype.replace(" ", "_") + ".csv")).open(encoding="utf-8", newline="") as stream:
            restored = list(csv.DictReader(stream))
        columns = sorted({key for row in rows for key in row})
        expected = [{key: csv_cell(row.get(key)) for key in columns} for row in rows]
        if restored != expected:
            raise RuntimeError("Controlled CSV export content/identity/count mismatch")
    return str(target)


def main():
    parser = argparse.ArgumentParser(description="Administrator persistence/export evidence, not a user-permission test")
    parser.add_argument("--site", required=True, choices=("crm.localhost", "recovery.localhost"))
    parser.add_argument("--snapshot-run", required=True)
    parser.add_argument("--expected-summary")
    parser.add_argument("--export-run")
    parser.add_argument("--confirm-synthetic-admin-export", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"M9[A-Za-z0-9_-]{1,64}", args.snapshot_run):
        parser.error("Snapshot requires a unique M9 run ID")
    if args.export_run and (not args.confirm_synthetic_admin_export or not re.fullmatch(r"M9[A-Za-z0-9_-]{1,64}", args.export_run)):
        parser.error("Export requires an M9 run ID and explicit synthetic administrator-export confirmation")
    import frappe

    frappe.init(site=args.site, sites_path=".")
    try:
        frappe.connect()
        frappe.set_user("Administrator")
        records, edges, summary = collect(frappe)
        parent = Path(args.site) / "private" / "recovery-evidence"
        for path in (parent, *parent.parents):
            if path.is_symlink():
                raise RuntimeError("Snapshot refuses linked paths")
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = parent / (args.snapshot_run + ".json")
        write_new(target, canonical(summary) + "\n")
        if args.expected_summary:
            expected = json.loads(Path(args.expected_summary).read_text(encoding="utf-8"))
            if summary != expected:
                raise RuntimeError("Persistence snapshot mismatch; preserve both states for investigation")
            print("PASS: object contents, original text, relationships and security schema match the expected private snapshot")
        if args.export_run:
            target = export(args.site, args.export_run, records, edges, summary)
            print(f"PASS: controlled administrator JSON/CSV export roundtrip retained privately at {target}")
        print("PASS: private persistence evidence retained; counts only:")
        for doctype, item in summary["doctypes"].items():
            print(f"{doctype}: {item['count']}")
        print(f"References: {summary['references']['count']}; missing: {summary['references']['missing']}")
    finally:
        frappe.destroy()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {type(error).__name__}; state/export check did not pass; no record deleted", file=sys.stderr)
        sys.exit(1)

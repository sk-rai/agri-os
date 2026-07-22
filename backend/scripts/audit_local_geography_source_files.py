#!/usr/bin/env python3
"""Inventory local geography source files without database writes.

This is the first CSV/XML/XLS local-file path before staging/import. It reports
file type, size, likely role, headers, row counts where cheap, and source gaps.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

GEOGRAPHY_HINTS = {
    "state": ["state", "statename", "statecode", "state_lgd"],
    "district": ["district", "districtname", "districtcode", "district_lgd"],
    "sub_district": ["subdistrict", "sub_district", "tehsil", "taluk", "block", "blockname"],
    "village": ["village", "villagename", "villagecode", "village_lgd"],
    "gram_panchayat": ["grampanchayat", "gram_panchayat", "gpname", "gpcode"],
    "pin_code": ["pincode", "pin_code", "pin"],
    "census": ["census"],
    "lgd": ["lgd"],
}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text).lower())


def _classify_headers(headers: list[str]) -> dict[str, list[str]]:
    normalized = {header: _norm(header) for header in headers}
    result: dict[str, list[str]] = {}
    for role, hints in GEOGRAPHY_HINTS.items():
        matches = [
            header
            for header, norm in normalized.items()
            if any(_norm(hint) in norm for hint in hints)
        ]
        if matches:
            result[role] = sorted(set(matches))
    return result


def _detect_role(path: Path, headers: list[str]) -> str:
    text = _norm(path.name + " " + " ".join(headers))
    if "villagegrampanchayat" in text or "grampanchayat" in text:
        return "VILLAGE_GRAM_PANCHAYAT_MAPPING"
    if "village" in text:
        return "VILLAGES"
    if "block" in text:
        return "BLOCKS_OR_SUB_DISTRICTS"
    if "subdistrict" in text:
        return "SUB_DISTRICTS"
    if "district" in text:
        return "DISTRICTS"
    if "pincode" in text or "pin" in text:
        return "PIN_CODES"
    return "UNKNOWN"


def _csv_summary(path: Path, sample_rows: int) -> dict[str, Any]:
    encodings = ["utf-8-sig", "utf-8", "latin-1"]
    last_error = None
    for encoding in encodings:
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                sample = handle.read(4096)
                handle.seek(0)
                dialect = csv.Sniffer().sniff(sample) if sample.strip() else csv.excel
                reader = csv.DictReader(handle, dialect=dialect)
                headers = list(reader.fieldnames or [])
                rows = []
                row_count = 0
                for row in reader:
                    row_count += 1
                    if len(rows) < sample_rows:
                        rows.append({str(k): ("" if v is None else str(v)[:120]) for k, v in row.items()})
                return {
                    "parser": "csv",
                    "encoding": encoding,
                    "headers": headers,
                    "row_count": row_count,
                    "sample_rows": rows,
                    "classified_fields": _classify_headers(headers),
                    "detected_role": _detect_role(path, headers),
                }
        except Exception as exc:
            last_error = exc
    return {"parser": "csv", "error": last_error.__class__.__name__ if last_error else "UNKNOWN", "message": str(last_error) if last_error else ""}


def _xml_summary(path: Path, sample_rows: int) -> dict[str, Any]:
    try:
        root = ET.parse(path).getroot()
    except Exception as exc:
        return {"parser": "xml", "error": exc.__class__.__name__, "message": str(exc)}

    rows: list[dict[str, str]] = []
    headers: set[str] = set()
    for elem in root.iter():
        children = list(elem)
        if not children:
            continue
        row = {}
        for child in children:
            text = child.text.strip() if child.text else ""
            if text:
                row[child.tag] = text[:120]
                headers.add(child.tag)
        if row:
            rows.append(row)
            if len(rows) >= sample_rows:
                break

    header_list = sorted(headers)
    return {
        "parser": "xml",
        "root_tag": root.tag,
        "headers": header_list,
        "sample_rows": rows,
        "classified_fields": _classify_headers(header_list),
        "detected_role": _detect_role(path, header_list),
    }


def _xls_summary(path: Path) -> dict[str, Any]:
    # Existing LGD files are SpreadsheetML with .xls extension. Avoid heavy Excel
    # dependencies here; parse_lgd_xls.py remains the richer parser.
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        return {"parser": "xls_text_probe", "error": exc.__class__.__name__, "message": str(exc)}

    headers = []
    for match in re.finditer(r"<Data[^>]*>(.*?)</Data>", text, flags=re.IGNORECASE | re.DOTALL):
        value = re.sub(r"<[^>]+>", "", match.group(1)).strip()
        if value:
            headers.append(value[:120])
        if len(headers) >= 40:
            break

    return {
        "parser": "xls_text_probe",
        "note": "Use acquire_master_data/parse_lgd_xls.py for full SpreadsheetML parsing.",
        "first_data_values": headers,
        "classified_fields": _classify_headers(headers),
        "detected_role": _detect_role(path, headers),
    }


def _file_summary(path: Path, sample_rows: int) -> dict[str, Any]:
    suffix = path.suffix.lower()
    summary: dict[str, Any] = {
        "path": str(path),
        "name": path.name,
        "suffix": suffix,
        "size_bytes": path.stat().st_size,
    }
    if suffix == ".csv":
        summary.update(_csv_summary(path, sample_rows))
    elif suffix == ".xml":
        summary.update(_xml_summary(path, sample_rows))
    elif suffix in {".xls", ".xlsx"}:
        summary.update(_xls_summary(path))
    else:
        summary.update({"parser": "unsupported"})
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit local geography source files.")
    parser.add_argument("--root", action="append", default=["../data/raw", "../data/raw/lgd"], help="Source root to scan; may be repeated.")
    parser.add_argument("--sample-rows", type=int, default=2)
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    files: dict[str, Path] = {}
    for root_text in args.root:
        root = (script_dir.parent / root_text).resolve()
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".csv", ".xml", ".xls", ".xlsx"}:
                files[str(path)] = path

    summaries = [_file_summary(path, args.sample_rows) for path in sorted(files.values())]
    role_counts: dict[str, int] = {}
    for item in summaries:
        role = item.get("detected_role") or "UNKNOWN"
        role_counts[str(role)] = role_counts.get(str(role), 0) + 1

    result = {
        "schema_version": "local_geography_source_inventory.v1",
        "file_count": len(summaries),
        "role_counts": dict(sorted(role_counts.items())),
        "files": summaries,
        "next_actions": [
            "Use parsed CSVs for quick staging tests where available.",
            "Refactor SpreadsheetML parsing from acquire_master_data/parse_lgd_xls.py into reusable local-file ingestion helpers.",
            "Do not apply DB changes until local files are staged, validated, and diffed.",
        ],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

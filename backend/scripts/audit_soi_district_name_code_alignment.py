#!/usr/bin/env python3
"""
Read-only audit: match Survey of India district rows to backend LGD master by normalized
state+district name, then compare SOI STATE_LGD/DIST_LGD fields against backend codes.

No DB writes. No external calls.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import shapefile
from sqlalchemy import text

from app.core.database import SessionLocal


ROOT = Path(__file__).resolve().parents[2]
SOI_SHP = ROOT / "data/staged/boundaries/survey_of_india/state_district_subdistrict_pan_india/State_District_Subdistrict_PAN INDIA/District_Subdistrict_PAN INDIA/District Boundary.shp"
OUT_DIR = ROOT / "data/staged/core_stack/soi_crosswalk"
OUT_CSV = OUT_DIR / "soi_district_name_code_alignment.csv"
OUT_JSON = OUT_DIR / "soi_district_name_code_alignment.json"

INVALID = {"", "NOT AVAILABLE", "NA", "N/A", "NULL", "NONE", "0"}


ALIASES = {
    "dadra nagar haveli daman diu": "dadra and nagar haveli and daman and diu",
    "dadra and nagar haveli and daman and diu": "dadra and nagar haveli and daman and diu",
    "jammu kashmir": "jammu and kashmir",
    "odisha": "odisha",
    "orissa": "odisha",
    "puducherry": "puducherry",
    "pondicherry": "puducherry",
}


def norm(value):
    value = "" if value is None else str(value)
    value = value.replace("&amp;", "&")
    value = value.lower().strip()
    value = re.sub(r"&", " and ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return ALIASES.get(value, value)


def compact(value):
    value = norm(value)
    value = value.replace(" and ", " ")
    return value.replace(" ", "")


def valid_lgd(value):
    value = "" if value is None else str(value).strip()
    return value.upper() not in INVALID and value.isdigit()


def load_backend():
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            select
              d.lgd_code as district_lgd_code,
              d.canonical_name as district_name,
              d.census_name as district_census_name,
              d.is_active as district_is_active,
              s.lgd_code as state_lgd_code,
              s.canonical_name as state_name,
              s.census_name as state_census_name,
              s.is_active as state_is_active
            from geography_districts d
            left join geography_states s on s.id = d.state_id
        """)).mappings().all()
    finally:
        db.close()

    by_code = {}
    by_state_name = {}
    for r in rows:
        row = dict(r)
        code = str(row["district_lgd_code"]).strip()
        by_code[code] = row

        state_keys = {compact(row.get("state_name")), compact(row.get("state_census_name"))}
        district_keys = {compact(row.get("district_name")), compact(row.get("district_census_name"))}

        for s in state_keys:
            for d in district_keys:
                if s and d:
                    by_state_name[(s, d)] = row

    return by_code, by_state_name


def load_soi():
    sf = shapefile.Reader(str(SOI_SHP))
    fields = [field[0] for field in sf.fields[1:]]
    rows = []
    for record in sf.records():
        row = dict(zip(fields, record))
        rows.append({
            "soi_objectid": row.get("OBJECTID"),
            "soi_state_name": str(row.get("STATE_UT") or "").strip(),
            "soi_state_lgd_code": str(row.get("STATE_LGD") or "").strip(),
            "soi_district_name": str(row.get("DISTRICT") or "").strip(),
            "soi_district_lgd_code": str(row.get("DIST_LGD") or "").strip(),
            "soi_remarks": str(row.get("REMARKS") or "").strip(),
            "soi_valid_state_lgd": valid_lgd(row.get("STATE_LGD")),
            "soi_valid_district_lgd": valid_lgd(row.get("DIST_LGD")),
        })
    return rows


def classify(soi, backend_by_code, backend_by_name):
    if not soi["soi_valid_state_lgd"] or not soi["soi_valid_district_lgd"]:
        return "SOI_INVALID_OR_DISPUTED", None, None

    backend_by_soi_code = backend_by_code.get(soi["soi_district_lgd_code"])
    backend_by_soi_name = backend_by_name.get((compact(soi["soi_state_name"]), compact(soi["soi_district_name"])))

    if backend_by_soi_code and backend_by_soi_name:
        same_backend_row = backend_by_soi_code["district_lgd_code"] == backend_by_soi_name["district_lgd_code"]
        state_code_match = str(backend_by_soi_name["state_lgd_code"]).strip() == soi["soi_state_lgd_code"]
        district_code_match = str(backend_by_soi_name["district_lgd_code"]).strip() == soi["soi_district_lgd_code"]

        if same_backend_row and state_code_match and district_code_match:
            return "NAME_AND_CODE_MATCH", backend_by_soi_name, backend_by_soi_code
        if not same_backend_row:
            return "SOI_CODE_POINTS_TO_DIFFERENT_BACKEND_DISTRICT", backend_by_soi_name, backend_by_soi_code
        if not state_code_match:
            return "STATE_CODE_DIFF_NAME_MATCH", backend_by_soi_name, backend_by_soi_code
        return "DISTRICT_CODE_DIFF_NAME_MATCH", backend_by_soi_name, backend_by_soi_code

    if backend_by_soi_name:
        return "NAME_MATCH_CODE_NOT_IN_BACKEND_OR_DIFF", backend_by_soi_name, backend_by_soi_code

    if backend_by_soi_code:
        return "CODE_MATCH_NAME_NOT_MATCHED", backend_by_soi_name, backend_by_soi_code

    return "NO_BACKEND_MATCH_BY_NAME_OR_CODE", None, None


def main():
    backend_by_code, backend_by_name = load_backend()
    soi_rows = load_soi()

    output = []
    for soi in soi_rows:
        category, matched_by_name, matched_by_code = classify(soi, backend_by_code, backend_by_name)

        output.append({
            "category": category,
            **soi,
            "backend_name_match_state_lgd_code": matched_by_name.get("state_lgd_code") if matched_by_name else None,
            "backend_name_match_state_name": matched_by_name.get("state_name") if matched_by_name else None,
            "backend_name_match_district_lgd_code": matched_by_name.get("district_lgd_code") if matched_by_name else None,
            "backend_name_match_district_name": matched_by_name.get("district_name") if matched_by_name else None,
            "backend_code_match_state_lgd_code": matched_by_code.get("state_lgd_code") if matched_by_code else None,
            "backend_code_match_state_name": matched_by_code.get("state_name") if matched_by_code else None,
            "backend_code_match_district_lgd_code": matched_by_code.get("district_lgd_code") if matched_by_code else None,
            "backend_code_match_district_name": matched_by_code.get("district_name") if matched_by_code else None,
        })

    counts = Counter(r["category"] for r in output)

    result = {
        "schema_version": "soi_district_name_code_alignment.v1",
        "mode": "READ_ONLY",
        "db_writes_made": False,
        "external_calls_made": False,
        "source_file": str(SOI_SHP),
        "counts": {
            "soi_records": len(soi_rows),
            **dict(sorted(counts.items())),
        },
        "readiness": {
            "soi_lgd_fields_safe_as_primary_keys": counts.get("SOI_CODE_POINTS_TO_DIFFERENT_BACKEND_DISTRICT", 0) == 0,
            "soi_geometry_useful_with_name_crosswalk": counts.get("NAME_AND_CODE_MATCH", 0) + counts.get("SOI_CODE_POINTS_TO_DIFFERENT_BACKEND_DISTRICT", 0) > 500,
            "safe_for_automatic_db_import": False,
        },
        "recommendation": [
            "Do not use SOI DIST_LGD as trusted primary key until mismatches are explained.",
            "Use backend LGD master as canonical administrative identity.",
            "Use SOI geometry only through a reviewed name/code crosswalk.",
            "Inspect SOI_CODE_POINTS_TO_DIFFERENT_BACKEND_DISTRICT rows carefully; they may indicate stale/misaligned SOI attributes.",
        ],
        "samples": {
            category: [r for r in output if r["category"] == category][:12]
            for category in sorted(counts)
            if category != "NAME_AND_CODE_MATCH"
        },
        "output_files": {
            "csv": str(OUT_CSV),
            "json": str(OUT_JSON),
        },
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(output[0].keys()))
        writer.writeheader()
        writer.writerows(output)

    OUT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())

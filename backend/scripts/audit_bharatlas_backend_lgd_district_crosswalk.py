#!/usr/bin/env python3
"""Audit BharatAtlas LGD district boundaries against backend LGD districts.

Read-only. This checks whether the staged BharatAtlas district boundary file can
be safely used as LGD-compatible geometry for dry-run CoRE overlay candidates.
It does not write database rows.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
import sys

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import text

BHARATLAS_DISTRICTS = ROOT / "data/staged/boundaries/bharatlas_lgd/LGD_Districts.geojson"
OUTPUT_DIR = ROOT / "data/staged/core_stack/lgd_crosswalk"

CATEGORY_ORDER = [
    "MATCHED_EXACT",
    "MATCHED_NAME_VARIANT",
    "STATE_CODE_MISMATCH",
    "BHARATLAS_ONLY",
    "BACKEND_ONLY",
    "DUPLICATE_BHARATLAS_CODE",
    "DUPLICATE_BACKEND_CODE",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bharatlas-geojson", type=Path, default=BHARATLAS_DISTRICTS)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--sample-limit", type=int, default=20)
    return parser.parse_args()


def norm_name(value: Any) -> str:
    if value is None:
        return ""
    text_value = unicodedata.normalize("NFKD", str(value))
    text_value = text_value.casefold()
    text_value = re.sub(r"&", " and ", text_value)
    text_value = re.sub(r"\band\b", " and ", text_value)
    text_value = re.sub(r"[^a-z0-9]+", " ", text_value)
    text_value = re.sub(r"\s+", " ", text_value).strip()
    return text_value


def compact_name(value: Any) -> str:
    return norm_name(value).replace(" ", "")


def load_bharatlas_rows(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for index, feature in enumerate(data.get("features", [])):
        props = feature.get("properties") or {}
        district_name = props.get("dtname") or props.get("Dist")
        state_name = props.get("stname")
        dist_lgd = str(props.get("dist_lgd") or "").strip()
        state_lgd = str(props.get("state_lgd") or "").strip()
        rows.append(
            {
                "source": "BHARATLAS",
                "feature_index": index,
                "district_lgd_code": dist_lgd,
                "district_name": district_name,
                "district_name_norm": norm_name(district_name),
                "district_name_compact": compact_name(district_name),
                "state_lgd_code": state_lgd,
                "state_name": state_name,
                "state_name_norm": norm_name(state_name),
                "state_name_compact": compact_name(state_name),
                "dtcode11": str(props.get("dtcode11") or "").strip(),
                "stcode11": str(props.get("stcode11") or "").strip(),
                "year_stat": props.get("year_stat"),
                "remarks": props.get("remarks"),
            }
        )
    return rows


def load_backend_rows() -> list[dict[str, Any]]:
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        records = db.execute(
            text(
                """
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
                order by s.lgd_code, d.lgd_code
                """
            )
        ).mappings().all()
    finally:
        db.close()

    rows = []
    for row in records:
        district_name = row["district_name"]
        district_census_name = row["district_census_name"]
        state_name = row["state_name"]
        state_census_name = row["state_census_name"]
        rows.append(
            {
                "source": "BACKEND",
                "district_lgd_code": str(row["district_lgd_code"] or "").strip(),
                "district_name": district_name,
                "district_census_name": district_census_name,
                "district_name_norm": norm_name(district_name),
                "district_census_name_norm": norm_name(district_census_name),
                "district_name_compact": compact_name(district_name),
                "district_census_name_compact": compact_name(district_census_name),
                "district_is_active": row["district_is_active"],
                "state_lgd_code": str(row["state_lgd_code"] or "").strip(),
                "state_name": state_name,
                "state_census_name": state_census_name,
                "state_name_norm": norm_name(state_name),
                "state_census_name_norm": norm_name(state_census_name),
                "state_name_compact": compact_name(state_name),
                "state_census_name_compact": compact_name(state_census_name),
                "state_is_active": row["state_is_active"],
            }
        )
    return rows


def index_by_code(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        code = str(row.get("district_lgd_code") or "").strip()
        if code:
            grouped[code].append(row)
    return grouped


def names_match(bharat: dict[str, Any], backend: dict[str, Any]) -> bool:
    bharat_names = {bharat["district_name_norm"], bharat["district_name_compact"]}
    backend_names = {
        backend["district_name_norm"],
        backend["district_census_name_norm"],
        backend["district_name_compact"],
        backend["district_census_name_compact"],
    }
    bharat_names.discard("")
    backend_names.discard("")
    return bool(bharat_names & backend_names)


def states_match(bharat: dict[str, Any], backend: dict[str, Any]) -> bool:
    if bharat["state_lgd_code"] != backend["state_lgd_code"]:
        return False
    bharat_names = {bharat["state_name_norm"], bharat["state_name_compact"]}
    backend_names = {
        backend["state_name_norm"],
        backend["state_census_name_norm"],
        backend["state_name_compact"],
        backend["state_census_name_compact"],
    }
    bharat_names.discard("")
    backend_names.discard("")
    return bool(bharat_names & backend_names) or bharat["state_lgd_code"] == backend["state_lgd_code"]


def compare(bharat_rows: list[dict[str, Any]], backend_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bharat_by_code = index_by_code(bharat_rows)
    backend_by_code = index_by_code(backend_rows)
    bharat_codes = set(bharat_by_code)
    backend_codes = set(backend_by_code)

    results = []

    for code in sorted(bharat_codes & backend_codes, key=lambda item: int(item) if item.isdigit() else item):
        if len(bharat_by_code[code]) > 1:
            for row in bharat_by_code[code]:
                results.append({"category": "DUPLICATE_BHARATLAS_CODE", **row})
            continue
        if len(backend_by_code[code]) > 1:
            for row in backend_by_code[code]:
                results.append({"category": "DUPLICATE_BACKEND_CODE", **row})
            continue

        bharat = bharat_by_code[code][0]
        backend = backend_by_code[code][0]
        state_code_match = bharat["state_lgd_code"] == backend["state_lgd_code"]
        state_name_match = states_match(bharat, backend)
        district_name_match = names_match(bharat, backend)

        if not state_code_match:
            category = "STATE_CODE_MISMATCH"
        elif district_name_match and state_name_match:
            category = "MATCHED_EXACT"
        else:
            category = "MATCHED_NAME_VARIANT"

        results.append(
            {
                "category": category,
                "district_lgd_code": code,
                "bharat_district_name": bharat["district_name"],
                "backend_district_name": backend["district_name"],
                "backend_district_census_name": backend["district_census_name"],
                "bharat_state_lgd_code": bharat["state_lgd_code"],
                "backend_state_lgd_code": backend["state_lgd_code"],
                "bharat_state_name": bharat["state_name"],
                "backend_state_name": backend["state_name"],
                "state_code_match": state_code_match,
                "state_name_match": state_name_match,
                "district_name_match": district_name_match,
                "backend_district_is_active": backend["district_is_active"],
                "recommendation": "SAFE_CODE_MATCH" if category == "MATCHED_EXACT" else "MANUAL_NAME_ALIAS_REVIEW",
            }
        )

    for code in sorted(bharat_codes - backend_codes, key=lambda item: int(item) if item.isdigit() else item):
        for row in bharat_by_code[code]:
            results.append(
                {
                    "category": "BHARATLAS_ONLY",
                    **row,
                    "recommendation": "BACKEND_LGD_MASTER_REFRESH_OR_MANUAL_CROSSWALK",
                }
            )

    for code in sorted(backend_codes - bharat_codes, key=lambda item: int(item) if item.isdigit() else item):
        for row in backend_by_code[code]:
            results.append(
                {
                    "category": "BACKEND_ONLY",
                    **row,
                    "recommendation": "BOUNDARY_SOURCE_VERSION_GAP_USE_FALLBACK_UNTIL_GEOMETRY_AVAILABLE",
                }
            )

    return results


def write_outputs(rows: list[dict[str, Any]], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "bharatlas_backend_lgd_district_crosswalk.json"
    csv_path = output_dir / "bharatlas_backend_lgd_district_crosswalk.csv"

    json_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    fieldnames = sorted({key for row in rows for key in row})
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return {"json": str(json_path), "csv": str(csv_path)}


def main() -> int:
    args = parse_args()

    missing_inputs = []
    if not args.bharatlas_geojson.exists():
        missing_inputs.append(str(args.bharatlas_geojson))

    if missing_inputs:
        print(
            json.dumps(
                {
                    "schema_version": "bharatlas_backend_lgd_district_crosswalk_audit.v1",
                    "mode": "READ_ONLY",
                    "external_calls_made": False,
                    "db_writes_made": False,
                    "missing_inputs": missing_inputs,
                    "readiness": {"ready_for_crosswalk_audit": False},
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1

    bharat_rows = load_bharatlas_rows(args.bharatlas_geojson)
    backend_rows = load_backend_rows()
    rows = compare(bharat_rows, backend_rows)
    files = write_outputs(rows, args.output_dir)

    counts = Counter(row["category"] for row in rows)
    status = {
        category: counts.get(category, 0)
        for category in CATEGORY_ORDER
        if counts.get(category, 0)
    }

    result = {
        "schema_version": "bharatlas_backend_lgd_district_crosswalk_audit.v1",
        "mode": "READ_ONLY",
        "external_calls_made": False,
        "db_writes_made": False,
        "output_files": files,
        "counts": {
            "bharatlas_features": len(bharat_rows),
            "bharatlas_dist_lgd_distinct": len(index_by_code(bharat_rows)),
            "backend_district_rows": len(backend_rows),
            "backend_lgd_distinct": len(index_by_code(backend_rows)),
            "crosswalk_rows": len(rows),
            **status,
        },
        "samples": {
            category: [row for row in rows if row["category"] == category][: args.sample_limit]
            for category in CATEGORY_ORDER
            if counts.get(category, 0)
        },
        "readiness": {
            "ready_for_manual_crosswalk_review": True,
            "duplicate_codes_found": bool(
                counts.get("DUPLICATE_BHARATLAS_CODE") or counts.get("DUPLICATE_BACKEND_CODE")
            ),
            "safe_for_automatic_db_import": False,
            "safe_for_dry_run_overlay_review": True,
        },
        "recommendation": [
            "Use BharatAtlas dist_lgd as the district geometry key for dry-run/manual-review overlay work.",
            "Do not treat BharatAtlas as authoritative government source; label it operational/unofficial republication.",
            "Matched LGD codes can support candidate review even when names differ, but name variants need alias/crosswalk review.",
            "BHARATLAS_ONLY and BACKEND_ONLY rows indicate source-version drift; keep fallback behavior for those districts.",
            "Any future importer should write MANUAL_REVIEW rows only and should not replace existing fallback mappings automatically.",
        ],
    }

    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

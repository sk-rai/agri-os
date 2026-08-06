#!/usr/bin/env python3
"""Verify dry-run CoRE/LGD district overlay candidate outputs.

Read-only. Checks local staged candidate JSON/CSV files and confirms the
candidate set is complete enough for manual review. It does not write database
rows.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_DIR = ROOT / "data/staged/core_stack/overlay_candidates"
JSON_PATH = CANDIDATE_DIR / "district_core_overlay_candidates.json"
CSV_PATH = CANDIDATE_DIR / "district_core_overlay_candidates.csv"

EXPECTED_REGION_SYSTEMS = {
    "CORE_STACK_AGRO_ECOLOGICAL_ZONE",
    "CORE_STACK_AGRO_CLIMATIC_ZONE",
    "CORE_STACK_BIOGEOGRAPHIC_ZONE",
}


def read_json_rows() -> list[dict]:
    if not JSON_PATH.exists():
        return []
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{JSON_PATH} does not contain a JSON list")
    return data


def read_csv_count() -> int:
    if not CSV_PATH.exists():
        return 0
    with CSV_PATH.open(encoding="utf-8", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def main() -> int:
    rows = read_json_rows()
    csv_count = read_csv_count()
    region_counts = Counter(row.get("region_system") for row in rows)
    status_counts = Counter(row.get("candidate_status") for row in rows)
    district_codes = {
        row.get("district_lgd_code")
        for row in rows
        if row.get("district_lgd_code")
    }
    duplicate_keys = [
        key
        for key, count in Counter(
            (
                row.get("district_lgd_code"),
                row.get("region_system"),
            )
            for row in rows
        ).items()
        if count > 1
    ]
    missing_required_fields = [
        index
        for index, row in enumerate(rows)
        if not all(
            row.get(field)
            for field in [
                "state_lgd_code",
                "district_lgd_code",
                "scope_level",
                "region_system",
                "region_class_name",
                "overlap_percent_of_district",
                "candidate_status",
                "review_status",
            ]
        )
    ]
    readiness = {
        "json_exists": JSON_PATH.exists(),
        "csv_exists": CSV_PATH.exists(),
        "json_csv_counts_match": len(rows) == csv_count,
        "rows_present": bool(rows),
        "all_expected_region_systems_present": set(region_counts) == EXPECTED_REGION_SYSTEMS,
        "one_row_per_district_region_system": not duplicate_keys,
        "all_rows_are_district_scope": all(row.get("scope_level") == "DISTRICT" for row in rows),
        "all_rows_manual_review": all(row.get("review_status") == "MANUAL_REVIEW" for row in rows),
        "no_no_overlap_rows": status_counts.get("NO_OVERLAP_FOUND", 0) == 0,
        "required_fields_present": not missing_required_fields,
        "ready_for_manual_review": bool(rows)
        and len(rows) == csv_count
        and set(region_counts) == EXPECTED_REGION_SYSTEMS
        and not duplicate_keys
        and status_counts.get("NO_OVERLAP_FOUND", 0) == 0
        and not missing_required_fields,
        "ready_for_db_import": False,
    }
    result = {
        "schema_version": "core_lgd_overlay_candidate_verification.v1",
        "candidate_dir": str(CANDIDATE_DIR),
        "json_path": str(JSON_PATH),
        "csv_path": str(CSV_PATH),
        "row_count": len(rows),
        "csv_row_count": csv_count,
        "district_count": len(district_codes),
        "region_counts": dict(sorted(region_counts.items())),
        "status_counts": dict(sorted(status_counts.items())),
        "duplicate_keys": duplicate_keys[:20],
        "missing_required_field_row_indexes": missing_required_fields[:20],
        "readiness": readiness,
        "warnings": [
            "Candidate files are dry-run review artifacts and are not DB imports.",
            "Area ranking used source lon/lat coordinate units; review before authoritative use.",
            "Do not commit large generated candidate files unless explicitly approved.",
        ],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if readiness["ready_for_manual_review"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

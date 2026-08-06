#!/usr/bin/env python3
"""Review dry-run CoRE/LGD district overlay candidates before import.

Read-only. Summarizes candidate quality and highlights rows that need manual
review. This script does not import into geography_climate_region_mappings.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CANDIDATE_CSV = ROOT / "data/staged/core_stack/overlay_candidates/district_core_overlay_candidates.csv"

SELECTED_STATES = {
    "27": "Maharashtra",
    "29": "Karnataka",
    "9": "Uttar Pradesh",
    "3": "Punjab",
    "19": "West Bengal",
}

EXPECTED_REGION_SYSTEMS = {
    "CORE_STACK_AGRO_ECOLOGICAL_ZONE",
    "CORE_STACK_AGRO_CLIMATIC_ZONE",
    "CORE_STACK_BIOGEOGRAPHIC_ZONE",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-csv", type=Path, default=DEFAULT_CANDIDATE_CSV)
    parser.add_argument("--low-overlap-threshold", type=float, default=60.0)
    parser.add_argument("--sample-limit", type=int, default=5)
    return parser.parse_args()


def read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            row["overlap_percent_of_district"] = float(row.get("overlap_percent_of_district") or 0)
            row["overlap_area_degrees2"] = float(row.get("overlap_area_degrees2") or 0)
            rows.append(row)
    return rows


def percentile(values: list[float], percent: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((percent / 100) * (len(ordered) - 1))))
    return ordered[index]


def summarize_region_system(rows: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    overlaps = [row["overlap_percent_of_district"] for row in rows]
    class_counts = Counter(row.get("region_class_name") for row in rows)
    low_rows = [
        row
        for row in sorted(rows, key=lambda item: item["overlap_percent_of_district"])
        if row["overlap_percent_of_district"] < threshold
    ]
    return {
        "row_count": len(rows),
        "district_count": len({row.get("district_lgd_code") for row in rows if row.get("district_lgd_code")}),
        "min_overlap_percent": min(overlaps) if overlaps else None,
        "p10_overlap_percent": percentile(overlaps, 10),
        "median_overlap_percent": median(overlaps) if overlaps else None,
        "low_overlap_threshold": threshold,
        "low_overlap_count": len(low_rows),
        "top_classes_by_district_count": [
            {"region_class_name": name, "district_count": count}
            for name, count in class_counts.most_common(10)
        ],
        "lowest_overlap_examples": [
            {
                "state_lgd_code": row.get("state_lgd_code"),
                "state_name": row.get("state_name"),
                "district_lgd_code": row.get("district_lgd_code"),
                "district_name": row.get("district_name"),
                "region_class_name": row.get("region_class_name"),
                "overlap_percent_of_district": row.get("overlap_percent_of_district"),
            }
            for row in low_rows[:10]
        ],
    }


def selected_state_samples(rows: list[dict[str, Any]], sample_limit: int) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("state_lgd_code") in SELECTED_STATES:
            grouped[row["state_lgd_code"]].append(row)

    samples = {}
    for state_code, state_rows in sorted(grouped.items(), key=lambda item: int(item[0])):
        ordered = sorted(
            state_rows,
            key=lambda row: (row["district_name"], row["region_system"]),
        )
        samples[state_code] = [
            {
                "state_name": row.get("state_name"),
                "district_lgd_code": row.get("district_lgd_code"),
                "district_name": row.get("district_name"),
                "region_system": row.get("region_system"),
                "region_class_name": row.get("region_class_name"),
                "overlap_percent_of_district": row.get("overlap_percent_of_district"),
            }
            for row in ordered[:sample_limit]
        ]
    return samples


def main() -> int:
    args = parse_args()
    rows = read_rows(args.candidate_csv)
    by_region: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_region[row.get("region_system")].append(row)

    district_region_keys = Counter((row.get("district_lgd_code"), row.get("region_system")) for row in rows)
    duplicate_keys = [key for key, count in district_region_keys.items() if count > 1]
    status_counts = Counter(row.get("candidate_status") for row in rows)
    review_counts = Counter(row.get("review_status") for row in rows)
    missing_fields = [
        index
        for index, row in enumerate(rows)
        if not row.get("state_lgd_code")
        or not row.get("district_lgd_code")
        or not row.get("region_class_name")
        or not row.get("region_system")
    ]
    low_overlap_total = sum(
        1
        for row in rows
        if row.get("overlap_percent_of_district", 0) < args.low_overlap_threshold
    )

    readiness = {
        "candidate_file_exists": args.candidate_csv.exists(),
        "rows_present": bool(rows),
        "all_expected_region_systems_present": set(by_region) == EXPECTED_REGION_SYSTEMS,
        "one_row_per_district_region_system": not duplicate_keys,
        "all_rows_manual_review": review_counts == {"MANUAL_REVIEW": len(rows)},
        "no_no_overlap_rows": status_counts.get("NO_OVERLAP_FOUND", 0) == 0,
        "required_fields_present": not missing_fields,
        "ready_for_manual_review": bool(rows)
        and set(by_region) == EXPECTED_REGION_SYSTEMS
        and not duplicate_keys
        and not missing_fields,
        "ready_for_db_import": False,
    }

    result = {
        "schema_version": "core_lgd_overlay_candidate_review.v1",
        "candidate_csv": str(args.candidate_csv),
        "row_count": len(rows),
        "district_count": len({row.get("district_lgd_code") for row in rows if row.get("district_lgd_code")}),
        "status_counts": dict(sorted(status_counts.items())),
        "review_status_counts": dict(sorted(review_counts.items())),
        "low_overlap_threshold": args.low_overlap_threshold,
        "low_overlap_total": low_overlap_total,
        "region_system_summaries": {
            region_system: summarize_region_system(region_rows, args.low_overlap_threshold)
            for region_system, region_rows in sorted(by_region.items())
        },
        "selected_state_samples": selected_state_samples(rows, args.sample_limit),
        "duplicate_keys": duplicate_keys[:20],
        "missing_required_field_row_indexes": missing_fields[:20],
        "readiness": readiness,
        "warnings": [
            "This is a dry-run review of candidate rows, not an import.",
            "Low overlap rows need manual review before trust is upgraded.",
            "Source/provenance and equal-area method review are still required before DB import.",
        ],
        "next_actions": [
            "Review low-overlap districts and selected-state samples.",
            "Record Bharatlas source/license/provenance decision.",
            "Decide whether candidate generation should use equal-area reprojection before import.",
            "Only then design a MANUAL_REVIEW importer for geography_climate_region_mappings.",
        ],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if readiness["ready_for_manual_review"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

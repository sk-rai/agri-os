#!/usr/bin/env python3
"""Bucket low-overlap CoRE/LGD district overlay rows for manual review.

Read-only. Consumes the equal-area comparison CSV when available, falls back to
the original candidate CSV otherwise. Writes local staged review artifacts only.
No database rows are written.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EQUAL_AREA_CSV = ROOT / "data/staged/core_stack/overlay_candidates/equal_area/district_core_overlay_equal_area_comparison.csv"
BASELINE_CSV = ROOT / "data/staged/core_stack/overlay_candidates/district_core_overlay_candidates.csv"
CROSSWALK_CSV = ROOT / "data/staged/core_stack/lgd_crosswalk/bharatlas_backend_lgd_district_crosswalk.csv"
OUTPUT_DIR = ROOT / "data/staged/core_stack/overlay_candidates/low_overlap_review"

DEFAULT_THRESHOLD = 60.0

COASTAL_OR_ISLAND_HINTS = {
    "andaman", "nicobar", "lakshadweep", "mahe", "yanam", "daman", "diu",
    "mumbai", "kolkata", "chennai", "puducherry", "goa", "baleshwar",
    "bhadrak", "cuttack", "jajapur", "east godavari",
}

URBAN_OR_SMALL_DISTRICT_HINTS = {
    "central", "new delhi", "north", "south", "east", "west", "shahdara",
    "outer", "mumbai", "kolkata", "chennai", "daman", "mahe", "yanam",
}

TRANSITION_REGION_WORDS = {
    "plain", "plateau", "ghats", "coast", "coastal", "himalayan",
    "peninsula", "arid", "semi", "subhumid", "gangetic", "deccan",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--candidate-csv", type=Path, default=None)
    parser.add_argument("--crosswalk-csv", type=Path, default=CROSSWALK_CSV)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    return parser.parse_args()


def norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()


def read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def choose_candidate_csv(explicit: Path | None) -> tuple[Path, str]:
    if explicit:
        return explicit, "explicit"
    if EQUAL_AREA_CSV.exists():
        return EQUAL_AREA_CSV, "equal_area"
    return BASELINE_CSV, "baseline_lon_lat"


def overlap_percent(row: dict[str, Any]) -> float:
    return as_float(
        row.get("equal_area_overlap_percent_of_district")
        or row.get("overlap_percent_of_district")
    )


def region_name(row: dict[str, Any]) -> str:
    return str(
        row.get("equal_area_region_class_name")
        or row.get("region_class_name")
        or ""
    )


def region_code(row: dict[str, Any]) -> str:
    return str(
        row.get("equal_area_region_class_code")
        or row.get("region_class_code")
        or ""
    )


def crosswalk_key(row: dict[str, Any]) -> str:
    return str(row.get("district_lgd_code") or "").strip()


def load_crosswalk(path: Path) -> dict[str, dict[str, Any]]:
    rows = read_csv(path)
    by_code = {}
    for row in rows:
        code = crosswalk_key(row)
        if code and code not in by_code:
            by_code[code] = row
    return by_code


def classify(row: dict[str, Any], crosswalk: dict[str, dict[str, Any]]) -> tuple[str, list[str]]:
    district_name = norm(row.get("district_name"))
    state_name = norm(row.get("state_name"))
    class_name = norm(region_name(row))
    code = crosswalk_key(row)
    cross = crosswalk.get(code) or {}
    cross_category = cross.get("category")

    reasons = []

    if cross_category == "STATE_CODE_MISMATCH":
        return "SOURCE_VERSION_CONFLICT", ["LGD code maps to different state/district between backend LGD master and BharatAtlas geometry"]

    if cross_category in {"BHARATLAS_ONLY", "BACKEND_ONLY"}:
        return "SOURCE_VERSION_DRIFT", [f"Crosswalk category is {cross_category}"]

    if any(token in district_name or token in state_name for token in COASTAL_OR_ISLAND_HINTS):
        reasons.append("District/state name suggests coastal, island, or enclave geometry")
        return "COASTAL_OR_ISLAND_GEOMETRY", reasons

    if any(token == district_name or district_name.startswith(token + " ") for token in URBAN_OR_SMALL_DISTRICT_HINTS):
        reasons.append("District name suggests urban/small administrative geometry")
        return "URBAN_OR_SMALL_DISTRICT", reasons

    transition_hits = [token for token in TRANSITION_REGION_WORDS if token in class_name]
    if len(transition_hits) >= 2:
        reasons.append(f"Region class spans transition terms: {', '.join(sorted(transition_hits)[:6])}")
        return "ECO_CLIMATIC_TRANSITION_ZONE", reasons

    return "MANUAL_REVIEW_REQUIRED", ["Low dominant overlap without a simple automated bucket"]


def build_review_rows(rows: list[dict[str, Any]], crosswalk: dict[str, dict[str, Any]], threshold: float) -> list[dict[str, Any]]:
    low_rows = [row for row in rows if overlap_percent(row) < threshold]
    review_rows = []
    for row in sorted(low_rows, key=overlap_percent):
        bucket, reasons = classify(row, crosswalk)
        review_rows.append(
            {
                "review_bucket": bucket,
                "review_reasons": "; ".join(reasons),
                "state_lgd_code": row.get("state_lgd_code"),
                "state_name": row.get("state_name"),
                "district_lgd_code": row.get("district_lgd_code"),
                "district_name": row.get("district_name"),
                "region_system": row.get("region_system"),
                "region_class_name": region_name(row),
                "region_class_code": region_code(row),
                "overlap_percent_of_district": round(overlap_percent(row), 4),
                "baseline_region_class_name": row.get("baseline_region_class_name"),
                "equal_area_region_class_name": row.get("equal_area_region_class_name"),
                "crosswalk_category": (crosswalk.get(crosswalk_key(row)) or {}).get("category"),
                "recommended_import_action": "EXCLUDE_AUTOMATIC_IMPORT"
                if bucket in {"SOURCE_VERSION_CONFLICT", "SOURCE_VERSION_DRIFT"}
                else "MANUAL_REVIEW_ONLY",
                "review_status": "MANUAL_REVIEW",
            }
        )
    return review_rows


def summarize(review_rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_bucket = Counter(row["review_bucket"] for row in review_rows)
    by_region = defaultdict(list)
    for row in review_rows:
        by_region[row["region_system"]].append(row)

    region_summaries = {}
    for region_system, rows in sorted(by_region.items()):
        overlaps = [as_float(row["overlap_percent_of_district"]) for row in rows]
        region_summaries[region_system] = {
            "low_overlap_count": len(rows),
            "min_overlap_percent": min(overlaps) if overlaps else None,
            "median_overlap_percent": median(overlaps) if overlaps else None,
            "bucket_counts": dict(sorted(Counter(row["review_bucket"] for row in rows).items())),
            "lowest_examples": rows[:8],
        }

    return {
        "bucket_counts": dict(sorted(by_bucket.items())),
        "region_system_summaries": region_summaries,
    }


def write_outputs(rows: list[dict[str, Any]], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "core_lgd_low_overlap_review.json"
    csv_path = output_dir / "core_lgd_low_overlap_review.csv"

    json_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    fieldnames = sorted({key for row in rows for key in row})
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return {"json": str(json_path), "csv": str(csv_path)}


def main() -> int:
    args = parse_args()
    candidate_csv, source_variant = choose_candidate_csv(args.candidate_csv)
    candidate_rows = read_csv(candidate_csv)
    crosswalk = load_crosswalk(args.crosswalk_csv)

    if not candidate_rows:
        print(
            json.dumps(
                {
                    "schema_version": "core_lgd_low_overlap_review.v1",
                    "mode": "READ_ONLY_LOW_OVERLAP_REVIEW",
                    "db_writes_made": False,
                    "external_calls_made": False,
                    "missing_or_empty_candidate_csv": str(candidate_csv),
                    "readiness": {"ready_for_low_overlap_review": False},
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1

    review_rows = build_review_rows(candidate_rows, crosswalk, args.threshold)
    files = write_outputs(review_rows, args.output_dir)
    summary = summarize(review_rows)

    result = {
        "schema_version": "core_lgd_low_overlap_review.v1",
        "mode": "READ_ONLY_LOW_OVERLAP_REVIEW",
        "db_writes_made": False,
        "external_calls_made": False,
        "candidate_csv": str(candidate_csv),
        "candidate_source_variant": source_variant,
        "crosswalk_csv": str(args.crosswalk_csv),
        "threshold": args.threshold,
        "low_overlap_row_count": len(review_rows),
        "output_files": files,
        **summary,
        "readiness": {
            "ready_for_manual_low_overlap_review": bool(review_rows),
            "safe_for_automatic_db_import": False,
        },
        "recommendation": [
            "Treat all low-overlap rows as MANUAL_REVIEW.",
            "Exclude SOURCE_VERSION_CONFLICT and SOURCE_VERSION_DRIFT rows from automatic import.",
            "LGD master remains canonical for code/state/name truth; BharatAtlas supplies operational geometry only.",
            "Keep fallback mappings active until reviewed polygon-derived rows are promoted.",
        ],
    }

    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

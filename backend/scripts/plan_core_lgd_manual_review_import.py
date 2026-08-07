#!/usr/bin/env python3
"""Plan a conservative MANUAL_REVIEW import for CoRE/LGD polygon mappings.

Read-only. This consumes local staged overlay/crosswalk/low-overlap artifacts
and backend climate/geography tables, then reports what rows an importer would
write. It does not write database rows.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

EQUAL_AREA_CSV = ROOT / "data/staged/core_stack/overlay_candidates/equal_area/district_core_overlay_equal_area_comparison.csv"
LOW_OVERLAP_CSV = ROOT / "data/staged/core_stack/overlay_candidates/low_overlap_review/core_lgd_low_overlap_review.csv"
CROSSWALK_CSV = ROOT / "data/staged/core_stack/lgd_crosswalk/bharatlas_backend_lgd_district_crosswalk.csv"
OUTPUT_DIR = ROOT / "data/staged/core_stack/manual_review_import_plan"

EXCLUDED_CROSSWALK_CATEGORIES = {
    "STATE_CODE_MISMATCH",
    "BHARATLAS_ONLY",
    "BACKEND_ONLY",
    "DUPLICATE_BHARATLAS_CODE",
    "DUPLICATE_BACKEND_CODE",
}

EXCLUDED_LOW_OVERLAP_BUCKETS = {
    "SOURCE_VERSION_CONFLICT",
    "SOURCE_VERSION_DRIFT",
}

POLYGON_CONFIDENCE = "POLYGON_DERIVED_DISTRICT_OVERLAY_REVIEW"
REVIEW_STATUS = "MANUAL_REVIEW"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-csv", type=Path, default=EQUAL_AREA_CSV)
    parser.add_argument("--low-overlap-csv", type=Path, default=LOW_OVERLAP_CSV)
    parser.add_argument("--crosswalk-csv", type=Path, default=CROSSWALK_CSV)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("district_lgd_code") or "").strip(),
        str(row.get("state_lgd_code") or "").strip(),
        str(row.get("region_system") or "").strip(),
    )


def district_code(row: dict[str, Any]) -> str:
    return str(row.get("district_lgd_code") or "").strip()


def region_system(row: dict[str, Any]) -> str:
    return str(row.get("region_system") or "").strip()


def region_class_name(row: dict[str, Any]) -> str:
    return html.unescape(str(row.get("equal_area_region_class_name") or row.get("region_class_name") or "")).strip()


def region_class_code(row: dict[str, Any]) -> str:
    return str(row.get("equal_area_region_class_code") or row.get("region_class_code") or "").strip()


def overlap_percent(row: dict[str, Any]) -> float:
    try:
        return float(row.get("equal_area_overlap_percent_of_district") or row.get("overlap_percent_of_district") or 0)
    except ValueError:
        return 0.0


def load_backend_state() -> dict[str, Any]:
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        districts = {
            str(row["lgd_code"]): dict(row)
            for row in db.execute(
                text(
                    """
                    select
                      d.id,
                      d.lgd_code,
                      d.canonical_name,
                      s.lgd_code as state_lgd_code,
                      s.canonical_name as state_name,
                      d.is_active
                    from geography_districts d
                    left join geography_states s on s.id = d.state_id
                    """
                )
            ).mappings()
        }

        regions = {
            (str(row["region_system"]), str(row["region_name"])): dict(row)
            for row in db.execute(
                text(
                    """
                    select id, region_code, region_name, region_system, review_status, confidence, is_active
                    from geography_climate_regions
                    """
                )
            ).mappings()
        }

        mappings = list(
            db.execute(
                text(
                    """
                    select
                      id,
                      region_id,
                      region_code,
                      scope_level,
                      state_lgd_code,
                      district_lgd_code,
                      source_references,
                      confidence,
                      review_status,
                      is_active
                    from geography_climate_region_mappings
                    where scope_level = 'DISTRICT'
                    """
                )
            ).mappings()
        )
    finally:
        db.close()

    return {
        "districts": districts,
        "regions": regions,
        "mappings": mappings,
    }


def existing_mapping_index(mappings: list[dict[str, Any]]) -> set[tuple[str, str]]:
    return {
        (
            str(row.get("district_lgd_code") or "").strip(),
            str(row.get("region_code") or "").strip(),
        )
        for row in mappings
        if row.get("district_lgd_code") and row.get("region_code")
    }


def build_lookup(rows: list[dict[str, Any]], field: str) -> dict[tuple[str, str, str], dict[str, Any]]:
    result = {}
    for row in rows:
        result[key(row)] = row
    return result


def import_decision(
    candidate: dict[str, Any],
    crosswalk: dict[tuple[str, str, str], dict[str, Any]],
    low_overlap: dict[tuple[str, str, str], dict[str, Any]],
    backend: dict[str, Any],
    existing_index: set[tuple[str, str]],
) -> dict[str, Any]:
    k = key(candidate)
    district_lgd = district_code(candidate)
    class_name = region_class_name(candidate)
    class_code = region_class_code(candidate)
    system = region_system(candidate)

    cross = crosswalk.get(k)
    low = low_overlap.get(k)

    reasons = []
    excluded = False

    cross_category = (cross or {}).get("category")
    low_bucket = (low or {}).get("review_bucket")

    if cross_category in EXCLUDED_CROSSWALK_CATEGORIES:
        excluded = True
        reasons.append(f"crosswalk category {cross_category}")

    if low_bucket in EXCLUDED_LOW_OVERLAP_BUCKETS:
        excluded = True
        reasons.append(f"low-overlap bucket {low_bucket}")

    if district_lgd not in backend["districts"]:
        excluded = True
        reasons.append("district missing in backend LGD master")

    region = backend["regions"].get((system, class_name))
    if not region:
        excluded = True
        reasons.append("climate region missing in backend geography_climate_regions")

    region_code = region["region_code"] if region else class_code
    collision = (district_lgd, str(region_code)) in existing_index
    if collision:
        reasons.append("existing district mapping with same district_lgd_code and region_code")

    source_references = [
        {
            "source": "CORE_STACK_GEE_EXPORT",
            "region_system": system,
            "region_class_name": class_name,
            "region_class_code": class_code,
            "geometry_method": "DISTRICT_POLYGON_INTERSECTION_EQUAL_AREA",
        },
        {
            "source": "BHARATLAS_LGD_DISTRICTS",
            "source_role": "OPERATIONAL_GEOMETRY",
            "source_authority": "UNOFFICIAL_REPUBLICATION",
            "district_lgd_code": district_lgd,
        },
        {
            "source": "BACKEND_LGD_MASTER",
            "source_role": "CANONICAL_CODE_NAME_STATE",
            "district_lgd_code": district_lgd,
        },
    ]

    return {
        "state_lgd_code": candidate.get("state_lgd_code"),
        "state_name": candidate.get("state_name"),
        "district_lgd_code": district_lgd,
        "district_name": candidate.get("district_name"),
        "scope_level": "DISTRICT",
        "region_system": system,
        "region_class_name": class_name,
        "region_class_code": class_code,
        "target_region_code": region_code,
        "target_region_id": str(region["id"]) if region else None,
        "overlap_percent_of_district": round(overlap_percent(candidate), 4),
        "crosswalk_category": cross_category,
        "low_overlap_bucket": low_bucket,
        "candidate_review_status": REVIEW_STATUS,
        "candidate_confidence": POLYGON_CONFIDENCE,
        "candidate_is_active": False,
        "would_write_db_row": not excluded,
        "would_update_existing_fallback": False,
        "existing_same_region_mapping": collision,
        "excluded": excluded,
        "exclusion_reasons": reasons,
        "source_references": source_references,
        "metadata": {
            "candidate_source": "CORE_LGD_EQUAL_AREA_DRY_RUN",
            "manual_review_required": True,
            "effective_in_land_intelligence": False,
            "fallback_mappings_preserved": True,
            "source_version_review": {
                "lgd_master_canonical": True,
                "bharatlas_geometry_operational_only": True,
            },
        },
    }


def write_outputs(rows: list[dict[str, Any]], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "core_lgd_manual_review_import_plan.json"
    csv_path = output_dir / "core_lgd_manual_review_import_plan.csv"

    json_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    flat_rows = []
    for row in rows:
        flat = dict(row)
        flat["source_references"] = json.dumps(row["source_references"], ensure_ascii=False, sort_keys=True)
        flat["metadata"] = json.dumps(row["metadata"], ensure_ascii=False, sort_keys=True)
        flat["exclusion_reasons"] = "; ".join(row["exclusion_reasons"])
        flat_rows.append(flat)

    fieldnames = sorted({key for row in flat_rows for key in row})
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flat_rows)

    return {"json": str(json_path), "csv": str(csv_path)}


def main() -> int:
    args = parse_args()

    candidates = read_csv(args.candidate_csv)
    low_rows = read_csv(args.low_overlap_csv)
    crosswalk_rows = read_csv(args.crosswalk_csv)

    missing_inputs = [
        str(path)
        for path, rows in [
            (args.candidate_csv, candidates),
            (args.crosswalk_csv, crosswalk_rows),
        ]
        if not path.exists() or not rows
    ]

    if missing_inputs:
        print(
            json.dumps(
                {
                    "schema_version": "core_lgd_manual_review_import_plan.v1",
                    "mode": "READ_ONLY_IMPORT_PLAN",
                    "db_writes_made": False,
                    "external_calls_made": False,
                    "missing_or_empty_inputs": missing_inputs,
                    "readiness": {"ready_for_import_planning": False},
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1

    backend = load_backend_state()
    existing_index = existing_mapping_index(backend["mappings"])

    # Crosswalk has one row per district, so expand lookup to region-system keys.
    crosswalk_by_district = {district_code(row): row for row in crosswalk_rows if district_code(row)}
    crosswalk = {
        key(candidate): crosswalk_by_district.get(district_code(candidate))
        for candidate in candidates
    }
    low_overlap = build_lookup(low_rows, "review_bucket")

    plan_rows = [
        import_decision(candidate, crosswalk, low_overlap, backend, existing_index)
        for candidate in candidates
    ]

    files = write_outputs(plan_rows, args.output_dir)

    status_counts = Counter("WOULD_WRITE" if row["would_write_db_row"] else "EXCLUDED" for row in plan_rows)
    exclusion_counts = Counter(reason for row in plan_rows for reason in row["exclusion_reasons"])
    crosswalk_counts = Counter(row.get("crosswalk_category") or "UNSET" for row in plan_rows)
    low_bucket_counts = Counter(row.get("low_overlap_bucket") or "NOT_LOW_OVERLAP" for row in plan_rows)
    collisions = sum(1 for row in plan_rows if row["existing_same_region_mapping"])

    result = {
        "schema_version": "core_lgd_manual_review_import_plan.v1",
        "mode": "READ_ONLY_IMPORT_PLAN",
        "db_writes_made": False,
        "external_calls_made": False,
        "candidate_csv": str(args.candidate_csv),
        "crosswalk_csv": str(args.crosswalk_csv),
        "low_overlap_csv": str(args.low_overlap_csv),
        "output_files": files,
        "row_count": len(plan_rows),
        "status_counts": dict(sorted(status_counts.items())),
        "exclusion_reason_counts": dict(sorted(exclusion_counts.items())),
        "crosswalk_category_counts": dict(sorted(crosswalk_counts.items())),
        "low_overlap_bucket_counts": dict(sorted(low_bucket_counts.items())),
        "existing_same_region_mapping_count": collisions,
        "planned_policy": {
            "review_status": REVIEW_STATUS,
            "confidence": POLYGON_CONFIDENCE,
            "candidate_is_active": False,
            "writes_replace_fallbacks": False,
            "effective_in_land_intelligence": False,
            "lgd_master_is_canonical": True,
            "bharatlas_is_operational_geometry_only": True,
        },
        "readiness": {
            "ready_for_manual_review_importer_design": True,
            "safe_to_run_db_import_now": False,
        },
        "recommendation": [
            "Do not run a DB import yet.",
            "If implemented, importer should write inactive/manual-review candidate rows only.",
            "Importer should exclude source-version drift/conflict rows and missing backend districts.",
            "Existing fallback mappings must remain active until polygon rows are reviewed and promoted.",
        ],
    }

    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

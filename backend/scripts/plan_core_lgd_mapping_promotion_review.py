#!/usr/bin/env python3
"""
Plan review/promotion candidates for inactive CoRE/LGD polygon-derived mappings.

Read-only. No DB writes.

Purpose:
- compare inactive POLY_REV rows against current active fallback mappings;
- identify low-risk pilot candidates;
- keep low-overlap/source-version rows out of automatic promotion;
- produce a CSV/JSON review queue for admin/manual review.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from app.core.database import SessionLocal


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data/staged/core_stack/promotion_review"
OUT_CSV = OUT_DIR / "core_lgd_mapping_promotion_review_plan.csv"
OUT_JSON = OUT_DIR / "core_lgd_mapping_promotion_review_plan.json"

PILOT_STATE_CODES = {"29", "27", "3"}  # Karnataka, Maharashtra, Punjab
PILOT_STATE_NAMES = {"KARNATAKA", "MAHARASHTRA", "PUNJAB"}
MIN_HIGH_OVERLAP = 80.0


def as_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def decide(row: dict) -> tuple[str, str]:
    overlap = as_float(row.get("overlap_percent_of_district"))
    low_bucket = (row.get("low_overlap_bucket") or "").strip()
    crosswalk = (row.get("crosswalk_category") or "").strip()
    state_code = str(row.get("state_lgd_code") or "").strip()
    state_name = str(row.get("state_name") or "").strip().upper()
    has_active_fallback = bool(row.get("active_fallback_region_code"))

    if low_bucket in {"SOURCE_VERSION_DRIFT", "SOURCE_VERSION_CONFLICT"}:
        return "BLOCKED_SOURCE_VERSION", "Source-version drift/conflict must not be promoted automatically"

    if crosswalk in {"BHARATLAS_ONLY", "STATE_CODE_MISMATCH", "UNSET"}:
        return "BLOCKED_CROSSWALK", f"Crosswalk category {crosswalk} requires manual source resolution"

    if low_bucket and low_bucket != "NOT_LOW_OVERLAP":
        return "MANUAL_REVIEW_LOW_OVERLAP", f"Low-overlap bucket {low_bucket} requires manual review"

    if overlap < MIN_HIGH_OVERLAP:
        return "MANUAL_REVIEW_LOW_OVERLAP", f"Overlap {overlap:.2f}% is below {MIN_HIGH_OVERLAP:.0f}%"

    if state_code in PILOT_STATE_CODES or state_name in PILOT_STATE_NAMES:
        if has_active_fallback:
            return "PILOT_REVIEW_REPLACES_FALLBACK", "High-overlap pilot candidate; would supersede active fallback only after explicit promotion"
        return "PILOT_REVIEW_NEW_MAPPING", "High-overlap pilot candidate with no active fallback"

    if has_active_fallback:
        return "GENERAL_REVIEW_REPLACES_FALLBACK", "High-overlap candidate outside pilot states; would supersede active fallback only after explicit promotion"

    return "GENERAL_REVIEW_NEW_MAPPING", "High-overlap candidate outside pilot states"


def main() -> int:
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            with poly as (
              select
                m.id,
                m.region_id,
                m.region_code,
                m.scope_level,
                m.state_lgd_code,
                m.district_lgd_code,
                m.confidence,
                m.review_status,
                m.is_active,
                m.version,
                m.metadata,
                m.metadata ->> 'district_name' as district_name,
                m.metadata ->> 'state_name' as state_name,
                m.metadata ->> 'region_system' as region_system,
                m.metadata ->> 'region_class_code' as region_class_code,
                m.metadata ->> 'region_class_name' as region_class_name,
                m.metadata ->> 'overlap_percent_of_district' as overlap_percent_of_district,
                m.metadata ->> 'crosswalk_category' as crosswalk_category,
                coalesce(nullif(m.metadata ->> 'low_overlap_bucket', ''), 'NOT_LOW_OVERLAP') as low_overlap_bucket
              from geography_climate_region_mappings m
              where m.confidence = 'POLY_REV'
            ),
            active_fallback as (
              select
                district_lgd_code,
                state_lgd_code,
                region_code,
                confidence,
                review_status,
                is_active
              from geography_climate_region_mappings
              where is_active is true
                and confidence in ('LOCAL_DEMO_DISTRICT_FALLBACK', 'LOCAL_DEMO_SEED')
            )
            select
              poly.*,
              af.region_code as active_fallback_region_code,
              af.confidence as active_fallback_confidence
            from poly
            left join active_fallback af
              on af.district_lgd_code is not distinct from poly.district_lgd_code
             and af.state_lgd_code is not distinct from poly.state_lgd_code
            order by
              poly.state_lgd_code,
              poly.district_lgd_code,
              poly.region_system,
              poly.region_code
        """)).mappings().all()
    finally:
        db.close()

    output_rows = []
    for row in rows:
        row = dict(row)
        decision, reason = decide(row)
        output_rows.append({
            "promotion_decision": decision,
            "promotion_reason": reason,
            "mapping_id": str(row["id"]),
            "region_id": str(row["region_id"]),
            "region_code": row["region_code"],
            "region_system": row["region_system"],
            "region_class_code": row["region_class_code"],
            "region_class_name": row["region_class_name"],
            "scope_level": row["scope_level"],
            "state_lgd_code": row["state_lgd_code"],
            "state_name": row["state_name"],
            "district_lgd_code": row["district_lgd_code"],
            "district_name": row["district_name"],
            "overlap_percent_of_district": row["overlap_percent_of_district"],
            "crosswalk_category": row["crosswalk_category"],
            "low_overlap_bucket": row["low_overlap_bucket"],
            "candidate_confidence": row["confidence"],
            "candidate_review_status": row["review_status"],
            "candidate_is_active": row["is_active"],
            "active_fallback_region_code": row["active_fallback_region_code"],
            "active_fallback_confidence": row["active_fallback_confidence"],
        })

    decision_counts = Counter(r["promotion_decision"] for r in output_rows)
    state_counts = Counter(
        (r["state_lgd_code"], r["state_name"], r["promotion_decision"])
        for r in output_rows
    )
    region_system_counts = Counter(
        (r["region_system"], r["promotion_decision"])
        for r in output_rows
    )

    pilot_rows = [
        r for r in output_rows
        if r["promotion_decision"].startswith("PILOT_REVIEW")
    ]

    blocked_rows = [
        r for r in output_rows
        if r["promotion_decision"].startswith("BLOCKED")
    ]

    result = {
        "schema_version": "core_lgd_mapping_promotion_review_plan.v1",
        "mode": "READ_ONLY_PROMOTION_PLAN",
        "db_writes_made": False,
        "external_calls_made": False,
        "policy": {
            "source_confidence": "POLY_REV",
            "source_review_status": "MANUAL_REVIEW",
            "source_is_active": False,
            "promotion_requires_separate_apply": True,
            "pilot_state_codes": sorted(PILOT_STATE_CODES),
            "min_high_overlap_percent": MIN_HIGH_OVERLAP,
        },
        "counts": {
            "input_poly_rev_rows": len(output_rows),
            "pilot_review_rows": len(pilot_rows),
            "blocked_rows": len(blocked_rows),
            "decision_counts": dict(sorted(decision_counts.items())),
        },
        "region_system_decision_counts": [
            {
                "region_system": key[0],
                "promotion_decision": key[1],
                "count": count,
            }
            for key, count in sorted(region_system_counts.items())
        ],
        "state_decision_counts": [
            {
                "state_lgd_code": key[0],
                "state_name": key[1],
                "promotion_decision": key[2],
                "count": count,
            }
            for key, count in sorted(state_counts.items())
        ],
        "samples": {
            "pilot_review": pilot_rows[:12],
            "blocked": blocked_rows[:12],
            "manual_low_overlap": [
                r for r in output_rows
                if r["promotion_decision"] == "MANUAL_REVIEW_LOW_OVERLAP"
            ][:12],
        },
        "readiness": {
            "safe_for_automatic_promotion": False,
            "ready_for_admin_review_surface": True,
            "has_pilot_review_candidates": len(pilot_rows) > 0,
            "source_rows_remain_inactive": all(not r["candidate_is_active"] for r in output_rows),
        },
        "output_files": {
            "csv": str(OUT_CSV),
            "json": str(OUT_JSON),
        },
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(output_rows[0].keys()))
        writer.writeheader()
        writer.writerows(output_rows)

    OUT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))

    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

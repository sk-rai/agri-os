#!/usr/bin/env python3
"""
Generate a read-only pilot review report comparing active fallback mappings
against inactive POLY_REV polygon-derived candidates.

Default pilot states:
- Karnataka 29
- Maharashtra 27
- Punjab 3

No DB writes.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from app.core.database import SessionLocal


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data/staged/core_stack/pilot_review_report"
OUT_CSV = OUT_DIR / "core_lgd_pilot_mapping_review_report.csv"
OUT_JSON = OUT_DIR / "core_lgd_pilot_mapping_review_report.json"

DEFAULT_STATE_CODES = ["29", "27", "3"]


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-code",
        action="append",
        dest="state_codes",
        help="State LGD code to include. Can be repeated. Defaults to Karnataka/Maharashtra/Punjab.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state_codes = args.state_codes or DEFAULT_STATE_CODES

    db = SessionLocal()
    try:
        rows = db.execute(text("""
            with fallback as (
              select
                m.state_lgd_code,
                m.district_lgd_code,
                count(*) as active_fallback_count,
                string_agg(m.region_code, ' | ' order by m.region_code) as active_fallback_region_codes,
                string_agg(coalesce(r.region_name, m.region_code), ' | ' order by m.region_code) as active_fallback_region_names,
                string_agg(coalesce(r.region_system, 'UNKNOWN'), ' | ' order by m.region_code) as active_fallback_region_systems,
                string_agg(m.confidence, ' | ' order by m.region_code) as active_fallback_confidences
              from geography_climate_region_mappings m
              left join geography_climate_regions r on r.id = m.region_id
              where m.is_active is true
                and m.confidence in ('LOCAL_DEMO_DISTRICT_FALLBACK', 'LOCAL_DEMO_SEED')
                and m.state_lgd_code = any(:state_codes)
              group by m.state_lgd_code, m.district_lgd_code
            ),
            poly as (
              select
                m.id as poly_mapping_id,
                m.state_lgd_code,
                m.district_lgd_code,
                m.region_code as poly_region_code,
                m.confidence as poly_confidence,
                m.review_status as poly_review_status,
                m.is_active as poly_is_active,
                r.region_name as poly_region_name,
                r.region_system as poly_region_system,
                m.metadata ->> 'state_name' as state_name,
                m.metadata ->> 'district_name' as district_name,
                m.metadata ->> 'region_class_name' as poly_region_class_name,
                m.metadata ->> 'region_class_code' as poly_region_class_code,
                m.metadata ->> 'overlap_percent_of_district' as overlap_percent_of_district,
                m.metadata ->> 'crosswalk_category' as crosswalk_category,
                coalesce(nullif(m.metadata ->> 'low_overlap_bucket', ''), 'NOT_LOW_OVERLAP') as low_overlap_bucket
              from geography_climate_region_mappings m
              left join geography_climate_regions r on r.id = m.region_id
              where m.confidence = 'POLY_REV'
                and m.state_lgd_code = any(:state_codes)
            )
            select
              poly.state_lgd_code,
              poly.state_name,
              poly.district_lgd_code,
              poly.district_name,
              poly.poly_region_system,
              poly.poly_mapping_id,
              poly.poly_region_code,
              poly.poly_region_name,
              poly.poly_region_class_code,
              poly.poly_region_class_name,
              poly.overlap_percent_of_district,
              poly.crosswalk_category,
              poly.low_overlap_bucket,
              fallback.active_fallback_count,
              fallback.active_fallback_region_codes,
              fallback.active_fallback_region_names,
              fallback.active_fallback_region_systems,
              fallback.active_fallback_confidences,
              case
                when fallback.active_fallback_count is null then 'NO_ACTIVE_FALLBACK'
                else 'HAS_ACTIVE_FALLBACK'
              end as comparison_status
            from poly
            left join fallback
              on fallback.state_lgd_code is not distinct from poly.state_lgd_code
             and fallback.district_lgd_code is not distinct from poly.district_lgd_code
            order by
              poly.state_lgd_code,
              poly.district_lgd_code,
              poly.poly_region_system,
              poly.poly_region_code
        """), {"state_codes": state_codes}).mappings().all()
    finally:
        db.close()

    output_rows = []
    for r in rows:
        item = dict(r)
        for key, value in list(item.items()):
            if value is not None and not isinstance(value, (str, int, float, bool)):
                item[key] = str(value)
        output_rows.append(item)

    status_counts = defaultdict(int)
    state_counts = defaultdict(int)
    region_counts = defaultdict(int)
    for row in output_rows:
        status_counts[row["comparison_status"]] += 1
        state_counts[(row["state_lgd_code"], row["state_name"], row["comparison_status"])] += 1
        region_counts[(row["poly_region_system"], row["comparison_status"])] += 1

    result = {
        "schema_version": "core_lgd_pilot_mapping_review_report.v1",
        "mode": "READ_ONLY_REPORT",
        "db_writes_made": False,
        "external_calls_made": False,
        "state_codes": state_codes,
        "counts": {
            "rows": len(output_rows),
            "status_counts": dict(sorted(status_counts.items())),
        },
        "state_status_counts": [
            {
                "state_lgd_code": key[0],
                "state_name": key[1],
                "comparison_status": key[2],
                "count": count,
            }
            for key, count in sorted(state_counts.items())
        ],
        "region_system_status_counts": [
            {
                "region_system": key[0],
                "comparison_status": key[1],
                "count": count,
            }
            for key, count in sorted(region_counts.items())
        ],
        "samples": {
            "has_active_fallback": [
                r for r in output_rows
                if r["comparison_status"] == "HAS_ACTIVE_FALLBACK"
            ][:20],
            "no_active_fallback": [
                r for r in output_rows
                if r["comparison_status"] == "NO_ACTIVE_FALLBACK"
            ][:20],
        },
        "readiness": {
            "safe_read_only": True,
            "ready_for_admin_review_surface": len(output_rows) > 0,
            "land_intelligence_behavior_changed": False,
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

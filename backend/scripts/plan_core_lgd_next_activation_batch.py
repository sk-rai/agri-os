#!/usr/bin/env python3
"""
Plan the next cautious CoRE/LGD activation batch.

Read-only. No DB writes.

The planner groups inactive POLY_REV candidate rows by district and recommends
pilot-state districts that have one clean candidate in each CoRE region system,
high dominant overlaps, active fallback rows to supersede, and no known blocker
flags.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from app.core.database import SessionLocal

PILOT_STATES = ("29", "27", "3")
EXPECTED_SYSTEMS = {
    "CORE_STACK_AGRO_CLIMATIC_ZONE",
    "CORE_STACK_AGRO_ECOLOGICAL_ZONE",
    "CORE_STACK_BIOGEOGRAPHIC_ZONE",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=9, help="Maximum district groups to recommend")
    parser.add_argument("--min-overlap", type=float, default=90.0, help="Minimum overlap for every row in a district group")
    parser.add_argument("--state", dest="state_lgd_code", help="Optional pilot state LGD filter")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db = SessionLocal()
    try:
        params = {
            "min_overlap": args.min_overlap,
            "limit": args.limit,
            "state_lgd_code": args.state_lgd_code,
        }
        state_filter = "and m.state_lgd_code = :state_lgd_code" if args.state_lgd_code else ""

        rows = db.execute(text(f"""
            with fallback as (
              select
                state_lgd_code,
                district_lgd_code,
                count(*) as active_fallback_count,
                string_agg(region_code, ' | ' order by region_code) as active_fallback_region_codes
              from geography_climate_region_mappings
              where is_active is true
                and confidence in ('LOCAL_DEMO_DISTRICT_FALLBACK', 'LOCAL_DEMO_SEED')
              group by state_lgd_code, district_lgd_code
            ),
            candidates as (
              select
                m.id::text as mapping_id,
                m.state_lgd_code,
                m.district_lgd_code,
                m.metadata ->> 'state_name' as state_name,
                m.metadata ->> 'district_name' as district_name,
                r.region_system,
                m.region_code,
                r.region_name,
                m.review_status,
                coalesce(nullif(m.metadata ->> 'low_overlap_bucket', ''), 'NOT_LOW_OVERLAP') as low_overlap_bucket,
                coalesce(m.metadata ->> 'crosswalk_category', '') as crosswalk_category,
                nullif(m.metadata ->> 'overlap_percent_of_district', '')::numeric as overlap_percent_of_district,
                coalesce(fallback.active_fallback_count, 0) as active_fallback_count,
                fallback.active_fallback_region_codes
              from geography_climate_region_mappings m
              left join geography_climate_regions r on r.id = m.region_id
              left join fallback
                on fallback.state_lgd_code is not distinct from m.state_lgd_code
               and fallback.district_lgd_code is not distinct from m.district_lgd_code
              where m.confidence = 'POLY_REV'
                and m.review_status = 'MANUAL_REVIEW'
                and m.is_active is false
                and m.state_lgd_code in ('29', '27', '3')
                {state_filter}
            ),
            grouped as (
              select
                state_lgd_code,
                district_lgd_code,
                max(state_name) as state_name,
                max(district_name) as district_name,
                count(*) as candidate_rows,
                count(distinct region_system) as region_system_count,
                min(overlap_percent_of_district) as min_overlap_percent,
                avg(overlap_percent_of_district) as avg_overlap_percent,
                max(active_fallback_count) as active_fallback_count,
                max(active_fallback_region_codes) as active_fallback_region_codes,
                sum(case when low_overlap_bucket <> 'NOT_LOW_OVERLAP' then 1 else 0 end) as low_overlap_flag_rows,
                sum(case when overlap_percent_of_district < :min_overlap then 1 else 0 end) as below_min_overlap_rows,
                sum(case when crosswalk_category in ('BHARATLAS_ONLY', 'STATE_CODE_MISMATCH', 'UNSET') then 1 else 0 end) as crosswalk_blocker_rows,
                jsonb_agg(jsonb_build_object(
                  'mapping_id', mapping_id,
                  'region_system', region_system,
                  'region_code', region_code,
                  'region_name', region_name,
                  'overlap_percent_of_district', overlap_percent_of_district,
                  'crosswalk_category', crosswalk_category,
                  'low_overlap_bucket', low_overlap_bucket
                ) order by region_system, region_code) as rows
              from candidates
              group by state_lgd_code, district_lgd_code
            )
            select
              *,
              case
                when candidate_rows <> 3 or region_system_count <> 3 then 'BLOCK_NOT_THREE_CORE_SYSTEMS'
                when active_fallback_count = 0 then 'BLOCK_NO_ACTIVE_FALLBACK'
                when low_overlap_flag_rows > 0 then 'BLOCK_LOW_OVERLAP_BUCKET'
                when below_min_overlap_rows > 0 then 'BLOCK_BELOW_MIN_OVERLAP'
                when crosswalk_blocker_rows > 0 then 'BLOCK_CROSSWALK'
                else 'RECOMMENDED_FOR_REVIEW_APPROVAL'
              end as recommendation
            from grouped
            order by
              case
                when candidate_rows = 3
                 and region_system_count = 3
                 and active_fallback_count > 0
                 and low_overlap_flag_rows = 0
                 and below_min_overlap_rows = 0
                 and crosswalk_blocker_rows = 0
                then 0 else 1 end,
              min_overlap_percent desc,
              state_lgd_code,
              district_lgd_code
            limit :limit
        """), params).mappings().all()

        items = [dict(row) for row in rows]
        recommended = [row for row in items if row["recommendation"] == "RECOMMENDED_FOR_REVIEW_APPROVAL"]
        counts: dict[str, int] = {}
        for row in items:
            counts[row["recommendation"]] = counts.get(row["recommendation"], 0) + 1

        result = {
            "schema_version": "core_lgd_next_activation_batch_plan.v1",
            "mode": "READ_ONLY_BATCH_PLAN",
            "db_writes_made": False,
            "external_calls_made": False,
            "filters": {
                "pilot_state_codes": list(PILOT_STATES),
                "state_lgd_code": args.state_lgd_code,
                "min_overlap": args.min_overlap,
                "limit": args.limit,
            },
            "counts": {
                "returned_district_groups": len(items),
                "recommended_district_groups": len(recommended),
            },
            "recommendation_counts": dict(sorted(counts.items())),
            "readiness": {
                "has_recommendations": len(recommended) > 0,
                "safe_read_only": True,
                "approval_required_before_activation": True,
                "activation_requires_separate_apply": True,
            },
            "items": items,
        }
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

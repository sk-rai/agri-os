#!/usr/bin/env python3
"""
Plan activation of approved CoRE/LGD polygon-derived mappings.

Read-only. No DB writes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from app.core.database import SessionLocal

SOURCE_CONFIDENCE = "POLY_REV"
APPROVED_STATUS = "APPROVED_FOR_PROMOTION"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", dest="state_lgd_code")
    parser.add_argument("--district", dest="district_lgd_code")
    parser.add_argument("--region-system", dest="region_system")
    parser.add_argument("--include-general", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db = SessionLocal()
    try:
        where = ["m.confidence = :confidence", "m.review_status = :review_status", "m.is_active is false"]
        params = {"confidence": SOURCE_CONFIDENCE, "review_status": APPROVED_STATUS}

        if args.state_lgd_code:
            where.append("m.state_lgd_code = :state_lgd_code")
            params["state_lgd_code"] = args.state_lgd_code
        if args.district_lgd_code:
            where.append("m.district_lgd_code = :district_lgd_code")
            params["district_lgd_code"] = args.district_lgd_code
        if args.region_system:
            where.append("r.region_system = :region_system")
            params["region_system"] = args.region_system

        where_sql = " and ".join(where)

        rows = db.execute(text(f"""
            with fallback as (
              select
                state_lgd_code,
                district_lgd_code,
                count(*) as active_fallback_count,
                string_agg(id::text, '|' order by id::text) as active_fallback_ids,
                string_agg(region_code, ' | ' order by region_code) as active_fallback_region_codes
              from geography_climate_region_mappings
              where is_active is true
                and confidence in ('LOCAL_DEMO_DISTRICT_FALLBACK', 'LOCAL_DEMO_SEED')
              group by state_lgd_code, district_lgd_code
            )
            select
              m.id::text as mapping_id,
              m.region_id::text as region_id,
              m.region_code,
              r.region_name,
              r.region_system,
              m.state_lgd_code,
              m.district_lgd_code,
              m.review_status,
              m.is_active,
              m.metadata ->> 'state_name' as state_name,
              m.metadata ->> 'district_name' as district_name,
              m.metadata ->> 'crosswalk_category' as crosswalk_category,
              coalesce(nullif(m.metadata ->> 'low_overlap_bucket', ''), 'NOT_LOW_OVERLAP') as low_overlap_bucket,
              nullif(m.metadata ->> 'overlap_percent_of_district', '')::numeric as overlap_percent_of_district,
              coalesce(f.active_fallback_count, 0) as active_fallback_count,
              f.active_fallback_ids,
              f.active_fallback_region_codes,
              case
                when coalesce(nullif(m.metadata ->> 'low_overlap_bucket', ''), 'NOT_LOW_OVERLAP') <> 'NOT_LOW_OVERLAP'
                  then 'BLOCK_LOW_OVERLAP_BUCKET'
                when nullif(m.metadata ->> 'overlap_percent_of_district', '')::numeric < 80
                  then 'BLOCK_OVERLAP_BELOW_80'
                when coalesce(m.metadata ->> 'crosswalk_category', '') in ('BHARATLAS_ONLY', 'STATE_CODE_MISMATCH', 'UNSET')
                  then 'BLOCK_CROSSWALK_CATEGORY'
                when m.state_lgd_code not in ('29', '27', '3') and :include_general is false
                  then 'BLOCK_NON_PILOT_DEFAULT'
                else 'ELIGIBLE_FOR_SEPARATE_APPLY'
              end as activation_decision
            from geography_climate_region_mappings m
            left join geography_climate_regions r on r.id = m.region_id
            left join fallback f
              on f.state_lgd_code is not distinct from m.state_lgd_code
             and f.district_lgd_code is not distinct from m.district_lgd_code
            where {where_sql}
            order by m.state_lgd_code, m.district_lgd_code, r.region_system, m.region_code
        """), {**params, "include_general": args.include_general}).mappings().all()

        items = [dict(row) for row in rows]
        eligible = [row for row in items if row["activation_decision"] == "ELIGIBLE_FOR_SEPARATE_APPLY"]
        districts = {(row["state_lgd_code"], row["district_lgd_code"]) for row in eligible}
        fallback_ids = sorted({
            fid
            for row in eligible
            for fid in (row.get("active_fallback_ids") or "").split("|")
            if fid
        })

        def counts_by(key: str) -> dict:
            out = {}
            for row in items:
                value = row.get(key) or "UNKNOWN"
                out[value] = out.get(value, 0) + 1
            return dict(sorted(out.items()))

        result = {
            "schema_version": "core_lgd_approved_mapping_activation_plan.v1",
            "mode": "READ_ONLY_ACTIVATION_PLAN",
            "db_writes_made": False,
            "external_calls_made": False,
            "filters": {
                "state_lgd_code": args.state_lgd_code,
                "district_lgd_code": args.district_lgd_code,
                "region_system": args.region_system,
                "include_general": args.include_general,
            },
            "source_policy": {
                "source_confidence": SOURCE_CONFIDENCE,
                "source_review_status": APPROVED_STATUS,
                "source_is_active": False,
                "future_active_confidence": "POLY_APPR",
                "future_version": "clap_v1",
                "activation_requires_separate_apply": True,
            },
            "counts": {
                "approved_rows": len(items),
                "eligible_rows": len(eligible),
                "eligible_districts": len(districts),
                "fallback_rows_that_would_be_superseded": len(fallback_ids),
            },
            "decision_counts": counts_by("activation_decision"),
            "state_counts": counts_by("state_lgd_code"),
            "region_system_counts": counts_by("region_system"),
            "samples": {
                "eligible": eligible[:10],
                "blocked": [row for row in items if row["activation_decision"] != "ELIGIBLE_FOR_SEPARATE_APPLY"][:10],
            },
            "readiness": {
                "has_approved_rows": len(items) > 0,
                "has_eligible_rows": len(eligible) > 0,
                "safe_read_only": True,
                "android_maestro_required_after_apply": True,
            },
        }

        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

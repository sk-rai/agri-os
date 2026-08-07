#!/usr/bin/env python3
"""
Verify imported CoRE/LGD manual-review candidate mappings.

Read-only. No DB writes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from app.core.database import SessionLocal


EXPECTED_POLY_REV_COUNT = 2298


def main() -> int:
    db = SessionLocal()
    try:
        polygon_summary = db.execute(text("""
            select
              count(*) as total,
              count(distinct district_lgd_code) as district_count,
              count(distinct region_code) as region_count,
              sum(case when is_active then 1 else 0 end) as active_count,
              sum(case when review_status = 'MANUAL_REVIEW' then 1 else 0 end) as manual_review_count,
              sum(case when version = 'clri_v1' then 1 else 0 end) as version_count
            from geography_climate_region_mappings
            where confidence = 'POLY_REV'
        """)).mappings().one()

        fallback_summary = db.execute(text("""
            select confidence, is_active, count(*) as count
            from geography_climate_region_mappings
            where confidence in ('LOCAL_DEMO_DISTRICT_FALLBACK', 'LOCAL_DEMO_SEED')
            group by confidence, is_active
            order by confidence, is_active
        """)).mappings().all()

        bad_rows = db.execute(text("""
            select id, region_code, district_lgd_code, review_status, is_active, confidence, version
            from geography_climate_region_mappings
            where confidence = 'POLY_REV'
              and (
                review_status <> 'MANUAL_REVIEW'
                or is_active is true
                or version <> 'clri_v1'
              )
            limit 20
        """)).mappings().all()

        duplicate_keys = db.execute(text("""
            select
              region_code,
              scope_level,
              state_lgd_code,
              district_lgd_code,
              confidence,
              review_status,
              count(*) as count
            from geography_climate_region_mappings
            where confidence = 'POLY_REV'
            group by region_code, scope_level, state_lgd_code, district_lgd_code, confidence, review_status
            having count(*) > 1
            limit 20
        """)).mappings().all()

        missing_region = db.execute(text("""
            select m.id, m.region_code
            from geography_climate_region_mappings m
            left join geography_climate_regions r on r.id = m.region_id
            where m.confidence = 'POLY_REV'
              and r.id is null
            limit 20
        """)).mappings().all()

        result = {
            "schema_version": "core_lgd_manual_review_mapping_verification.v1",
            "mode": "READ_ONLY_VERIFY",
            "db_writes_made": False,
            "external_calls_made": False,
            "expected": {
                "poly_rev_count": EXPECTED_POLY_REV_COUNT,
                "poly_rev_is_active": False,
                "poly_rev_review_status": "MANUAL_REVIEW",
                "poly_rev_version": "clri_v1",
            },
            "polygon_summary": dict(polygon_summary),
            "fallback_summary": [dict(r) for r in fallback_summary],
            "issues": {
                "bad_policy_rows": [dict(r) for r in bad_rows],
                "duplicate_keys": [dict(r) for r in duplicate_keys],
                "missing_region_refs": [dict(r) for r in missing_region],
            },
        }

        result["readiness"] = {
            "poly_rev_count_matches": polygon_summary["total"] == EXPECTED_POLY_REV_COUNT,
            "all_poly_rev_inactive": polygon_summary["active_count"] == 0,
            "all_poly_rev_manual_review": polygon_summary["manual_review_count"] == polygon_summary["total"],
            "all_poly_rev_expected_version": polygon_summary["version_count"] == polygon_summary["total"],
            "no_duplicate_poly_rev_keys": len(duplicate_keys) == 0,
            "no_missing_region_refs": len(missing_region) == 0,
            "fallbacks_remain_active": any(
                r["confidence"] == "LOCAL_DEMO_DISTRICT_FALLBACK" and r["is_active"] is True and r["count"] == 186
                for r in fallback_summary
            ),
            "safe_for_land_intelligence_behavior": polygon_summary["active_count"] == 0,
        }

        print(json.dumps(result, indent=2, sort_keys=True, default=str))

        failed = [k for k, v in result["readiness"].items() if not v]
        if failed:
            print(json.dumps({"failed_checks": failed}, indent=2), file=sys.stderr)
            return 1
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

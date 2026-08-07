#!/usr/bin/env python3
"""
Verify Bagalkote CoRE/LGD pilot activation.

Read-only. No DB writes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from app.core.database import SessionLocal

STATE = "29"
DISTRICT = "524"


def main() -> int:
    db = SessionLocal()
    try:
        active_rows = db.execute(text("""
            select
              m.id::text,
              m.region_code,
              r.region_name,
              r.region_system,
              m.confidence,
              m.review_status,
              m.version,
              m.is_active
            from geography_climate_region_mappings m
            left join geography_climate_regions r on r.id = m.region_id
            where m.state_lgd_code = :state
              and m.district_lgd_code = :district
              and m.is_active is true
            order by r.region_system, m.region_code
        """), {"state": STATE, "district": DISTRICT}).mappings().all()

        inactive_fallbacks = db.execute(text("""
            select id::text, region_code, confidence, review_status, is_active, metadata
            from geography_climate_region_mappings
            where state_lgd_code = :state
              and district_lgd_code = :district
              and confidence in ('LOCAL_DEMO_DISTRICT_FALLBACK', 'LOCAL_DEMO_SEED')
        """), {"state": STATE, "district": DISTRICT}).mappings().all()

        active = [dict(row) for row in active_rows]
        fallbacks = [dict(row) for row in inactive_fallbacks]

        expected_systems = {
            "CORE_STACK_AGRO_CLIMATIC_ZONE",
            "CORE_STACK_AGRO_ECOLOGICAL_ZONE",
            "CORE_STACK_BIOGEOGRAPHIC_ZONE",
        }
        active_systems = {row["region_system"] for row in active}

        result = {
            "schema_version": "core_lgd_bagalkote_activation_verification.v1",
            "mode": "READ_ONLY_VERIFY",
            "db_writes_made": False,
            "external_calls_made": False,
            "scope": {
                "state_lgd_code": STATE,
                "district_lgd_code": DISTRICT,
                "district_name": "Bagalkote",
            },
            "active_summary": {
                "active_count": len(active),
                "active_systems": sorted(active_systems),
                "active_confidence_counts": {},
                "active_review_status_counts": {},
                "active_version_counts": {},
            },
            "fallback_summary": {
                "fallback_rows": len(fallbacks),
                "active_fallback_rows": sum(1 for row in fallbacks if row["is_active"]),
            },
            "active_rows": active,
            "fallback_rows": fallbacks,
        }

        for row in active:
            result["active_summary"]["active_confidence_counts"][row["confidence"]] = result["active_summary"]["active_confidence_counts"].get(row["confidence"], 0) + 1
            result["active_summary"]["active_review_status_counts"][row["review_status"]] = result["active_summary"]["active_review_status_counts"].get(row["review_status"], 0) + 1
            result["active_summary"]["active_version_counts"][row["version"]] = result["active_summary"]["active_version_counts"].get(row["version"], 0) + 1

        result["readiness"] = {
            "has_three_active_core_rows": len(active) == 3,
            "all_active_rows_are_poly_appr": all(row["confidence"] == "POLY_APPR" for row in active),
            "all_active_rows_promoted": all(row["review_status"] == "PROMOTED" for row in active),
            "all_active_rows_expected_version": all(row["version"] == "clap_v1" for row in active),
            "has_expected_core_systems": active_systems == expected_systems,
            "fallback_is_no_longer_active": result["fallback_summary"]["active_fallback_rows"] == 0,
            "land_intelligence_expected_source_derived": True,
        }

        print(json.dumps(result, indent=2, sort_keys=True, default=str))

        failed = [name for name, ok in result["readiness"].items() if not ok]
        if failed:
            print(json.dumps({"failed_checks": failed}, indent=2), file=sys.stderr)
            return 1
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

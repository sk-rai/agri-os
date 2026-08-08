#!/usr/bin/env python3
"""
Verify district-scoped CoRE/LGD activation.

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


EXPECTED_SYSTEMS = {
    "CORE_STACK_AGRO_CLIMATIC_ZONE",
    "CORE_STACK_AGRO_ECOLOGICAL_ZONE",
    "CORE_STACK_BIOGEOGRAPHIC_ZONE",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, dest="state_lgd_code")
    parser.add_argument("--district", required=True, dest="district_lgd_code")
    parser.add_argument("--district-name", default=None)
    parser.add_argument("--expected-active-count", type=int, default=3)
    parser.add_argument("--expect-source-derived", action="store_true", default=True)
    return parser.parse_args()


def count_by(rows: list[dict], key: str) -> dict:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "UNKNOWN")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def main() -> int:
    args = parse_args()
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
        """), {
            "state": args.state_lgd_code,
            "district": args.district_lgd_code,
        }).mappings().all()

        fallback_rows = db.execute(text("""
            select id::text, region_code, confidence, review_status, is_active, metadata
            from geography_climate_region_mappings
            where state_lgd_code = :state
              and district_lgd_code = :district
              and confidence in ('LOCAL_DEMO_DISTRICT_FALLBACK', 'LOCAL_DEMO_SEED')
            order by region_code
        """), {
            "state": args.state_lgd_code,
            "district": args.district_lgd_code,
        }).mappings().all()

        active = [dict(row) for row in active_rows]
        fallbacks = [dict(row) for row in fallback_rows]
        active_systems = {row["region_system"] for row in active}

        result = {
            "schema_version": "core_lgd_activation_verification.v1",
            "mode": "READ_ONLY_VERIFY",
            "db_writes_made": False,
            "external_calls_made": False,
            "scope": {
                "state_lgd_code": args.state_lgd_code,
                "district_lgd_code": args.district_lgd_code,
                "district_name": args.district_name,
            },
            "expected": {
                "active_count": args.expected_active_count,
                "active_confidence": "POLY_APPR",
                "active_review_status": "PROMOTED",
                "active_version": "clap_v1",
                "active_region_systems": sorted(EXPECTED_SYSTEMS),
                "active_fallback_rows": 0,
            },
            "active_summary": {
                "active_count": len(active),
                "active_systems": sorted(active_systems),
                "active_confidence_counts": count_by(active, "confidence"),
                "active_review_status_counts": count_by(active, "review_status"),
                "active_version_counts": count_by(active, "version"),
            },
            "fallback_summary": {
                "fallback_rows": len(fallbacks),
                "active_fallback_rows": sum(1 for row in fallbacks if row["is_active"]),
            },
            "active_rows": active,
            "fallback_rows": fallbacks,
        }

        result["readiness"] = {
            "has_expected_active_core_rows": len(active) == args.expected_active_count,
            "all_active_rows_are_poly_appr": all(row["confidence"] == "POLY_APPR" for row in active),
            "all_active_rows_promoted": all(row["review_status"] == "PROMOTED" for row in active),
            "all_active_rows_expected_version": all(row["version"] == "clap_v1" for row in active),
            "has_expected_core_systems": active_systems == EXPECTED_SYSTEMS,
            "fallback_is_no_longer_active": result["fallback_summary"]["active_fallback_rows"] == 0,
            "land_intelligence_expected_source_derived": args.expect_source_derived,
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

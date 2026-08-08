#!/usr/bin/env python3
"""Verify active promoted CoRE/LGD district mapping state.

Read-only verifier for the current controlled rollout:
- POLY_APPR active promoted rows
- fallback rows superseded
- selected districts have exactly 3 active CoRE rows
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import SessionLocal  # noqa: E402

EXPECTED_DISTRICTS = {
    ("29", "524"): "Bagalkote",
    ("29", "525"): "Bengaluru Urban",
    ("29", "526"): "Bengaluru Rural",
    ("29", "528"): "Ballari",
    ("29", "529"): "Bidar",
    ("29", "534"): "Dakshina Kannada",
    ("29", "630"): "Chikkaballapura",
    ("27", "466"): "Ahmednagar",
    ("27", "467"): "Akola",
    ("27", "469"): "Aurangabad",
    ("27", "470"): "Beed",
    ("27", "471"): "Bhandara",
    ("27", "472"): "Buldhana",
    ("27", "477"): "Hingoli",
    ("3", "27"): "Amritsar",
    ("3", "28"): "Bathinda",
    ("3", "29"): "Faridkot",
    ("3", "39"): "Sri Muktsar Sahib",
    ("3", "605"): "Barnala",
    ("3", "737"): "Malerkotla",
}

CORE_SYSTEMS = {
    "CORE_STACK_AGRO_CLIMATIC_ZONE",
    "CORE_STACK_AGRO_ECOLOGICAL_ZONE",
    "CORE_STACK_BIOGEOGRAPHIC_ZONE",
}


def as_dict(row: Any) -> dict[str, Any]:
    return dict(row)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-districts", type=int, default=20)
    parser.add_argument("--expected-rows", type=int, default=60)
    parser.add_argument("--expected-inactive-fallbacks", type=int, default=20)
    parser.add_argument("--expected-active-fallbacks", type=int, default=166)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        active_rows = [
            as_dict(row)
            for row in db.execute(text("""
                select
                  m.state_lgd_code,
                  coalesce(m.metadata ->> 'state_name', m.state_lgd_code) as state_name,
                  m.district_lgd_code,
                  coalesce(m.metadata ->> 'district_name', m.district_lgd_code) as district_name,
                  m.region_code,
                  r.region_system,
                  coalesce(r.region_name, m.region_code) as region_name,
                  m.confidence,
                  m.review_status,
                  m.is_active,
                  m.version
                from geography_climate_region_mappings m
                left join geography_climate_regions r on r.id = m.region_id
                where m.scope_level = 'DISTRICT'
                  and m.confidence = 'POLY_APPR'
                  and m.review_status = 'PROMOTED'
                  and m.version = 'clap_v1'
                  and m.is_active is true
                order by m.state_lgd_code, m.district_lgd_code, r.region_system
            """)).mappings()
        ]

        fallback_counts = [
            as_dict(row)
            for row in db.execute(text("""
                select confidence, is_active, count(*)::int as count
                from geography_climate_region_mappings
                where confidence in ('LOCAL_DEMO_DISTRICT_FALLBACK', 'LOCAL_DEMO_SEED')
                group by confidence, is_active
                order by confidence, is_active
            """)).mappings()
        ]

        districts: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in active_rows:
            districts.setdefault((row["state_lgd_code"], row["district_lgd_code"]), []).append(row)

        active_by_state = [
            as_dict(row)
            for row in db.execute(text("""
                select
                  state_lgd_code,
                  coalesce(max(metadata ->> 'state_name'), state_lgd_code) as state_name,
                  count(distinct district_lgd_code)::int as active_districts,
                  count(*)::int as active_mapping_rows
                from geography_climate_region_mappings
                where confidence = 'POLY_APPR'
                  and review_status = 'PROMOTED'
                  and version = 'clap_v1'
                  and is_active is true
                  and scope_level = 'DISTRICT'
                group by state_lgd_code
                order by state_lgd_code
            """)).mappings()
        ]

        inactive_fallbacks = sum(
            row["count"]
            for row in fallback_counts
            if row["confidence"] == "LOCAL_DEMO_DISTRICT_FALLBACK" and row["is_active"] is False
        )
        active_fallbacks = sum(
            row["count"]
            for row in fallback_counts
            if row["confidence"] == "LOCAL_DEMO_DISTRICT_FALLBACK" and row["is_active"] is True
        )

        missing_expected = [
            {"state_lgd_code": state, "district_lgd_code": district, "district_name": name}
            for (state, district), name in EXPECTED_DISTRICTS.items()
            if (state, district) not in districts
        ]

        unexpected_districts = [
            {
                "state_lgd_code": state,
                "district_lgd_code": district,
                "district_name": rows[0]["district_name"],
            }
            for (state, district), rows in districts.items()
            if (state, district) not in EXPECTED_DISTRICTS
        ]

        bad_district_systems = []
        for (state, district), rows in districts.items():
            systems = {row["region_system"] for row in rows}
            if systems != CORE_SYSTEMS or len(rows) != 3:
                bad_district_systems.append({
                    "state_lgd_code": state,
                    "district_lgd_code": district,
                    "district_name": rows[0]["district_name"],
                    "row_count": len(rows),
                    "systems": sorted(systems),
                })

        total_districts = len(districts)
        total_rows = len(active_rows)

        readiness = {
            "safe_read_only": True,
            "active_row_count_matches": total_rows == args.expected_rows,
            "active_district_count_matches": total_districts == args.expected_districts,
            "inactive_fallback_count_matches": inactive_fallbacks == args.expected_inactive_fallbacks,
            "active_fallback_count_matches": active_fallbacks == args.expected_active_fallbacks,
            "all_expected_districts_present": not missing_expected,
            "no_unexpected_districts": not unexpected_districts,
            "every_active_district_has_three_core_systems": not bad_district_systems,
        }

        result = {
            "schema_version": "core_lgd_active_promoted_state_verification.v1",
            "mode": "READ_ONLY_VERIFY",
            "db_writes_made": False,
            "external_calls_made": False,
            "active_poly_appr_total": {
                "active_districts": total_districts,
                "active_mapping_rows": total_rows,
            },
            "active_poly_appr_by_state": active_by_state,
            "fallback_counts": fallback_counts,
            "issues": {
                "missing_expected": missing_expected,
                "unexpected_districts": unexpected_districts,
                "bad_district_systems": bad_district_systems,
            },
            "readiness": readiness,
        }

        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if all(readiness.values()) else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

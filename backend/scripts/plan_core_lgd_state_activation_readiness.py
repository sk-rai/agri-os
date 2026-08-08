#!/usr/bin/env python3
"""Plan a guarded state-level CoRE/LGD activation expansion.

Read-only:
- no DB writes
- no external calls
- identifies promoted/approved/manual rows by district
- highlights districts ready for a later explicit activation workflow
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text

from app.core.database import SessionLocal

DEFAULT_OUTPUT_DIR = Path("../data/staged/core_stack/state_activation_readiness").resolve()
CORE_SYSTEMS = {
    "CORE_STACK_AGRO_CLIMATIC_ZONE",
    "CORE_STACK_AGRO_ECOLOGICAL_ZONE",
    "CORE_STACK_BIOGEOGRAPHIC_ZONE",
}
DEFAULT_MIN_OVERLAP = Decimal("80.0")


def as_jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    return value


def row_to_dict(row: Any) -> dict[str, Any]:
    return {key: as_jsonable(value) for key, value in dict(row).items()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", default="29", help="State LGD code. Default: 29 Karnataka")
    parser.add_argument("--min-overlap", default=str(DEFAULT_MIN_OVERLAP), help="Minimum overlap percent")
    parser.add_argument("--include-general", action="store_true", help="Include GENERAL_REVIEW rows, not just pilot rows")
    args = parser.parse_args()

    min_overlap = Decimal(str(args.min_overlap))
    state_lgd_code = str(args.state).strip()

    output_dir = DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    out_json = output_dir / f"core_lgd_state_{state_lgd_code}_activation_readiness.json"
    out_csv = output_dir / f"core_lgd_state_{state_lgd_code}_activation_readiness.csv"

    db = SessionLocal()
    try:
        rows = [
            row_to_dict(row)
            for row in db.execute(
                text(
                    """
                    with fallback as (
                      select
                        state_lgd_code,
                        district_lgd_code,
                        count(*)::int as active_fallback_count,
                        string_agg(id::text, ' | ' order by id::text) as active_fallback_ids,
                        string_agg(region_code, ' | ' order by region_code) as active_fallback_region_codes
                      from geography_climate_region_mappings
                      where is_active is true
                        and confidence in ('LOCAL_DEMO_DISTRICT_FALLBACK', 'LOCAL_DEMO_SEED')
                        and scope_level = 'DISTRICT'
                      group by state_lgd_code, district_lgd_code
                    ),
                    poly as (
                      select
                        m.id::text as mapping_id,
                        m.region_id::text as region_id,
                        m.state_lgd_code,
                        m.district_lgd_code,
                        coalesce(m.metadata ->> 'state_name', m.state_lgd_code) as state_name,
                        coalesce(m.metadata ->> 'district_name', m.district_lgd_code) as district_name,
                        r.region_system,
                        m.region_code,
                        coalesce(r.region_name, m.region_code) as region_name,
                        m.confidence,
                        m.review_status,
                        m.is_active,
                        m.version,
                        nullif(m.metadata ->> 'overlap_percent_of_district', '')::numeric as overlap_percent_of_district,
                        coalesce(nullif(m.metadata ->> 'crosswalk_category', ''), 'UNKNOWN') as crosswalk_category,
                        coalesce(nullif(m.metadata ->> 'low_overlap_bucket', ''), 'NOT_LOW_OVERLAP') as low_overlap_bucket
                      from geography_climate_region_mappings m
                      left join geography_climate_regions r on r.id = m.region_id
                      where m.scope_level = 'DISTRICT'
                        and m.state_lgd_code = :state_lgd_code
                        and (
                          (m.confidence = 'POLY_REV' and m.is_active is false)
                          or (m.confidence = 'POLY_APPR' and m.is_active is true)
                        )
                    )
                    select
                      poly.*,
                      fallback.active_fallback_count,
                      fallback.active_fallback_ids,
                      fallback.active_fallback_region_codes,
                      case
                        when poly.confidence = 'POLY_APPR' and poly.is_active is true and poly.review_status = 'PROMOTED'
                          then 'ALREADY_PROMOTED'
                        when poly.review_status = 'REJECTED'
                          then 'BLOCKED_REJECTED'
                        when poly.low_overlap_bucket in ('SOURCE_VERSION_DRIFT', 'SOURCE_VERSION_CONFLICT')
                          then 'BLOCKED_SOURCE_VERSION'
                        when poly.crosswalk_category in ('BHARATLAS_ONLY', 'STATE_CODE_MISMATCH', 'UNSET')
                          then 'BLOCKED_CROSSWALK'
                        when poly.low_overlap_bucket <> 'NOT_LOW_OVERLAP'
                          then 'BLOCKED_LOW_OVERLAP_BUCKET'
                        when poly.overlap_percent_of_district < :min_overlap
                          then 'BLOCKED_LOW_OVERLAP'
                        when poly.review_status = 'APPROVED_FOR_PROMOTION'
                          then 'READY_APPROVED_FOR_ACTIVATION'
                        when poly.review_status = 'MANUAL_REVIEW'
                          then 'NEEDS_ADMIN_REVIEW'
                        else 'NEEDS_REVIEW'
                      end as readiness_status
                    from poly
                    left join fallback
                      on fallback.state_lgd_code is not distinct from poly.state_lgd_code
                     and fallback.district_lgd_code is not distinct from poly.district_lgd_code
                    order by district_name, region_system, region_code
                    """
                ),
                {"state_lgd_code": state_lgd_code, "min_overlap": min_overlap},
            ).mappings()
        ]

        if not args.include_general:
            rows = [
                row for row in rows
                if row["readiness_status"] in {
                    "ALREADY_PROMOTED",
                    "READY_APPROVED_FOR_ACTIVATION",
                    "NEEDS_ADMIN_REVIEW",
                    "BLOCKED_REJECTED",
                    "BLOCKED_SOURCE_VERSION",
                    "BLOCKED_CROSSWALK",
                    "BLOCKED_LOW_OVERLAP_BUCKET",
                    "BLOCKED_LOW_OVERLAP",
                    "NEEDS_REVIEW",
                }
            ]

        by_district: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            by_district[(row["state_lgd_code"], row["district_lgd_code"])].append(row)

        district_summaries = []
        for (_state, district), district_rows in by_district.items():
            systems = {row["region_system"] for row in district_rows if row["region_system"]}
            statuses = Counter(row["readiness_status"] for row in district_rows)
            approved_ready = [
                row for row in district_rows
                if row["readiness_status"] == "READY_APPROVED_FOR_ACTIVATION"
            ]
            already_promoted = [
                row for row in district_rows
                if row["readiness_status"] == "ALREADY_PROMOTED"
            ]
            blocked = [
                row for row in district_rows
                if row["readiness_status"].startswith("BLOCKED")
            ]
            manual = [
                row for row in district_rows
                if row["readiness_status"] == "NEEDS_ADMIN_REVIEW"
            ]

            has_all_core_systems = CORE_SYSTEMS.issubset(systems)
            has_three_approved_ready = len({row["region_system"] for row in approved_ready}) == 3
            has_three_already_promoted = len({row["region_system"] for row in already_promoted}) == 3
            district_name = district_rows[0]["district_name"]
            state_name = district_rows[0]["state_name"]

            if has_three_already_promoted:
                district_status = "ALREADY_FULLY_PROMOTED"
            elif blocked:
                district_status = "BLOCKED"
            elif has_all_core_systems and has_three_approved_ready:
                district_status = "READY_FOR_SEPARATE_APPLY"
            elif manual:
                district_status = "NEEDS_ADMIN_REVIEW"
            else:
                district_status = "INCOMPLETE_OR_MIXED"

            district_summaries.append({
                "state_lgd_code": state_lgd_code,
                "state_name": state_name,
                "district_lgd_code": district,
                "district_name": district_name,
                "district_status": district_status,
                "row_count": len(district_rows),
                "systems_present": sorted(systems),
                "has_all_core_systems": has_all_core_systems,
                "status_counts": dict(statuses),
                "active_fallback_count": max((row["active_fallback_count"] or 0) for row in district_rows),
                "min_overlap_percent": min(
                    (Decimal(str(row["overlap_percent_of_district"])) for row in district_rows if row["overlap_percent_of_district"] is not None),
                    default=None,
                ),
            })

        district_summaries.sort(key=lambda row: (row["district_status"], row["district_name"]))

        status_counts = Counter(row["readiness_status"] for row in rows)
        district_status_counts = Counter(row["district_status"] for row in district_summaries)

        ready_districts = [row for row in district_summaries if row["district_status"] == "READY_FOR_SEPARATE_APPLY"]
        manual_districts = [row for row in district_summaries if row["district_status"] == "NEEDS_ADMIN_REVIEW"]
        blocked_districts = [row for row in district_summaries if row["district_status"] == "BLOCKED"]
        already_promoted_districts = [row for row in district_summaries if row["district_status"] == "ALREADY_FULLY_PROMOTED"]

        result = {
            "schema_version": "core_lgd_state_activation_readiness.v1",
            "mode": "READ_ONLY_STATE_ACTIVATION_READINESS",
            "db_writes_made": False,
            "external_calls_made": False,
            "filters": {
                "state_lgd_code": state_lgd_code,
                "min_overlap_percent": str(min_overlap),
                "include_general": args.include_general,
            },
            "counts": {
                "rows": len(rows),
                "districts": len(district_summaries),
                "ready_districts": len(ready_districts),
                "manual_review_districts": len(manual_districts),
                "blocked_districts": len(blocked_districts),
                "already_promoted_districts": len(already_promoted_districts),
            },
            "row_status_counts": dict(status_counts),
            "district_status_counts": dict(district_status_counts),
            "samples": {
                "ready_for_separate_apply": ready_districts[:10],
                "needs_admin_review": manual_districts[:10],
                "blocked": blocked_districts[:10],
                "already_promoted": already_promoted_districts[:10],
            },
            "readiness": {
                "safe_read_only": True,
                "has_ready_districts": bool(ready_districts),
                "activation_requires_separate_apply": True,
                "android_maestro_required_after_apply": True,
            },
            "output_files": {
                "json": str(out_json),
                "csv": str(out_csv),
            },
        }

        out_json.write_text(json.dumps(result, indent=2, sort_keys=True, default=str))

        import csv
        with out_csv.open("w", newline="") as fh:
            fieldnames = [
                "state_lgd_code",
                "state_name",
                "district_lgd_code",
                "district_name",
                "district_status",
                "row_count",
                "systems_present",
                "has_all_core_systems",
                "status_counts",
                "active_fallback_count",
                "min_overlap_percent",
            ]
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for row in district_summaries:
                writable = dict(row)
                writable["systems_present"] = json.dumps(writable["systems_present"])
                writable["status_counts"] = json.dumps(writable["status_counts"], sort_keys=True)
                writable["min_overlap_percent"] = as_jsonable(writable["min_overlap_percent"])
                writer.writerow(writable)

        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

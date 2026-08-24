#!/usr/bin/env python3
"""Read-only inspection report for inactive NWDP boundary runtime pilot rows."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DEFAULT_OUTPUT = Path("/tmp/nwdp-boundary-runtime-pilot-inspection.json")
RUNTIME_TABLES = [
    "geography_boundary_runtime_sets",
    "geography_boundary_runtime_features",
    "geography_boundary_runtime_crosswalks",
    "geography_boundary_runtime_promotion_events",
]


def db_url_from_settings() -> str:
    from app.core.config import settings

    value = (
        getattr(settings, "database_url", None)
        or getattr(settings, "DATABASE_URL", None)
        or getattr(settings, "sqlalchemy_database_uri", None)
        or getattr(settings, "SQLALCHEMY_DATABASE_URI", None)
        or getattr(settings, "postgres_url", None)
        or getattr(settings, "POSTGRES_URL", None)
    )
    return str(value or "postgresql+psycopg2://agri_os:agri_os_dev@localhost:5432/agri_os")


def inspect_runtime(conn, limit: int) -> dict[str, Any]:
    runtime_counts = {
        table: int(conn.execute(text(f"select count(*) from {table}")).scalar() or 0)
        for table in RUNTIME_TABLES
    }
    runtime_active_counts = {
        table: int(conn.execute(text(f"select count(*) from {table} where is_active = true")).scalar() or 0)
        for table in RUNTIME_TABLES
    }
    runtime_sets = [dict(row) for row in conn.execute(text("""
        select id::text as runtime_set_id, status, activation_status, is_active,
               source_system, state_or_ut, source_format
        from geography_boundary_runtime_sets
        order by created_at, id
    """)).mappings().all()]
    promotion_events = [dict(row) for row in conn.execute(text("""
        select id::text as promotion_event_id, runtime_set_id::text,
               source_import_batch_id::text, promotion_mode, promotion_status,
               is_active, candidate_count, runtime_feature_count,
               runtime_crosswalk_count, promoted_by
        from geography_boundary_runtime_promotion_events
        order by created_at, id
    """)).mappings().all()]
    crosswalks = [dict(row) for row in conn.execute(text("""
        select
          rw.id::text as runtime_crosswalk_id,
          rw.runtime_set_id::text,
          rw.runtime_feature_id::text,
          rw.source_candidate_id::text as candidate_id,
          rw.runtime_scope,
          rw.village_id::text,
          rw.village_lgd_code,
          rw.confidence,
          rw.reviewer_decision,
          rw.is_active as runtime_crosswalk_active,
          rf.is_active as runtime_feature_active,
          rf.geometry_validation_status,
          rf.geometry_hash,
          rf.bbox_wgs84,
          rf.centroid_wgs84,
          c.source_feature_index,
          c.review_status,
          c.promotion_status,
          c.is_active as staging_candidate_active,
          f.source_district_name,
          f.source_subdistrict_name,
          f.source_block_name,
          f.source_village_name,
          f.source_vlcode
        from geography_boundary_runtime_crosswalks rw
        join geography_boundary_runtime_features rf on rf.id = rw.runtime_feature_id
        join geography_boundary_crosswalk_candidates c on c.id = rw.source_candidate_id
        join geography_boundary_source_features f on f.id = c.source_feature_id
        order by c.source_feature_index
        limit :limit
    """), {"limit": limit}).mappings().all()]
    staging_guardrails = dict(conn.execute(text("""
        select
          count(*) as linked_candidate_count,
          sum(case when c.is_active = false then 1 else 0 end) as inactive_count,
          sum(case when c.promotion_status = 'NOT_PROMOTED' then 1 else 0 end) as not_promoted_count,
          sum(case when c.review_status = 'APPROVED_FOR_PROMOTION' then 1 else 0 end) as approved_count,
          sum(case when c.reviewer_decision = 'ACCEPT_DIRECT_CODE_MATCH' then 1 else 0 end) as accepted_direct_count
        from geography_boundary_runtime_crosswalks rw
        join geography_boundary_crosswalk_candidates c on c.id = rw.source_candidate_id
    """)).mappings().one())

    return {
        "runtime_counts": runtime_counts,
        "runtime_active_counts": runtime_active_counts,
        "runtime_sets": runtime_sets,
        "promotion_events": promotion_events,
        "staging_guardrails": staging_guardrails,
        "crosswalks": crosswalks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()

    engine = create_engine(db_url_from_settings())
    with engine.connect() as conn:
        inspection = inspect_runtime(conn, args.limit)

    expected_counts = {
        "geography_boundary_runtime_sets": 1,
        "geography_boundary_runtime_features": 10,
        "geography_boundary_runtime_crosswalks": 10,
        "geography_boundary_runtime_promotion_events": 1,
    }
    healthy = (
        inspection["runtime_counts"] == expected_counts
        and all(value == 0 for value in inspection["runtime_active_counts"].values())
        and inspection["staging_guardrails"] == {
            "linked_candidate_count": 10,
            "inactive_count": 10,
            "not_promoted_count": 10,
            "approved_count": 10,
            "accepted_direct_count": 10,
        }
    )

    report = {
        "schema_version": "nwdp_boundary_runtime_pilot_inspection.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": healthy,
        "mode": "READ_ONLY_RUNTIME_PILOT_INSPECTION",
        "db_writes_attempted": False,
        "runtime_tables_written": False,
        "runtime_spatial_matching_changed": False,
        "android_behavior_changed": False,
        "inspection": inspection,
        "readiness": {
            "runtime_rows_available_for_review": inspection["runtime_counts"] == expected_counts,
            "runtime_rows_active": any(value > 0 for value in inspection["runtime_active_counts"].values()),
            "ready_for_runtime_spatial_matching": False,
            "android_behavior_changed": False,
            "lookup_api_enabled": False,
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())

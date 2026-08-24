#!/usr/bin/env python3
"""Read-only activation planner for inactive NWDP boundary runtime pilot rows."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DEFAULT_OUTPUT = Path("/tmp/nwdp-boundary-runtime-activation-plan.json")
RUNTIME_TABLES = [
    "geography_boundary_runtime_sets",
    "geography_boundary_runtime_features",
    "geography_boundary_runtime_crosswalks",
    "geography_boundary_runtime_promotion_events",
]
EXPECTED_COUNTS = {
    "geography_boundary_runtime_sets": 1,
    "geography_boundary_runtime_features": 10,
    "geography_boundary_runtime_crosswalks": 10,
    "geography_boundary_runtime_promotion_events": 1,
}


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


def runtime_counts(conn, active_only: bool = False) -> dict[str, int]:
    suffix = " where is_active = true" if active_only else ""
    return {
        table: int(conn.execute(text(f"select count(*) from {table}{suffix}")).scalar() or 0)
        for table in RUNTIME_TABLES
    }


def activation_plan(conn) -> dict:
    counts = runtime_counts(conn)
    active_counts = runtime_counts(conn, active_only=True)

    runtime_set_rows = [dict(row) for row in conn.execute(text("""
        select id::text as runtime_set_id, status, activation_status, is_active,
               source_system, state_or_ut, source_format, activated_at
        from geography_boundary_runtime_sets
        order by created_at, id
    """)).mappings().all()]

    feature_guardrails = dict(conn.execute(text("""
        select
          count(*) as feature_count,
          sum(case when is_active = false then 1 else 0 end) as inactive_count,
          sum(case when geometry_validation_status = 'VALIDATED' then 1 else 0 end) as validated_count,
          sum(case when geometry_hash is not null then 1 else 0 end) as hash_count,
          sum(case when bbox_wgs84 <> '[]'::jsonb then 1 else 0 end) as bbox_count,
          sum(case when centroid_wgs84 <> '{}'::jsonb then 1 else 0 end) as centroid_count
        from geography_boundary_runtime_features
    """)).mappings().one())

    crosswalk_guardrails = dict(conn.execute(text("""
        select
          count(*) as crosswalk_count,
          sum(case when rw.is_active = false then 1 else 0 end) as inactive_count,
          sum(case when rw.runtime_scope in ('village', 'village_review') then 1 else 0 end) as village_scope_count,
          sum(case when rw.village_id is not null then 1 else 0 end) as village_id_count,
          sum(case when rw.village_lgd_code is not null then 1 else 0 end) as village_lgd_count,
          sum(case when c.is_active = false then 1 else 0 end) as staging_inactive_count,
          sum(case when c.promotion_status = 'NOT_PROMOTED' then 1 else 0 end) as staging_not_promoted_count,
          sum(case when c.review_status = 'APPROVED_FOR_PROMOTION' then 1 else 0 end) as staging_approved_count,
          sum(case when c.reviewer_decision = 'ACCEPT_DIRECT_CODE_MATCH' then 1 else 0 end) as staging_accepted_direct_count
        from geography_boundary_runtime_crosswalks rw
        join geography_boundary_crosswalk_candidates c on c.id = rw.source_candidate_id
    """)).mappings().one())

    promotion_event_guardrails = dict(conn.execute(text("""
        select
          count(*) as event_count,
          sum(case when is_active = false then 1 else 0 end) as inactive_count,
          sum(case when promotion_mode = 'TINY_PILOT_REVIEWED_BATCH' then 1 else 0 end) as tiny_pilot_mode_count,
          sum(case when promotion_status = 'APPLIED' then 1 else 0 end) as applied_count,
          sum(candidate_count) as candidate_count,
          sum(runtime_feature_count) as runtime_feature_count,
          sum(runtime_crosswalk_count) as runtime_crosswalk_count
        from geography_boundary_runtime_promotion_events
    """)).mappings().one())

    preconditions = {
        "runtime_row_shape_matches_tiny_pilot": counts == EXPECTED_COUNTS,
        "runtime_rows_all_inactive": all(value == 0 for value in active_counts.values()),
        "single_inactive_runtime_set": len(runtime_set_rows) == 1 and runtime_set_rows[0]["activation_status"] == "INACTIVE" and runtime_set_rows[0]["is_active"] is False,
        "runtime_features_validated": feature_guardrails == {
            "feature_count": 10,
            "inactive_count": 10,
            "validated_count": 10,
            "hash_count": 10,
            "bbox_count": 10,
            "centroid_count": 10,
        },
        "runtime_crosswalks_link_valid_staging": crosswalk_guardrails == {
            "crosswalk_count": 10,
            "inactive_count": 10,
            "village_scope_count": 10,
            "village_id_count": 10,
            "village_lgd_count": 10,
            "staging_inactive_count": 10,
            "staging_not_promoted_count": 10,
            "staging_approved_count": 10,
            "staging_accepted_direct_count": 10,
        },
        "promotion_event_audit_shape_valid": promotion_event_guardrails == {
            "event_count": 1,
            "inactive_count": 1,
            "tiny_pilot_mode_count": 1,
            "applied_count": 1,
            "candidate_count": 10,
            "runtime_feature_count": 10,
            "runtime_crosswalk_count": 10,
        },
    }

    planned_activation_diff = {
        "geography_boundary_runtime_sets": {"activate_count": 1, "set_activation_status_to": "ACTIVE"},
        "geography_boundary_runtime_features": {"activate_count": 10},
        "geography_boundary_runtime_crosswalks": {"activate_count": 10},
        "geography_boundary_runtime_promotion_events": {"activate_count": 0, "reason": "promotion event remains immutable audit evidence"},
        "staging_candidates": {"activate_count": 0, "promote_count": 0},
        "android_behavior": {"changed": False},
        "lookup_api": {"enabled": False},
    }

    rollback_plan = {
        "required_before_apply": True,
        "minimum_shape": [
            "set runtime set activation_status back to INACTIVE or forward to SUPERSEDED",
            "set runtime set/features/crosswalks is_active=false",
            "preserve promotion event and audit metadata",
            "do not delete runtime rows during rollback",
            "do not mutate source features or staged candidates",
        ],
    }

    return {
        "runtime_counts": counts,
        "runtime_active_counts": active_counts,
        "runtime_sets": runtime_set_rows,
        "feature_guardrails": feature_guardrails,
        "crosswalk_guardrails": crosswalk_guardrails,
        "promotion_event_guardrails": promotion_event_guardrails,
        "preconditions": preconditions,
        "planned_activation_diff": planned_activation_diff,
        "rollback_plan": rollback_plan,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    engine = create_engine(db_url_from_settings())
    with engine.connect() as conn:
        plan = activation_plan(conn)

    healthy = all(plan["preconditions"].values())
    report = {
        "schema_version": "nwdp_boundary_runtime_activation_plan.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": healthy,
        "mode": "READ_ONLY_ACTIVATION_DRY_RUN",
        "activation_applied": False,
        "db_writes_attempted": False,
        "runtime_tables_written": False,
        "runtime_spatial_matching_changed": False,
        "android_behavior_changed": False,
        "lookup_api_enabled": False,
        "plan": plan,
        "readiness": {
            "ready_for_activation_apply": healthy,
            "activation_requires_separate_checkpoint": True,
            "rollback_policy_required_before_apply": True,
            "ready_for_runtime_spatial_matching": False,
            "android_behavior_changed": False,
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())

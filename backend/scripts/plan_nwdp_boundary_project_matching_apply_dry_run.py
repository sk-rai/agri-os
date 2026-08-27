#!/usr/bin/env python3
"""Dry-run-only plan for guarded NWDP boundary project matching apply.

This script does not apply project matching. It only reports what a future
project-scoped apply would be allowed to consider.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings


def db_url_from_settings() -> str:
    return str(
        getattr(settings, "database_url", None)
        or getattr(settings, "DATABASE_URL", None)
        or getattr(settings, "sqlalchemy_database_uri", None)
        or getattr(settings, "SQLALCHEMY_DATABASE_URI", None)
        or getattr(settings, "postgres_url", None)
        or getattr(settings, "POSTGRES_URL", None)
    )


def json_default(value: Any) -> str:
    return str(value)


PROJECT_VILLAGES_SQL = """
    select e.project_id, f.village_id
    from farmer_project_enrollments e
    join farmers f on f.id = e.farmer_id
    where e.is_active = true
      and f.is_active = true
      and f.village_id is not null
      and e.project_id = :project_id

    union

    select f.project_id, f.village_id
    from farmers f
    where f.is_active = true
      and f.project_id = :project_id
      and f.village_id is not null

    union

    select p.project_id, p.village_id
    from parcels p
    where p.is_active = true
      and p.project_id = :project_id
      and p.village_id is not null

    union

    select e.project_id, p.village_id
    from farmer_project_enrollments e
    join parcels p on p.farmer_id = e.farmer_id
    where e.is_active = true
      and p.is_active = true
      and e.project_id = :project_id
      and p.village_id is not null
"""


def choose_project_id(conn) -> str | None:
    row = conn.execute(text("""
        select p.id::text as project_id
        from projects p
        where p.is_active = true
        order by p.created_at desc
        limit 1
    """)).mappings().first()
    return row["project_id"] if row else None


def build_plan(project_id: str | None, limit: int) -> dict[str, Any]:
    engine = create_engine(db_url_from_settings())

    with engine.connect() as conn:
        selected_project_id = project_id or choose_project_id(conn)
        if not selected_project_id:
            return {
                "schema_version": "nwdp_boundary_project_matching_apply_dry_run.v1",
                "mode": "DRY_RUN_ONLY_PROJECT_MATCHING_APPLY_PLAN",
                "healthy": False,
                "error": "NO_ACTIVE_PROJECT_FOUND",
                "guardrails": {
                    "db_writes_attempted": False,
                    "runtime_tables_written": False,
                    "candidate_activation_changed": False,
                    "candidate_promotion_changed": False,
                    "runtime_spatial_matching_changed": False,
                    "lookup_api_enabled": False,
                    "android_behavior_changed": False,
                },
            }

        project = conn.execute(text("""
            select id::text as project_id, tenant_id, name, status, geography_scope
            from projects
            where id = :project_id
        """), {"project_id": selected_project_id}).mappings().first()

        if not project:
            return {
                "schema_version": "nwdp_boundary_project_matching_apply_dry_run.v1",
                "mode": "DRY_RUN_ONLY_PROJECT_MATCHING_APPLY_PLAN",
                "healthy": False,
                "error": "PROJECT_NOT_FOUND",
                "project_id": selected_project_id,
                "guardrails": {
                    "db_writes_attempted": False,
                    "runtime_tables_written": False,
                    "candidate_activation_changed": False,
                    "candidate_promotion_changed": False,
                    "runtime_spatial_matching_changed": False,
                    "lookup_api_enabled": False,
                    "android_behavior_changed": False,
                },
            }

        summary = conn.execute(text(f"""
            with project_villages as (
                {PROJECT_VILLAGES_SQL}
            ),
            eligible as (
                select
                  c.id,
                  c.proposed_village_id
                from geography_boundary_import_batches b
                join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
                where b.source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
                  and c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
                  and c.review_status = 'AUTO_CANDIDATE'
                  and c.is_active = false
                  and c.promotion_status = 'NOT_PROMOTED'
                  and c.proposed_village_id is not null
            ),
            excluded as (
                select
                  c.id,
                  c.proposed_village_id,
                  c.candidate_bucket,
                  c.review_status
                from geography_boundary_import_batches b
                join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
                where b.source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
                  and c.proposed_village_id is not null
                  and c.is_active = false
                  and c.promotion_status = 'NOT_PROMOTED'
            )
            select
              count(distinct pv.village_id)::bigint as project_village_count,
              count(distinct eligible.proposed_village_id)::bigint as villages_with_eligible_boundary,
              count(distinct eligible.id)::bigint as dry_run_candidate_selection_count,
              count(distinct excluded.id) filter (where excluded.review_status = 'MANUAL_REVIEW')::bigint as manual_review_excluded_count,
              count(distinct excluded.id) filter (where excluded.review_status = 'BLOCKED')::bigint as blocked_excluded_count,
              count(distinct excluded.id) filter (where excluded.candidate_bucket <> 'DIRECT_VLCODE_MATCH')::bigint as non_direct_bucket_excluded_count
            from project_villages pv
            left join eligible on eligible.proposed_village_id = pv.village_id
            left join excluded on excluded.proposed_village_id = pv.village_id
        """), {"project_id": selected_project_id}).mappings().one()

        selected = conn.execute(text(f"""
            with project_villages as (
                {PROJECT_VILLAGES_SQL}
            )
            select
              b.state_or_ut,
              c.id::text as candidate_id,
              c.proposed_village_id::text,
              c.proposed_village_lgd_code,
              c.source_feature_index,
              c.candidate_bucket,
              c.review_status,
              c.promotion_status,
              f.source_vlcode,
              f.source_district_name,
              f.source_subdistrict_name,
              f.source_village_name
            from project_villages pv
            join geography_boundary_crosswalk_candidates c on c.proposed_village_id = pv.village_id
            join geography_boundary_import_batches b on b.id = c.import_batch_id
            join geography_boundary_source_features f on f.id = c.source_feature_id
            where b.source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
              and c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
              and c.review_status = 'AUTO_CANDIDATE'
              and c.is_active = false
              and c.promotion_status = 'NOT_PROMOTED'
              and c.proposed_village_id is not null
            order by b.state_or_ut, f.source_feature_index
            limit :limit
        """), {"project_id": selected_project_id, "limit": limit}).mappings().all()

    summary_dict = dict(summary)
    return {
        "schema_version": "nwdp_boundary_project_matching_apply_dry_run.v1",
        "mode": "DRY_RUN_ONLY_PROJECT_MATCHING_APPLY_PLAN",
        "healthy": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": dict(project),
        "candidate_selection_policy": {
            "source_system": "NWDP_GSI_VILLAGE_BOUNDARY",
            "candidate_bucket": "DIRECT_VLCODE_MATCH",
            "review_status": "AUTO_CANDIDATE",
            "required_is_active": False,
            "required_promotion_status": "NOT_PROMOTED",
            "requires_project_scope": True,
            "requires_proposed_village_id": True,
            "manual_review_candidates_excluded": True,
            "blocked_candidates_excluded": True,
            "non_direct_candidates_excluded": True,
        },
        "summary": {
            **summary_dict,
            "apply_would_write_project_matching_records": False,
            "apply_is_implemented": False,
            "rollback_policy_required_before_apply": True,
            "admin_confirmation_required_before_apply": True,
            "feature_flag_required_before_apply": True,
        },
        "selected_candidate_samples": [dict(row) for row in selected],
        "guardrails": {
            "db_writes_attempted": False,
            "runtime_tables_written": False,
            "candidate_activation_changed": False,
            "candidate_promotion_changed": False,
            "runtime_spatial_matching_changed": False,
            "lookup_api_enabled": False,
            "android_behavior_changed": False,
        },
        "readiness": {
            "ready_for_project_matching_apply_design_review": True,
            "ready_for_project_matching_apply": False,
            "ready_for_runtime_spatial_matching": False,
            "ready_for_lookup_api_enablement": False,
            "ready_for_android_behavior_change": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run-only NWDP project matching apply plan.")
    parser.add_argument("--project-id", default="")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--output", default="/tmp/nwdp-boundary-project-matching-apply-dry-run.json")
    args = parser.parse_args()

    result = build_plan(args.project_id or None, args.limit)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True, default=json_default) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True, default=json_default))
    return 0 if result.get("healthy") else 1


if __name__ == "__main__":
    raise SystemExit(main())

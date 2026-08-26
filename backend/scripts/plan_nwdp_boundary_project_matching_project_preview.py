#!/usr/bin/env python3
"""Read-only NWDP boundary project matching coverage preview.

This plans project-scoped matching coverage only. It does not activate candidates,
promote candidates, write runtime tables, enable lookup behavior, or change Android behavior.
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
    row = conn.execute(text(f"""
        with project_villages as (
            select e.project_id, f.village_id
            from farmer_project_enrollments e
            join farmers f on f.id = e.farmer_id
            where e.is_active = true and f.is_active = true and f.village_id is not null

            union

            select f.project_id, f.village_id
            from farmers f
            where f.is_active = true and f.project_id is not null and f.village_id is not null

            union

            select p.project_id, p.village_id
            from parcels p
            where p.is_active = true and p.project_id is not null and p.village_id is not null

            union

            select e.project_id, p.village_id
            from farmer_project_enrollments e
            join parcels p on p.farmer_id = e.farmer_id
            where e.is_active = true and p.is_active = true and p.village_id is not null
        )
        select p.id::text as project_id, count(distinct pv.village_id) as villages
        from projects p
        left join project_villages pv on pv.project_id = p.id
        where p.is_active = true
        group by p.id
        order by count(distinct pv.village_id) desc, p.created_at desc
        limit 1
    """)).mappings().first()
    return row["project_id"] if row else None


def build_preview(project_id: str | None, limit: int) -> dict[str, Any]:
    engine = create_engine(db_url_from_settings())
    with engine.connect() as conn:
        selected_project_id = project_id or choose_project_id(conn)
        if not selected_project_id:
            return {
                "schema_version": "nwdp_boundary_project_matching_project_preview.v1",
                "mode": "READ_ONLY_PROJECT_MATCHING_PROJECT_PREVIEW",
                "healthy": False,
                "error": "NO_ACTIVE_PROJECT_FOUND",
                "db_writes_attempted": False,
                "runtime_tables_written": False,
            }

        project = conn.execute(text("""
            select id::text as project_id, tenant_id, name, status, geography_scope
            from projects
            where id = :project_id
        """), {"project_id": selected_project_id}).mappings().first()

        if not project:
            return {
                "schema_version": "nwdp_boundary_project_matching_project_preview.v1",
                "mode": "READ_ONLY_PROJECT_MATCHING_PROJECT_PREVIEW",
                "healthy": False,
                "error": "PROJECT_NOT_FOUND",
                "project_id": selected_project_id,
                "db_writes_attempted": False,
                "runtime_tables_written": False,
            }

        totals = conn.execute(text(f"""
            with project_villages as (
                {PROJECT_VILLAGES_SQL}
            ),
            eligible as (
                select
                  c.id,
                  c.proposed_village_id,
                  c.candidate_bucket,
                  c.review_status,
                  c.promotion_status,
                  c.is_active
                from geography_boundary_import_batches b
                join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
                where b.source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
                  and c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
                  and c.review_status = 'AUTO_CANDIDATE'
                  and c.is_active = false
                  and c.promotion_status = 'NOT_PROMOTED'
                  and c.proposed_village_id is not null
            ),
            review_backlog as (
                select
                  c.id,
                  c.proposed_village_id,
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
              count(distinct pv.village_id) - count(distinct eligible.proposed_village_id) as villages_without_eligible_boundary,
              count(distinct eligible.id)::bigint as eligible_candidate_count,
              count(distinct review_backlog.id) filter (where review_backlog.review_status = 'MANUAL_REVIEW')::bigint as manual_review_candidate_count,
              count(distinct review_backlog.id) filter (where review_backlog.review_status = 'BLOCKED')::bigint as blocked_candidate_count
            from project_villages pv
            left join eligible on eligible.proposed_village_id = pv.village_id
            left join review_backlog on review_backlog.proposed_village_id = pv.village_id
        """), {"project_id": selected_project_id}).mappings().one()

        rows = conn.execute(text(f"""
            with project_villages as (
                {PROJECT_VILLAGES_SQL}
            ),
            eligible as (
                select
                  b.state_or_ut,
                  c.id::text as candidate_id,
                  c.proposed_village_id,
                  c.proposed_village_lgd_code,
                  c.source_feature_index,
                  c.candidate_bucket,
                  c.review_status,
                  c.promotion_status,
                  f.source_vlcode,
                  f.source_district_name,
                  f.source_subdistrict_name,
                  f.source_village_name
                from geography_boundary_import_batches b
                join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
                join geography_boundary_source_features f on f.id = c.source_feature_id
                where b.source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
                  and c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
                  and c.review_status = 'AUTO_CANDIDATE'
                  and c.is_active = false
                  and c.promotion_status = 'NOT_PROMOTED'
                  and c.proposed_village_id is not null
            )
            select
              pv.village_id::text,
              gv.lgd_code as village_lgd_code,
              gv.canonical_name as village_name,
              eligible.state_or_ut,
              count(eligible.candidate_id)::bigint as eligible_candidate_count,
              min(eligible.candidate_id) as sample_candidate_id,
              min(eligible.source_feature_index) as sample_source_feature_index,
              min(eligible.source_vlcode) as sample_source_vlcode,
              min(eligible.source_district_name) as sample_source_district_name,
              min(eligible.source_subdistrict_name) as sample_source_subdistrict_name,
              min(eligible.source_village_name) as sample_source_village_name
            from project_villages pv
            join geography_villages gv on gv.id = pv.village_id
            left join eligible on eligible.proposed_village_id = pv.village_id
            group by pv.village_id, gv.lgd_code, gv.canonical_name, eligible.state_or_ut
            order by eligible.state_or_ut nulls last, gv.canonical_name
            limit :limit
        """), {"project_id": selected_project_id, "limit": limit}).mappings().all()

    summary = dict(totals)
    project_village_count = int(summary.get("project_village_count") or 0)
    eligible_villages = int(summary.get("villages_with_eligible_boundary") or 0)

    return {
        "schema_version": "nwdp_boundary_project_matching_project_preview.v1",
        "mode": "READ_ONLY_PROJECT_MATCHING_PROJECT_PREVIEW",
        "healthy": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": dict(project),
        "summary": {
            **summary,
            "coverage_ratio": (eligible_villages / project_village_count) if project_village_count else 0,
            "manual_review_excluded_from_matching": True,
            "blocked_excluded_from_matching": True,
        },
        "items": [dict(row) for row in rows],
        "guardrails": {
            "db_writes_attempted": False,
            "candidate_activation_changed": False,
            "candidate_promotion_changed": False,
            "runtime_tables_written": False,
            "runtime_spatial_matching_changed": False,
            "lookup_api_enabled": False,
            "android_behavior_changed": False,
        },
        "readiness": {
            "ready_for_admin_project_matching_preview": True,
            "ready_for_project_matching_apply": False,
            "ready_for_runtime_spatial_matching": False,
            "ready_for_lookup_api_enablement": False,
            "ready_for_android_behavior_change": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only NWDP boundary project matching coverage preview.")
    parser.add_argument("--project-id", default="")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--output", default="/tmp/nwdp-boundary-project-matching-project-preview.json")
    args = parser.parse_args()

    result = build_preview(args.project_id or None, args.limit)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True, default=json_default) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True, default=json_default))
    return 0 if result.get("healthy") else 1


if __name__ == "__main__":
    raise SystemExit(main())

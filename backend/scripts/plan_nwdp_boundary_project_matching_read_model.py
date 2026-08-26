#!/usr/bin/env python3
"""Read-only NWDP boundary project matching read-model planner.

Plans the query shape for future admin/project matching over inactive DIRECT_VLCODE
staging candidates only. Does not write DB, activate candidates, promote rows,
write runtime tables, or enable lookup/Android behavior.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DEFAULT_OUTPUT = Path("/tmp/nwdp-boundary-project-matching-read-model-plan.json")


def db_url_from_settings() -> str:
    from app.core.config import settings

    return str(
        getattr(settings, "database_url", None)
        or getattr(settings, "DATABASE_URL", None)
        or getattr(settings, "sqlalchemy_database_uri", None)
        or getattr(settings, "SQLALCHEMY_DATABASE_URI", None)
        or getattr(settings, "postgres_url", None)
        or getattr(settings, "POSTGRES_URL", None)
    )


def main() -> int:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    engine = create_engine(db_url_from_settings())

    with engine.connect() as conn:
        totals = dict(conn.execute(text("""
            with eligible as (
              select
                b.state_or_ut,
                c.id,
                c.proposed_village_id,
                c.proposed_village_lgd_code
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
              select c.*
              from geography_boundary_import_batches b
              join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
              where b.source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
                and not (
                  c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
                  and c.review_status = 'AUTO_CANDIDATE'
                  and c.is_active = false
                  and c.promotion_status = 'NOT_PROMOTED'
                  and c.proposed_village_id is not null
                )
            )
            select
              (select count(*)::bigint from eligible) as eligible_rows,
              (select count(distinct proposed_village_id)::bigint from eligible) as eligible_villages,
              (select count(distinct state_or_ut)::bigint from eligible) as eligible_states,
              (select count(*) filter (where review_status = 'MANUAL_REVIEW')::bigint from excluded) as excluded_manual_review_rows,
              (select count(*) filter (where review_status = 'BLOCKED')::bigint from excluded) as excluded_blocked_rows,
              (select count(*) filter (where is_active = true)::bigint from geography_boundary_crosswalk_candidates) as active_candidates,
              (select count(*) filter (where promotion_status <> 'NOT_PROMOTED')::bigint from geography_boundary_crosswalk_candidates) as promoted_candidates
        """)).mappings().one())

        state_rows = [dict(row) for row in conn.execute(text("""
            select
              b.state_or_ut,
              count(*)::bigint as eligible_rows,
              count(distinct c.proposed_village_id)::bigint as eligible_villages
            from geography_boundary_import_batches b
            join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
            where b.source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
              and c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
              and c.review_status = 'AUTO_CANDIDATE'
              and c.is_active = false
              and c.promotion_status = 'NOT_PROMOTED'
              and c.proposed_village_id is not null
            group by b.state_or_ut
            order by b.state_or_ut
        """)).mappings().all()]

        sample_rows = [dict(row) for row in conn.execute(text("""
            select
              b.state_or_ut,
              c.id::text as candidate_id,
              c.proposed_village_id::text,
              c.proposed_village_lgd_code,
              f.source_district_name,
              f.source_subdistrict_name,
              f.source_block_name,
              f.source_village_name,
              f.source_vlcode
            from geography_boundary_import_batches b
            join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
            join geography_boundary_source_features f on f.id = c.source_feature_id
            where b.source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
              and c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
              and c.review_status = 'AUTO_CANDIDATE'
              and c.is_active = false
              and c.promotion_status = 'NOT_PROMOTED'
              and c.proposed_village_id is not null
            order by b.state_or_ut, f.source_feature_index
            limit 25
        """)).mappings().all()]

    totals = {key: int(value or 0) for key, value in totals.items()}
    state_rows = [
        {
            "state_or_ut": row["state_or_ut"],
            "eligible_rows": int(row["eligible_rows"] or 0),
            "eligible_villages": int(row["eligible_villages"] or 0),
        }
        for row in state_rows
    ]

    healthy = (
        totals["eligible_rows"] > 0
        and totals["eligible_villages"] > 0
        and totals["active_candidates"] == 0
        and totals["promoted_candidates"] == 0
    )

    result = {
        "schema_version": "nwdp_boundary_project_matching_read_model_plan.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "READ_ONLY_PROJECT_MATCHING_READ_MODEL_PLAN",
        "healthy": healthy,
        "claim_boundary": "Planning only. This read model would expose inactive direct-code staging candidates for admin/project matching review. It does not activate candidates, promote rows, write runtime geometry, enable point-in-polygon matching, change lookup behavior, or change Android behavior.",
        "read_model_contract": {
            "endpoint_candidate": "/api/v1/master-data/geography/nwdp-boundary-project-matching/eligible-candidates",
            "required_filters": ["state_or_ut or village_id/project geography scope"],
            "eligible_predicate": "DIRECT_VLCODE_MATCH + AUTO_CANDIDATE + inactive + NOT_PROMOTED + proposed_village_id present",
            "excluded_predicates": ["MANUAL_REVIEW", "BLOCKED", "parent mismatch", "special reference features", "active/promoted rows"],
            "default_limit": 100,
            "max_limit": 1000,
        },
        "totals": totals,
        "state_summaries": state_rows,
        "samples": sample_rows,
        "planned_diff": {
            "db_writes": 0,
            "candidate_activations": 0,
            "candidate_promotions": 0,
            "runtime_table_writes": 0,
            "lookup_api_enabled": False,
            "android_behavior_changed": False,
        },
        "guardrails": {
            "db_writes_attempted": False,
            "runtime_tables_written": False,
            "runtime_spatial_matching_changed": False,
            "lookup_api_enabled": False,
            "android_behavior_changed": False,
            "manual_review_excluded": True,
            "blocked_excluded": True,
        },
        "readiness": {
            "ready_for_read_only_endpoint": healthy,
            "ready_for_project_matching_apply": False,
            "ready_for_runtime_spatial_matching": False,
            "requires_separate_apply_checkpoint": True,
        },
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())

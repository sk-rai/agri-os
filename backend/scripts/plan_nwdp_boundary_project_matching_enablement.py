#!/usr/bin/env python3
"""Read-only NWDP boundary project matching enablement planner.

Plans how inactive staged NWDP boundary matches could later be made available to
admin/project matching. This does not activate candidates, promote candidates,
write runtime tables, enable lookup behavior, or change Android behavior.
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

DEFAULT_OUTPUT = Path("/tmp/nwdp-boundary-project-matching-enablement-plan.json")


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
    return str(value)


def main() -> int:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    engine = create_engine(db_url_from_settings())

    with engine.connect() as conn:
        totals = dict(conn.execute(text("""
            with candidate_scope as (
              select c.*
              from geography_boundary_import_batches b
              join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
              where b.source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
            )
            select
              count(*)::bigint as candidates,
              count(*) filter (
                where candidate_bucket = 'DIRECT_VLCODE_MATCH'
                  and review_status = 'AUTO_CANDIDATE'
                  and is_active = false
                  and promotion_status = 'NOT_PROMOTED'
                  and proposed_village_id is not null
              )::bigint as eligible_direct_match_candidates,
              count(*) filter (
                where review_status = 'MANUAL_REVIEW'
                  and is_active = false
                  and promotion_status = 'NOT_PROMOTED'
              )::bigint as manual_review_candidates,
              count(*) filter (
                where review_status = 'BLOCKED'
                  and is_active = false
                  and promotion_status = 'NOT_PROMOTED'
              )::bigint as blocked_candidates,
              count(*) filter (where is_active = true)::bigint as active_candidates,
              count(*) filter (where promotion_status <> 'NOT_PROMOTED')::bigint as promoted_candidates
            from candidate_scope
        """)).mappings().one())

        state_rows = [dict(row) for row in conn.execute(text("""
            select
              b.state_or_ut,
              count(*) filter (
                where c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
                  and c.review_status = 'AUTO_CANDIDATE'
                  and c.is_active = false
                  and c.promotion_status = 'NOT_PROMOTED'
                  and c.proposed_village_id is not null
              )::bigint as eligible_direct_match_candidates,
              count(*) filter (
                where c.review_status = 'MANUAL_REVIEW'
                  and c.is_active = false
                  and c.promotion_status = 'NOT_PROMOTED'
              )::bigint as manual_review_candidates,
              count(*) filter (
                where c.review_status = 'BLOCKED'
                  and c.is_active = false
                  and c.promotion_status = 'NOT_PROMOTED'
              )::bigint as blocked_candidates
            from geography_boundary_import_batches b
            join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
            where b.source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
            group by b.state_or_ut
            order by b.state_or_ut
        """)).mappings().all()]

    totals = {k: int(v or 0) for k, v in totals.items()}
    state_rows = [{k: (int(v) if k.endswith("_candidates") else v) for k, v in row.items()} for row in state_rows]

    healthy = (
        totals["candidates"] == 654285
        and totals["eligible_direct_match_candidates"] > 0
        and totals["active_candidates"] == 0
        and totals["promoted_candidates"] == 0
    )

    result = {
        "schema_version": "nwdp_boundary_project_matching_enablement_plan.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "READ_ONLY_PROJECT_MATCHING_ENABLEMENT_PLAN",
        "healthy": healthy,
        "claim_boundary": "Planning only. This does not activate staging candidates, promote candidates, materialize runtime geometry, enable lookup behavior, enable point-in-polygon matching, or change Android behavior.",
        "totals": totals,
        "state_summaries": state_rows,
        "eligibility_policy": {
            "eligible_initial_scope": "DIRECT_VLCODE_MATCH + AUTO_CANDIDATE + NOT_PROMOTED + inactive + proposed_village_id present",
            "manual_review_excluded": True,
            "blocked_excluded": True,
            "parent_mismatch_excluded_until_review": True,
            "special_reference_features_excluded": True,
            "runtime_geometry_required_before_point_in_polygon": True,
        },
        "planned_enablement_diff": {
            "admin_project_matching_read_model": {
                "eligible_candidate_count": totals["eligible_direct_match_candidates"],
                "can_be_designed_next": True,
            },
            "manual_review_queue": {
                "kept_unresolved_count": totals["manual_review_candidates"],
                "enabled_for_application_behavior": False,
            },
            "blocked_queue": {
                "kept_excluded_count": totals["blocked_candidates"],
                "enabled_for_application_behavior": False,
            },
            "runtime_tables": {
                "write_count": 0,
                "enabled": False,
            },
            "lookup_api": {
                "enabled": False,
            },
            "android_behavior": {
                "changed": False,
            },
        },
        "guardrails": {
            "db_writes_attempted": False,
            "runtime_tables_written": False,
            "runtime_spatial_matching_changed": False,
            "lookup_api_enabled": False,
            "android_behavior_changed": False,
            "candidate_activation_allowed": False,
            "candidate_promotion_allowed": False,
        },
        "rollback_or_kill_switch_shape": {
            "required_before_apply": True,
            "minimum_shape": [
                "feature flag for admin/project matching read model defaults off",
                "state-level enablement switch defaults off",
                "project-level use must be reversible without mutating staging rows",
                "manual review and blocked candidates remain excluded",
                "runtime table activation requires separate promotion checkpoint",
            ],
        },
        "readiness": {
            "ready_for_admin_project_matching_read_model_design": healthy,
            "ready_for_runtime_spatial_matching": False,
            "ready_for_lookup_api_enablement": False,
            "ready_for_android_behavior_change": False,
            "requires_separate_apply_checkpoint": True,
        },
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())

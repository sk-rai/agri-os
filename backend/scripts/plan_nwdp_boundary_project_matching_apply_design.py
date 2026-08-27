#!/usr/bin/env python3
"""Read-only design plan for future NWDP project matching apply."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def build_plan() -> dict:
    return {
        "schema_version": "nwdp_boundary_project_matching_apply_design_plan.v1",
        "mode": "READ_ONLY_PROJECT_MATCHING_APPLY_DESIGN_PLAN",
        "healthy": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "claim_boundary": (
            "Design contract only. This plan proposes the guarded write target, "
            "rollback policy, and verification gates for future project matching apply. "
            "It does not write project matching records, activate candidates, promote "
            "candidates, write runtime tables, enable lookup APIs, or change Android behavior."
        ),
        "proposed_write_target": {
            "table": "geography_boundary_project_matches",
            "purpose": "Project-scoped linkage from a project village to one reviewed NWDP boundary candidate.",
            "required_columns": [
                "id",
                "tenant_id",
                "project_id",
                "village_id",
                "boundary_candidate_id",
                "source_system",
                "match_source",
                "match_status",
                "applied_by",
                "applied_at",
                "rollback_token",
                "metadata",
                "created_at",
                "updated_at",
                "version",
                "is_active",
            ],
            "required_unique_constraints": [
                "one active NWDP boundary project match per project_id + village_id + source_system"
            ],
            "required_foreign_keys": [
                "project_id -> projects.id",
                "village_id -> geography_villages.id",
                "boundary_candidate_id -> geography_boundary_crosswalk_candidates.id",
            ],
        },
        "candidate_selection_policy": {
            "source_system": "NWDP_GSI_VILLAGE_BOUNDARY",
            "candidate_bucket": "DIRECT_VLCODE_MATCH",
            "review_status": "AUTO_CANDIDATE",
            "required_is_active": False,
            "required_promotion_status": "NOT_PROMOTED",
            "requires_proposed_village_id": True,
            "requires_project_scope": True,
            "manual_review_candidates_excluded": True,
            "blocked_candidates_excluded": True,
            "non_direct_candidates_excluded": True,
        },
        "apply_gates": {
            "apply_implemented": False,
            "feature_flag_required": True,
            "admin_confirmation_required": True,
            "project_scope_required": True,
            "dry_run_required_immediately_before_apply": True,
            "rollback_token_required": True,
            "post_apply_verification_required": True,
        },
        "rollback_policy": {
            "required_before_apply": True,
            "rollback_unit": "rollback_token",
            "rollback_action": "deactivate project match rows created by the apply token",
            "must_not_delete_staging_candidates": True,
            "must_not_mutate_runtime_tables": True,
            "must_not_mutate_android_behavior": True,
            "must_not_promote_candidates": True,
        },
        "post_apply_verification": {
            "verify_project_match_rows_created": True,
            "verify_only_selected_project_scope_changed": True,
            "verify_candidate_activation_changed": False,
            "verify_candidate_promotion_changed": False,
            "verify_runtime_tables_written": False,
            "verify_runtime_spatial_matching_changed": False,
            "verify_lookup_api_enabled": False,
            "verify_android_behavior_changed": False,
        },
        "guardrails": {
            "db_writes_attempted": False,
            "project_matching_records_written": False,
            "candidate_activation_changed": False,
            "candidate_promotion_changed": False,
            "runtime_tables_written": False,
            "runtime_spatial_matching_changed": False,
            "lookup_api_enabled": False,
            "android_behavior_changed": False,
        },
        "readiness": {
            "ready_for_apply_design_review": True,
            "ready_for_project_matching_apply": False,
            "ready_for_runtime_spatial_matching": False,
            "ready_for_lookup_api_enablement": False,
            "ready_for_android_behavior_change": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("/tmp/nwdp-boundary-project-matching-apply-design-plan.json"))
    args = parser.parse_args()

    plan = build_plan()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "healthy": plan["healthy"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Plan-only checkpoint for one-state inactive NWDP demographic profile apply.

This script defines the guarded apply contract. It does not insert rows.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_OUTPUT = Path("/tmp/nwdp-demographic-one-state-inactive-apply-plan.json")


def build_plan(state_or_ut: str | None, output: Path) -> dict:
    state_scope_present = bool(state_or_ut and state_or_ut.strip())

    return {
        "schema_version": "nwdp_demographic_one_state_inactive_apply_plan.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": state_scope_present,
        "mode": "PLAN_ONLY_ONE_STATE_INACTIVE_PROFILE_APPLY",
        "target_table": "geography_village_demographic_profiles",
        "state_or_ut": state_or_ut,
        "claim_boundary": (
            "This is a plan-only checkpoint for future one-state inactive NWDP "
            "demographic profile import. It does not insert rows, promote rows, "
            "enable lookup, change Android behavior, or claim official Census import."
        ),
        "error": None if state_scope_present else "NWDP_DEMOGRAPHIC_ONE_STATE_APPLY_PLAN_REQUIRES_STATE_SCOPE",
        "selection_policy": {
            "source_system": "NWDP_GSI_VILLAGE_BOUNDARY",
            "source_version": "20260824T110250Z",
            "state_scope_required": True,
            "all_state_apply_allowed": False,
            "candidate_bucket_required": "DIRECT_VLCODE_MATCH",
            "candidate_review_status_required": "AUTO_CANDIDATE",
            "candidate_promotion_status_required": "NOT_PROMOTED",
            "candidate_proposed_village_id_required": True,
            "raw_feature_required": True,
        },
        "insert_policy": {
            "profile_review_status": "AUTO_CANDIDATE",
            "profile_promotion_status": "NOT_PROMOTED",
            "profile_is_active": False,
            "insert_scope": "inactive demographic profile rows only",
            "runtime_table_write_allowed": False,
            "candidate_activation_allowed": False,
            "candidate_promotion_allowed": False,
        },
        "idempotency_policy": {
            "primary_dedupe_key": [
                "source_system",
                "source_version",
                "source_feature_id",
            ],
            "active_promoted_uniqueness_key": [
                "village_id",
                "source_system",
                "source_version",
            ],
            "skip_existing_source_feature": True,
            "do_not_update_existing_profiles": True,
            "do_not_delete_existing_profiles": True,
        },
        "planned_output_shape": {
            "planned_insert_count": 0,
            "skipped_existing_count": 0,
            "missing_raw_feature_count": 0,
            "state_district_summary": [],
            "review_status_counts": {
                "AUTO_CANDIDATE": 0,
                "MANUAL_REVIEW": 0,
                "APPROVED_FOR_PROMOTION": 0,
                "BLOCKED": 0,
                "REJECTED": 0,
            },
            "promotion_status_counts": {
                "NOT_PROMOTED": 0,
                "PROMOTED": 0,
            },
            "sample_rows": [],
        },
        "guardrails": {
            "db_writes_attempted": False,
            "demographic_profile_rows_written": False,
            "profiles_promoted": False,
            "lgd_geography_overwritten": False,
            "official_census_claimed_imported": False,
            "nwdp_candidates_activated": False,
            "nwdp_candidates_promoted": False,
            "project_matching_records_written": False,
            "runtime_lookup_enabled": False,
            "android_behavior_changed": False,
        },
        "readiness": {
            "ready_for_one_state_inactive_apply_implementation": state_scope_present,
            "ready_for_demographic_profile_apply": False,
            "ready_for_runtime_lookup_enablement": False,
            "ready_for_android_behavior_change": False,
            "ready_for_official_census_import": False,
        },
        "output": str(output),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-or-ut", default=None)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    result = build_plan(args.state_or_ut, args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

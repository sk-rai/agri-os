#!/usr/bin/env python3
"""Guarded NWDP demographic profile import apply command.

Current checkpoint is intentionally disabled. It may plan from safe candidates,
but it must not insert demographic profile rows until a separate, explicit
state-scoped apply checkpoint is implemented.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_OUTPUT = Path("/tmp/nwdp-demographic-profile-import-apply-disabled.json")


def build_disabled_result(state_or_ut: str | None, output: Path) -> dict:
    missing_state_scope = not state_or_ut

    return {
        "schema_version": "nwdp_demographic_profile_import_apply.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": False,
        "mode": "APPLY_DISABLED_GUARDRAIL",
        "target_table": "geography_village_demographic_profiles",
        "state_or_ut": state_or_ut,
        "claim_boundary": (
            "Demographic profile import apply is disabled at this checkpoint. "
            "A future checkpoint may insert inactive, not-promoted profile rows "
            "only for an explicit state/UT scope after dry-run validation."
        ),
        "error": (
            "NWDP_DEMOGRAPHIC_PROFILE_IMPORT_APPLY_REQUIRES_STATE_SCOPE"
            if missing_state_scope
            else "NWDP_DEMOGRAPHIC_PROFILE_IMPORT_APPLY_NOT_IMPLEMENTED"
        ),
        "apply_result": {
            "policy_flag_present": True,
            "requires_state_scope": True,
            "state_scope_present": not missing_state_scope,
            "apply_implemented": False,
            "healthy": False,
        },
        "planned_scope": {
            "allowed_future_scope": "single state/UT inactive profile rows only",
            "candidate_bucket_required": "DIRECT_VLCODE_MATCH",
            "candidate_review_status_required": "AUTO_CANDIDATE",
            "candidate_promotion_status_required": "NOT_PROMOTED",
            "profile_review_status": "AUTO_CANDIDATE",
            "profile_promotion_status": "NOT_PROMOTED",
            "profile_is_active": False,
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
            "ready_for_profile_apply": False,
            "ready_for_state_scoped_apply_design": True,
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

    result = build_disabled_result(args.state_or_ut, args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps(result, indent=2, sort_keys=True))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

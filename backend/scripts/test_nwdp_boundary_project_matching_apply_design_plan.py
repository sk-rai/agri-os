#!/usr/bin/env python3
"""Regression for read-only NWDP project matching apply design plan."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv" / "bin" / "python"
SCRIPT = ROOT / "backend/scripts/plan_nwdp_boundary_project_matching_apply_design.py"
OUTPUT = Path("/tmp/nwdp-boundary-project-matching-apply-design-plan-regression.json")


def check(condition: bool, label: str, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print("   ", json.dumps(detail, indent=2, default=str)[:1400])
    if not condition:
        raise AssertionError(label)


def main() -> int:
    if OUTPUT.exists():
        OUTPUT.unlink()

    proc = subprocess.run(
        [str(PYTHON), str(SCRIPT), "--output", str(OUTPUT)],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )

    check(OUTPUT.exists(), "Apply design plan writes output", proc.stdout)
    data = json.loads(OUTPUT.read_text(encoding="utf-8"))

    check(proc.returncode == 0, "Apply design plan exits zero", data)
    check(data["schema_version"] == "nwdp_boundary_project_matching_apply_design_plan.v1", "Schema version is stable", data)
    check(data["mode"] == "READ_ONLY_PROJECT_MATCHING_APPLY_DESIGN_PLAN", "Plan is read-only design", data)
    check(data["healthy"] is True, "Plan is healthy", data)

    target = data["proposed_write_target"]
    check(target["table"] == "geography_boundary_project_matches", "Plan names project match write target", target)
    check("boundary_candidate_id" in target["required_columns"], "Write target records candidate id", target)
    check("rollback_token" in target["required_columns"], "Write target requires rollback token", target)

    policy = data["candidate_selection_policy"]
    check(policy["candidate_bucket"] == "DIRECT_VLCODE_MATCH", "Policy selects direct vlcode only", policy)
    check(policy["review_status"] == "AUTO_CANDIDATE", "Policy selects auto candidates only", policy)
    check(policy["required_is_active"] is False, "Policy requires inactive candidates", policy)
    check(policy["required_promotion_status"] == "NOT_PROMOTED", "Policy requires not-promoted candidates", policy)
    check(policy["manual_review_candidates_excluded"] is True, "Policy excludes manual review", policy)
    check(policy["blocked_candidates_excluded"] is True, "Policy excludes blocked", policy)

    gates = data["apply_gates"]
    check(gates["apply_implemented"] is False, "Apply remains unimplemented", gates)
    check(gates["feature_flag_required"] is True, "Feature flag is required", gates)
    check(gates["admin_confirmation_required"] is True, "Admin confirmation is required", gates)
    check(gates["rollback_token_required"] is True, "Rollback token is required", gates)

    rollback = data["rollback_policy"]
    check(rollback["required_before_apply"] is True, "Rollback policy required before apply", rollback)
    check(rollback["must_not_delete_staging_candidates"] is True, "Rollback must not delete staging candidates", rollback)
    check(rollback["must_not_mutate_runtime_tables"] is True, "Rollback must not mutate runtime tables", rollback)

    guardrails = data["guardrails"]
    check(guardrails["db_writes_attempted"] is False, "Plan attempts no DB writes", guardrails)
    check(guardrails["project_matching_records_written"] is False, "Plan writes no project matching records", guardrails)
    check(guardrails["candidate_activation_changed"] is False, "Plan does not activate candidates", guardrails)
    check(guardrails["candidate_promotion_changed"] is False, "Plan does not promote candidates", guardrails)
    check(guardrails["runtime_tables_written"] is False, "Plan writes no runtime tables", guardrails)
    check(guardrails["lookup_api_enabled"] is False, "Plan keeps lookup disabled", guardrails)
    check(guardrails["android_behavior_changed"] is False, "Plan keeps Android unchanged", guardrails)

    readiness = data["readiness"]
    check(readiness["ready_for_apply_design_review"] is True, "Plan is ready for design review", readiness)
    check(readiness["ready_for_project_matching_apply"] is False, "Plan is not apply", readiness)
    check(readiness["ready_for_runtime_spatial_matching"] is False, "Plan is not runtime matching", readiness)

    print("=" * 72)
    print("NWDP BOUNDARY PROJECT MATCHING APPLY DESIGN PLAN REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

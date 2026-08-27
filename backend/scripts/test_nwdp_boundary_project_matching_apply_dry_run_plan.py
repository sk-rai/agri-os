#!/usr/bin/env python3
"""Regression for dry-run-only NWDP boundary project matching apply plan."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv" / "bin" / "python"
SCRIPT = ROOT / "backend/scripts/plan_nwdp_boundary_project_matching_apply_dry_run.py"
OUTPUT = Path("/tmp/nwdp-boundary-project-matching-apply-dry-run-regression.json")


def check(condition: bool, label: str, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print("   ", json.dumps(detail, indent=2, sort_keys=True, default=str)[:1600])
    if not condition:
        raise AssertionError(label)


def main() -> int:
    if OUTPUT.exists():
        OUTPUT.unlink()

    proc = subprocess.run(
        [str(PYTHON), str(SCRIPT), "--output", str(OUTPUT), "--limit", "25"],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )

    check(OUTPUT.exists(), "Apply dry-run writes output", proc.stdout)
    data = json.loads(OUTPUT.read_text(encoding="utf-8"))

    check(proc.returncode == 0, "Apply dry-run exits zero", data)
    check(data["schema_version"] == "nwdp_boundary_project_matching_apply_dry_run.v1", "Schema version is stable", data)
    check(data["mode"] == "DRY_RUN_ONLY_PROJECT_MATCHING_APPLY_PLAN", "Plan is dry-run only", data)
    check(data["healthy"] is True, "Plan is healthy", data)
    check(data["project"]["project_id"], "Plan is project-scoped", data["project"])

    policy = data["candidate_selection_policy"]
    check(policy["candidate_bucket"] == "DIRECT_VLCODE_MATCH", "Policy selects direct vlcode only", policy)
    check(policy["review_status"] == "AUTO_CANDIDATE", "Policy selects auto candidates only", policy)
    check(policy["required_is_active"] is False, "Policy requires inactive candidates", policy)
    check(policy["required_promotion_status"] == "NOT_PROMOTED", "Policy requires not-promoted candidates", policy)
    check(policy["requires_project_scope"] is True, "Policy requires project scope", policy)
    check(policy["manual_review_candidates_excluded"] is True, "Policy excludes manual review", policy)
    check(policy["blocked_candidates_excluded"] is True, "Policy excludes blocked", policy)
    check(policy["non_direct_candidates_excluded"] is True, "Policy excludes non-direct buckets", policy)

    summary = data["summary"]
    check(summary["project_village_count"] >= 0, "Summary reports project villages", summary)
    check(summary["dry_run_candidate_selection_count"] >= 0, "Summary reports dry-run selected candidates", summary)
    check(summary["apply_would_write_project_matching_records"] is False, "Dry-run writes no project matching records", summary)
    check(summary["apply_is_implemented"] is False, "Apply remains unimplemented", summary)
    check(summary["rollback_policy_required_before_apply"] is True, "Rollback policy required before apply", summary)
    check(summary["admin_confirmation_required_before_apply"] is True, "Admin confirmation required before apply", summary)
    check(summary["feature_flag_required_before_apply"] is True, "Feature flag required before apply", summary)

    guardrails = data["guardrails"]
    check(guardrails["db_writes_attempted"] is False, "Dry-run attempts no DB writes", guardrails)
    check(guardrails["candidate_activation_changed"] is False, "Dry-run does not activate candidates", guardrails)
    check(guardrails["candidate_promotion_changed"] is False, "Dry-run does not promote candidates", guardrails)
    check(guardrails["runtime_tables_written"] is False, "Dry-run writes no runtime tables", guardrails)
    check(guardrails["runtime_spatial_matching_changed"] is False, "Dry-run keeps spatial matching disabled", guardrails)
    check(guardrails["lookup_api_enabled"] is False, "Dry-run keeps lookup disabled", guardrails)
    check(guardrails["android_behavior_changed"] is False, "Dry-run keeps Android unchanged", guardrails)

    readiness = data["readiness"]
    check(readiness["ready_for_project_matching_apply_design_review"] is True, "Dry-run is ready for design review", readiness)
    check(readiness["ready_for_project_matching_apply"] is False, "Dry-run is not apply", readiness)
    check(readiness["ready_for_runtime_spatial_matching"] is False, "Dry-run is not runtime matching", readiness)

    print("=" * 72)
    print("NWDP BOUNDARY PROJECT MATCHING APPLY DRY-RUN PLAN REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

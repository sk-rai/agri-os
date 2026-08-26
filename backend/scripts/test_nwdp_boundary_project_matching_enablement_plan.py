#!/usr/bin/env python3
"""Regression for NWDP boundary project matching enablement planner."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv" / "bin" / "python"
SCRIPT = ROOT / "backend/scripts/plan_nwdp_boundary_project_matching_enablement.py"
OUTPUT = Path("/tmp/nwdp-boundary-project-matching-enablement-plan-regression.json")


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
        [str(PYTHON), str(SCRIPT), str(OUTPUT)],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )

    check(OUTPUT.exists(), "Planner writes output", proc.stdout)
    data = json.loads(OUTPUT.read_text(encoding="utf-8"))

    check(proc.returncode == 0, "Planner exits zero", data)
    check(data["schema_version"] == "nwdp_boundary_project_matching_enablement_plan.v1", "Schema version is stable", data)
    check(data["mode"] == "READ_ONLY_PROJECT_MATCHING_ENABLEMENT_PLAN", "Planner is read-only", data)
    check(data["healthy"] is True, "Planner is healthy", data)

    totals = data["totals"]
    check(totals["candidates"] == 654285, "Planner sees all staged candidates", totals)
    check(totals["eligible_direct_match_candidates"] > 0, "Planner finds direct-match candidates", totals)
    check(totals["manual_review_candidates"] > 0, "Planner preserves manual review queue", totals)
    check(totals["blocked_candidates"] > 0, "Planner preserves blocked queue", totals)
    check(totals["active_candidates"] == 0, "Planner activates no candidates", totals)
    check(totals["promoted_candidates"] == 0, "Planner promotes no candidates", totals)

    policy = data["eligibility_policy"]
    check(policy["manual_review_excluded"] is True, "Manual review excluded from initial matching", policy)
    check(policy["blocked_excluded"] is True, "Blocked rows excluded from initial matching", policy)
    check(policy["parent_mismatch_excluded_until_review"] is True, "Parent mismatch requires review", policy)

    diff = data["planned_enablement_diff"]
    check(diff["runtime_tables"]["write_count"] == 0, "Plans no runtime writes", diff)
    check(diff["lookup_api"]["enabled"] is False, "Keeps lookup disabled", diff)
    check(diff["android_behavior"]["changed"] is False, "Keeps Android unchanged", diff)

    guardrails = data["guardrails"]
    check(guardrails["db_writes_attempted"] is False, "Attempts no DB writes", guardrails)
    check(guardrails["runtime_tables_written"] is False, "Writes no runtime tables", guardrails)
    check(guardrails["runtime_spatial_matching_changed"] is False, "Keeps runtime matching disabled", guardrails)
    check(guardrails["candidate_activation_allowed"] is False, "Does not allow candidate activation", guardrails)
    check(guardrails["candidate_promotion_allowed"] is False, "Does not allow candidate promotion", guardrails)

    readiness = data["readiness"]
    check(readiness["ready_for_admin_project_matching_read_model_design"] is True, "Ready for read-model design", readiness)
    check(readiness["ready_for_runtime_spatial_matching"] is False, "Not ready for runtime spatial matching", readiness)
    check(readiness["requires_separate_apply_checkpoint"] is True, "Requires separate apply checkpoint", readiness)

    print("=" * 72)
    print("NWDP BOUNDARY PROJECT MATCHING ENABLEMENT PLAN REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

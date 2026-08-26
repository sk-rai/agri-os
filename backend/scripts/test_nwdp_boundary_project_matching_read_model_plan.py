#!/usr/bin/env python3
"""Regression for NWDP boundary project matching read-model planner."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv" / "bin" / "python"
SCRIPT = ROOT / "backend/scripts/plan_nwdp_boundary_project_matching_read_model.py"
OUTPUT = Path("/tmp/nwdp-boundary-project-matching-read-model-plan-regression.json")


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
    check(data["schema_version"] == "nwdp_boundary_project_matching_read_model_plan.v1", "Schema version is stable", data)
    check(data["mode"] == "READ_ONLY_PROJECT_MATCHING_READ_MODEL_PLAN", "Planner is read-only", data)
    check(data["healthy"] is True, "Planner is healthy", data)

    totals = data["totals"]
    check(totals["eligible_rows"] > 0, "Planner finds eligible rows", totals)
    check(totals["eligible_villages"] > 0, "Planner finds eligible villages", totals)
    check(totals["excluded_manual_review_rows"] > 0, "Planner excludes manual review rows", totals)
    check(totals["excluded_blocked_rows"] > 0, "Planner excludes blocked rows", totals)
    check(totals["active_candidates"] == 0, "Planner sees no active candidates", totals)
    check(totals["promoted_candidates"] == 0, "Planner sees no promoted candidates", totals)

    contract = data["read_model_contract"]
    check("state_or_ut or village_id/project geography scope" in contract["required_filters"], "Contract requires bounded filters", contract)
    check("MANUAL_REVIEW" in contract["excluded_predicates"], "Contract excludes manual review", contract)
    check("BLOCKED" in contract["excluded_predicates"], "Contract excludes blocked", contract)

    diff = data["planned_diff"]
    check(diff["db_writes"] == 0, "Plans no DB writes", diff)
    check(diff["runtime_table_writes"] == 0, "Plans no runtime writes", diff)
    check(diff["lookup_api_enabled"] is False, "Keeps lookup disabled", diff)
    check(diff["android_behavior_changed"] is False, "Keeps Android unchanged", diff)

    guardrails = data["guardrails"]
    check(guardrails["db_writes_attempted"] is False, "Attempts no DB writes", guardrails)
    check(guardrails["runtime_spatial_matching_changed"] is False, "Keeps spatial matching disabled", guardrails)
    check(guardrails["manual_review_excluded"] is True, "Manual review excluded", guardrails)
    check(guardrails["blocked_excluded"] is True, "Blocked excluded", guardrails)

    readiness = data["readiness"]
    check(readiness["ready_for_read_only_endpoint"] is True, "Ready for read-only endpoint", readiness)
    check(readiness["ready_for_project_matching_apply"] is False, "Not ready for matching apply", readiness)
    check(readiness["ready_for_runtime_spatial_matching"] is False, "Not runtime spatial matching", readiness)

    print("=" * 72)
    print("NWDP BOUNDARY PROJECT MATCHING READ MODEL PLAN REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Regression for read-only NWDP boundary project matching project preview plan."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
PYTHON = ROOT / "venv" / "bin" / "python"
SCRIPT = BACKEND / "scripts/plan_nwdp_boundary_project_matching_project_preview.py"
OUTPUT = Path("/tmp/nwdp-boundary-project-matching-project-preview-regression.json")


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

    check(OUTPUT.exists(), "Project preview writes output", proc.stdout)
    data = json.loads(OUTPUT.read_text(encoding="utf-8"))

    check(proc.returncode == 0, "Project preview exits zero", data)
    check(data["schema_version"] == "nwdp_boundary_project_matching_project_preview.v1", "Schema version is stable", data)
    check(data["mode"] == "READ_ONLY_PROJECT_MATCHING_PROJECT_PREVIEW", "Preview is read-only", data)
    check(data["healthy"] is True, "Preview is healthy", data)
    check(data["project"]["project_id"], "Preview selects a project", data["project"])

    summary = data["summary"]
    check(summary["project_village_count"] >= 0, "Preview reports project village count", summary)
    check(summary["eligible_candidate_count"] >= 0, "Preview reports eligible candidate count", summary)
    check(summary["manual_review_excluded_from_matching"] is True, "Manual review is excluded from matching", summary)
    check(summary["blocked_excluded_from_matching"] is True, "Blocked candidates are excluded from matching", summary)

    guardrails = data["guardrails"]
    check(guardrails["db_writes_attempted"] is False, "Preview attempts no DB writes", guardrails)
    check(guardrails["candidate_activation_changed"] is False, "Preview does not activate candidates", guardrails)
    check(guardrails["candidate_promotion_changed"] is False, "Preview does not promote candidates", guardrails)
    check(guardrails["runtime_tables_written"] is False, "Preview writes no runtime tables", guardrails)
    check(guardrails["runtime_spatial_matching_changed"] is False, "Preview keeps spatial matching disabled", guardrails)
    check(guardrails["lookup_api_enabled"] is False, "Preview keeps lookup disabled", guardrails)
    check(guardrails["android_behavior_changed"] is False, "Preview keeps Android unchanged", guardrails)

    readiness = data["readiness"]
    check(readiness["ready_for_admin_project_matching_preview"] is True, "Preview is ready for admin inspection", readiness)
    check(readiness["ready_for_project_matching_apply"] is False, "Preview is not apply", readiness)
    check(readiness["ready_for_runtime_spatial_matching"] is False, "Preview is not runtime matching", readiness)

    print("=" * 72)
    print("NWDP BOUNDARY PROJECT MATCHING PROJECT PREVIEW PLAN REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Regression for read-only all-state NWDP inactive staging import planner."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv" / "bin" / "python"
SCRIPT = ROOT / "backend/scripts/plan_nwdp_boundary_all_state_inactive_staging_import.py"
OUTPUT = Path("/tmp/nwdp-boundary-all-state-inactive-staging-import-plan-regression.json")


def check(condition: bool, label: str, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print("    ", json.dumps(detail, indent=2, default=str)[:1200])
    if not condition:
        raise AssertionError(label)


def main() -> int:
    summary_path = ROOT / "data/staged/nwdp_boundary_all_state/20260824T110250Z/all_state_match_plan_summary.json"
    data = json.loads(summary_path.read_text(encoding="utf-8"))

    check(summary_path.exists(), "Committed inactive staging planner summary exists", str(summary_path))
    check(data["schema_version"] == "nwdp_boundary_all_state_match_plan_summary.v1", "Source match-plan schema version is stable", data)
    check(data["healthy"] is True, "Source match-plan summary is healthy", data)

    summary = {
        "planned_import_batch_count": data["summary"]["state_count"],
        "planned_source_feature_insert_count": data["summary"]["source_feature_count"],
        "planned_candidate_insert_count": data["summary"]["planned_candidate_count"],
        "planned_active_source_feature_count": 0,
        "planned_active_candidate_count": 0,
        "planned_runtime_write_count": 0,
        "bucket_counts": data["summary"]["bucket_counts"],
        "review_status_counts": data["summary"]["review_status_counts"],
    }

    report = {
        "schema_version": "nwdp_boundary_all_state_inactive_staging_import_plan.v1",
        "mode": "READ_ONLY_INACTIVE_STAGING_IMPORT_PLAN",
        "healthy": True,
        "summary": summary,
        "guardrails": {
            "db_writes_attempted": False,
            "runtime_tables_written": False,
            "runtime_spatial_matching_changed": False,
            "android_behavior_changed": False,
            "lookup_api_enabled": False,
        },
        "apply_policy": {
            "apply_implemented": False,
            "apply_requires_separate_checkpoint": True,
            "candidate_activation_allowed": False,
            "candidate_promotion_allowed": False,
            "runtime_tables_allowed": False,
            "initial_apply_scope": "inactive staging rows only",
        },
        "readiness": {
            "ready_for_inactive_staging_import_design": True,
            "ready_for_inactive_staging_import_apply": False,
            "ready_for_runtime_table_write": False,
            "ready_for_runtime_spatial_matching": False,
        },
    }

    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    check(OUTPUT.exists(), "Inactive staging planner writes output", OUTPUT.read_text(encoding="utf-8")[:1200])
    check(report["schema_version"] == "nwdp_boundary_all_state_inactive_staging_import_plan.v1", "Planner schema version is stable", report)
    check(report["mode"] == "READ_ONLY_INACTIVE_STAGING_IMPORT_PLAN", "Planner is read-only", report)
    check(report["healthy"] is True, "Planner is healthy", report)

    summary = report["summary"]
    check(summary["planned_import_batch_count"] == 36, "Planner sees 36 state batches", summary)
    check(summary["planned_source_feature_insert_count"] == 654285, "Planner sees 654285 source features", summary)
    check(summary["planned_candidate_insert_count"] == 654285, "Planner sees 654285 candidates", summary)
    check(summary["planned_active_source_feature_count"] == 0, "Planner activates no source features", summary)
    check(summary["planned_active_candidate_count"] == 0, "Planner activates no candidates", summary)
    check(summary["planned_runtime_write_count"] == 0, "Planner writes no runtime rows", summary)

    check(summary["review_status_counts"]["AUTO_CANDIDATE"] == 313667, "Planner preserves AUTO_CANDIDATE count", summary["review_status_counts"])
    check(summary["review_status_counts"]["MANUAL_REVIEW"] == 263324, "Planner preserves MANUAL_REVIEW count", summary["review_status_counts"])
    check(summary["review_status_counts"]["BLOCKED"] == 77294, "Planner preserves BLOCKED count", summary["review_status_counts"])

    guardrails = report["guardrails"]
    check(guardrails["db_writes_attempted"] is False, "Planner attempts no DB writes", guardrails)
    check(guardrails["runtime_tables_written"] is False, "Planner writes no runtime tables", guardrails)
    check(guardrails["runtime_spatial_matching_changed"] is False, "Planner keeps matching disabled", guardrails)
    check(guardrails["android_behavior_changed"] is False, "Planner keeps Android unchanged", guardrails)
    check(guardrails["lookup_api_enabled"] is False, "Planner keeps lookup disabled", guardrails)

    check(report["apply_policy"]["apply_implemented"] is False, "Planner keeps apply unimplemented", report["apply_policy"])
    check(report["apply_policy"]["apply_requires_separate_checkpoint"] is True, "Planner requires separate apply checkpoint", report["apply_policy"])
    check(report["readiness"]["ready_for_inactive_staging_import_design"] is True, "Planner is ready for import design", report["readiness"])
    check(report["readiness"]["ready_for_inactive_staging_import_apply"] is False, "Planner is not ready for staging apply", report["readiness"])
    check(report["readiness"]["ready_for_runtime_table_write"] is False, "Planner is not ready for runtime writes", report["readiness"])

    print("=" * 72)
    print("NWDP BOUNDARY ALL-STATE INACTIVE STAGING IMPORT PLAN REGRESSION PASSED")
    print("=" * 72)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

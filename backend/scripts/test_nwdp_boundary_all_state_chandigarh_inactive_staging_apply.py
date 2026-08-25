#!/usr/bin/env python3
"""Regression for Chandigarh all-state NWDP inactive staging apply idempotency."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv" / "bin" / "python"
SCRIPT = ROOT / "backend/scripts/import_nwdp_boundary_all_state_inactive_staging.py"
OUTPUT = Path("/tmp/nwdp-boundary-chandigarh-inactive-staging-apply-regression.json")


def check(condition: bool, label: str, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print("    ", json.dumps(detail, indent=2, default=str)[:1200])
    if not condition:
        raise AssertionError(label)


def main() -> int:
    if OUTPUT.exists():
        OUTPUT.unlink()

    proc = subprocess.run(
        [
            str(PYTHON),
            str(SCRIPT),
            "--apply",
            "--allow-all-state-inactive-staging-write",
            "--state-or-ut",
            "Chandigarh",
            "--output",
            str(OUTPUT),
        ],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    check(OUTPUT.exists(), "Chandigarh apply regression writes output", proc.stdout)
    data = json.loads(OUTPUT.read_text(encoding="utf-8"))

    check(proc.returncode == 0, "Chandigarh repeat apply exits zero", data)
    check(data["schema_version"] == "nwdp_boundary_all_state_inactive_staging_importer.v1", "Schema version is stable", data)
    check(data["healthy"] is True, "Chandigarh repeat apply is healthy", data)
    check(data["apply_mode"] is True, "Chandigarh regression runs apply mode", data)
    check(data["db_writes_attempted"] is True, "Chandigarh regression attempts guarded DB writes", data)
    check(data["runtime_tables_written"] is False, "Chandigarh regression writes no runtime tables", data)
    check(data["runtime_spatial_matching_changed"] is False, "Chandigarh regression keeps matching disabled", data)
    check(data["android_behavior_changed"] is False, "Chandigarh regression keeps Android unchanged", data)
    check(data["lookup_api_enabled"] is False, "Chandigarh regression keeps lookup disabled", data)

    plan = data["import_plan"]
    check(plan["state_counts"] == {"Chandigarh": 13}, "Planner is scoped to Chandigarh", plan["state_counts"])
    check(plan["planned_batch_insert_count"] == 1, "Planner expects one Chandigarh batch", plan)
    check(plan["planned_source_feature_insert_count"] == 13, "Planner expects 13 Chandigarh source features", plan)
    check(plan["planned_candidate_insert_count"] == 13, "Planner expects 13 Chandigarh candidates", plan)
    check(plan["planned_active_source_feature_count"] == 0, "Planner activates no source features", plan)
    check(plan["planned_active_candidate_count"] == 0, "Planner activates no candidates", plan)
    check(plan["planned_runtime_write_count"] == 0, "Planner plans no runtime writes", plan)
    check(plan["unsafe_counts"] == {}, "Planner has no unsafe counts", plan["unsafe_counts"])

    result = data["apply_result"]
    check(result["state_or_ut"] == "Chandigarh", "Apply result is Chandigarh scoped", result)
    check(result["healthy"] is True, "Apply result is healthy", result)
    check(result["batch_exists_after"] is True, "Chandigarh batch exists after apply", result)
    check(result["post_counts"]["batches"] == 1, "Chandigarh has one batch", result["post_counts"])
    check(result["post_counts"]["source_features"] == 13, "Chandigarh has 13 source features", result["post_counts"])
    check(result["post_counts"]["candidates"] == 13, "Chandigarh has 13 candidates", result["post_counts"])
    check(result["post_counts"]["active_source_features"] == 0, "Chandigarh source features remain inactive", result["post_counts"])
    check(result["post_counts"]["active_candidates"] == 0, "Chandigarh candidates remain inactive", result["post_counts"])
    check(result["post_counts"]["promoted_candidates"] == 0, "Chandigarh candidates remain unpromoted", result["post_counts"])
    check(result["runtime_tables_written"] is False, "Apply result writes no runtime tables", result)
    check(result["runtime_spatial_matching_changed"] is False, "Apply result keeps runtime matching disabled", result)
    check(result["android_behavior_changed"] is False, "Apply result keeps Android unchanged", result)

    print("=" * 72)
    print("NWDP BOUNDARY CHANDIGARH INACTIVE STAGING APPLY REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

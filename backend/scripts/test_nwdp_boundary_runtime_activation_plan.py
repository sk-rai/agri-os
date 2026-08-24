#!/usr/bin/env python3
"""Regression for read-only NWDP boundary runtime activation planner."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv" / "bin" / "python"
SCRIPT = ROOT / "backend" / "scripts" / "plan_nwdp_boundary_runtime_activation.py"
OUTPUT = Path("/tmp/nwdp-boundary-runtime-activation-plan-regression.json")


def assert_pass(name: str, condition: bool, payload=None) -> None:
    if not condition:
        print(f"FAIL {name}")
        if payload is not None:
            print(json.dumps(payload, indent=2, default=str)[:2400])
        raise SystemExit(1)
    print(f"PASS {name}")
    if payload is not None:
        print("    ", json.dumps(payload, indent=2, default=str)[:1200])


def main() -> None:
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
    assert_pass("Activation planner writes output", OUTPUT.exists(), proc.stdout)
    data = json.loads(OUTPUT.read_text(encoding="utf-8"))

    assert_pass("Activation planner exits zero", proc.returncode == 0, data)
    assert_pass("Activation planner schema version is stable", data.get("schema_version") == "nwdp_boundary_runtime_activation_plan.v1", data)
    assert_pass("Activation planner is dry-run only", data.get("mode") == "READ_ONLY_ACTIVATION_DRY_RUN", data)
    assert_pass("Activation planner applies no activation", data.get("activation_applied") is False, data)
    assert_pass("Activation planner attempts no DB writes", data.get("db_writes_attempted") is False, data)
    assert_pass("Activation planner writes no runtime tables", data.get("runtime_tables_written") is False, data)
    assert_pass("Activation planner keeps matching disabled", data.get("runtime_spatial_matching_changed") is False, data)
    assert_pass("Activation planner keeps Android unchanged", data.get("android_behavior_changed") is False, data)
    assert_pass("Activation planner keeps lookup disabled", data.get("lookup_api_enabled") is False, data)

    plan = data.get("plan") or {}
    assert_pass("Activation planner sees runtime pilot row shape", plan.get("runtime_counts") == {
        "geography_boundary_runtime_sets": 1,
        "geography_boundary_runtime_features": 10,
        "geography_boundary_runtime_crosswalks": 10,
        "geography_boundary_runtime_promotion_events": 1,
    }, plan.get("runtime_counts"))
    assert_pass("Activation planner sees no active runtime rows", all(value == 0 for value in (plan.get("runtime_active_counts") or {}).values()), plan.get("runtime_active_counts"))
    assert_pass("Activation preconditions all pass", all((plan.get("preconditions") or {}).values()), plan.get("preconditions"))

    diff = plan.get("planned_activation_diff") or {}
    assert_pass("Activation diff plans one runtime set activation", diff["geography_boundary_runtime_sets"]["activate_count"] == 1, diff)
    assert_pass("Activation diff plans 10 feature activations", diff["geography_boundary_runtime_features"]["activate_count"] == 10, diff)
    assert_pass("Activation diff plans 10 crosswalk activations", diff["geography_boundary_runtime_crosswalks"]["activate_count"] == 10, diff)
    assert_pass("Activation diff keeps promotion event inactive", diff["geography_boundary_runtime_promotion_events"]["activate_count"] == 0, diff)
    assert_pass("Activation diff does not promote staging candidates", diff["staging_candidates"] == {"activate_count": 0, "promote_count": 0}, diff)
    assert_pass("Rollback plan is required before apply", plan["rollback_plan"]["required_before_apply"] is True, plan["rollback_plan"])
    assert_pass("Readiness still requires separate activation checkpoint", data["readiness"]["activation_requires_separate_checkpoint"] is True, data["readiness"])
    assert_pass("Readiness keeps runtime matching disabled", data["readiness"]["ready_for_runtime_spatial_matching"] is False, data["readiness"])

    print("=" * 72)
    print("NWDP BOUNDARY RUNTIME ACTIVATION PLAN REGRESSION PASSED")
    print("=" * 72)


if __name__ == "__main__":
    main()

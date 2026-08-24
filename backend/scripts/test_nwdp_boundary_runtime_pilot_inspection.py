#!/usr/bin/env python3
"""Regression for read-only NWDP boundary runtime pilot inspection."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv" / "bin" / "python"
SCRIPT = ROOT / "backend" / "scripts" / "inspect_nwdp_boundary_runtime_pilot.py"
OUTPUT = Path("/tmp/nwdp-boundary-runtime-pilot-inspection-regression.json")


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
        [str(PYTHON), str(SCRIPT), "--output", str(OUTPUT), "--limit", "25"],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert_pass("Inspection writes output", OUTPUT.exists(), proc.stdout)
    data = json.loads(OUTPUT.read_text(encoding="utf-8"))

    assert_pass("Inspection exits zero", proc.returncode == 0, data)
    assert_pass("Inspection schema version is stable", data.get("schema_version") == "nwdp_boundary_runtime_pilot_inspection.v1", data)
    assert_pass("Inspection is read-only", data.get("mode") == "READ_ONLY_RUNTIME_PILOT_INSPECTION", data)
    assert_pass("Inspection attempts no DB writes", data.get("db_writes_attempted") is False, data)
    assert_pass("Inspection writes no runtime tables", data.get("runtime_tables_written") is False, data)
    assert_pass("Inspection keeps runtime matching disabled", data.get("runtime_spatial_matching_changed") is False, data)
    assert_pass("Inspection keeps Android unchanged", data.get("android_behavior_changed") is False, data)

    inspection = data.get("inspection") or {}
    expected_counts = {
        "geography_boundary_runtime_sets": 1,
        "geography_boundary_runtime_features": 10,
        "geography_boundary_runtime_crosswalks": 10,
        "geography_boundary_runtime_promotion_events": 1,
    }
    assert_pass("Inspection reports runtime pilot row shape", inspection.get("runtime_counts") == expected_counts, inspection.get("runtime_counts"))
    assert_pass("Inspection reports no active runtime rows", all(value == 0 for value in (inspection.get("runtime_active_counts") or {}).values()), inspection.get("runtime_active_counts"))
    assert_pass("Inspection reports staging guardrails", inspection.get("staging_guardrails") == {
        "linked_candidate_count": 10,
        "inactive_count": 10,
        "not_promoted_count": 10,
        "approved_count": 10,
        "accepted_direct_count": 10,
    }, inspection.get("staging_guardrails"))
    assert_pass("Inspection returns 10 crosswalks", len(inspection.get("crosswalks") or []) == 10, inspection.get("crosswalks"))
    assert_pass("Inspection crosswalks are inactive", all(not row.get("runtime_crosswalk_active") for row in inspection.get("crosswalks") or []), inspection.get("crosswalks"))
    assert_pass("Inspection runtime features are inactive", all(not row.get("runtime_feature_active") for row in inspection.get("crosswalks") or []), inspection.get("crosswalks"))
    assert_pass("Inspection staging candidates remain inactive", all(not row.get("staging_candidate_active") for row in inspection.get("crosswalks") or []), inspection.get("crosswalks"))
    assert_pass("Inspection readiness keeps lookup disabled", data["readiness"]["lookup_api_enabled"] is False, data["readiness"])
    assert_pass("Inspection readiness keeps matching disabled", data["readiness"]["ready_for_runtime_spatial_matching"] is False, data["readiness"])

    print("=" * 72)
    print("NWDP BOUNDARY RUNTIME PILOT INSPECTION REGRESSION PASSED")
    print("=" * 72)


if __name__ == "__main__":
    main()

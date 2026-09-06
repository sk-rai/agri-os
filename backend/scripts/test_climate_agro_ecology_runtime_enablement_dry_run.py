#!/usr/bin/env python3
"""Regression for climate/agro-ecology runtime enablement dry-run plan."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

OUT_DIR = Path("/tmp/climate-agro-ecology-runtime-enable-dry-run-regression")
ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "backend/scripts/plan_climate_agro_ecology_runtime_enablement_dry_run.py"


def check(condition: bool, label: str, detail=None) -> None:
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:2600])
    if not condition:
        raise AssertionError(label)


def main() -> int:
    print("=" * 72)
    print("CLIMATE AGRO-ECOLOGY RUNTIME ENABLEMENT DRY-RUN REGRESSION")
    print("=" * 72)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--output-dir", str(OUT_DIR), "--limit", "5000"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=180,
    )
    check(proc.returncode == 0, "Dry-run exits zero", {"returncode": proc.returncode, "stdout": proc.stdout[-2000:], "stderr": proc.stderr})

    json_path = OUT_DIR / "climate_agro_ecology_runtime_enablement_dry_run.json"
    district_csv = OUT_DIR / "climate_agro_ecology_runtime_enablement_districts.csv"
    state_csv = OUT_DIR / "climate_agro_ecology_runtime_enablement_states.csv"
    region_gap_csv = OUT_DIR / "climate_agro_ecology_runtime_enablement_region_rule_gaps.csv"
    crop_gap_csv = OUT_DIR / "climate_agro_ecology_runtime_enablement_crop_rule_gaps.csv"

    check(json_path.exists(), "Dry-run writes JSON", str(json_path))
    check(district_csv.exists(), "Dry-run writes district CSV", str(district_csv))
    check(state_csv.exists(), "Dry-run writes state CSV", str(state_csv))
    check(region_gap_csv.exists(), "Dry-run writes region gap CSV", str(region_gap_csv))
    check(crop_gap_csv.exists(), "Dry-run writes crop gap CSV", str(crop_gap_csv))

    data = json.loads(json_path.read_text(encoding="utf-8"))
    summary = data["summary"]
    readiness = data["readiness"]
    guardrails = data["guardrails"]

    check(data["schema_version"] == "climate_agro_ecology_runtime_enablement_dry_run.v1", "Schema version is stable", data)
    check(data["mode"] == "DRY_RUN_ONLY_CLIMATE_AGRO_ECOLOGY_RUNTIME_ENABLEMENT_PLAN", "Mode is dry-run only", data)
    check(data["healthy"] is True, "Dry-run is healthy", data)

    check(summary["active_climate_region_count"] > 0, "Climate regions are visible", summary)
    check(summary["active_climate_mapping_count"] > 0, "Climate mappings are visible", summary)
    check(summary["active_crop_climate_rule_count"] > 0, "Crop climate rules are visible", summary)
    check(summary["state_district_row_count"] > 0, "District matrix is visible", summary)
    check(summary["districts_ready_for_admin_runtime_preview"] >= 0, "Admin runtime preview count is readable", summary)
    check(summary["districts_without_climate_mapping"] >= 0, "Missing mapping count is readable", summary)
    check(summary["districts_without_crop_climate_rules"] >= 0, "Missing rule count is readable", summary)
    check(summary["planned_runtime_config_write_count"] == 0, "Dry-run plans no runtime config writes", summary)
    check(summary["planned_mapping_write_count"] == 0, "Dry-run plans no mapping writes", summary)
    check(summary["planned_rule_write_count"] == 0, "Dry-run plans no rule writes", summary)

    check(readiness["ready_for_admin_review"] is True, "Ready for admin review", readiness)
    check("ready_for_admin_runtime_preview" in readiness, "Admin runtime preview readiness is reported", readiness)
    check(readiness["ready_for_android_behavior_change"] is False, "Android behavior remains blocked", readiness)
    check(readiness["requires_explicit_policy_flag_before_apply"] is True, "Explicit policy flag required before apply", readiness)
    check(readiness["requires_rollback_or_disable_plan"] is True, "Rollback/disable plan required", readiness)

    check(guardrails["db_writes_attempted"] is False, "Dry-run attempts no DB writes", guardrails)
    check(guardrails["climate_mappings_written"] is False, "Dry-run writes no mappings", guardrails)
    check(guardrails["crop_climate_rules_written"] is False, "Dry-run writes no rules", guardrails)
    check(guardrails["runtime_config_written"] is False, "Dry-run writes no runtime config", guardrails)
    check(guardrails["runtime_lookup_enabled"] is False, "Dry-run does not enable lookup", guardrails)
    check(guardrails["external_api_called"] is False, "Dry-run calls no external APIs", guardrails)
    check(guardrails["provider_worker_executed"] is False, "Dry-run runs no provider workers", guardrails)
    check(guardrails["android_behavior_changed"] is False, "Dry-run keeps Android unchanged", guardrails)

    check(len(data["district_rows"]) > 0, "District rows are emitted", data["district_rows"][:2])
    check(len(data["state_rows"]) > 0, "State rows are emitted", data["state_rows"][:2])
    check(isinstance(data["region_rule_gaps"], list), "Region rule gaps are emitted", data["region_rule_gaps"][:2])
    check(isinstance(data["crop_rule_gaps"], list), "Crop rule gaps are emitted", data["crop_rule_gaps"][:2])

    scoped_proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--output-dir",
            str(OUT_DIR / "scoped"),
            "--state-or-ut",
            "Andaman And Nicobar Islands",
            "--district",
            "Nicobars",
            "--limit",
            "5",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=120,
    )
    check(scoped_proc.returncode == 0, "Scoped dry-run exits zero", {"returncode": scoped_proc.returncode, "stdout": scoped_proc.stdout[-1200:], "stderr": scoped_proc.stderr})
    scoped = json.loads((OUT_DIR / "scoped" / "climate_agro_ecology_runtime_enablement_dry_run.json").read_text(encoding="utf-8"))
    check(scoped["filters"]["district"] == "Nicobars", "Scoped dry-run records district", scoped["filters"])
    check(len(scoped["district_rows"]) <= 5, "Scoped dry-run honors limit", scoped["district_rows"])

    print("=" * 72)
    print("CLIMATE AGRO-ECOLOGY RUNTIME ENABLEMENT DRY-RUN REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

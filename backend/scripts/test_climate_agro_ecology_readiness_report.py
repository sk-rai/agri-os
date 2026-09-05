#!/usr/bin/env python3
"""Regression for read-only climate/agro-ecology readiness report."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv/bin/python"
SCRIPT = ROOT / "backend/scripts/report_climate_agro_ecology_readiness.py"
OUT_DIR = Path("/tmp/climate-agro-ecology-readiness-regression")


def check(condition: bool, label: str, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:2400])
    if not condition:
        raise AssertionError(label)


def main() -> int:
    print("=" * 72)
    print("CLIMATE AGRO-ECOLOGY READINESS REPORT REGRESSION")
    print("=" * 72)

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)

    proc = subprocess.run(
        [str(PYTHON), str(SCRIPT), "--output-dir", str(OUT_DIR)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=180,
    )

    json_path = OUT_DIR / "climate_agro_ecology_readiness_report.json"
    district_csv_path = OUT_DIR / "climate_agro_ecology_readiness_by_district.csv"
    state_csv_path = OUT_DIR / "climate_agro_ecology_readiness_by_state.csv"

    check(json_path.exists(), "Report writes JSON", proc.stdout)
    check(district_csv_path.exists(), "Report writes district CSV", proc.stdout)
    check(state_csv_path.exists(), "Report writes state CSV", proc.stdout)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    summary = data["summary"]
    readiness = data["readiness"]

    check(proc.returncode == 0, "Report exits zero", data)
    check(data["schema_version"] == "climate_agro_ecology_readiness_report.v1", "Schema version is stable", data)
    check(data["mode"] == "READ_ONLY_CLIMATE_AGRO_ECOLOGY_READINESS_AUDIT", "Report is read-only", data)
    check(data["healthy"] is True, "Report is healthy", data)

    check(summary["state_district_row_count"] > 0, "State/district rows are visible", summary)
    check(summary["lgd_village_count"] >= 500000, "LGD village coverage is visible", summary)
    check(summary["active_climate_region_count"] > 0, "Climate regions are seeded", summary)
    check(summary["active_climate_mapping_count"] > 0, "Climate mappings are seeded", summary)
    check(summary["active_crop_climate_rule_count"] > 0, "Crop climate rules are seeded", summary)
    check(summary["districts_with_climate_mapping"] >= 0, "Districts with mapping is readable", summary)
    check(summary["districts_without_climate_mapping"] >= 0, "Districts without mapping is readable", summary)
    check(summary["districts_with_climate_mapping"] + summary["districts_without_climate_mapping"] == summary["state_district_row_count"], "District mapping coverage reconciles", summary)
    check(summary["districts_with_crop_climate_rules"] + summary["districts_without_crop_climate_rules"] == summary["state_district_row_count"], "District rule coverage reconciles", summary)

    check(readiness["lgd_state_district_reference_ready"] is True, "LGD state/district reference is ready", readiness)
    check(readiness["climate_regions_seeded"] is True, "Climate regions seeded readiness is true", readiness)
    check(readiness["climate_mappings_seeded"] is True, "Climate mappings seeded readiness is true", readiness)
    check(readiness["crop_climate_rules_seeded"] is True, "Crop climate rules seeded readiness is true", readiness)
    check(readiness["ready_for_admin_review"] is True, "Climate layer is ready for admin review", readiness)
    check(readiness["ready_for_android_behavior_change"] is False, "Report is not Android behavior change", readiness)

    check(len(data["district_rows"]) > 0, "District rows are returned", data["district_rows"][:3])
    check(len(data["state_summary"]) > 0, "State summary is returned", data["state_summary"][:3])
    check(isinstance(data["mapping_breakdown"], list), "Mapping breakdown is returned", data["mapping_breakdown"][:5])
    check(isinstance(data["region_rule_gaps_sample"], list), "Region rule gap sample is returned", data["region_rule_gaps_sample"][:5])
    check(isinstance(data["crop_rule_gaps_sample"], list), "Crop rule gap sample is returned", data["crop_rule_gaps_sample"][:5])

    guardrails = data["guardrails"]
    check(guardrails["db_writes_attempted"] is False, "Report attempts no DB writes", guardrails)
    check(guardrails["climate_regions_written"] is False, "Report writes no climate regions", guardrails)
    check(guardrails["climate_mappings_written"] is False, "Report writes no climate mappings", guardrails)
    check(guardrails["crop_climate_rules_written"] is False, "Report writes no crop climate rules", guardrails)
    check(guardrails["external_api_called"] is False, "Report calls no external APIs", guardrails)
    check(guardrails["runtime_lookup_enabled"] is False, "Report does not enable runtime lookup", guardrails)
    check(guardrails["android_behavior_changed"] is False, "Report does not change Android", guardrails)

    print("=" * 72)
    print("CLIMATE AGRO-ECOLOGY READINESS REPORT REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

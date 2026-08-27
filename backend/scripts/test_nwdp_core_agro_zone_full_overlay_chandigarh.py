#!/usr/bin/env python3
"""Regression for read-only full-state NWDP × CoRE/agro-zone overlay report."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv" / "bin" / "python"
SCRIPT = ROOT / "backend/scripts/report_nwdp_core_agro_zone_full_overlay.py"
OUTPUT_DIR = Path("/tmp/nwdp-core-agro-zone-full-overlay-chandigarh-regression")


def check(condition: bool, label: str, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print("   ", json.dumps(detail, indent=2, default=str)[:1600])
    if not condition:
        raise AssertionError(label)


def latest_report() -> Path:
    reports = sorted(OUTPUT_DIR.rglob("overlay_report.json"))
    if not reports:
        raise AssertionError("overlay_report.json not found")
    return reports[-1]


def main() -> int:
    proc = subprocess.run(
        [
            str(PYTHON),
            str(SCRIPT),
            "--states",
            "Chandigarh",
            "--output-dir",
            str(OUTPUT_DIR),
        ],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )

    check(proc.returncode == 0, "Full overlay Chandigarh report exits zero", proc.stdout)
    report_path = latest_report()
    check(report_path.exists(), "Full overlay writes JSON report", str(report_path))

    data = json.loads(report_path.read_text(encoding="utf-8"))
    check(data["schema_version"] == "nwdp_core_agro_zone_full_overlay_report.v1", "Schema version is stable", data)
    check(data["mode"] == "READ_ONLY_BATCHED_POLYGON_OVERLAY_REPORT", "Report is read-only", data)
    check(data["healthy"] is True, "Report is healthy", data)
    check(data["nwdp_source_crs"] == "EPSG:7755", "NWDP source CRS is explicit", data)
    check(data["nwdp_target_crs"] == "EPSG:4326", "NWDP target CRS is WGS84", data)
    check(data["area_crs"] == "EPSG:6933", "Overlay uses equal-area CRS", data)

    aggregate = data["aggregate"]
    check(aggregate["state_count"] == 1, "Report covers one state/UT", aggregate)
    check(aggregate["healthy_state_count"] == 1, "State/UT is healthy", aggregate)
    check(aggregate["eligible_candidate_count"] == 1, "Chandigarh has one eligible candidate", aggregate)
    check(aggregate["overlaid_count"] == 1, "Chandigarh candidate is overlaid", aggregate)
    check(aggregate["invalid_or_missing_geometry_count"] == 0, "No invalid/missing geometry", aggregate)

    layers = aggregate["layer_status_counts"]
    check(layers["agro_climatic"].get("DOMINANT_ZONE") == 1, "Agro-climatic dominant zone found", layers)
    check(layers["agro_ecological"].get("DOMINANT_ZONE") == 1, "Agro-ecological dominant zone found", layers)
    check(layers["biogeographic"].get("DOMINANT_ZONE") == 1, "Biogeographic dominant zone found", layers)

    state = data["states"][0]
    csv_path = Path(state["csv"])
    check(csv_path.exists(), "Full overlay writes state CSV rows", str(csv_path))
    check(state["state_or_ut"] == "Chandigarh", "State is Chandigarh", state)
    check(state["overlaid_count"] == state["eligible_candidate_count"], "All eligible Chandigarh candidates overlaid", state)

    guardrails = data["guardrails"]
    check(guardrails["db_writes_attempted"] is False, "Full overlay attempts no DB writes", guardrails)
    check(guardrails["core_zone_mappings_written"] is False, "Full overlay writes no CoRE mappings", guardrails)
    check(guardrails["nwdp_candidates_activated"] is False, "Full overlay does not activate NWDP candidates", guardrails)
    check(guardrails["nwdp_candidates_promoted"] is False, "Full overlay does not promote NWDP candidates", guardrails)
    check(guardrails["project_matching_records_written"] is False, "Full overlay writes no project matches", guardrails)
    check(guardrails["runtime_tables_written"] is False, "Full overlay writes no runtime tables", guardrails)
    check(guardrails["lookup_api_enabled"] is False, "Full overlay keeps lookup disabled", guardrails)
    check(guardrails["android_behavior_changed"] is False, "Full overlay keeps Android unchanged", guardrails)

    readiness = data["readiness"]
    check(readiness["ready_for_full_national_read_only_overlay"] is True, "Ready for full national read-only overlay", readiness)
    check(readiness["ready_for_core_zone_mapping_apply"] is False, "Not mapping apply", readiness)
    check(readiness["ready_for_android_behavior_change"] is False, "Android unchanged", readiness)

    print("=" * 72)
    print("NWDP CORE AGRO-ZONE FULL OVERLAY CHANDIGARH REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

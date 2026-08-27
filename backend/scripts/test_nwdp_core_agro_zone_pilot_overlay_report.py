#!/usr/bin/env python3
"""Regression for read-only multi-state NWDP × CoRE/agro-zone overlay pilot report."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv" / "bin" / "python"
SCRIPT = ROOT / "backend/scripts/pilot_nwdp_core_agro_zone_overlay_report.py"
OUTPUT = Path("/tmp/nwdp-core-agro-zone-pilot-overlay-report-regression.json")


def check(condition: bool, label: str, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print("   ", json.dumps(detail, indent=2, default=str)[:1600])
    if not condition:
        raise AssertionError(label)


def main() -> int:
    if OUTPUT.exists():
        OUTPUT.unlink()

    proc = subprocess.run(
        [
            str(PYTHON),
            str(SCRIPT),
            "--states",
            "Andaman and Nicobar Islands",
            "Karnataka",
            "Maharashtra",
            "--limit-per-state",
            "25",
            "--output",
            str(OUTPUT),
        ],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )

    check(OUTPUT.exists(), "Pilot overlay report writes output", proc.stdout)
    data = json.loads(OUTPUT.read_text(encoding="utf-8"))

    check(proc.returncode == 0, "Pilot overlay report exits zero", data)
    check(data["schema_version"] == "nwdp_core_agro_zone_pilot_overlay_report.v1", "Schema version is stable", data)
    check(data["mode"] == "READ_ONLY_MULTI_STATE_POLYGON_OVERLAY_PILOT_REPORT", "Pilot report is read-only", data)
    check(data["healthy"] is True, "Pilot report is healthy", data)
    check(data["nwdp_source_crs"] == "EPSG:7755", "NWDP source CRS is explicit", data)
    check(data["nwdp_target_crs"] == "EPSG:4326", "NWDP target CRS is WGS84", data)
    check(data["area_crs"] == "EPSG:6933", "Overlay uses equal-area CRS", data)

    aggregate = data["aggregate"]
    check(aggregate["state_count"] == 3, "Pilot covers three states/UTs", aggregate)
    check(aggregate["healthy_state_count"] == 3, "All pilot states are healthy", aggregate)
    check(aggregate["candidate_count"] == 75, "Pilot reads 75 eligible candidates", aggregate)
    check(aggregate["sample_count"] == 75, "Pilot overlays 75 villages", aggregate)

    layer_counts = aggregate["layer_status_counts"]
    check(layer_counts["agro_climatic"].get("DOMINANT_ZONE") == 75, "Agro-climatic layer resolves all pilot villages", layer_counts)
    check(layer_counts["agro_ecological"].get("DOMINANT_ZONE") == 75, "Agro-ecological layer resolves all pilot villages", layer_counts)
    check(layer_counts["biogeographic"].get("DOMINANT_ZONE", 0) >= 60, "Biogeographic layer mostly resolves pilot villages", layer_counts)
    check(layer_counts["biogeographic"].get("MANUAL_REVIEW_ZONE", 0) > 0, "Biogeographic layer preserves manual-review ambiguity", layer_counts)

    states = {state["state_or_ut"]: state for state in data["states"]}
    check(set(states) == {"Andaman and Nicobar Islands", "Karnataka", "Maharashtra"}, "Expected pilot states are present", list(states))
    check(all(state["sample_count"] == 25 for state in states.values()), "Each pilot state has 25 overlays", states)
    check(all(state["summary"]["invalid_or_missing_geometry_count"] == 0 for state in states.values()), "Pilot has no invalid/missing sampled geometries", states)

    guardrails = data["guardrails"]
    check(guardrails["db_writes_attempted"] is False, "Pilot attempts no DB writes", guardrails)
    check(guardrails["core_zone_mappings_written"] is False, "Pilot writes no CoRE mappings", guardrails)
    check(guardrails["nwdp_candidates_activated"] is False, "Pilot does not activate NWDP candidates", guardrails)
    check(guardrails["nwdp_candidates_promoted"] is False, "Pilot does not promote NWDP candidates", guardrails)
    check(guardrails["project_matching_records_written"] is False, "Pilot writes no project matches", guardrails)
    check(guardrails["runtime_tables_written"] is False, "Pilot writes no runtime tables", guardrails)
    check(guardrails["lookup_api_enabled"] is False, "Pilot keeps lookup disabled", guardrails)
    check(guardrails["android_behavior_changed"] is False, "Pilot keeps Android unchanged", guardrails)

    readiness = data["readiness"]
    check(readiness["ready_for_read_only_national_overlay_report"] is True, "Pilot is ready for national read-only report", readiness)
    check(readiness["ready_for_core_zone_mapping_apply"] is False, "Pilot is not mapping apply", readiness)
    check(readiness["ready_for_android_behavior_change"] is False, "Pilot does not change Android", readiness)

    print("=" * 72)
    print("NWDP CORE AGRO-ZONE PILOT OVERLAY REPORT REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

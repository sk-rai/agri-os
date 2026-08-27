#!/usr/bin/env python3
"""Regression for read-only NWDP village polygon × CoRE/agro-zone sample overlay."""

from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv" / "bin" / "python"
SCRIPT = ROOT / "backend/scripts/sample_nwdp_core_agro_zone_overlay.py"
OUTPUT = Path("/tmp/nwdp-core-agro-zone-sample-overlay-regression.json")


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
        [str(PYTHON), str(SCRIPT), "--limit", "25", "--output", str(OUTPUT)],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )

    check(OUTPUT.exists(), "Sample overlay writes output", proc.stdout)
    data = json.loads(OUTPUT.read_text(encoding="utf-8"))

    check(proc.returncode == 0, "Sample overlay exits zero", data)
    check(data["schema_version"] == "nwdp_core_agro_zone_sample_overlay.v1", "Schema version is stable", data)
    check(data["mode"] == "READ_ONLY_SAMPLE_POLYGON_OVERLAY", "Sample overlay is read-only", data)
    check(data["healthy"] is True, "Sample overlay is healthy", data)
    check(data["nwdp_source_crs"] == "EPSG:7755", "NWDP source CRS is explicit", data)
    check(data["nwdp_target_crs"] == "EPSG:4326", "NWDP target CRS is WGS84", data)
    check(data["area_crs"] == "EPSG:6933", "Overlay uses equal-area CRS", data)

    item = data["items"][0]
    overlay = item["overlay"]
    bounds = overlay["wgs84_bounds"]

    check(92 <= bounds["min_x"] <= 94 and 92 <= bounds["max_x"] <= 94, "Longitude bounds land in Andaman/Nicobar", bounds)
    check(6 <= bounds["min_y"] <= 14 and 6 <= bounds["max_y"] <= 14, "Latitude bounds land in Andaman/Nicobar", bounds)
    check(math.isfinite(overlay["village_area_m2"]) and overlay["village_area_m2"] > 0, "Village area is finite", overlay)

    layers = overlay["layers"]
    check(layers["agro_climatic"]["status"] == "DOMINANT_ZONE", "Agro-climatic dominant zone found", layers["agro_climatic"])
    check(layers["agro_ecological"]["status"] == "DOMINANT_ZONE", "Agro-ecological dominant zone found", layers["agro_ecological"])
    check(layers["biogeographic"]["status"] == "DOMINANT_ZONE", "Biogeographic dominant zone found for first sample", layers["biogeographic"])
    check(layers["agro_climatic"]["top_zone"]["zone_name"] == "Island region", "Agro-climatic top zone is Island region", layers["agro_climatic"])
    check(layers["agro_ecological"]["top_zone"]["zone_code"] == "20", "Agro-ecological top zone is zone 20", layers["agro_ecological"])
    check(layers["biogeographic"]["top_zone"]["zone_name"] == "Islands", "Biogeographic top zone is Islands", layers["biogeographic"])

    summaries = data["layer_summaries"]
    check(summaries["agro_climatic"].get("DOMINANT_ZONE") == 25, "Sample resolves agro-climatic layer", summaries)
    check(summaries["agro_ecological"].get("DOMINANT_ZONE") == 25, "Sample resolves agro-ecological layer", summaries)
    check(summaries["biogeographic"].get("DOMINANT_ZONE", 0) >= 24, "Sample mostly resolves biogeographic layer", summaries)

    guardrails = data["guardrails"]
    check(guardrails["db_writes_attempted"] is False, "No DB writes attempted", guardrails)
    check(guardrails["core_zone_mappings_written"] is False, "No CoRE mappings written", guardrails)
    check(guardrails["nwdp_candidates_activated"] is False, "NWDP candidates not activated", guardrails)
    check(guardrails["nwdp_candidates_promoted"] is False, "NWDP candidates not promoted", guardrails)
    check(guardrails["project_matching_records_written"] is False, "No project matches written", guardrails)
    check(guardrails["runtime_tables_written"] is False, "No runtime tables written", guardrails)
    check(guardrails["lookup_api_enabled"] is False, "Lookup remains disabled", guardrails)
    check(guardrails["android_behavior_changed"] is False, "Android unchanged", guardrails)

    print("=" * 72)
    print("NWDP CORE AGRO-ZONE SAMPLE OVERLAY REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

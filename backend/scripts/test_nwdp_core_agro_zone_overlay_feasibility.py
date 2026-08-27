#!/usr/bin/env python3
"""Regression for read-only NWDP × CoRE/agro-zone overlay feasibility audit."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv" / "bin" / "python"
SCRIPT = ROOT / "backend/scripts/audit_nwdp_core_agro_zone_overlay_feasibility.py"
OUTPUT = Path("/tmp/nwdp-core-agro-zone-overlay-feasibility-regression.json")


def check(condition: bool, label: str, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print("   ", json.dumps(detail, indent=2, default=str)[:1400])
    if not condition:
        raise AssertionError(label)


def main() -> int:
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

    check(OUTPUT.exists(), "Overlay feasibility audit writes output", proc.stdout)
    data = json.loads(OUTPUT.read_text(encoding="utf-8"))

    check(proc.returncode == 0, "Overlay feasibility audit exits zero", data)
    check(data["schema_version"] == "nwdp_core_agro_zone_overlay_feasibility_audit.v1", "Schema version is stable", data)
    check(data["mode"] == "READ_ONLY_OVERLAY_FEASIBILITY_AUDIT", "Audit is read-only", data)
    check(data["healthy"] is True, "Audit is healthy", data)

    layers = data["zone_layers"]
    check(len(layers) == 3, "Audit sees three normalized zone layers", layers)
    check(all(layer["healthy"] for layer in layers), "All zone layers are healthy", layers)
    check(any("Agro_Climatic_Zones" in layer["path"] and layer["feature_count"] == 15 for layer in layers), "Agro-climatic layer has 15 features", layers)
    check(any("Agro_Ecological_Zones" in layer["path"] and layer["feature_count"] == 20 for layer in layers), "Agro-ecological layer has 20 features", layers)
    check(any("Biogeographic_Zone" in layer["path"] and layer["feature_count"] == 26 for layer in layers), "Biogeographic layer has 26 polygon features", layers)

    nwdp = data["nwdp_candidate_summary"]
    check(nwdp["candidates"] == 654285, "Audit sees all NWDP candidates", nwdp)
    check(nwdp["active_candidates"] == 0, "NWDP candidates remain inactive", nwdp)
    check(nwdp["promoted_candidates"] == 0, "NWDP candidates remain unpromoted", nwdp)
    check(nwdp["safe_direct_auto_candidates"] > 0, "Audit sees safe/future NWDP village candidates", nwdp)
    check(nwdp["safe_direct_auto_villages"] > 0, "Audit sees matched NWDP villages", nwdp)

    geometry = data["nwdp_source_feature_geometry_metadata"]
    check(geometry["source_features"] == 654285, "Audit sees all NWDP source features", geometry)
    check(geometry["active_source_features"] == 0, "NWDP source features remain inactive", geometry)

    feasibility = data["feasibility"]
    check(feasibility["zone_layers_available"] is True, "Zone layers are available", feasibility)
    check(feasibility["safe_nwdp_village_matches_available"] is True, "Safe NWDP village matches are available", feasibility)
    check(feasibility["full_polygon_overlay_requires_raw_geojson_or_runtime_geometry"] is True, "Audit documents raw GeoJSON requirement", feasibility)

    guardrails = data["guardrails"]
    check(guardrails["db_writes_attempted"] is False, "Audit attempts no DB writes", guardrails)
    check(guardrails["core_zone_mappings_written"] is False, "Audit writes no CoRE mappings", guardrails)
    check(guardrails["nwdp_candidates_activated"] is False, "Audit does not activate NWDP candidates", guardrails)
    check(guardrails["nwdp_candidates_promoted"] is False, "Audit does not promote NWDP candidates", guardrails)
    check(guardrails["project_matching_records_written"] is False, "Audit writes no project matches", guardrails)
    check(guardrails["runtime_tables_written"] is False, "Audit writes no runtime tables", guardrails)
    check(guardrails["lookup_api_enabled"] is False, "Audit keeps lookup disabled", guardrails)
    check(guardrails["android_behavior_changed"] is False, "Audit keeps Android unchanged", guardrails)

    print("=" * 72)
    print("NWDP CORE AGRO-ZONE OVERLAY FEASIBILITY REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

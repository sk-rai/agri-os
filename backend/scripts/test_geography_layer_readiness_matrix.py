#!/usr/bin/env python3
"""Regression for read-only geography layer readiness matrix."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv/bin/python"
SCRIPT = ROOT / "backend/scripts/report_geography_layer_readiness_matrix.py"
OUT_DIR = Path("/tmp/geography-layer-readiness-matrix-regression")


def check(condition: bool, label: str, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:2400])
    if not condition:
        raise AssertionError(label)


def main() -> int:
    print("=" * 72)
    print("GEOGRAPHY LAYER READINESS MATRIX REGRESSION")
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
        timeout=240,
    )

    json_path = OUT_DIR / "geography_layer_readiness_matrix.json"
    csv_path = OUT_DIR / "geography_layer_readiness_matrix_by_district.csv"

    check(json_path.exists(), "Matrix writes JSON", proc.stdout)
    check(csv_path.exists(), "Matrix writes CSV", proc.stdout)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    summary = data["summary"]
    gap_accounting = data["gap_accounting"]

    check(proc.returncode == 0, "Matrix exits zero", data)
    check(data["schema_version"] == "geography_layer_readiness_matrix.v1", "Schema version is stable", data)
    check(data["mode"] == "READ_ONLY_STATE_DISTRICT_GEOGRAPHY_LAYER_READINESS_MATRIX", "Matrix is read-only", data)
    check(data["healthy"] is True, "Matrix is healthy", data)
    check(len(data["rows"]) > 0, "Matrix returns state/district rows", data["rows"][:3])

    check(summary["state_district_row_count"] > 0, "State/district row count is positive", summary)
    check(summary["lgd_village_count"] >= 500000, "LGD village coverage is visible", summary)
    check(summary["pin_linked_village_count"] >= 500000, "Village pin-code coverage is visible", summary)
    check(summary["demographic_profile_row_count"] >= 450000, "NWDP demographic admin layer is visible", summary)
    check(summary["demographic_active_promoted_count"] >= 450000, "Promoted demographic layer is visible", summary)
    check(summary["demographic_remaining_eligible_count"] == 0, "No demographic rows remain promotion-eligible", summary)
    check(summary["boundary_candidate_count"] >= 550000, "NWDP boundary candidate layer is visible in district matrix", summary)
    check(summary["boundary_runtime_feature_count"] >= 0, "Boundary runtime pilot count is readable", summary)
    check(summary["project_boundary_match_count"] >= 0, "Project boundary match count is readable", summary)
    check(summary["climate_mapping_count"] >= 0, "Climate mapping count is readable", summary)
    check(gap_accounting["boundary_candidate_raw_count"] >= summary["boundary_candidate_count"], "Boundary raw count covers matrix count", gap_accounting)
    check(gap_accounting["boundary_candidate_outside_state_district_matrix_count"] >= 0, "Boundary outside-matrix gap is reported", gap_accounting)
    check(gap_accounting["boundary_candidate_outside_state_district_matrix_count"] > 0, "Boundary outside-matrix gap is visible", gap_accounting)
    check(gap_accounting["demographic_profile_raw_count"] == summary["demographic_profile_row_count"], "Demographic profiles are fully placeable in matrix", gap_accounting)
    check(gap_accounting["pin_link_raw_count"] == summary["pin_link_count"], "Pin links are fully placeable in matrix", gap_accounting)

    posture = data["source_posture"]
    check(posture["lgd_is_canonical_runtime_identity"] is True, "LGD is canonical runtime identity", posture)
    check(posture["village_pin_codes_android_ready"] is True, "Village pin-code layer is Android-ready", posture)
    check(posture["nwdp_demographic_android_enabled"] is False, "NWDP demographic remains disabled for Android", posture)
    check(posture["nwdp_boundary_runtime_lookup_enabled"] is False, "NWDP boundary runtime lookup remains disabled", posture)
    check(posture["soi_direct_lgd_join_safe"] is False, "SOI direct LGD join remains unsafe", posture)
    check(posture["bharatlas_operational_review_source"] is True, "BharatAtlas remains operational review source", posture)

    guardrails = data["guardrails"]
    check(guardrails["db_writes_attempted"] is False, "Matrix attempts no DB writes", guardrails)
    check(guardrails["lgd_geography_overwritten"] is False, "Matrix does not overwrite LGD geography", guardrails)
    check(guardrails["runtime_lookup_enabled"] is False, "Matrix does not enable runtime lookup", guardrails)
    check(guardrails["android_behavior_changed"] is False, "Matrix does not change Android behavior", guardrails)
    check(guardrails["official_census_claimed_imported"] is False, "Matrix does not claim official Census import", guardrails)

    required_row_fields = {
        "state_or_ut",
        "district",
        "state_lgd_code",
        "district_lgd_code",
        "lgd_village_count",
        "pin_linked_village_count",
        "demographic_profile_row_count",
        "boundary_candidate_count",
        "boundary_direct_vlcode_match_count",
        "boundary_runtime_feature_count",
        "project_boundary_match_count",
        "climate_mapping_count",
        "crop_climate_rule_count",
        "lgd_runtime_ready",
        "pin_code_runtime_ready",
        "demographic_admin_ready",
        "demographic_android_enabled",
        "boundary_admin_review_ready",
        "boundary_runtime_ready",
        "soi_direct_join_safe",
        "bharatlas_operational_review_source",
    }
    check(required_row_fields.issubset(data["rows"][0].keys()), "Rows expose required layer fields", data["rows"][0])

    print("=" * 72)
    print("GEOGRAPHY LAYER READINESS MATRIX REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

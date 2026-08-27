#!/usr/bin/env python3
"""Regression for read-only NWDP × CoRE/agro-zone ambiguity reduction plan."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv" / "bin" / "python"
SCRIPT = ROOT / "backend/scripts/plan_nwdp_boundary_core_agro_zone_ambiguity_reduction.py"
OUTPUT = Path("/tmp/nwdp-boundary-core-agro-zone-ambiguity-reduction-plan-regression.json")


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

    check(OUTPUT.exists(), "Ambiguity reduction plan writes output", proc.stdout)
    data = json.loads(OUTPUT.read_text(encoding="utf-8"))

    check(proc.returncode == 0, "Ambiguity reduction plan exits zero", data)
    check(data["schema_version"] == "nwdp_boundary_core_agro_zone_ambiguity_reduction_plan.v1", "Schema version is stable", data)
    check(data["mode"] == "READ_ONLY_CORE_AGRO_ZONE_AMBIGUITY_REDUCTION_PLAN", "Plan is read-only", data)
    check(data["healthy"] is True, "Plan is healthy", data)

    inputs = data["input_layers"]
    check(inputs["existing_geography_master"]["known_count"] == 576083, "Plan references geography master village count", inputs)
    check(inputs["nwdp_boundary_staging"]["staged_candidate_count"] == 654285, "Plan references NWDP staged candidate count", inputs)
    check(inputs["nwdp_boundary_staging"]["safe_direct_auto_candidate_count"] == 313667, "Plan references safe direct auto count", inputs)
    check(inputs["core_or_agro_zone_layer"]["required"] is True, "Plan requires target agro/core zone layer", inputs)

    method = data["overlay_method"]
    check(method["operation"] == "area-weighted polygon intersection", "Plan uses area-weighted overlay", method)
    check(method["classification_rules"]["dominant_zone_threshold"] == 0.80, "Plan defines dominant-zone threshold", method)
    check(method["classification_rules"]["review_zone_threshold_min"] == 0.50, "Plan defines manual-review threshold", method)
    check(method["area_audit_required"] is True, "Plan requires area audit", method)

    policy = method["candidate_selection"]
    check(policy["candidate_bucket"] == "DIRECT_VLCODE_MATCH", "Plan uses direct-code candidates only", policy)
    check(policy["review_status"] == "AUTO_CANDIDATE", "Plan uses auto candidates only", policy)
    check(policy["required_is_active"] is False, "Plan requires inactive candidates", policy)
    check(policy["required_promotion_status"] == "NOT_PROMOTED", "Plan requires not-promoted candidates", policy)

    outputs = data["expected_outputs"]
    check(outputs["previously_ambiguous_count"] is True, "Plan reports previous ambiguity count", outputs)
    check(outputs["reduced_to_dominant_zone_count"] is True, "Plan reports reduced ambiguity count", outputs)
    check(outputs["still_multi_zone_unresolved_count"] is True, "Plan reports still-unresolved count", outputs)

    limits = data["why_this_reduces_ambiguity"]["remaining_limits"]
    check(any("do not contain climate" in item for item in limits), "Plan states NWDP cannot classify alone", limits)
    check(any("zone polygon/rule layer is still required" in item for item in limits), "Plan states zone layer is required", limits)

    guardrails = data["guardrails"]
    check(guardrails["db_writes_attempted"] is False, "Plan attempts no DB writes", guardrails)
    check(guardrails["core_zone_mappings_written"] is False, "Plan writes no CoRE zone mappings", guardrails)
    check(guardrails["nwdp_candidates_activated"] is False, "Plan does not activate NWDP candidates", guardrails)
    check(guardrails["nwdp_candidates_promoted"] is False, "Plan does not promote NWDP candidates", guardrails)
    check(guardrails["project_matching_records_written"] is False, "Plan writes no project matching records", guardrails)
    check(guardrails["runtime_tables_written"] is False, "Plan writes no runtime tables", guardrails)
    check(guardrails["lookup_api_enabled"] is False, "Plan keeps lookup disabled", guardrails)
    check(guardrails["android_behavior_changed"] is False, "Plan keeps Android unchanged", guardrails)

    readiness = data["readiness"]
    check(readiness["ready_for_read_only_overlay_analysis"] is True, "Plan is ready for read-only overlay analysis", readiness)
    check(readiness["ready_for_core_zone_mapping_apply"] is False, "Plan is not apply", readiness)
    check(readiness["ready_for_android_behavior_change"] is False, "Plan does not change Android", readiness)

    print("=" * 72)
    print("NWDP BOUNDARY CORE AGRO-ZONE AMBIGUITY REDUCTION PLAN REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

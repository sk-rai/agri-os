#!/usr/bin/env python3
"""Regression for disabled admin preview endpoint plan for NWDP demographic profiles."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv" / "bin" / "python"
SCRIPT = ROOT / "backend/scripts/plan_nwdp_demographic_admin_preview_endpoint.py"
OUTPUT = Path("/tmp/nwdp-demographic-admin-preview-endpoint-plan-regression.json")


def check(condition: bool, label: str, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:1600])
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

    check(OUTPUT.exists(), "Preview endpoint plan writes output", proc.stdout)
    data = json.loads(OUTPUT.read_text(encoding="utf-8"))

    check(proc.returncode == 0, "Preview endpoint plan exits zero", data)
    check(data["schema_version"] == "nwdp_demographic_admin_preview_endpoint_plan.v1", "Schema version is stable", data)
    check(data["mode"] == "READ_ONLY_DISABLED_ADMIN_PREVIEW_ENDPOINT_PLAN", "Plan is read-only disabled endpoint", data)
    check(data["healthy"] is True, "Plan is healthy", data)
    check(data["target_endpoint"] == "GET /api/v1/master-data/geography/nwdp-demographic-profiles/preview", "Endpoint path is stable", data)
    check(data["target_table"] == "geography_village_demographic_profiles", "Endpoint reads profile table", data)
    check(data["status"] == "planned_disabled_until_profile_import", "Endpoint remains disabled until import", data)

    behavior = data["intended_behavior"]
    empty = behavior["default_response_when_empty"]
    check(behavior["method"] == "GET", "Endpoint is GET", behavior)
    check(behavior["writes_db"] is False, "Endpoint writes no DB rows", behavior)
    check(empty["enabled"] is False, "Empty response is disabled", empty)
    check(empty["reason"] == "NO_DEMOGRAPHIC_PROFILE_ROWS_IMPORTED", "Empty response reason is explicit", empty)
    check(empty["profile_row_count"] == 0, "Empty response has zero profiles", empty)
    check(empty["ready_for_profile_apply"] is False, "Preview is not profile apply", empty)
    check(empty["ready_for_android_behavior_change"] is False, "Preview is not Android change", empty)

    fields = set(behavior["future_preview_fields"])
    for field in ["state_or_ut", "source_system", "source_version", "source_vlcode", "total_population", "total_households", "promotion_status", "is_active"]:
        check(field in fields, f"Future preview field planned: {field}")

    notes = data["implementation_notes"]
    check(any("Do not expose this to Android" in item for item in notes), "Plan keeps endpoint out of Android runtime", notes)
    check(any("Do not claim official Census" in item for item in notes), "Plan keeps Census claim separate", notes)

    guardrails = data["guardrails"]
    check(all(value is False for value in guardrails.values()), "All guardrails remain false", guardrails)
    check(guardrails["endpoint_implemented"] is False, "Endpoint not implemented yet", guardrails)
    check(guardrails["demographic_profile_rows_written"] is False, "No profiles written", guardrails)
    check(guardrails["runtime_lookup_enabled"] is False, "Runtime lookup disabled", guardrails)
    check(guardrails["android_behavior_changed"] is False, "Android unchanged", guardrails)

    readiness = data["readiness"]
    check(readiness["ready_for_endpoint_implementation"] is True, "Ready for endpoint implementation", readiness)
    check(readiness["ready_for_profile_import_apply"] is False, "Not ready for profile import apply", readiness)
    check(readiness["ready_for_runtime_lookup_enablement"] is False, "Not ready for runtime lookup", readiness)
    check(readiness["ready_for_android_behavior_change"] is False, "Not ready for Android", readiness)

    print("=" * 72)
    print("NWDP DEMOGRAPHIC ADMIN PREVIEW ENDPOINT PLAN REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

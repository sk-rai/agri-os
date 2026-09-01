#!/usr/bin/env python3
"""Regression for disabled NWDP demographic profile promotion apply guard."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv/bin/python"
SCRIPT = ROOT / "backend/scripts/apply_nwdp_demographic_profile_promotion.py"
OUTPUT = Path("/tmp/nwdp-demographic-profile-promotion-apply-disabled-regression.json")


def check(condition, label, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:2200])
    if not condition:
        raise AssertionError(label)


def run(args):
    if OUTPUT.exists():
        OUTPUT.unlink()
    proc = subprocess.run(
        [str(PYTHON), str(SCRIPT), *args, "--output", str(OUTPUT)],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=30,
    )
    check(OUTPUT.exists(), "Promotion apply guard writes audit output", proc.stdout)
    return proc.returncode, json.loads(OUTPUT.read_text(encoding="utf-8"))


def assert_no_mutation(data):
    check(data["before"]["profile_row_count"] == data["after"]["profile_row_count"], "Profile row count unchanged", data)
    check(data["before"]["active_profile_row_count"] == data["after"]["active_profile_row_count"], "Active count unchanged", data)
    check(data["before"]["promoted_profile_row_count"] == data["after"]["promoted_profile_row_count"], "Promoted count unchanged", data)

    guardrails = data["guardrails"]
    check(guardrails["db_writes_attempted"] is False, "Guard writes no DB rows", guardrails)
    check(guardrails["profile_review_status_changed"] is False, "Guard changes no review status", guardrails)
    check(guardrails["profiles_promoted"] is False, "Guard promotes no profiles", guardrails)
    check(guardrails["profile_rows_activated"] is False, "Guard activates no profiles", guardrails)
    check(guardrails["runtime_lookup_enabled"] is False, "Runtime lookup remains disabled", guardrails)
    check(guardrails["android_behavior_changed"] is False, "Android remains unchanged", guardrails)


def main() -> int:
    print("=" * 72)
    print("NWDP DEMOGRAPHIC PROFILE PROMOTION APPLY DISABLED REGRESSION")
    print("=" * 72)

    code, no_apply = run(["--state-or-ut", "Promotion Fixture State", "--district", "Promotion Fixture District"])
    check(code != 0, "Missing apply flag exits non-zero", no_apply)
    check(no_apply["error"] == "NWDP_DEMOGRAPHIC_PROFILE_PROMOTION_APPLY_REQUIRES_EXPLICIT_APPLY_FLAG", "Missing apply flag error is explicit", no_apply)
    assert_no_mutation(no_apply)

    code, no_scope = run(["--apply"])
    check(code != 0, "Missing state/district scope exits non-zero", no_scope)
    check(no_scope["error"] == "NWDP_DEMOGRAPHIC_PROFILE_PROMOTION_APPLY_REQUIRES_STATE_AND_DISTRICT_SCOPE", "Missing scope error is explicit", no_scope)
    check(no_scope["scope"]["state_and_district_scope_required"] is True, "State/district scope is required", no_scope["scope"])
    assert_no_mutation(no_scope)

    code, disabled = run(["--apply", "--state-or-ut", "Andaman & Nicobar Island", "--district", "Nicobars"])
    check(code != 0, "Disabled apply exits non-zero", disabled)
    check(disabled["schema_version"] == "nwdp_demographic_profile_promotion_apply.v1", "Schema version is stable", disabled)
    check(disabled["mode"] == "PROMOTION_APPLY_DISABLED_GUARD", "Mode is disabled guard", disabled)
    check(disabled["error"] == "NWDP_DEMOGRAPHIC_PROFILE_PROMOTION_APPLY_DISABLED_BY_POLICY", "Disabled policy error is explicit", disabled)
    check(disabled["scope"]["state_and_district_scope_present"] is True, "Scoped disabled apply records scope", disabled["scope"])

    policy = disabled["selection_policy"]
    check(policy["required_review_status"] == "APPROVED_FOR_PROMOTION", "Promotion requires approved review status", policy)
    check(policy["required_promotion_status"] == "NOT_PROMOTED", "Promotion requires not-promoted status", policy)
    check(policy["required_is_active"] is False, "Promotion requires inactive profile", policy)
    check(policy["dry_run_required_before_apply"] is True, "Promotion requires dry-run before apply", policy)

    result = disabled["apply_result"]
    check(result["apply_implemented"] is False, "Apply implementation remains disabled", result)
    check(result["promoted_count"] == 0, "Disabled apply promotes zero rows", result)
    check(result["activated_count"] == 0, "Disabled apply activates zero rows", result)

    readiness = disabled["readiness"]
    check(readiness["ready_for_profile_promotion_apply"] is False, "Not ready for promotion apply", readiness)
    check(readiness["ready_for_tiny_fixture_promotion_apply_regression"] is True, "Ready for tiny fixture promotion apply regression", readiness)
    check(readiness["ready_for_runtime_lookup_enablement"] is False, "Not ready for runtime lookup", readiness)
    check(readiness["ready_for_android_behavior_change"] is False, "Not ready for Android change", readiness)

    assert_no_mutation(disabled)

    print("=" * 72)
    print("NWDP DEMOGRAPHIC PROFILE PROMOTION APPLY DISABLED REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

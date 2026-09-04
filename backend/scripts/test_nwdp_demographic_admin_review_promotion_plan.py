#!/usr/bin/env python3
"""Regression for NWDP demographic admin review/promotion plan."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv/bin/python"
SCRIPT = ROOT / "backend/scripts/plan_nwdp_demographic_admin_review_promotion.py"
OUTPUT = Path("/tmp/nwdp-demographic-admin-review-promotion-plan-regression.json")


def check(condition, label, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:1800])
    if not condition:
        raise AssertionError(label)


def main() -> int:
    print("=" * 72)
    print("NWDP DEMOGRAPHIC ADMIN REVIEW/PROMOTION PLAN REGRESSION")
    print("=" * 72)

    proc = subprocess.run([
        str(PYTHON), str(SCRIPT),
        "--state-or-ut", "Andaman & Nicobar Island",
        "--district", "Nicobars",
        "--limit", "20",
        "--output", str(OUTPUT),
    ], cwd=str(ROOT), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False, timeout=30)

    check(OUTPUT.exists(), "Plan writes audit output", proc.stdout)
    data = json.loads(OUTPUT.read_text(encoding="utf-8"))

    check(proc.returncode == 0, "Plan exits zero", data)
    check(data["schema_version"] == "nwdp_demographic_admin_review_promotion_plan.v1", "Schema version is stable", data)
    check(data["mode"] == "READ_ONLY_ADMIN_REVIEW_PROMOTION_PLAN", "Plan is read-only", data)
    check(data["healthy"] is True, "Plan is healthy", data)
    check(data["target_table"] == "geography_village_demographic_profiles", "Target table is explicit", data)

    summary = data["summary"]
    check(summary["profile_row_count"] == 162, "Nicobars profile count is stable", summary)
    check(summary["active_profile_row_count"] >= 0, "Active profile count is readable", summary)
    check(summary["promoted_profile_row_count"] >= 0, "Promoted profile count is readable", summary)
    check(summary["auto_candidate_count"] >= 0, "Auto-candidate queue count is readable", summary)
    check(summary["review_queue_candidate_count"] >= 0, "Review queue count is readable", summary)
    check(summary["promotion_queue_candidate_count"] >= 0, "Promotion queue count is readable", summary)

    check(data["approved_vs_manual_review"] == {
        "approved_for_promotion_count": summary["approved_for_promotion_count"],
        "manual_review_count": summary["manual_review_count"],
    }, "Approved versus manual review counts match summary", data["approved_vs_manual_review"])

    row = data["state_district_summary"][0]
    check(row["state_or_ut"] == "Andaman & Nicobar Island", "State/district summary includes state", row)
    check(row["district"] == "Nicobars", "State/district summary includes district", row)
    check(row["profile_row_count"] == 162, "State/district summary includes profile count", row)

    review_policy = data["review_policy"]
    check(review_policy["admin_should_analyze_by_state_district"] is True, "Admin analysis is state/district scoped", review_policy)
    check(review_policy["bulk_review_without_state_or_district_filter_allowed"] is False, "Bulk review requires scope", review_policy)
    check("APPROVED_FOR_PROMOTION" in review_policy["allowed_future_review_statuses"], "Approval status is planned", review_policy)
    check("MANUAL_REVIEW" in review_policy["allowed_future_review_statuses"], "Manual review status is planned", review_policy)

    promotion_policy = data["promotion_policy"]
    check(promotion_policy["promotion_supported_by_this_plan"] is False, "Plan does not promote", promotion_policy)
    check(promotion_policy["promotion_requires_separate_dry_run"] is True, "Promotion needs separate dry-run", promotion_policy)
    check(promotion_policy["promotion_requires_separate_apply_checkpoint"] is True, "Promotion needs separate apply checkpoint", promotion_policy)
    check(promotion_policy["required_review_status_for_future_promotion"] == "APPROVED_FOR_PROMOTION", "Future promotion requires approval", promotion_policy)

    guardrails = data["guardrails"]
    check(guardrails["db_writes_attempted"] is False, "Plan attempts no DB writes", guardrails)
    check(guardrails["profile_review_status_changed"] is False, "Plan changes no review status", guardrails)
    check(guardrails["profiles_promoted"] is False, "Plan promotes no profiles", guardrails)
    check(guardrails["profile_rows_activated"] is False, "Plan activates no profiles", guardrails)
    check(guardrails["runtime_lookup_enabled"] is False, "Runtime lookup remains disabled", guardrails)
    check(guardrails["android_behavior_changed"] is False, "Android remains unchanged", guardrails)

    readiness = data["readiness"]
    check(readiness["ready_for_admin_review_endpoint_design"] in (True, False), "Admin review endpoint design readiness is reported", readiness)
    check(readiness["ready_for_promotion_dry_run_design"] in (True, False), "Promotion dry-run design readiness is reported", readiness)
    check(readiness["ready_for_profile_promotion_apply"] is False, "Not ready for promotion apply", readiness)
    check(readiness["ready_for_runtime_lookup_enablement"] is False, "Not ready for runtime lookup", readiness)
    check(readiness["ready_for_android_behavior_change"] is False, "Not ready for Android", readiness)

    print("=" * 72)
    print("NWDP DEMOGRAPHIC ADMIN REVIEW/PROMOTION PLAN REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

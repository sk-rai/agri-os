#!/usr/bin/env python3
"""Regression for NWDP demographic promotion readiness report."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv/bin/python"
SCRIPT = ROOT / "backend/scripts/report_nwdp_demographic_promotion_readiness.py"
OUT_DIR = Path("/tmp/nwdp-demographic-promotion-readiness-regression")


def check(condition, label, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:2200])
    if not condition:
        raise AssertionError(label)


def main() -> int:
    print("=" * 72)
    print("NWDP DEMOGRAPHIC PROMOTION READINESS REPORT REGRESSION")
    print("=" * 72)

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)

    proc = subprocess.run([
        str(PYTHON),
        str(SCRIPT),
        "--state-or-ut",
        "Andaman & Nicobar Island",
        "--output-dir",
        str(OUT_DIR),
    ], cwd=str(ROOT), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False, timeout=30)

    json_path = OUT_DIR / "nwdp_demographic_promotion_readiness_report.json"
    csv_path = OUT_DIR / "nwdp_demographic_promotion_readiness_by_district.csv"

    check(json_path.exists(), "Readiness report writes JSON", proc.stdout)
    check(csv_path.exists(), "Readiness report writes CSV", proc.stdout)

    data = json.loads(json_path.read_text(encoding="utf-8"))

    check(proc.returncode == 0, "Readiness report exits zero", data)
    check(data["schema_version"] == "nwdp_demographic_promotion_readiness_report.v1", "Schema version is stable", data)
    check(data["mode"] == "READ_ONLY_STATE_DISTRICT_PROMOTION_READINESS_REPORT", "Report is read-only", data)
    check(data["healthy"] is True, "Report is healthy", data)

    summary = data["summary"]
    check(summary["profile_row_count"] == 512, "Andaman profile total is stable", summary)
    expected_approved = 5 if summary["profile_row_count"] == 512 else 0
    expected_eligible = 0
    expected_not_eligible = summary["profile_row_count"] - expected_eligible
    check(summary["eligible_for_promotion_count"] == expected_eligible, "Eligible rows match current approval checkpoint", summary)
    check(summary["not_eligible_for_promotion_count"] == expected_not_eligible, "Not-eligible rows match current approval checkpoint", summary)
    check(summary["auto_candidate_count"] == summary["profile_row_count"] - expected_approved, "Auto-candidate rows match current promotion checkpoint", summary)
    check(summary["manual_review_count"] == 0, "No manual-review rows in Andaman imported state", summary)
    check(summary["approved_for_promotion_count"] == expected_approved, "Approved rows match current promotion checkpoint", summary)
    check(summary["active_profile_row_count"] == expected_approved, "Active rows match current promotion checkpoint", summary)
    check(summary["promoted_profile_row_count"] == expected_approved, "Promoted rows match current promotion checkpoint", summary)

    rows = data["state_district_summary"]
    check(len(rows) == 3, "Andaman report has three district rows", rows)
    check(sum(row["profile_row_count"] for row in rows) == 512, "District rows sum to Andaman total", rows)
    check(sum(row["eligible_for_promotion_count"] for row in rows) == expected_eligible, "District eligible counts match current approval checkpoint", rows)
    check(sum(row["not_eligible_for_promotion_count"] for row in rows) == expected_not_eligible, "District not-eligible counts match current approval checkpoint", rows)
    check(sum(row["auto_candidate_count"] for row in rows) == summary["profile_row_count"] - expected_approved, "District auto-candidate counts match current promotion checkpoint", rows)

    policy = data["eligibility_policy"]
    check(policy["eligible_requires_review_status"] == "APPROVED_FOR_PROMOTION", "Eligibility requires approval", policy)
    check(policy["eligible_requires_promotion_status"] == "NOT_PROMOTED", "Eligibility requires not promoted", policy)
    check(policy["eligible_requires_is_active"] is False, "Eligibility requires inactive", policy)

    guardrails = data["guardrails"]
    check(guardrails["db_writes_attempted"] is False, "Report writes no DB rows", guardrails)
    check(guardrails["profile_review_status_changed"] is False, "Report changes no review status", guardrails)
    check(guardrails["profiles_promoted"] is False, "Report promotes no profiles", guardrails)
    check(guardrails["profile_rows_activated"] is False, "Report activates no rows", guardrails)
    check(guardrails["runtime_lookup_enabled"] is False, "Runtime lookup remains disabled", guardrails)
    check(guardrails["android_behavior_changed"] is False, "Android remains unchanged", guardrails)

    readiness = data["readiness"]
    check(readiness["ready_for_admin_review_prioritization"] is True, "Ready for admin review prioritization", readiness)
    expected_ready_for_dry_run = data["summary"]["eligible_for_promotion_count"] > 0
    check(readiness["ready_for_promotion_dry_run"] is expected_ready_for_dry_run, "Promotion dry-run readiness matches approved checkpoint", readiness)
    check(readiness["ready_for_profile_promotion_apply"] is False, "Not ready for promotion apply", readiness)
    check(readiness["ready_for_runtime_lookup_enablement"] is False, "Not ready for runtime lookup", readiness)
    check(readiness["ready_for_android_behavior_change"] is False, "Not ready for Android", readiness)

    print("=" * 72)
    print("NWDP DEMOGRAPHIC PROMOTION READINESS REPORT REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

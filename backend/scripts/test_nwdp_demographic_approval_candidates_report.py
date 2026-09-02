#!/usr/bin/env python3
"""Regression for NWDP demographic approval candidate report."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv/bin/python"
SCRIPT = ROOT / "backend/scripts/report_nwdp_demographic_approval_candidates.py"
OUT_DIR = Path("/tmp/nwdp-demographic-approval-candidates-regression")


def check(condition, label, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:2200])
    if not condition:
        raise AssertionError(label)


def main() -> int:
    print("=" * 72)
    print("NWDP DEMOGRAPHIC APPROVAL CANDIDATES REPORT REGRESSION")
    print("=" * 72)

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)

    proc = subprocess.run([
        str(PYTHON),
        str(SCRIPT),
        "--state-or-ut",
        "Andaman & Nicobar Island",
        "--district",
        "South Andamans",
        "--limit",
        "25",
        "--output-dir",
        str(OUT_DIR),
    ], cwd=str(ROOT), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False, timeout=30)

    json_files = list(OUT_DIR.glob("*approval_candidates.json"))
    csv_files = list(OUT_DIR.glob("*approval_candidates.csv"))
    check(len(json_files) == 1, "Approval candidate report writes one JSON", proc.stdout)
    check(len(csv_files) == 1, "Approval candidate report writes one CSV", proc.stdout)

    data = json.loads(json_files[0].read_text(encoding="utf-8"))

    check(proc.returncode == 0, "Approval candidate report exits zero", data)
    check(data["schema_version"] == "nwdp_demographic_approval_candidates_report.v1", "Schema version is stable", data)
    check(data["mode"] == "READ_ONLY_APPROVAL_CANDIDATE_REPORT", "Report is read-only", data)
    check(data["healthy"] is True, "Report is healthy", data)

    filters = data["filters"]
    check(filters["state_or_ut"] == "Andaman & Nicobar Island", "Report records state filter", filters)
    check(filters["district"] == "South Andamans", "Report records district filter", filters)

    summary = data["summary"]
    check(summary["profile_row_count"] == 123, "South Andamans profile count is stable", summary)
    expected_approved = 5 if summary["profile_row_count"] == 123 else 0
    expected_candidates = summary["profile_row_count"] - expected_approved
    check(summary["approval_candidate_count"] == expected_candidates, "South Andamans approval candidates match current checkpoint", summary)
    check(summary["manual_review_count"] == 0, "No manual-review rows yet", summary)
    check(summary["approved_for_promotion_count"] == expected_approved, "Approved count matches current checkpoint", summary)
    check(summary["active_profile_row_count"] == expected_approved, "Active rows match promoted checkpoint", summary)
    check(summary["promoted_profile_row_count"] == expected_approved, "Promoted rows match promoted checkpoint", summary)
    check(summary["approval_candidate_ratio"] == expected_candidates / summary["profile_row_count"], "Approval candidate ratio matches current checkpoint", summary)

    policy = data["approval_policy"]
    check(policy["approval_candidates_require_review_status"] == "AUTO_CANDIDATE", "Approval candidates require auto-candidate status", policy)
    check(policy["approval_candidates_require_promotion_status"] == "NOT_PROMOTED", "Approval candidates require not-promoted status", policy)
    check(policy["approval_candidates_require_is_active"] is False, "Approval candidates require inactive rows", policy)
    check(policy["state_and_district_scope_required"] is True, "Approval report is scoped", policy)
    check(policy["bulk_approval_apply_supported_by_this_report"] is False, "Report does not apply approval", policy)

    items = data["items"]
    check(len(items) == 25, "Report respects item limit", items[:2])
    check(all(item["review_status"] == "AUTO_CANDIDATE" for item in items), "Items are auto-candidate", items[:2])
    check(all(item["promotion_status"] == "NOT_PROMOTED" for item in items), "Items are not promoted", items[:2])
    check(all(item["is_active"] is False for item in items), "Items are inactive", items[:2])

    guardrails = data["guardrails"]
    check(guardrails["db_writes_attempted"] is False, "Report writes no DB rows", guardrails)
    check(guardrails["profile_review_status_changed"] is False, "Report changes no review status", guardrails)
    check(guardrails["profiles_promoted"] is False, "Report promotes no profiles", guardrails)
    check(guardrails["profile_rows_activated"] is False, "Report activates no rows", guardrails)
    check(guardrails["runtime_lookup_enabled"] is False, "Runtime lookup remains disabled", guardrails)
    check(guardrails["android_behavior_changed"] is False, "Android remains unchanged", guardrails)

    readiness = data["readiness"]
    check(readiness["ready_for_scoped_admin_approval_plan"] is True, "Ready for scoped admin approval plan", readiness)
    check(readiness["ready_for_bulk_approval_apply"] is False, "Not ready for bulk approval apply", readiness)
    check(readiness["ready_for_promotion_dry_run"] is False, "Not ready for promotion dry-run", readiness)
    check(readiness["ready_for_profile_promotion_apply"] is False, "Not ready for promotion apply", readiness)

    print("=" * 72)
    print("NWDP DEMOGRAPHIC APPROVAL CANDIDATES REPORT REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

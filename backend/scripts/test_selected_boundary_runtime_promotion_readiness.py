#!/usr/bin/env python3
"""Regression for selected NWDP boundary runtime promotion readiness report."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = Path("/tmp/selected-boundary-runtime-promotion-readiness-regression")


def check(condition: bool, label: str, detail=None) -> None:
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:3000])
    if not condition:
        raise AssertionError(label)


def main() -> int:
    print("=" * 72)
    print("SELECTED BOUNDARY RUNTIME PROMOTION READINESS REGRESSION")
    print("=" * 72)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "backend/scripts/report_selected_boundary_runtime_promotion_readiness.py"),
            "--output-dir",
            str(OUT_DIR),
            "--limit",
            "50",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=120,
    )

    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr)

    check(proc.returncode == 0, "Readiness report exits zero", {"returncode": proc.returncode, "stderr": proc.stderr[-2000:]})

    json_path = OUT_DIR / "selected_boundary_runtime_promotion_readiness.json"
    state_csv = OUT_DIR / "selected_boundary_runtime_promotion_readiness_by_state_district.csv"
    sample_csv = OUT_DIR / "selected_boundary_runtime_promotion_readiness_samples.csv"

    check(json_path.exists(), "Report writes JSON", str(json_path))
    check(state_csv.exists(), "Report writes state/district CSV", str(state_csv))
    check(sample_csv.exists(), "Report writes sample CSV", str(sample_csv))

    data = json.loads(json_path.read_text(encoding="utf-8"))
    summary = data["summary"]
    readiness = data["readiness"]
    policy = data["promotion_policy"]
    guardrails = data["guardrails"]

    check(data["schema_version"] == "selected_boundary_runtime_promotion_readiness.v1", "Schema version is stable", data)
    check(data["mode"] == "READ_ONLY_SELECTED_BOUNDARY_RUNTIME_PROMOTION_READINESS", "Report is read-only mode", data)
    check(data["healthy"] is True, "Report is healthy", data)

    check(summary["candidate_count"] > 0, "NWDP boundary candidates are visible", summary)
    check(summary["direct_vlcode_match_count"] > 0, "Direct VLCode candidates are visible", summary)
    check(summary["auto_candidate_count"] > 0, "Auto candidates are visible", summary)
    check(summary["manual_review_count"] >= 0, "Manual review count is readable", summary)
    check(summary["blocked_count"] >= 0, "Blocked count is readable", summary)
    check(summary["selected_runtime_promotable_count"] >= 0, "Selected promotable count is readable", summary)
    check(summary["existing_runtime_set_count"] >= 0, "Runtime set count is readable", summary)
    check(summary["existing_runtime_feature_count"] >= 0, "Runtime feature count is readable", summary)
    check(summary["existing_runtime_crosswalk_count"] >= 0, "Runtime crosswalk count is readable", summary)

    check(policy["required_candidate_bucket"] == "DIRECT_VLCODE_MATCH", "Policy requires direct code match", policy)
    check(policy["required_review_status"] == "AUTO_CANDIDATE", "Policy requires auto candidate", policy)
    check(policy["required_promotion_status"] == "NOT_PROMOTED", "Policy requires not-promoted", policy)
    check(policy["requires_runtime_eligible_source"] is True, "Policy requires runtime-eligible source", policy)
    check(policy["requires_valid_geometry"] is True, "Policy requires valid geometry", policy)
    check(policy["manual_review_candidates_excluded"] is True, "Manual review is excluded", policy)
    check(policy["blocked_candidates_excluded"] is True, "Blocked is excluded", policy)
    check(policy["real_apply_supported_by_this_report"] is False, "Report does not support real apply", policy)

    check(readiness["ready_for_selected_runtime_promotion_dry_run"] == (summary["selected_runtime_promotable_count"] > 0), "Dry-run readiness follows selected count", readiness)
    check(readiness["ready_for_selected_runtime_promotion_apply"] is False, "Apply remains disabled", readiness)
    check(readiness["ready_for_runtime_lookup_enablement"] is False, "Runtime lookup remains disabled", readiness)
    check(readiness["ready_for_android_behavior_change"] is False, "Android remains unchanged", readiness)
    check(readiness["requires_rollback_or_supersession_plan"] is True, "Rollback/supersession plan is required", readiness)

    check(guardrails["db_writes_attempted"] is False, "Report attempts no DB writes", guardrails)
    check(guardrails["runtime_sets_written"] is False, "Report writes no runtime sets", guardrails)
    check(guardrails["runtime_features_written"] is False, "Report writes no runtime features", guardrails)
    check(guardrails["runtime_crosswalks_written"] is False, "Report writes no runtime crosswalks", guardrails)
    check(guardrails["promotion_events_written"] is False, "Report writes no promotion events", guardrails)
    check(guardrails["candidates_promoted"] is False, "Report promotes no candidates", guardrails)
    check(guardrails["candidates_activated"] is False, "Report activates no candidates", guardrails)
    check(guardrails["runtime_lookup_enabled"] is False, "Report keeps lookup disabled", guardrails)
    check(guardrails["android_behavior_changed"] is False, "Report keeps Android unchanged", guardrails)
    check(guardrails["lgd_geography_overwritten"] is False, "Report does not overwrite LGD", guardrails)

    check(isinstance(data["state_district_rows"], list), "State/district rows are emitted", data["state_district_rows"][:3])
    check(isinstance(data["selected_candidate_samples"], list), "Candidate samples are emitted", data["selected_candidate_samples"][:3])

    print("=" * 72)
    print("SELECTED BOUNDARY RUNTIME PROMOTION READINESS REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

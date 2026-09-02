#!/usr/bin/env python3
"""Regression for disabled NWDP demographic review approval apply guard."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
PYTHON = ROOT / "venv" / "bin" / "python"

sys.path.insert(0, str(BACKEND))

from scripts.apply_nwdp_demographic_profile_import import SOURCE_SYSTEM, SOURCE_VERSION, load_settings_url  # noqa: E402

SCRIPT = BACKEND / "scripts/apply_nwdp_demographic_profile_review_approval.py"
OUTPUT = Path("/tmp/nwdp-demographic-profile-review-approval-apply-disabled-regression.json")
TARGET_TABLE = "geography_village_demographic_profiles"
STATE = "Andaman & Nicobar Island"
DISTRICT = "South Andamans"


def check(condition: bool, label: str, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:2400])
    if not condition:
        raise AssertionError(label)


def profile_counts() -> dict:
    engine = create_engine(load_settings_url())
    with engine.connect() as conn:
        return dict(conn.execute(text(f"""
            select
              count(*)::bigint as profile_row_count,
              count(*) filter (where review_status = 'AUTO_CANDIDATE')::bigint as auto_candidate_count,
              count(*) filter (where review_status = 'APPROVED_FOR_PROMOTION')::bigint as approved_for_promotion_count,
              count(*) filter (where is_active = true)::bigint as active_profile_row_count,
              count(*) filter (where promotion_status = 'PROMOTED')::bigint as promoted_profile_row_count
            from {TARGET_TABLE}
            where source_system = :source_system
              and source_version = :source_version
              and source_state_name = :state
              and source_district_name = :district
        """), {
            "source_system": SOURCE_SYSTEM,
            "source_version": SOURCE_VERSION,
            "state": STATE,
            "district": DISTRICT,
        }).mappings().one())


def run_guard(*extra_args: str) -> tuple[int, dict]:
    if OUTPUT.exists():
        OUTPUT.unlink()

    proc = subprocess.run(
        [str(PYTHON), str(SCRIPT), *extra_args, "--output", str(OUTPUT)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    check(OUTPUT.exists(), "Approval guard writes audit output", proc.stdout or proc.stderr)
    data = json.loads(OUTPUT.read_text(encoding="utf-8"))
    data["returncode"] = proc.returncode
    return proc.returncode, data


def assert_no_mutation(data: dict, before: dict):
    after = profile_counts()
    check(after == before, "Profile counts remain unchanged", {"before": before, "after": after})
    check(data["guardrails"]["db_writes_attempted"] is False, "Guard attempts no DB writes", data["guardrails"])
    check(data["guardrails"]["profile_review_status_changed"] is False, "Guard changes no review status", data["guardrails"])
    check(data["guardrails"]["profiles_promoted"] is False, "Guard promotes no profiles", data["guardrails"])
    check(data["guardrails"]["profile_rows_activated"] is False, "Guard activates no rows", data["guardrails"])
    check(data["guardrails"]["runtime_lookup_enabled"] is False, "Runtime lookup remains disabled", data["guardrails"])
    check(data["guardrails"]["android_behavior_changed"] is False, "Android remains unchanged", data["guardrails"])


def main() -> int:
    print("=" * 72)
    print("NWDP DEMOGRAPHIC PROFILE REVIEW APPROVAL APPLY DISABLED REGRESSION")
    print("=" * 72)

    before = profile_counts()
    check(before["profile_row_count"] == 123, "South Andamans profile count is stable", before)
    check(before["auto_candidate_count"] == 118, "South Andamans remaining candidates stay auto-candidate", before)
    check(before["approved_for_promotion_count"] == 5, "South Andamans approval checkpoint has five approved rows", before)
    check(before["active_profile_row_count"] == 5, "South Andamans has five active demographic profiles", before)
    check(before["promoted_profile_row_count"] == 5, "South Andamans has five promoted demographic profiles", before)

    code, no_apply = run_guard(
        "--state-or-ut", STATE,
        "--district", DISTRICT,
        "--reviewer-notes", "approval guard regression",
        "--max-rows", "5",
    )
    check(code != 0, "No-apply guard exits non-zero", no_apply)
    check(no_apply["error"] == "NWDP_DEMOGRAPHIC_PROFILE_REVIEW_APPROVAL_APPLY_REQUIRES_EXPLICIT_APPLY_FLAG", "Explicit apply flag is required", no_apply)
    assert_no_mutation(no_apply, before)

    code, no_scope = run_guard(
        "--apply",
        "--reviewer-notes", "approval guard regression",
        "--max-rows", "5",
    )
    check(code != 0, "No-scope guard exits non-zero", no_scope)
    check(no_scope["error"] == "NWDP_DEMOGRAPHIC_PROFILE_REVIEW_APPROVAL_APPLY_REQUIRES_STATE_AND_DISTRICT_SCOPE", "State/district scope is required", no_scope)
    assert_no_mutation(no_scope, before)

    code, no_notes = run_guard(
        "--apply",
        "--state-or-ut", STATE,
        "--district", DISTRICT,
        "--max-rows", "5",
    )
    check(code != 0, "No-notes guard exits non-zero", no_notes)
    check(no_notes["error"] == "NWDP_DEMOGRAPHIC_PROFILE_REVIEW_APPROVAL_APPLY_REQUIRES_REVIEWER_NOTES", "Reviewer notes are required", no_notes)
    assert_no_mutation(no_notes, before)

    code, disabled = run_guard(
        "--apply",
        "--state-or-ut", STATE,
        "--district", DISTRICT,
        "--reviewer-notes", "approval guard regression",
        "--max-rows", "5",
    )
    check(code != 0, "Disabled approval apply exits non-zero", disabled)
    check(disabled["schema_version"] == "nwdp_demographic_profile_review_approval_apply.v1", "Schema version is stable", disabled)
    check(disabled["error"] == "NWDP_DEMOGRAPHIC_PROFILE_REVIEW_APPROVAL_APPLY_DISABLED_BY_POLICY", "Approval apply is disabled by policy", disabled)
    check(disabled["scope"]["state_and_district_scope_present"] is True, "Guard records state/district scope", disabled["scope"])
    check(disabled["approval_summary"]["candidate_profile_row_count"] == 118, "Guard sees 118 remaining scoped candidates", disabled["approval_summary"])
    check(disabled["approval_summary"]["planned_approval_count"] == 5, "Guard honors max-row planning", disabled["approval_summary"])
    check(disabled["apply_result"]["apply_implemented"] is False, "Apply remains unimplemented", disabled["apply_result"])
    check(disabled["apply_result"]["approved_count"] == 0, "No rows are approved", disabled["apply_result"])
    check(len(disabled["sample_items"]) > 0, "Guard returns sample candidate items", disabled["sample_items"][:2])
    check(all(item["review_status"] == "AUTO_CANDIDATE" for item in disabled["sample_items"]), "Sample items are auto-candidates", disabled["sample_items"][:2])
    check(all(item["promotion_status"] == "NOT_PROMOTED" for item in disabled["sample_items"]), "Sample items are not promoted", disabled["sample_items"][:2])
    check(all(item["is_active"] is False for item in disabled["sample_items"]), "Sample items are inactive", disabled["sample_items"][:2])
    check(disabled["readiness"]["ready_for_tiny_fixture_review_approval_apply_regression"] is True, "Ready for tiny fixture approval apply regression", disabled["readiness"])
    check(disabled["readiness"]["ready_for_real_scoped_review_approval_apply"] is False, "Not ready for real scoped approval apply", disabled["readiness"])
    check(disabled["readiness"]["ready_for_promotion_dry_run"] is False, "Not ready for promotion dry-run", disabled["readiness"])
    assert_no_mutation(disabled, before)

    print("=" * 72)
    print("NWDP DEMOGRAPHIC PROFILE REVIEW APPROVAL APPLY DISABLED REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

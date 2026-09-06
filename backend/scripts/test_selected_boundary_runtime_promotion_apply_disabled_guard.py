#!/usr/bin/env python3
"""Regression for disabled selected NWDP boundary runtime promotion apply guard."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.database import SessionLocal  # noqa: E402


OUT_DIR = Path("/tmp/selected-boundary-runtime-promotion-apply-disabled-guard-regression")
SCRIPT = ROOT / "backend/scripts/apply_selected_boundary_runtime_promotion_disabled.py"


def check(condition: bool, label: str, detail=None) -> None:
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:3000])
    if not condition:
        raise AssertionError(label)


def table_counts(db) -> dict[str, int]:
    row = db.execute(text("""
        select
          (select count(*)::bigint from geography_boundary_runtime_sets) as runtime_set_rows,
          (select count(*)::bigint from geography_boundary_runtime_sets where is_active = true) as active_runtime_set_rows,
          (select count(*)::bigint from geography_boundary_runtime_features) as runtime_feature_rows,
          (select count(*)::bigint from geography_boundary_runtime_features where is_active = true) as active_runtime_feature_rows,
          (select count(*)::bigint from geography_boundary_runtime_crosswalks) as runtime_crosswalk_rows,
          (select count(*)::bigint from geography_boundary_runtime_crosswalks where is_active = true) as active_runtime_crosswalk_rows,
          (select count(*)::bigint from geography_boundary_runtime_promotion_events) as runtime_promotion_event_rows,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates) as boundary_candidate_rows,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates where is_active = true) as active_boundary_candidate_rows,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates where promotion_status = 'PROMOTED') as promoted_boundary_candidate_rows
    """)).mappings().one()
    return {key: int(value or 0) for key, value in dict(row).items()}


def run_guard(*args: str):
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--output-dir",
            str(OUT_DIR),
            "--limit",
            "25",
            *args,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=240,
    )


def read_audit() -> dict:
    return json.loads((OUT_DIR / "selected_boundary_runtime_promotion_apply_disabled_audit.json").read_text(encoding="utf-8"))


def assert_counts_unchanged(db, before: dict[str, int], label: str) -> None:
    after = table_counts(db)
    check(after == before, label, {"before": before, "after": after})


def main() -> int:
    print("=" * 72)
    print("SELECTED BOUNDARY RUNTIME PROMOTION APPLY DISABLED GUARD REGRESSION")
    print("=" * 72)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    try:
        before = table_counts(db)

        no_apply = run_guard("--state-or-ut", "Andaman and Nicobar Islands", "--district", "Nicobars")
        check(no_apply.returncode != 0, "Missing apply flag exits non-zero", no_apply.stdout[-2000:])
        data = read_audit()
        check(data["schema_version"] == "selected_boundary_runtime_promotion_apply_disabled_guard.v1", "Schema version is stable", data)
        check(data["mode"] == "DISABLED_SELECTED_BOUNDARY_RUNTIME_PROMOTION_APPLY_GUARD", "Mode is disabled guard", data)
        check(data["error"] == "EXPLICIT_APPLY_FLAG_REQUIRED", "Explicit apply flag is required", data)
        check(data["apply_requested"] is False, "No-apply attempt is recorded", data)
        check(data["readiness_report"]["healthy"] is True, "Guard embeds selected runtime readiness report", data["readiness_report"]["summary"])
        assert_counts_unchanged(db, before, "No-apply guard leaves DB counts unchanged")

        missing_scope = run_guard(
            "--apply",
            "--rollback-token",
            "selected-runtime-disabled-guard-regression",
            "--dry-run-confirmed",
            "--admin-confirmation",
            "--enable-selected-runtime-promotion",
        )
        check(missing_scope.returncode != 0, "Missing scope exits non-zero", missing_scope.stdout[-2000:])
        data = read_audit()
        check(data["error"] == "STATE_OR_DISTRICT_SCOPE_REQUIRED", "State/district scope is required", data)
        check(data["readiness_report"]["error"] == "STATE_OR_DISTRICT_SCOPE_REQUIRED_BEFORE_READINESS_SELECTION", "Readiness selection is blocked without scope", data["readiness_report"])
        assert_counts_unchanged(db, before, "Missing-scope guard leaves DB counts unchanged")

        missing_rollback = run_guard(
            "--apply",
            "--state-or-ut",
            "Andaman and Nicobar Islands",
            "--district",
            "Nicobars",
            "--dry-run-confirmed",
            "--admin-confirmation",
            "--enable-selected-runtime-promotion",
        )
        check(missing_rollback.returncode != 0, "Missing rollback/supersession plan exits non-zero", missing_rollback.stdout[-2000:])
        data = read_audit()
        check(data["error"] == "ROLLBACK_OR_SUPERSESSION_PLAN_REQUIRED", "Rollback/supersession plan is required", data)
        assert_counts_unchanged(db, before, "Missing-rollback guard leaves DB counts unchanged")

        disabled = run_guard(
            "--apply",
            "--state-or-ut",
            "Andaman and Nicobar Islands",
            "--district",
            "Nicobars",
            "--rollback-token",
            "selected-runtime-disabled-guard-regression",
            "--dry-run-confirmed",
            "--admin-confirmation",
            "--enable-selected-runtime-promotion",
        )
        check(disabled.returncode != 0, "Disabled selected runtime apply exits non-zero", disabled.stdout[-2000:])
        data = read_audit()
        check(data["error"] == "SELECTED_BOUNDARY_RUNTIME_PROMOTION_APPLY_DISABLED_BY_POLICY", "Apply remains disabled by policy", data)
        check(data["apply_requested"] is True, "Apply attempt is recorded", data)
        check(data["enable_selected_runtime_promotion_requested"] is True, "Future enable flag is recorded", data)
        check(data["dry_run_confirmed"] is True, "Dry-run confirmation is recorded", data)
        check(data["admin_confirmation"] is True, "Admin confirmation is recorded", data)
        check(data["rollback_token"] == "selected-runtime-disabled-guard-regression", "Rollback token is recorded", data)
        check(data["counts_unchanged"] is True, "Audit reports unchanged DB counts", data)

        summary = data["readiness_report"]["summary"]
        check(summary["candidate_count"] >= 0, "Selected runtime candidate count is readable", summary)
        check(summary["invalid_geometry_count"] >= 0, "Invalid geometry blockers are readable", summary)
        check(summary["not_runtime_eligible_source_count"] >= 0, "Runtime eligibility blockers are readable", summary)
        check(summary["selected_runtime_promotable_count"] >= 0, "Selected promotable count is readable", summary)

        policy = data["policy"]
        check(policy["real_apply_supported"] is False, "Real apply remains unsupported", policy)
        check(policy["state_or_district_scope_required_before_real_apply"] is True, "Scope required before real apply", policy)
        check(policy["rollback_or_supersession_plan_required_before_real_apply"] is True, "Rollback/supersession required before real apply", policy)
        check(policy["dry_run_required_before_real_apply"] is True, "Dry-run required before real apply", policy)
        check(policy["requires_runtime_eligible_source_feature"] is True, "Runtime eligible source feature required", policy)
        check(policy["requires_valid_geometry"] is True, "Valid geometry required", policy)

        guardrails = data["guardrails"]
        check(guardrails["db_writes_attempted"] is False, "Guard attempts no DB writes", guardrails)
        check(guardrails["runtime_tables_written"] is False, "Guard writes no runtime tables", guardrails)
        check(guardrails["runtime_lookup_enabled"] is False, "Guard keeps runtime lookup disabled", guardrails)
        check(guardrails["boundary_candidates_promoted"] is False, "Guard promotes no boundary candidates", guardrails)
        check(guardrails["boundary_candidates_activated"] is False, "Guard activates no boundary candidates", guardrails)
        check(guardrails["android_behavior_changed"] is False, "Guard keeps Android unchanged", guardrails)
        check(guardrails["lgd_geography_overwritten"] is False, "Guard does not overwrite LGD", guardrails)

        readiness = data["readiness"]
        check(readiness["ready_for_selected_runtime_promotion_apply"] is False, "Not ready for selected runtime apply", readiness)
        check(readiness["ready_for_runtime_lookup_enablement"] is False, "Not ready for runtime lookup enablement", readiness)
        check(readiness["ready_for_android_behavior_change"] is False, "Not ready for Android behavior change", readiness)

        check((OUT_DIR / "selected_boundary_runtime_promotion_apply_disabled_audit.json").exists(), "Audit JSON is written", str(OUT_DIR))
        check((OUT_DIR / "selected_boundary_runtime_promotion_apply_disabled_candidates.csv").exists(), "Candidate CSV is written", str(OUT_DIR))

        assert_counts_unchanged(db, before, "Disabled apply guard leaves DB counts unchanged")

        print("=" * 72)
        print("SELECTED BOUNDARY RUNTIME PROMOTION APPLY DISABLED GUARD REGRESSION PASSED")
        print("=" * 72)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

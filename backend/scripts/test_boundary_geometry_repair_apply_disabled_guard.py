#!/usr/bin/env python3
"""Regression for disabled NWDP boundary geometry repair apply guard."""

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


OUT_DIR = Path("/tmp/boundary-geometry-repair-apply-disabled-guard-regression")
SCRIPT = ROOT / "backend/scripts/apply_boundary_geometry_repair_disabled.py"


def check(condition: bool, label: str, detail=None) -> None:
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:3000])
    if not condition:
        raise AssertionError(label)


def table_counts(db) -> dict[str, int]:
    row = db.execute(text("""
        select
          (select count(*)::bigint from geography_boundary_source_features) as source_feature_rows,
          (select count(*)::bigint from geography_boundary_source_features where eligible_for_runtime_after_promotion = true) as runtime_eligible_source_feature_rows,
          (select count(*)::bigint from geography_boundary_source_features where geometry_validation_status in ('VALID', 'VALIDATED', 'VALID_WITH_WARNINGS')) as valid_geometry_source_feature_rows,
          (select count(*)::bigint from geography_boundary_source_features where geometry_validation_status not in ('VALID', 'VALIDATED', 'VALID_WITH_WARNINGS') or geometry_validation_status is null) as invalid_or_unknown_geometry_source_feature_rows,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates) as boundary_candidate_rows,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates where is_active = true) as active_boundary_candidate_rows,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates where promotion_status = 'PROMOTED') as promoted_boundary_candidate_rows,
          (select count(*)::bigint from geography_boundary_runtime_sets) as runtime_set_rows,
          (select count(*)::bigint from geography_boundary_runtime_features) as runtime_feature_rows,
          (select count(*)::bigint from geography_boundary_runtime_crosswalks) as runtime_crosswalk_rows,
          (select count(*)::bigint from geography_boundary_runtime_promotion_events) as runtime_promotion_event_rows
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
            "100",
            *args,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=300,
    )


def read_audit() -> dict:
    return json.loads((OUT_DIR / "boundary_geometry_repair_apply_disabled_audit.json").read_text(encoding="utf-8"))


def assert_counts_unchanged(db, before: dict[str, int], label: str) -> None:
    after = table_counts(db)
    check(after == before, label, {"before": before, "after": after})


def main() -> int:
    print("=" * 72)
    print("BOUNDARY GEOMETRY REPAIR APPLY DISABLED GUARD REGRESSION")
    print("=" * 72)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    try:
        before = table_counts(db)

        no_apply = run_guard()
        check(no_apply.returncode != 0, "Missing apply flag exits non-zero", no_apply.stdout[-2000:])
        data = read_audit()
        check(data["schema_version"] == "boundary_geometry_repair_apply_disabled_guard.v1", "Schema version is stable", data)
        check(data["mode"] == "DISABLED_BOUNDARY_GEOMETRY_REPAIR_APPLY_GUARD", "Mode is disabled guard", data)
        check(data["error"] == "EXPLICIT_APPLY_FLAG_REQUIRED", "Explicit apply flag is required", data)
        check(data["apply_requested"] is False, "No-apply attempt is recorded", data)
        check(data["classification_report"]["healthy"] is True, "Guard embeds healthy classification report", data["classification_report"]["summary"])
        assert_counts_unchanged(db, before, "No-apply guard leaves DB counts unchanged")

        missing_scope = run_guard(
            "--apply",
            "--enable-geometry-repair",
            "--enable-runtime-eligibility-update",
            "--rollback-token",
            "boundary-geometry-repair-disabled-guard-regression",
            "--classification-reviewed",
            "--admin-confirmation",
        )
        check(missing_scope.returncode != 0, "Missing state/district scope exits non-zero", missing_scope.stdout[-2000:])
        data = read_audit()
        check(data["error"] == "STATE_OR_DISTRICT_SCOPE_REQUIRED", "State/district scope is required", data)
        assert_counts_unchanged(db, before, "Missing-scope guard leaves DB counts unchanged")

        missing_repair_flag = run_guard(
            "--apply",
            "--state-or-ut",
            "Andaman And Nicobar Islands",
            "--district",
            "Nicobars",
            "--enable-runtime-eligibility-update",
            "--rollback-token",
            "boundary-geometry-repair-disabled-guard-regression",
            "--classification-reviewed",
            "--admin-confirmation",
        )
        check(missing_repair_flag.returncode != 0, "Missing geometry repair policy flag exits non-zero", missing_repair_flag.stdout[-2000:])
        data = read_audit()
        check(data["error"] == "ENABLE_GEOMETRY_REPAIR_POLICY_FLAG_REQUIRED", "Geometry repair policy flag is required", data)
        assert_counts_unchanged(db, before, "Missing-repair-flag guard leaves DB counts unchanged")

        missing_eligibility_flag = run_guard(
            "--apply",
            "--state-or-ut",
            "Andaman And Nicobar Islands",
            "--district",
            "Nicobars",
            "--enable-geometry-repair",
            "--rollback-token",
            "boundary-geometry-repair-disabled-guard-regression",
            "--classification-reviewed",
            "--admin-confirmation",
        )
        check(missing_eligibility_flag.returncode != 0, "Missing runtime eligibility policy flag exits non-zero", missing_eligibility_flag.stdout[-2000:])
        data = read_audit()
        check(data["error"] == "ENABLE_RUNTIME_ELIGIBILITY_UPDATE_POLICY_FLAG_REQUIRED", "Runtime eligibility policy flag is required", data)
        assert_counts_unchanged(db, before, "Missing-eligibility-flag guard leaves DB counts unchanged")

        missing_rollback = run_guard(
            "--apply",
            "--state-or-ut",
            "Andaman And Nicobar Islands",
            "--district",
            "Nicobars",
            "--enable-geometry-repair",
            "--enable-runtime-eligibility-update",
            "--classification-reviewed",
            "--admin-confirmation",
        )
        check(missing_rollback.returncode != 0, "Missing rollback/supersession plan exits non-zero", missing_rollback.stdout[-2000:])
        data = read_audit()
        check(data["error"] == "ROLLBACK_OR_SUPERSESSION_PLAN_REQUIRED", "Rollback/supersession plan is required", data)
        assert_counts_unchanged(db, before, "Missing-rollback guard leaves DB counts unchanged")

        disabled = run_guard(
            "--apply",
            "--state-or-ut",
            "Andaman And Nicobar Islands",
            "--district",
            "Nicobars",
            "--enable-geometry-repair",
            "--enable-runtime-eligibility-update",
            "--rollback-token",
            "boundary-geometry-repair-disabled-guard-regression",
            "--classification-reviewed",
            "--admin-confirmation",
        )
        check(disabled.returncode != 0, "Disabled geometry repair apply exits non-zero", disabled.stdout[-2000:])
        data = read_audit()
        check(data["error"] == "BOUNDARY_GEOMETRY_REPAIR_APPLY_DISABLED_BY_POLICY", "Apply remains disabled by policy", data)
        check(data["apply_requested"] is True, "Apply attempt is recorded", data)
        check(data["enable_geometry_repair_requested"] is True, "Geometry repair flag is recorded", data)
        check(data["enable_runtime_eligibility_update_requested"] is True, "Runtime eligibility flag is recorded", data)
        check(data["classification_reviewed"] is True, "Classification review is recorded", data)
        check(data["admin_confirmation"] is True, "Admin confirmation is recorded", data)
        check(data["rollback_token"] == "boundary-geometry-repair-disabled-guard-regression", "Rollback token is recorded", data)
        check(data["counts_unchanged"] is True, "Audit reports unchanged DB counts", data)

        summary = data["classification_report"]["summary"]
        check(summary["candidate_count"] > 0, "Classification sees boundary candidates", summary)
        check(summary["invalid_or_unknown_geometry_count"] > 0, "Classification sees geometry blockers", summary)
        check(summary["runtime_ineligible_source_count"] > 0, "Classification sees runtime eligibility blockers", summary)
        check(summary["no_repair_needed_runtime_promotable_count"] == 0, "Classification sees no promotable rows yet", summary)

        policy = data["policy"]
        check(policy["real_apply_supported"] is False, "Real apply remains unsupported", policy)
        check(policy["state_or_district_scope_required"] is True, "State/district scope required", policy)
        check(policy["future_geometry_repair_policy_flag_required"] is True, "Geometry repair policy flag required", policy)
        check(policy["future_runtime_eligibility_policy_flag_required"] is True, "Runtime eligibility policy flag required", policy)
        check(policy["rollback_or_supersession_plan_required_before_real_apply"] is True, "Rollback/supersession required", policy)
        check(policy["classification_review_required_before_real_apply"] is True, "Classification review required", policy)
        check(policy["geometry_repair_write_allowed"] is False, "Geometry repair writes are not allowed", policy)
        check(policy["geometry_validation_status_write_allowed"] is False, "Validation status writes are not allowed", policy)
        check(policy["source_runtime_eligibility_write_allowed"] is False, "Runtime eligibility writes are not allowed", policy)
        check(policy["runtime_table_write_allowed"] is False, "Runtime table writes are not allowed", policy)
        check(policy["android_behavior_change_allowed"] is False, "Android behavior change is not allowed", policy)

        guardrails = data["guardrails"]
        check(guardrails["db_writes_attempted"] is False, "Guard attempts no DB writes", guardrails)
        check(guardrails["geometry_repair_attempted"] is False, "Guard attempts no geometry repair", guardrails)
        check(guardrails["geometry_validation_status_changed"] is False, "Guard changes no validation status", guardrails)
        check(guardrails["source_runtime_eligibility_changed"] is False, "Guard changes no runtime eligibility", guardrails)
        check(guardrails["source_features_changed"] is False, "Guard changes no source features", guardrails)
        check(guardrails["boundary_candidates_promoted"] is False, "Guard promotes no candidates", guardrails)
        check(guardrails["boundary_candidates_activated"] is False, "Guard activates no candidates", guardrails)
        check(guardrails["runtime_tables_written"] is False, "Guard writes no runtime tables", guardrails)
        check(guardrails["runtime_lookup_enabled"] is False, "Guard keeps runtime lookup disabled", guardrails)
        check(guardrails["android_behavior_changed"] is False, "Guard keeps Android unchanged", guardrails)
        check(guardrails["lgd_geography_overwritten"] is False, "Guard does not overwrite LGD", guardrails)

        readiness = data["readiness"]
        check(readiness["ready_for_admin_repair_planning"] is True, "Ready for admin repair planning", readiness)
        check(readiness["ready_for_geometry_validation_pipeline_design"] is True, "Ready for validation pipeline design", readiness)
        check(readiness["ready_for_runtime_eligibility_review"] is True, "Ready for runtime eligibility review", readiness)
        check(readiness["ready_for_boundary_geometry_repair_apply"] is False, "Not ready for geometry repair apply", readiness)
        check(readiness["ready_for_selected_runtime_promotion_apply"] is False, "Not ready for selected runtime promotion apply", readiness)
        check(readiness["ready_for_runtime_lookup_enablement"] is False, "Runtime lookup remains disabled", readiness)
        check(readiness["ready_for_android_behavior_change"] is False, "Android remains unchanged", readiness)

        check((OUT_DIR / "boundary_geometry_repair_apply_disabled_audit.json").exists(), "Audit JSON is written", str(OUT_DIR))
        check((OUT_DIR / "boundary_geometry_repair_apply_disabled_classifications.csv").exists(), "Classification CSV is written", str(OUT_DIR))

        assert_counts_unchanged(db, before, "Disabled apply guard leaves DB counts unchanged")

        print("=" * 72)
        print("BOUNDARY GEOMETRY REPAIR APPLY DISABLED GUARD REGRESSION PASSED")
        print("=" * 72)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

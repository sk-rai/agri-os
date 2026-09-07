#!/usr/bin/env python3
"""Regression for read-only NWDP boundary geometry validation readiness report."""

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


OUT_DIR = Path("/tmp/boundary-geometry-validation-readiness-regression")
SCRIPT = ROOT / "backend/scripts/report_boundary_geometry_validation_readiness.py"


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
          (select count(*)::bigint from geography_boundary_crosswalk_candidates) as boundary_candidate_rows,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates where is_active = true) as active_boundary_candidate_rows,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates where promotion_status = 'PROMOTED') as promoted_boundary_candidate_rows,
          (select count(*)::bigint from geography_boundary_runtime_sets) as runtime_set_rows,
          (select count(*)::bigint from geography_boundary_runtime_features) as runtime_feature_rows,
          (select count(*)::bigint from geography_boundary_runtime_crosswalks) as runtime_crosswalk_rows,
          (select count(*)::bigint from geography_boundary_runtime_promotion_events) as runtime_promotion_event_rows
    """)).mappings().one()
    return {key: int(value or 0) for key, value in dict(row).items()}


def run_report(*args: str):
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--output-dir",
            str(OUT_DIR),
            "--limit",
            "50",
            *args,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=180,
    )


def main() -> int:
    print("=" * 72)
    print("BOUNDARY GEOMETRY VALIDATION READINESS REGRESSION")
    print("=" * 72)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    try:
        before = table_counts(db)

        proc = run_report()
        if proc.stdout:
            print(proc.stdout)
        if proc.stderr:
            print(proc.stderr)

        check(proc.returncode == 0, "Readiness report exits zero", {"returncode": proc.returncode, "stderr": proc.stderr[-2000:]})

        json_path = OUT_DIR / "boundary_geometry_validation_readiness.json"
        status_csv = OUT_DIR / "boundary_geometry_validation_readiness_by_status.csv"
        state_csv = OUT_DIR / "boundary_geometry_validation_readiness_by_state_district.csv"
        sample_csv = OUT_DIR / "boundary_geometry_validation_readiness_blocker_samples.csv"

        check(json_path.exists(), "Report writes JSON", str(json_path))
        check(status_csv.exists(), "Report writes status CSV", str(status_csv))
        check(state_csv.exists(), "Report writes state/district CSV", str(state_csv))
        check(sample_csv.exists(), "Report writes blocker sample CSV", str(sample_csv))

        data = json.loads(json_path.read_text(encoding="utf-8"))
        summary = data["summary"]
        readiness = data["readiness"]
        policy = data["validation_policy"]
        guardrails = data["guardrails"]

        check(data["schema_version"] == "boundary_geometry_validation_readiness.v1", "Schema version is stable", data)
        check(data["mode"] == "READ_ONLY_BOUNDARY_GEOMETRY_VALIDATION_READINESS", "Report is read-only mode", data)
        check(data["healthy"] is True, "Report is healthy", data)

        check(summary["candidate_count"] > 0, "Boundary candidates are visible", summary)
        check(summary["direct_vlcode_match_count"] > 0, "Direct VLCode candidates are visible", summary)
        check(summary["auto_candidate_count"] > 0, "Auto candidates are visible", summary)
        check(summary["invalid_geometry_count"] > 0, "Invalid geometry blockers are visible", summary)
        check(summary["not_runtime_eligible_source_count"] > 0, "Runtime-ineligible source blockers are visible", summary)
        check(summary["selected_runtime_promotable_count"] == 0, "No selected runtime promotable candidates yet", summary)
        check(summary["existing_runtime_feature_count"] >= 0, "Runtime feature count is readable", summary)
        check(summary["active_runtime_feature_count"] == 0, "No active runtime boundary features are enabled", summary)

        check(policy["source_system"] == "NWDP_GSI_VILLAGE_BOUNDARY", "Policy records NWDP source", policy)
        check(policy["requires_runtime_eligible_source"] is True, "Policy requires runtime-eligible source", policy)
        check(policy["requires_direct_vlcode_match"] is True, "Policy requires direct code match", policy)
        check(policy["requires_auto_candidate_review_status"] is True, "Policy requires auto candidate", policy)
        check(policy["requires_not_promoted"] is True, "Policy requires not promoted", policy)
        check(policy["requires_inactive_candidate"] is True, "Policy requires inactive candidate", policy)
        check(policy["geometry_repair_supported_by_this_report"] is False, "Report does not repair geometry", policy)
        check(policy["runtime_promotion_supported_by_this_report"] is False, "Report does not promote runtime boundary", policy)
        check(policy["android_behavior_change_supported_by_this_report"] is False, "Report does not support Android changes", policy)

        check(readiness["ready_for_admin_geometry_review"] is True, "Ready for admin geometry review", readiness)
        check(readiness["ready_for_geometry_repair_plan"] is True, "Ready for geometry repair planning", readiness)
        check(readiness["ready_for_selected_runtime_promotion_dry_run"] is False, "Not ready for selected runtime dry-run", readiness)
        check(readiness["ready_for_selected_runtime_promotion_apply"] is False, "Not ready for selected runtime apply", readiness)
        check(readiness["ready_for_runtime_lookup_enablement"] is False, "Runtime lookup remains disabled", readiness)
        check(readiness["ready_for_android_behavior_change"] is False, "Android remains unchanged", readiness)
        check(readiness["requires_rollback_or_supersession_plan"] is True, "Rollback/supersession required", readiness)

        check(guardrails["db_writes_attempted"] is False, "Report attempts no DB writes", guardrails)
        check(guardrails["geometry_repair_attempted"] is False, "Report attempts no geometry repair", guardrails)
        check(guardrails["source_features_changed"] is False, "Report changes no source features", guardrails)
        check(guardrails["runtime_features_written"] is False, "Report writes no runtime features", guardrails)
        check(guardrails["runtime_crosswalks_written"] is False, "Report writes no runtime crosswalks", guardrails)
        check(guardrails["promotion_events_written"] is False, "Report writes no promotion events", guardrails)
        check(guardrails["boundary_candidates_promoted"] is False, "Report promotes no candidates", guardrails)
        check(guardrails["boundary_candidates_activated"] is False, "Report activates no candidates", guardrails)
        check(guardrails["runtime_lookup_enabled"] is False, "Report keeps runtime lookup disabled", guardrails)
        check(guardrails["android_behavior_changed"] is False, "Report keeps Android unchanged", guardrails)
        check(guardrails["lgd_geography_overwritten"] is False, "Report does not overwrite LGD", guardrails)

        check(isinstance(data["status_rows"], list) and len(data["status_rows"]) > 0, "Status rows are emitted", data["status_rows"][:3])
        check(isinstance(data["state_district_rows"], list) and len(data["state_district_rows"]) > 0, "State/district rows are emitted", data["state_district_rows"][:3])
        check(isinstance(data["blocker_samples"], list), "Blocker samples are emitted", data["blocker_samples"][:3])

        scoped = run_report("--state-or-ut", "Andaman And Nicobar Islands", "--district", "Nicobars")
        check(scoped.returncode == 0, "Scoped readiness report exits zero", {"returncode": scoped.returncode, "stderr": scoped.stderr[-2000:]})
        scoped_data = json.loads(json_path.read_text(encoding="utf-8"))
        check(scoped_data["filters"]["district"] == "Nicobars", "Scoped report records district filter", scoped_data["filters"])
        check(scoped_data["summary"]["candidate_count"] > 0, "Scoped report sees candidates", scoped_data["summary"])
        check(scoped_data["summary"]["not_validated_geometry_count"] > 0, "Scoped report sees not-validated geometry backlog", scoped_data["summary"])
        check(scoped_data["summary"]["confirmed_invalid_geometry_count"] == 0, "Scoped report distinguishes explicitly invalid database rows", scoped_data["summary"])

        after = table_counts(db)
        check(after == before, "Readiness report leaves DB counts unchanged", {"before": before, "after": after})

        print("=" * 72)
        print("BOUNDARY GEOMETRY VALIDATION READINESS REGRESSION PASSED")
        print("=" * 72)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

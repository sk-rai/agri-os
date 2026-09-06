#!/usr/bin/env python3
"""Regression for disabled NWDP boundary project matching apply guard."""

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
from scripts.report_project_boundary_readiness import scope_counts_for_project  # noqa: E402


OUT_DIR = Path("/tmp/nwdp-boundary-project-matching-apply-disabled-guard-regression")


def check(condition: bool, label: str, detail=None) -> None:
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:3000])
    if not condition:
        raise AssertionError(label)


def table_counts(db) -> dict[str, int]:
    row = db.execute(text("""
        select
          (select count(*)::bigint from geography_boundary_project_matches) as project_match_rows,
          (select count(*)::bigint from geography_boundary_project_matches where is_active = true) as active_project_match_rows,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates) as boundary_candidate_rows,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates where is_active = true) as active_boundary_candidate_rows,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates where promotion_status = 'PROMOTED') as promoted_boundary_candidate_rows,
          (select count(*)::bigint from geography_boundary_runtime_features) as runtime_feature_rows,
          (select count(*)::bigint from geography_boundary_runtime_crosswalks) as runtime_crosswalk_rows
    """)).mappings().one()
    return {key: int(value or 0) for key, value in dict(row).items()}


def choose_ready_project(db) -> str:
    rows = db.execute(text("""
        select id::text as project_id, geography_scope
        from projects
        where is_active = true
          and geography_scope is not null
          and geography_scope::text not in ('{}', 'null', '[]')
        order by created_at desc nulls last
    """)).mappings().all()

    for row in rows:
        scope = row["geography_scope"] or {}
        if isinstance(scope, str):
            scope = json.loads(scope)
        if not isinstance(scope, dict):
            continue
        counts = scope_counts_for_project(db, row["project_id"], scope)
        if counts["scope_resolved_village_count"] > 0 and counts["scope_eligible_boundary_candidate_count"] > 0:
            return row["project_id"]

    raise RuntimeError("No project with resolved scope and eligible boundary candidates found")


def run_guard(project_id: str, *extra_args: str):
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "backend/scripts/apply_nwdp_boundary_project_matching_disabled.py"),
            "--project-id",
            project_id,
            "--limit",
            "25",
            "--output-dir",
            str(OUT_DIR),
            *extra_args,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=120,
    )


def main() -> int:
    print("=" * 72)
    print("NWDP BOUNDARY PROJECT MATCHING APPLY DISABLED GUARD REGRESSION")
    print("=" * 72)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    try:
        project_id = choose_ready_project(db)
        before = table_counts(db)

        no_apply = run_guard(project_id)
        check(no_apply.returncode != 0, "Missing apply flag exits non-zero", no_apply.stdout[-2000:])
        data = json.loads((OUT_DIR / "project_boundary_apply_disabled_audit.json").read_text(encoding="utf-8"))
        check(data["schema_version"] == "nwdp_boundary_project_matching_apply_disabled_guard.v1", "Schema version is stable", data)
        check(data["mode"] == "DISABLED_PROJECT_BOUNDARY_MATCHING_APPLY_GUARD", "Mode is disabled guard", data)
        check(data["error"] == "EXPLICIT_APPLY_FLAG_REQUIRED", "Explicit apply flag is required", data)
        check(data["apply_requested"] is False, "No-apply attempt is recorded", data)
        check(data["dry_run"]["healthy"] is True, "Guard embeds healthy dry-run", data["dry_run"]["summary"])
        check(data["dry_run"]["summary"]["dry_run_candidate_selection_count"] > 0, "Dry-run selected candidates are visible", data["dry_run"]["summary"])

        after_no_apply = table_counts(db)
        check(after_no_apply == before, "No-apply guard leaves DB counts unchanged", {"before": before, "after": after_no_apply})

        disabled = run_guard(
            project_id,
            "--apply",
            "--enable-project-boundary-apply",
            "--rollback-token",
            "project-boundary-disabled-guard-regression",
        )
        check(disabled.returncode != 0, "Disabled apply exits non-zero", disabled.stdout[-2000:])

        data = json.loads((OUT_DIR / "project_boundary_apply_disabled_audit.json").read_text(encoding="utf-8"))
        check(data["error"] == "PROJECT_BOUNDARY_MATCHING_APPLY_DISABLED_BY_POLICY", "Apply remains disabled by policy", data)
        check(data["apply_requested"] is True, "Apply attempt is recorded", data)
        check(data["enable_project_boundary_apply_requested"] is True, "Future enable flag is recorded", data)
        check(data["rollback_token"] == "project-boundary-disabled-guard-regression", "Rollback token is recorded", data)
        check(data["counts_unchanged"] is True, "Audit reports unchanged counts", data)

        check((OUT_DIR / "project_boundary_apply_disabled_audit.json").exists(), "Audit JSON is written", str(OUT_DIR))
        check((OUT_DIR / "project_boundary_apply_disabled_selected_candidates.csv").exists(), "Selected candidate CSV is written", str(OUT_DIR))

        policy = data["policy"]
        check(policy["real_apply_supported"] is False, "Real apply is unsupported", policy)
        check(policy["rollback_token_required_before_real_apply"] is True, "Rollback token required before real apply", policy)
        check(policy["dry_run_required_before_real_apply"] is True, "Dry-run required before real apply", policy)

        guardrails = data["guardrails"]
        check(guardrails["db_writes_attempted"] is False, "Guard attempts no DB writes", guardrails)
        check(guardrails["project_boundary_matches_written"] is False, "Guard writes no project matches", guardrails)
        check(guardrails["boundary_candidates_activated"] is False, "Guard activates no candidates", guardrails)
        check(guardrails["boundary_candidates_promoted"] is False, "Guard promotes no candidates", guardrails)
        check(guardrails["runtime_boundary_features_written"] is False, "Guard writes no runtime features", guardrails)
        check(guardrails["runtime_boundary_crosswalks_written"] is False, "Guard writes no runtime crosswalks", guardrails)
        check(guardrails["lookup_api_enabled"] is False, "Guard keeps lookup disabled", guardrails)
        check(guardrails["android_behavior_changed"] is False, "Guard keeps Android unchanged", guardrails)
        check(guardrails["lgd_geography_overwritten"] is False, "Guard does not overwrite LGD", guardrails)

        readiness = data["readiness"]
        check(readiness["ready_for_project_boundary_apply"] is False, "Not ready for real project boundary apply", readiness)
        check(readiness["ready_for_project_boundary_apply_implementation_design"] is True, "Ready for apply implementation design", readiness)
        check(readiness["ready_for_runtime_spatial_matching"] is False, "Not ready for runtime spatial matching", readiness)
        check(readiness["ready_for_android_behavior_change"] is False, "Not ready for Android change", readiness)

        after_disabled = table_counts(db)
        check(after_disabled == before, "Disabled apply leaves DB counts unchanged", {"before": before, "after": after_disabled})

        print("=" * 72)
        print("NWDP BOUNDARY PROJECT MATCHING APPLY DISABLED GUARD REGRESSION PASSED")
        print("=" * 72)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

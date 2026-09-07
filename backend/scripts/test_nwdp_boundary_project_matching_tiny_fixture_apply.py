#!/usr/bin/env python3
"""Regression for tiny-fixture NWDP boundary project matching apply."""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.database import SessionLocal  # noqa: E402


OUT_DIR = Path("/tmp/nwdp-boundary-project-matching-tiny-fixture-apply-regression")
SCRIPT = ROOT / "backend/scripts/apply_nwdp_boundary_project_matching_tiny_fixture.py"
PROJECT_ID = "d14b4f90-45c1-4a0b-bf99-8f5f70e51d91"
ROLLBACK_TOKEN = "project-boundary-tiny-fixture-apply-regression"
FIXTURE_SOURCE = "nwdp_boundary_project_matching_tiny_fixture_regression"
MATCH_SOURCE = "TINY_FIXTURE_PROJECT_MATCHING_APPLY"


def check(condition: bool, label: str, detail=None) -> None:
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:3000])
    if not condition:
        raise AssertionError(label)


def table_counts(db) -> dict[str, int]:
    row = db.execute(text("""
        select
          (select count(*)::bigint from projects) as project_rows,
          (select count(*)::bigint from geography_boundary_project_matches) as project_match_rows,
          (select count(*)::bigint from geography_boundary_project_matches where is_active = true) as active_project_match_rows,
          (select count(*)::bigint from geography_boundary_project_matches where match_source = :match_source) as tiny_fixture_project_match_rows,
          (select count(*)::bigint from geography_boundary_project_matches where match_source = :match_source and is_active = true) as active_tiny_fixture_project_match_rows,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates) as boundary_candidate_rows,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates where is_active = true) as active_boundary_candidate_rows,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates where promotion_status = 'PROMOTED') as promoted_boundary_candidate_rows,
          (select count(*)::bigint from geography_boundary_runtime_features) as runtime_feature_rows,
          (select count(*)::bigint from geography_boundary_runtime_features where is_active = true) as active_runtime_feature_rows,
          (select count(*)::bigint from geography_boundary_runtime_crosswalks) as runtime_crosswalk_rows,
          (select count(*)::bigint from geography_boundary_runtime_crosswalks where is_active = true) as active_runtime_crosswalk_rows
    """), {"match_source": MATCH_SOURCE}).mappings().one()
    return {key: int(value or 0) for key, value in dict(row).items()}


def choose_candidate(db) -> dict:
    row = db.execute(text("""
        select
          c.id::text as candidate_id,
          c.proposed_village_id::text as village_id,
          c.proposed_village_lgd_code,
          b.state_or_ut,
          sf.source_district_name,
          sf.source_village_name,
          sf.source_vlcode
        from geography_boundary_import_batches b
        join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
        join geography_boundary_source_features sf on sf.id = c.source_feature_id
        where b.source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
          and c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
          and c.review_status = 'AUTO_CANDIDATE'
          and c.promotion_status = 'NOT_PROMOTED'
          and c.is_active = false
          and c.proposed_village_id is not null
        order by b.state_or_ut, sf.source_feature_index
        limit 1
    """)).mappings().first()
    if not row:
        raise RuntimeError("No eligible NWDP boundary project matching candidate found")
    return dict(row)


def create_fixture_project(db, candidate: dict) -> None:
    db.execute(text("""
        delete from geography_boundary_project_matches
        where project_id = :project_id
           or rollback_token = :rollback_token
           or match_source = :match_source
    """), {
        "project_id": PROJECT_ID,
        "rollback_token": ROLLBACK_TOKEN,
        "match_source": MATCH_SOURCE,
    })
    db.execute(text("delete from projects where id = :project_id"), {"project_id": PROJECT_ID})

    scope = {
        "source": FIXTURE_SOURCE,
        "state_or_ut": candidate["state_or_ut"],
        "village_ids": [candidate["village_id"]],
        "village_lgd_codes": [candidate["proposed_village_lgd_code"]],
    }

    db.execute(text("""
        insert into projects (
          id,
          tenant_id,
          name,
          description,
          start_date,
          end_date,
          status,
          geography_scope,
          crop_scope,
          config,
          created_at,
          updated_at,
          version,
          is_active
        )
        values (
          :id,
          'default',
          'NWDP Boundary Project Matching Tiny Fixture Apply Test',
          'Temporary fixture project for project-boundary matching apply regression.',
          :start_date,
          :end_date,
          'ACTIVE',
          cast(:geography_scope as jsonb),
          '[]'::jsonb,
          '{}'::jsonb,
          now(),
          now(),
          'v1.0',
          true
        )
    """), {
        "id": PROJECT_ID,
        "start_date": date(2026, 9, 7),
        "end_date": date(2026, 9, 8),
        "geography_scope": json.dumps(scope),
    })
    db.commit()


def cleanup_fixture(db) -> None:
    db.execute(text("""
        delete from geography_boundary_project_matches
        where project_id = :project_id
           or rollback_token = :rollback_token
           or match_source = :match_source
    """), {
        "project_id": PROJECT_ID,
        "rollback_token": ROLLBACK_TOKEN,
        "match_source": MATCH_SOURCE,
    })
    db.execute(text("delete from projects where id = :project_id"), {"project_id": PROJECT_ID})
    db.commit()


def run_apply(*extra: str):
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--project-id",
            PROJECT_ID,
            "--limit",
            "2",
            "--output-dir",
            str(OUT_DIR),
            "--rollback-token",
            ROLLBACK_TOKEN,
            *extra,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=180,
    )


def read_audit() -> dict:
    return json.loads((OUT_DIR / "project_boundary_tiny_fixture_apply_audit.json").read_text(encoding="utf-8"))


def main() -> int:
    print("=" * 72)
    print("NWDP BOUNDARY PROJECT MATCHING TINY FIXTURE APPLY REGRESSION")
    print("=" * 72)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    try:
        before_all = table_counts(db)
        candidate = choose_candidate(db)
        create_fixture_project(db, candidate)
        before_apply = table_counts(db)

        check(before_apply["project_rows"] == before_all["project_rows"] + 1, "Fixture project is created", {"before": before_all, "after": before_apply})
        check(before_apply["tiny_fixture_project_match_rows"] == 0, "Fixture starts with no project matches", before_apply)

        missing_apply = run_apply()
        check(missing_apply.returncode != 0, "Missing apply flag exits non-zero", missing_apply.stdout[-2000:])
        data = read_audit()
        check(data["error"] == "EXPLICIT_APPLY_FLAG_REQUIRED", "Explicit apply flag is required", data)
        check(data["counts_unchanged"] is True, "Missing apply writes no rows", data)
        check(table_counts(db) == before_apply, "Missing apply leaves DB unchanged", {"before": before_apply, "after": table_counts(db)})

        first = run_apply(
            "--apply",
            "--enable-project-boundary-apply",
            "--dry-run-confirmed",
            "--admin-confirmation",
            "--applied-by",
            "tiny-fixture-regression",
        )
        if first.stdout:
            print(first.stdout)
        if first.stderr:
            print(first.stderr)

        check(first.returncode == 0, "Tiny fixture apply exits zero", {"returncode": first.returncode, "stderr": first.stderr[-2000:]})
        data = read_audit()
        summary = data["summary"]
        guardrails = data["guardrails"]
        policy = data["policy"]

        check(data["schema_version"] == "nwdp_boundary_project_matching_tiny_fixture_apply.v1", "Schema version is stable", data)
        check(data["healthy"] is True, "Apply is healthy", data)
        check(data["mode"] == "TINY_FIXTURE_PROJECT_BOUNDARY_MATCHING_APPLY", "Apply mode is explicit", data)
        check(summary["planned_match_count"] > 0, "Apply plans fixture matches", summary)
        check(summary["inserted_match_count"] > 0, "Apply inserts fixture project match rows", summary)
        check(summary["idempotent_skipped_match_count"] == 0, "First apply has no idempotent skips", summary)

        after_first = table_counts(db)
        check(after_first["active_tiny_fixture_project_match_rows"] == summary["inserted_match_count"], "Inserted fixture rows are active", after_first)
        check(after_first["active_project_match_rows"] == before_apply["active_project_match_rows"] + summary["inserted_match_count"], "Active project match count increases by inserted rows", {"before": before_apply, "after": after_first, "summary": summary})
        check(after_first["boundary_candidate_rows"] == before_apply["boundary_candidate_rows"], "Apply does not create/delete boundary candidates", {"before": before_apply, "after": after_first})
        check(after_first["active_boundary_candidate_rows"] == before_apply["active_boundary_candidate_rows"], "Apply does not activate candidates", {"before": before_apply, "after": after_first})
        check(after_first["promoted_boundary_candidate_rows"] == before_apply["promoted_boundary_candidate_rows"], "Apply does not promote candidates", {"before": before_apply, "after": after_first})
        check(after_first["runtime_feature_rows"] == before_apply["runtime_feature_rows"], "Apply writes no runtime features", {"before": before_apply, "after": after_first})
        check(after_first["runtime_crosswalk_rows"] == before_apply["runtime_crosswalk_rows"], "Apply writes no runtime crosswalks", {"before": before_apply, "after": after_first})

        check(policy["tiny_fixture_only"] is True, "Policy is tiny-fixture only", policy)
        check(policy["broad_apply_supported"] is False, "Broad apply remains unsupported", policy)
        check(policy["target_table"] == "geography_boundary_project_matches", "Target table is explicit", policy)
        check(policy["runtime_boundary_promotion_allowed"] is False, "Runtime boundary promotion not allowed", policy)
        check(policy["runtime_lookup_enablement_allowed"] is False, "Runtime lookup enablement not allowed", policy)
        check(policy["android_behavior_change_allowed"] is False, "Android behavior change not allowed", policy)

        check(guardrails["project_boundary_matches_written"] is True, "Apply records project match write", guardrails)
        check(guardrails["boundary_candidates_activated"] is False, "Apply activates no candidates", guardrails)
        check(guardrails["boundary_candidates_promoted"] is False, "Apply promotes no candidates", guardrails)
        check(guardrails["runtime_tables_written"] is False, "Apply writes no runtime tables", guardrails)
        check(guardrails["runtime_spatial_matching_changed"] is False, "Apply keeps spatial matching unchanged", guardrails)
        check(guardrails["lookup_api_enabled"] is False, "Apply keeps lookup disabled", guardrails)
        check(guardrails["android_behavior_changed"] is False, "Apply keeps Android unchanged", guardrails)
        check(guardrails["lgd_geography_overwritten"] is False, "Apply does not overwrite LGD", guardrails)

        second = run_apply(
            "--apply",
            "--enable-project-boundary-apply",
            "--dry-run-confirmed",
            "--admin-confirmation",
            "--applied-by",
            "tiny-fixture-regression",
        )
        check(second.returncode == 0, "Second tiny fixture apply exits zero", second.stdout[-2000:])
        second_data = read_audit()
        second_summary = second_data["summary"]
        check(second_summary["inserted_match_count"] == 0, "Second apply inserts zero rows", second_summary)
        check(second_summary["idempotent_skipped_match_count"] == summary["planned_match_count"], "Second apply is idempotent", second_summary)
        after_second = table_counts(db)
        check(after_second == after_first, "Second apply leaves counts unchanged", {"after_first": after_first, "after_second": after_second})

        rollback = run_apply(
            "--rollback",
            "--applied-by",
            "tiny-fixture-regression",
        )
        check(rollback.returncode == 0, "Rollback exits zero", rollback.stdout[-2000:])
        rollback_data = read_audit()
        check(rollback_data["mode"] == "TINY_FIXTURE_PROJECT_BOUNDARY_MATCHING_ROLLBACK", "Rollback mode is explicit", rollback_data)
        check(rollback_data["rollback_count"] == summary["inserted_match_count"], "Rollback deactivates inserted fixture rows", rollback_data)
        after_rollback = table_counts(db)
        check(after_rollback["active_tiny_fixture_project_match_rows"] == 0, "Rollback leaves no active fixture matches", after_rollback)
        check(after_rollback["active_project_match_rows"] == before_apply["active_project_match_rows"], "Rollback returns active project match count", {"before_apply": before_apply, "after_rollback": after_rollback})
        check(after_rollback["boundary_candidate_rows"] == before_apply["boundary_candidate_rows"], "Rollback does not create/delete candidates", {"before_apply": before_apply, "after_rollback": after_rollback})
        check(after_rollback["runtime_feature_rows"] == before_apply["runtime_feature_rows"], "Rollback writes no runtime features", {"before_apply": before_apply, "after_rollback": after_rollback})

        check((OUT_DIR / "project_boundary_tiny_fixture_apply_audit.json").exists(), "Audit JSON is written", str(OUT_DIR))
        check((OUT_DIR / "project_boundary_tiny_fixture_apply_rows.csv").exists(), "Rows CSV is written", str(OUT_DIR))

        cleanup_fixture(db)
        after_cleanup = table_counts(db)
        check(after_cleanup == before_all, "Regression cleans fixture and returns DB counts", {"before_all": before_all, "after_cleanup": after_cleanup})

        print("=" * 72)
        print("NWDP BOUNDARY PROJECT MATCHING TINY FIXTURE APPLY REGRESSION PASSED")
        print("=" * 72)
        return 0
    finally:
        cleanup_fixture(db)
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

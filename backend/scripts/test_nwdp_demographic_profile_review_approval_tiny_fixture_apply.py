#!/usr/bin/env python3
"""Tiny fixture regression for NWDP demographic review approval apply."""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
PYTHON = ROOT / "venv" / "bin" / "python"

sys.path.insert(0, str(BACKEND))

from scripts.apply_nwdp_demographic_profile_import import SOURCE_SYSTEM, SOURCE_VERSION, load_settings_url  # noqa: E402

SCRIPT = BACKEND / "scripts/apply_nwdp_demographic_profile_review_approval.py"
OUTPUT = Path("/tmp/nwdp-demographic-profile-review-approval-tiny-fixture-apply-regression.json")
TARGET_TABLE = "geography_village_demographic_profiles"
STATE = "Review Approval Tiny Fixture State"
DISTRICT = "Review Approval Tiny Fixture District"


def check(condition: bool, label: str, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:2600])
    if not condition:
        raise AssertionError(label)


def engine():
    return create_engine(load_settings_url())


def fixture_counts(conn) -> dict:
    return dict(conn.execute(text(f"""
        select
          count(*)::bigint as fixture_row_count,
          count(*) filter (where review_status = 'AUTO_CANDIDATE')::bigint as auto_candidate_fixture_row_count,
          count(*) filter (where review_status = 'APPROVED_FOR_PROMOTION')::bigint as approved_fixture_row_count,
          count(*) filter (where is_active = true)::bigint as active_fixture_row_count,
          count(*) filter (where promotion_status = 'PROMOTED')::bigint as promoted_fixture_row_count
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


def cleanup(conn) -> None:
    conn.execute(text(f"""
        delete from {TARGET_TABLE}
        where source_system = :source_system
          and source_version = :source_version
          and source_state_name = :state
          and source_district_name = :district
    """), {
        "source_system": SOURCE_SYSTEM,
        "source_version": SOURCE_VERSION,
        "state": STATE,
        "district": DISTRICT,
    })


def create_fixture(conn) -> None:
    village_ids = [
        str(row["id"])
        for row in conn.execute(text("""
            select id
            from geography_villages
            order by id
            limit 2
        """)).mappings()
    ]
    check(len(village_ids) >= 2, "At least two canonical villages exist for approval fixture", village_ids)

    rows = [
        {
            "id": str(uuid.uuid4()),
            "village_id": village_ids[0],
            "source_feature_id": str(uuid.uuid4()),
            "source_feature_index": 910001,
            "source_vlcode": "review-approval-tiny-fixture-vlcode-a",
            "source_village_name": "Review Approval Fixture A",
            "total_population": 100,
            "total_households": 20,
        },
        {
            "id": str(uuid.uuid4()),
            "village_id": village_ids[1],
            "source_feature_id": str(uuid.uuid4()),
            "source_feature_index": 910002,
            "source_vlcode": "review-approval-tiny-fixture-vlcode-b",
            "source_village_name": "Review Approval Fixture B",
            "total_population": 80,
            "total_households": 16,
        },
    ]

    for row in rows:
        conn.execute(text(f"""
            insert into {TARGET_TABLE} (
              id,
              village_id,
              source_system,
              source_version,
              source_feature_id,
              source_feature_index,
              source_vlcode,
              source_state_name,
              source_district_name,
              source_subdistrict_name,
              source_village_name,
              total_population,
              total_households,
              rural_urban,
              source_properties,
              match_evidence,
              review_status,
              is_active,
              promotion_status,
              created_at,
              updated_at
            )
            values (
              :id,
              :village_id,
              :source_system,
              :source_version,
              :source_feature_id,
              :source_feature_index,
              :source_vlcode,
              :state,
              :district,
              'Review Approval Tiny Fixture Subdistrict',
              :source_village_name,
              :total_population,
              :total_households,
              'Rural',
              '{{"fixture": true}}'::jsonb,
              '{{"fixture": true, "scope": "review_approval_tiny_fixture_apply_regression"}}'::jsonb,
              'AUTO_CANDIDATE',
              false,
              'NOT_PROMOTED',
              now(),
              now()
            )
        """), {
            **row,
            "source_system": SOURCE_SYSTEM,
            "source_version": SOURCE_VERSION,
            "state": STATE,
            "district": DISTRICT,
        })


def run_apply() -> tuple[int, dict]:
    if OUTPUT.exists():
        OUTPUT.unlink()

    proc = subprocess.run(
        [
            str(PYTHON),
            str(SCRIPT),
            "--apply",
            "--enable-policy",
            "--state-or-ut", STATE,
            "--district", DISTRICT,
            "--reviewer-notes", "tiny fixture bulk approval for promotion readiness",
            "--max-rows", "2",
            "--output", str(OUTPUT),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    check(OUTPUT.exists(), "Approval apply writes audit output", proc.stdout or proc.stderr)
    data = json.loads(OUTPUT.read_text(encoding="utf-8"))
    data["returncode"] = proc.returncode
    return proc.returncode, data


def main() -> int:
    print("=" * 72)
    print("NWDP DEMOGRAPHIC PROFILE REVIEW APPROVAL TINY FIXTURE APPLY REGRESSION")
    print("=" * 72)

    db_engine = engine()

    with db_engine.begin() as conn:
        before_global = dict(conn.execute(text(f"""
            select
              count(*)::bigint as profile_row_count,
              count(*) filter (where review_status = 'APPROVED_FOR_PROMOTION')::bigint as approved_for_promotion_count,
              count(*) filter (where is_active = true)::bigint as active_profile_row_count,
              count(*) filter (where promotion_status = 'PROMOTED')::bigint as promoted_profile_row_count
            from {TARGET_TABLE}
        """)).mappings().one())

        cleanup(conn)
        create_fixture(conn)
        fixture_before = fixture_counts(conn)

    check(fixture_before["fixture_row_count"] == 2, "Fixture has two rows", fixture_before)
    check(fixture_before["auto_candidate_fixture_row_count"] == 2, "Fixture starts auto-candidate", fixture_before)
    check(fixture_before["approved_fixture_row_count"] == 0, "Fixture starts unapproved", fixture_before)
    check(fixture_before["active_fixture_row_count"] == 0, "Fixture starts inactive", fixture_before)
    check(fixture_before["promoted_fixture_row_count"] == 0, "Fixture starts not promoted", fixture_before)

    code, first = run_apply()
    check(code == 0, "Tiny fixture approval apply exits zero", first)
    check(first["healthy"] is True, "Tiny fixture approval apply is healthy", first)
    check(first["enable_policy"] is True, "Explicit enable policy is recorded", first)
    check(first["approval_summary"]["candidate_profile_row_count"] == 2, "First apply sees two candidates", first["approval_summary"])
    check(first["apply_result"]["planned_approval_count"] == 2, "First apply plans two approvals", first["apply_result"])
    check(first["apply_result"]["approved_count"] == 2, "First apply approves two rows", first["apply_result"])
    check(first["guardrails"]["db_writes_attempted"] is True, "Apply records DB writes", first["guardrails"])
    check(first["guardrails"]["profile_review_status_changed"] is True, "Apply records review status change", first["guardrails"])
    check(first["guardrails"]["profiles_promoted"] is False, "Apply promotes no profiles", first["guardrails"])
    check(first["guardrails"]["profile_rows_activated"] is False, "Apply activates no rows", first["guardrails"])
    check(first["guardrails"]["runtime_lookup_enabled"] is False, "Runtime lookup remains disabled", first["guardrails"])
    check(first["guardrails"]["android_behavior_changed"] is False, "Android remains unchanged", first["guardrails"])

    with db_engine.connect() as conn:
        fixture_after_first = fixture_counts(conn)

    check(fixture_after_first["fixture_row_count"] == 2, "Fixture rows remain present", fixture_after_first)
    check(fixture_after_first["approved_fixture_row_count"] == 2, "Fixture rows are approved", fixture_after_first)
    check(fixture_after_first["auto_candidate_fixture_row_count"] == 0, "Fixture rows leave auto-candidate bucket", fixture_after_first)
    check(fixture_after_first["active_fixture_row_count"] == 0, "Fixture rows remain inactive", fixture_after_first)
    check(fixture_after_first["promoted_fixture_row_count"] == 0, "Fixture rows remain not promoted", fixture_after_first)

    code, second = run_apply()
    check(code == 0, "Second tiny fixture approval apply exits zero", second)
    check(second["apply_result"]["planned_approval_count"] == 0, "Second apply sees no remaining candidates", second["apply_result"])
    check(second["apply_result"]["approved_count"] == 0, "Second apply is idempotent", second["apply_result"])
    check(second["guardrails"]["profile_review_status_changed"] is False, "Second apply changes no review status", second["guardrails"])

    with db_engine.begin() as conn:
        cleanup(conn)
        after_global = dict(conn.execute(text(f"""
            select
              count(*)::bigint as profile_row_count,
              count(*) filter (where review_status = 'APPROVED_FOR_PROMOTION')::bigint as approved_for_promotion_count,
              count(*) filter (where is_active = true)::bigint as active_profile_row_count,
              count(*) filter (where promotion_status = 'PROMOTED')::bigint as promoted_profile_row_count
            from {TARGET_TABLE}
        """)).mappings().one())

    check(after_global == before_global, "Regression returns profile table to pre-test counts", {
        "before": before_global,
        "after": after_global,
    })

    print("=" * 72)
    print("NWDP DEMOGRAPHIC PROFILE REVIEW APPROVAL TINY FIXTURE APPLY REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

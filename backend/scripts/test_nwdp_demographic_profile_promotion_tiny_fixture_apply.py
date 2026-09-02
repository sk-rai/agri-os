#!/usr/bin/env python3
"""Regression for tiny fixture NWDP demographic profile promotion apply."""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.database import SessionLocal
from scripts.apply_nwdp_demographic_profile_import import SOURCE_SYSTEM

PYTHON = ROOT / "venv/bin/python"
SCRIPT = ROOT / "backend/scripts/apply_nwdp_demographic_profile_promotion.py"
OUTPUT = Path("/tmp/nwdp-demographic-profile-promotion-tiny-fixture-apply.json")
FIXTURE_SOURCE_VERSION = "promotion-tiny-fixture-apply-regression"
FIXTURE_STATE = "Promotion Tiny Fixture State"
FIXTURE_DISTRICT = "Promotion Tiny Fixture District"


def check(condition, label, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:2200])
    if not condition:
        raise AssertionError(label)


def profile_counts(db):
    return dict(db.execute(text("""
        select
          count(*)::bigint as profile_row_count,
          count(*) filter (where is_active = true)::bigint as active_profile_row_count,
          count(*) filter (where promotion_status = 'PROMOTED')::bigint as promoted_profile_row_count
        from geography_village_demographic_profiles
    """)).mappings().one())


def fixture_counts(db):
    return dict(db.execute(text("""
        select
          count(*)::bigint as fixture_row_count,
          count(*) filter (where is_active = true)::bigint as active_fixture_row_count,
          count(*) filter (where promotion_status = 'PROMOTED')::bigint as promoted_fixture_row_count,
          count(*) filter (where review_status = 'APPROVED_FOR_PROMOTION')::bigint as approved_fixture_row_count
        from geography_village_demographic_profiles
        where source_version = :source_version
    """), {"source_version": FIXTURE_SOURCE_VERSION}).mappings().one())


def cleanup(db):
    db.execute(text("""
        delete from geography_village_demographic_profiles
        where source_version = :source_version
    """), {"source_version": FIXTURE_SOURCE_VERSION})
    db.commit()


def insert_fixture(db):
    village_ids = [
        str(row["id"])
        for row in db.execute(text("select id from geography_villages order by id limit 2")).mappings()
    ]
    check(len(village_ids) >= 2, "At least two canonical villages exist for promotion fixture", village_ids)

    rows = []
    for idx, name in enumerate(("Approved Promotion Fixture A", "Approved Promotion Fixture B")):
        rows.append({
            "id": str(uuid.uuid4()),
            "source_feature_id": str(uuid.uuid4()),
            "village_id": village_ids[idx],
            "village": name,
        })

    for row in rows:
        db.execute(text("""
            insert into geography_village_demographic_profiles (
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
              male_population,
              female_population,
              total_households,
              average_household_size,
              rural_urban,
              source_properties,
              match_evidence,
              review_status,
              is_active,
              promotion_status
            )
            values (
              :id,
              :village_id,
              :source_system,
              :source_version,
              :source_feature_id,
              0,
              'promotion-tiny-fixture-vlcode',
              :state,
              :district,
              'Promotion Tiny Fixture Subdistrict',
              :village,
              10,
              5,
              5,
              2,
              5,
              'Rural',
              cast(:source_properties as jsonb),
              cast(:match_evidence as jsonb),
              'APPROVED_FOR_PROMOTION',
              false,
              'NOT_PROMOTED'
            )
        """), {
            **row,
            "source_system": SOURCE_SYSTEM,
            "source_version": FIXTURE_SOURCE_VERSION,
            "state": FIXTURE_STATE,
            "district": FIXTURE_DISTRICT,
            "source_properties": json.dumps({"fixture": True}),
            "match_evidence": json.dumps({"fixture": True, "scope": "promotion_tiny_fixture_apply_regression"}),
        })
    db.commit()


def run_apply():
    if OUTPUT.exists():
        OUTPUT.unlink()
    proc = subprocess.run([
        str(PYTHON),
        str(SCRIPT),
        "--apply",
        "--enable-policy",
        "--state-or-ut",
        FIXTURE_STATE,
        "--district",
        FIXTURE_DISTRICT,
        "--source-version",
        FIXTURE_SOURCE_VERSION,
        "--output",
        str(OUTPUT),
    ], cwd=str(ROOT), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False, timeout=30)
    check(OUTPUT.exists(), "Promotion apply writes audit output", proc.stdout)
    return proc.returncode, json.loads(OUTPUT.read_text(encoding="utf-8"))


def main() -> int:
    print("=" * 72)
    print("NWDP DEMOGRAPHIC PROFILE PROMOTION TINY FIXTURE APPLY REGRESSION")
    print("=" * 72)

    with SessionLocal() as db:
        cleanup(db)
        before = profile_counts(db)
        insert_fixture(db)
        inserted = fixture_counts(db)
        check(inserted["fixture_row_count"] == 2, "Fixture has two eligible rows", inserted)
        check(inserted["active_fixture_row_count"] == 0, "Fixture starts inactive", inserted)
        check(inserted["promoted_fixture_row_count"] == 0, "Fixture starts not promoted", inserted)

    try:
        code, first = run_apply()
        check(code == 0, "Tiny fixture promotion apply exits zero", first)
        check(first["healthy"] is True, "Tiny fixture apply is healthy", first)
        check(first["enable_policy"] is True, "Explicit policy flag is recorded", first)
        check(first["apply_result"]["planned_promotion_count"] == 2, "Apply plans two promotions", first["apply_result"])
        check(first["apply_result"]["promoted_count"] == 2, "Apply promotes two fixture rows", first["apply_result"])
        check(first["apply_result"]["activated_count"] == 2, "Apply activates two fixture rows", first["apply_result"])

        guardrails = first["guardrails"]
        check(guardrails["db_writes_attempted"] is True, "Apply records DB writes", guardrails)
        check(guardrails["profiles_promoted"] is True, "Apply records profile promotion", guardrails)
        check(guardrails["profile_rows_activated"] is True, "Apply records profile activation", guardrails)
        check(guardrails["runtime_lookup_enabled"] is False, "Runtime lookup remains disabled", guardrails)
        check(guardrails["android_behavior_changed"] is False, "Android remains unchanged", guardrails)
        check(guardrails["official_census_claimed_imported"] is False, "Official Census remains unclaimed", guardrails)

        with SessionLocal() as db:
            after_apply = fixture_counts(db)

        check(after_apply["fixture_row_count"] == 2, "Fixture rows remain present after apply", after_apply)
        check(after_apply["active_fixture_row_count"] == 2, "Fixture rows are active after apply", after_apply)
        check(after_apply["promoted_fixture_row_count"] == 2, "Fixture rows are promoted after apply", after_apply)
        check(after_apply["approved_fixture_row_count"] == 2, "Fixture review approval remains", after_apply)

        code, second = run_apply()
        check(code == 0, "Second tiny fixture promotion apply exits zero", second)
        check(second["apply_result"]["planned_promotion_count"] == 0, "Second apply sees no remaining eligible rows", second["apply_result"])
        check(second["apply_result"]["promoted_count"] == 0, "Second apply is idempotent", second["apply_result"])
        check(second["apply_result"]["activated_count"] == 0, "Second apply activates zero rows", second["apply_result"])

    finally:
        with SessionLocal() as db:
            cleanup(db)
            after = profile_counts(db)

    check(before == after, "Regression returns profile table to pre-test counts", {"before": before, "after": after})

    print("=" * 72)
    print("NWDP DEMOGRAPHIC PROFILE PROMOTION TINY FIXTURE APPLY REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

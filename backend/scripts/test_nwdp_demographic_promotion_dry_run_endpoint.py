#!/usr/bin/env python3
"""Regression for NWDP demographic profile promotion dry-run endpoint."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.database import SessionLocal
from app.main import app
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin

ENDPOINT = "/api/v1/master-data/geography/nwdp-demographic-profiles/promotion/dry-run"
FIXTURE_SOURCE_VERSION = "promotion-dry-run-regression"


def check(condition, label, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:2000])
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


def cleanup(db):
    db.execute(text("""
        delete from geography_village_demographic_profiles
        where source_version = :source_version
    """), {"source_version": FIXTURE_SOURCE_VERSION})
    db.commit()


def insert_fixture(db):
    village_id = db.execute(text("select id::text from geography_villages limit 1")).scalar()
    rows = [
        {
            "id": str(uuid.uuid4()),
            "source_feature_id": str(uuid.uuid4()),
            "review_status": "APPROVED_FOR_PROMOTION",
            "district": "Promotion Fixture District",
            "village": "Approved Fixture Village",
        },
        {
            "id": str(uuid.uuid4()),
            "source_feature_id": str(uuid.uuid4()),
            "review_status": "MANUAL_REVIEW",
            "district": "Promotion Fixture District",
            "village": "Manual Fixture Village",
        },
    ]

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
              'NWDP_GSI_VILLAGE_BOUNDARY',
              :source_version,
              :source_feature_id,
              0,
              'promotion-fixture-vlcode',
              'Promotion Fixture State',
              :district,
              'Promotion Fixture Subdistrict',
              :village,
              10,
              5,
              5,
              2,
              5,
              'Rural',
              cast(:source_properties as jsonb),
              cast(:match_evidence as jsonb),
              :review_status,
              false,
              'NOT_PROMOTED'
            )
        """), {
            **row,
            "village_id": village_id,
            "source_version": FIXTURE_SOURCE_VERSION,
            "source_properties": json.dumps({"fixture": True}),
            "match_evidence": json.dumps({"fixture": True, "scope": "promotion_dry_run_regression"}),
        })
    db.commit()
    return rows


def main() -> int:
    print("=" * 72)
    print("NWDP DEMOGRAPHIC PROMOTION DRY-RUN ENDPOINT REGRESSION")
    print("=" * 72)

    client = TestClient(app)

    with SessionLocal() as db:
        cleanup(db)
        before = profile_counts(db)
        insert_fixture(db)
        admin_user, headers = create_test_admin(db)

        try:
            unauth = client.get(ENDPOINT)
            check(unauth.status_code in (401, 403), "Unauthenticated dry-run is denied", unauth.text)

            empty = client.get(
                ENDPOINT,
                headers=headers,
                params={"state_or_ut": "Promotion Fixture State", "district": "No Approved District"},
            )
            check(empty.status_code == 200, "Empty scoped dry-run returns 200", empty.text)
            empty_data = empty.json()
            check(empty_data["enabled"] is False, "Empty dry-run is disabled", empty_data)
            check(empty_data["reason"] == "NO_APPROVED_INACTIVE_NOT_PROMOTED_DEMOGRAPHIC_PROFILES", "Empty reason is explicit", empty_data)

            response = client.get(
                ENDPOINT,
                headers=headers,
                params={"state_or_ut": "Promotion Fixture State", "district": "Promotion Fixture District"},
            )
            check(response.status_code == 200, "Promotion dry-run returns 200", response.text)
            data = response.json()

            check(data["schema_version"] == "nwdp_demographic_profile_promotion_dry_run.v1", "Schema version is stable", data)
            check(data["mode"] == "read_only_promotion_dry_run", "Mode is dry-run", data)
            check(data["healthy"] is True, "Dry-run is healthy", data)
            check(data["enabled"] is True, "Dry-run enabled when approved rows exist", data)

            summary = data["summary"]
            check(summary["eligible_profile_row_count"] == 1, "Dry-run sees only approved row", summary)
            check(summary["approved_for_promotion_count"] == 1, "Approved count is one", summary)
            check(summary["active_profile_row_count"] == 0, "No active rows eligible", summary)
            check(summary["promoted_profile_row_count"] == 0, "No promoted rows eligible", summary)

            policy = data["selection_policy"]
            check(policy["required_review_status"] == "APPROVED_FOR_PROMOTION", "Dry-run requires approved review status", policy)
            check(policy["required_promotion_status"] == "NOT_PROMOTED", "Dry-run requires not promoted", policy)
            check(policy["required_is_active"] is False, "Dry-run requires inactive row", policy)

            check(len(data["state_district_summary"]) == 1, "Dry-run returns state/district summary", data["state_district_summary"])
            check(len(data["items"]) == 1, "Dry-run returns one eligible item", data["items"])
            check(data["items"][0]["review_status"] == "APPROVED_FOR_PROMOTION", "Item is approved", data["items"][0])
            check(data["items"][0]["promotion_status"] == "NOT_PROMOTED", "Item remains not promoted", data["items"][0])
            check(data["items"][0]["is_active"] is False, "Item remains inactive", data["items"][0])

            guardrails = data["guardrails"]
            check(guardrails["db_writes_attempted"] is False, "Dry-run writes no DB rows", guardrails)
            check(guardrails["profile_review_status_changed"] is False, "Dry-run changes no review status", guardrails)
            check(guardrails["profiles_promoted"] is False, "Dry-run promotes no profiles", guardrails)
            check(guardrails["profile_rows_activated"] is False, "Dry-run activates no rows", guardrails)
            check(guardrails["runtime_lookup_enabled"] is False, "Runtime lookup remains disabled", guardrails)
            check(guardrails["android_behavior_changed"] is False, "Android remains unchanged", guardrails)

        finally:
            cleanup(db)
            delete_test_admin(db, admin_user.id)
            after = profile_counts(db)

    check(before == after, "Regression returns profile table to pre-test counts", {"before": before, "after": after})

    print("=" * 72)
    print("NWDP DEMOGRAPHIC PROMOTION DRY-RUN ENDPOINT REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

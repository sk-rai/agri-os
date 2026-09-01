#!/usr/bin/env python3
"""Regression for guarded NWDP demographic profile admin review endpoint."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.main import app  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin  # noqa: E402


ENDPOINT_PREFIX = "/api/v1/master-data/geography/nwdp-demographic-profiles"


def db_url() -> str:
    return str(
        getattr(settings, "database_url", None)
        or getattr(settings, "DATABASE_URL", None)
        or "postgresql+psycopg2://agri_os:agri_os_dev@localhost:5432/agri_os"
    )


def check(condition, label, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:2000])
    if not condition:
        raise AssertionError(label)


def count_profiles(conn):
    return dict(conn.execute(text("""
        select
          count(*)::bigint as profile_row_count,
          count(*) filter (where is_active = true)::bigint as active_profile_row_count,
          count(*) filter (where promotion_status = 'PROMOTED')::bigint as promoted_profile_row_count
        from geography_village_demographic_profiles
    """)).mappings().one())


def create_fixture(conn) -> str:
    village_id = conn.execute(text("""
        select id::text
        from geography_villages
        limit 1
    """)).scalar()

    profile_id = str(uuid.uuid4())
    conn.execute(text("""
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
          'review-endpoint-regression',
          :source_feature_id,
          0,
          'review-fixture-vlcode',
          'Review Fixture State',
          'Review Fixture District',
          'Review Fixture Subdistrict',
          'Review Fixture Village',
          10,
          5,
          5,
          2,
          5,
          'Rural',
          cast(:source_properties as jsonb),
          cast(:match_evidence as jsonb),
          'AUTO_CANDIDATE',
          false,
          'NOT_PROMOTED'
        )
    """), {
        "id": profile_id,
        "village_id": village_id,
        "source_feature_id": str(uuid.uuid4()),
        "source_properties": json.dumps({"fixture": True}),
        "match_evidence": json.dumps({"fixture": True, "scope": "admin_review_endpoint_regression"}),
    })
    return profile_id


def main() -> int:
    print("=" * 72)
    print("NWDP DEMOGRAPHIC ADMIN REVIEW ENDPOINT REGRESSION")
    print("=" * 72)

    engine = create_engine(db_url())
    client = TestClient(app)
    admin_db = SessionLocal()
    admin_user, headers = create_test_admin(admin_db)

    with engine.begin() as conn:
        before = count_profiles(conn)
        profile_id = create_fixture(conn)

    try:
        unauth = client.patch(
            f"{ENDPOINT_PREFIX}/{profile_id}/review",
            json={
                "review_status": "MANUAL_REVIEW",
                "reviewer_decision": "MARK_MANUAL_REVIEW",
                "reviewer_notes": "needs manual review",
            },
        )
        check(unauth.status_code in (401, 403), "Unauthenticated review update is denied", unauth.text)

        bad_notes = client.patch(
            f"{ENDPOINT_PREFIX}/{profile_id}/review",
            headers=headers,
            json={
                "review_status": "MANUAL_REVIEW",
                "reviewer_decision": "MARK_MANUAL_REVIEW",
                "reviewer_notes": "",
            },
        )
        check(bad_notes.status_code == 422, "Review notes are required", bad_notes.text)

        mismatch = client.patch(
            f"{ENDPOINT_PREFIX}/{profile_id}/review",
            headers=headers,
            json={
                "review_status": "APPROVED_FOR_PROMOTION",
                "reviewer_decision": "MARK_MANUAL_REVIEW",
                "reviewer_notes": "mismatch should fail",
            },
        )
        check(mismatch.status_code == 422, "Decision/status mismatch is rejected", mismatch.text)

        approved = client.patch(
            f"{ENDPOINT_PREFIX}/{profile_id}/review",
            headers=headers,
            json={
                "review_status": "APPROVED_FOR_PROMOTION",
                "reviewer_decision": "APPROVE_FOR_PROMOTION",
                "reviewer_notes": "approved for later dry-run promotion review",
                "evidence_summary": {"fixture": True, "decision": "positive regression approval"},
            },
        )
        check(approved.status_code == 200, "Admin can approve inactive profile for future promotion", approved.text)
        approved_data = approved.json()
        check(approved_data["schema_version"] == "nwdp_demographic_profile_admin_review.v1", "Schema version is stable", approved_data)
        check(approved_data["previous_review_status"] == "AUTO_CANDIDATE", "Previous review status is returned", approved_data)
        check(approved_data["review_status"] == "APPROVED_FOR_PROMOTION", "Review status changed to approved", approved_data)
        check(approved_data["promotion_status"] == "NOT_PROMOTED", "Profile remains not promoted", approved_data)
        check(approved_data["is_active"] is False, "Profile remains inactive", approved_data)
        check(approved_data["profiles_promoted"] is False, "Endpoint promotes no profiles", approved_data)
        check(approved_data["profile_rows_activated"] is False, "Endpoint activates no rows", approved_data)
        check(approved_data["runtime_lookup_enabled"] is False, "Runtime lookup remains disabled", approved_data)
        check(approved_data["android_behavior_changed"] is False, "Android remains unchanged", approved_data)

        manual = client.patch(
            f"{ENDPOINT_PREFIX}/{profile_id}/review",
            headers=headers,
            json={
                "review_status": "MANUAL_REVIEW",
                "reviewer_decision": "MARK_MANUAL_REVIEW",
                "reviewer_notes": "send back to manual review bucket",
            },
        )
        check(manual.status_code == 200, "Admin can move profile to manual review", manual.text)
        manual_data = manual.json()
        check(manual_data["previous_review_status"] == "APPROVED_FOR_PROMOTION", "Second transition reports previous approval", manual_data)
        check(manual_data["review_status"] == "MANUAL_REVIEW", "Review status changed to manual review", manual_data)

        with engine.connect() as conn:
            row = conn.execute(text("""
                select review_status, promotion_status, is_active, match_evidence
                from geography_village_demographic_profiles
                where id = :id
            """), {"id": profile_id}).mappings().one()

        check(row["review_status"] == "MANUAL_REVIEW", "DB row records manual review status", dict(row))
        check(row["promotion_status"] == "NOT_PROMOTED", "DB row remains not promoted", dict(row))
        check(row["is_active"] is False, "DB row remains inactive", dict(row))
        evidence = dict(row["match_evidence"] or {})
        check(len(evidence.get("review_history") or []) >= 2, "Review history is appended", evidence)
        check(evidence["review_guardrail"]["promotion_status_remains_not_promoted"] is True, "Review guardrail records no promotion", evidence)

    finally:
        with engine.begin() as conn:
            conn.execute(text("""
                delete from geography_village_demographic_profiles
                where source_version = 'review-endpoint-regression'
            """))
            after = count_profiles(conn)
        delete_test_admin(admin_db, admin_user.id)
        admin_db.close()

    check(before == after, "Regression returns profile table to pre-test counts", {"before": before, "after": after})

    print("=" * 72)
    print("NWDP DEMOGRAPHIC ADMIN REVIEW ENDPOINT REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

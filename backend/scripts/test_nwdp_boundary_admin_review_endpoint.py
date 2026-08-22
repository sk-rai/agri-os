#!/usr/bin/env python3
"""Regression for NWDP boundary candidate review metadata endpoint."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import SessionLocal
from app.main import app
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin


def check(condition: bool, label: str, detail=None):
    status = "PASS" if condition else "FAIL"
    print(f"{status} {label}")
    if detail is not None:
        print(f"      {detail if isinstance(detail, str) else json.dumps(detail, indent=2, default=str)[:1200]}")
    if not condition:
        raise AssertionError(label)


def summary(db):
    return db.execute(text("""
        select
          count(*) as candidates,
          sum(case when is_active then 1 else 0 end) as active_candidates,
          sum(case when promotion_status <> 'NOT_PROMOTED' then 1 else 0 end) as promoted_candidates
        from geography_boundary_crosswalk_candidates
    """)).mappings().one()


def target_candidate(db):
    return db.execute(text("""
        select id::text, review_status, reviewer_decision, is_active, promotion_status
        from geography_boundary_crosswalk_candidates
        where candidate_bucket = 'PARENT_MATCH_VILLAGE_UNRESOLVED'
          and is_active = false
          and promotion_status = 'NOT_PROMOTED'
        order by source_feature_index
        limit 1
    """)).mappings().one()


def special_candidate(db):
    return db.execute(text("""
        select id::text
        from geography_boundary_crosswalk_candidates
        where candidate_bucket = 'SPECIAL_REFERENCE_FEATURE'
          and is_active = false
          and promotion_status = 'NOT_PROMOTED'
        order by source_feature_index
        limit 1
    """)).scalar()


def main() -> int:
    print("=" * 72)
    print("NWDP BOUNDARY ADMIN REVIEW ENDPOINT REGRESSION")
    print("=" * 72)

    client = TestClient(app)
    db = SessionLocal()
    admin = None

    try:
        before = summary(db)
        check(before["candidates"] >= 29789, "NWDP staged candidates exist", dict(before))
        check(before["active_candidates"] == 0, "Candidates start inactive", dict(before))
        check(before["promoted_candidates"] == 0, "Candidates start unpromoted", dict(before))

        candidate = target_candidate(db)
        candidate_id = candidate["id"]

        denied = client.patch(
            f"/api/v1/master-data/geography/nwdp-boundary-candidates/{candidate_id}/review",
            headers={"X-Tenant-ID": "default"},
            json={
                "reviewer_decision": "KEEP_PENDING",
                "review_status": "MANUAL_REVIEW",
                "reviewer_notes": "",
            },
        )
        check(denied.status_code in {401, 403}, "Unauthenticated review is denied", denied.text[:500])

        admin, headers = create_test_admin(db, role="ADMIN_EDITOR", tenant_id="default")

        missing_notes = client.patch(
            f"/api/v1/master-data/geography/nwdp-boundary-candidates/{candidate_id}/review",
            headers=headers,
            json={
                "reviewer_decision": "ACCEPT_REVIEWED_NAME_MATCH",
                "review_status": "APPROVED_FOR_PROMOTION",
                "reviewer_notes": "",
            },
        )
        check(missing_notes.status_code == 422, "Non-pending review requires notes", missing_notes.text[:500])

        response = client.patch(
            f"/api/v1/master-data/geography/nwdp-boundary-candidates/{candidate_id}/review",
            headers=headers,
            json={
                "reviewer_decision": "KEEP_PENDING",
                "review_status": "MANUAL_REVIEW",
                "reviewer_notes": "",
                "evidence_summary": {"regression": "keep pending without activation"},
            },
        )
        check(response.status_code == 200, "Admin editor can update review metadata", response.text[:800])
        data = response.json()
        check(data["schema_version"] == "nwdp_boundary_admin_candidate_review.v1", "Review schema version is stable", data)
        check(data["is_active"] is False, "Review endpoint keeps candidate inactive", data)
        check(data["promotion_status"] == "NOT_PROMOTED", "Review endpoint does not promote", data)
        check(data["runtime_spatial_matching_changed"] is False, "Review endpoint has no runtime spatial impact", data)
        check(data["android_behavior_changed"] is False, "Review endpoint has no Android impact", data)

        special_id = special_candidate(db)
        special_bad = client.patch(
            f"/api/v1/master-data/geography/nwdp-boundary-candidates/{special_id}/review",
            headers=headers,
            json={
                "reviewer_decision": "ACCEPT_DIRECT_CODE_MATCH",
                "review_status": "APPROVED_FOR_PROMOTION",
                "reviewer_notes": "Regression should reject special reference promotion.",
            },
        )
        check(special_bad.status_code == 422, "Special reference feature cannot be approved for promotion", special_bad.text[:600])

        special_ref = client.patch(
            f"/api/v1/master-data/geography/nwdp-boundary-candidates/{special_id}/review",
            headers=headers,
            json={
                "reviewer_decision": "MARK_REFERENCE_ONLY",
                "review_status": "REFERENCE_ONLY",
                "reviewer_notes": "Regression marks special feature reference-only without activation.",
            },
        )
        check(special_ref.status_code == 200, "Special reference feature can be marked reference-only", special_ref.text[:800])
        special_ref_data = special_ref.json()
        check(special_ref_data["is_active"] is False, "Reference-only review remains inactive", special_ref_data)
        check(special_ref_data["promotion_status"] == "NOT_PROMOTED", "Reference-only review remains unpromoted", special_ref_data)

        reset = client.patch(
            f"/api/v1/master-data/geography/nwdp-boundary-candidates/{special_id}/review",
            headers=headers,
            json={
                "reviewer_decision": "BLOCK_PENDING_SOURCE_REVIEW",
                "review_status": "BLOCKED",
                "reviewer_notes": "Regression reset to blocked for repeatability.",
            },
        )
        check(reset.status_code == 200, "Special reference reset succeeds", reset.text[:800])

        after = summary(db)
        check(after["candidates"] == before["candidates"], "Review endpoint did not create/delete candidates", dict(after))
        check(after["active_candidates"] == 0, "Review endpoint did not activate candidates", dict(after))
        check(after["promoted_candidates"] == 0, "Review endpoint did not promote candidates", dict(after))

        print("=" * 72)
        print("NWDP BOUNDARY ADMIN REVIEW ENDPOINT REGRESSION PASSED")
        print("=" * 72)
        return 0
    finally:
        if admin is not None:
            delete_test_admin(db, admin.id)
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

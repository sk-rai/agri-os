#!/usr/bin/env python3
"""Regression for guarded project-scoped NWDP boundary assignment API."""

from __future__ import annotations

import json
import sys
import uuid
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.database import SessionLocal
from app.main import app
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin

TENANT_ID = "default"
ROLLBACK_TOKEN = "nwdp-project-boundary-assignment-api-regression"
MATCH_SOURCE = "ADMIN_PROJECT_MATCHING"


def check(condition, label, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print("   ", json.dumps(detail, indent=2, sort_keys=True, default=str)[:1600])
    if not condition:
        raise AssertionError(label)


def validated_candidate(db):
    row = db.execute(text("""
        select
          c.id::text as candidate_id,
          c.proposed_village_id::text as village_id,
          c.proposed_village_lgd_code,
          b.state_or_ut,
          f.geometry_validation_status
        from geography_boundary_crosswalk_candidates c
        join geography_boundary_import_batches b on b.id = c.import_batch_id
        join geography_boundary_source_features f on f.id = c.source_feature_id
        where b.source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
          and c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
          and c.review_status = 'AUTO_CANDIDATE'
          and c.promotion_status = 'NOT_PROMOTED'
          and c.is_active = false
          and c.proposed_village_id is not null
          and f.geometry_validation_status = 'VALIDATED'
        order by f.source_feature_index
        limit 1
    """)).mappings().first()
    if not row:
        raise RuntimeError("No validated project-boundary candidate found")
    return dict(row)


def non_validated_candidate(db):
    row = db.execute(text("""
        select
          c.id::text as candidate_id,
          c.proposed_village_id::text as village_id,
          c.proposed_village_lgd_code,
          b.state_or_ut,
          f.geometry_validation_status
        from geography_boundary_crosswalk_candidates c
        join geography_boundary_import_batches b on b.id = c.import_batch_id
        join geography_boundary_source_features f on f.id = c.source_feature_id
        where b.source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
          and c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
          and c.review_status = 'AUTO_CANDIDATE'
          and c.promotion_status = 'NOT_PROMOTED'
          and c.is_active = false
          and c.proposed_village_id is not null
          and f.geometry_validation_status <> 'VALIDATED'
        order by f.source_feature_index
        limit 1
    """)).mappings().first()
    if not row:
        raise RuntimeError("No non-validated boundary candidate found")
    return dict(row)


def counts(db):
    row = db.execute(text("""
        select
          (select count(*) from geography_boundary_project_matches) as matches,
          (select count(*) from geography_boundary_project_matches
             where is_active = true) as active_matches,
          (select count(*) from geography_boundary_crosswalk_candidates
             where is_active = true) as active_candidates,
          (select count(*) from geography_boundary_crosswalk_candidates
             where promotion_status = 'PROMOTED') as promoted_candidates,
          (select count(*) from geography_boundary_runtime_features) as runtime_features,
          (select count(*) from geography_boundary_runtime_crosswalks) as runtime_crosswalks
    """)).mappings().one()
    return {key: int(value or 0) for key, value in dict(row).items()}


def create_project_fixture(db, project_id, farmer_id, candidate):
    db.execute(text("""
        insert into projects (
          id, tenant_id, name, description, start_date, end_date, status,
          geography_scope, crop_scope, config, created_at, updated_at,
          version, is_active
        )
        values (
          :project_id, :tenant_id, 'NWDP Assignment API Regression',
          'Temporary project boundary assignment fixture.',
          :start_date, :end_date, 'ACTIVE',
          cast(:scope as jsonb), '[]'::jsonb, '{}'::jsonb,
          now(), now(), 'v1.0', true
        )
    """), {
        "project_id": project_id,
        "tenant_id": TENANT_ID,
        "start_date": date(2026, 1, 1),
        "end_date": date(2026, 12, 31),
        "scope": json.dumps({
            "source": "nwdp_project_boundary_assignment_api_regression",
            "state_or_ut": candidate["state_or_ut"],
            "village_ids": [candidate["village_id"]],
            "village_lgd_codes": [candidate["proposed_village_lgd_code"]],
        }),
    })
    db.execute(text("""
        insert into farmers (
          id, tenant_id, project_id, mobile_number, village_id, display_name,
          status, created_at, updated_at, version, is_active
        )
        values (
          :farmer_id, :tenant_id, :project_id, :mobile, :village_id,
          'NWDP Assignment API Farmer', 'ACTIVE',
          now(), now(), 'v1.0', true
        )
    """), {
        "farmer_id": farmer_id,
        "tenant_id": TENANT_ID,
        "project_id": project_id,
        "mobile": "9999900099",
        "village_id": candidate["village_id"],
    })
    db.commit()


def cleanup(db, project_id, farmer_id):
    db.rollback()
    db.execute(text("""
        delete from geography_boundary_project_matches
        where project_id = :project_id or rollback_token = :token
    """), {"project_id": project_id, "token": ROLLBACK_TOKEN})
    db.execute(
        text("delete from farmers where id = :farmer_id"),
        {"farmer_id": farmer_id},
    )
    db.execute(
        text("delete from projects where id = :project_id"),
        {"project_id": project_id},
    )
    db.commit()


def main():
    print("=" * 72)
    print("NWDP PROJECT BOUNDARY ASSIGNMENT API REGRESSION")
    print("=" * 72)

    client = TestClient(app)
    db = SessionLocal()
    admin = viewer = None
    project_id = str(uuid.uuid4())
    farmer_id = str(uuid.uuid4())

    try:
        candidate = validated_candidate(db)
        unsafe_candidate = non_validated_candidate(db)
        baseline = counts(db)
        create_project_fixture(db, project_id, farmer_id, candidate)

        unsafe_farmer_id = str(uuid.uuid4())
        db.execute(text("""
            insert into farmers (
              id, tenant_id, project_id, mobile_number, village_id, display_name,
              status, created_at, updated_at, version, is_active
            )
            values (
              :farmer_id, :tenant_id, :project_id, :mobile, :village_id,
              'NWDP Unsafe Assignment API Farmer', 'ACTIVE',
              now(), now(), 'v1.0', true
            )
        """), {
            "farmer_id": unsafe_farmer_id,
            "tenant_id": TENANT_ID,
            "project_id": project_id,
            "mobile": "9999900098",
            "village_id": unsafe_candidate["village_id"],
        })
        db.commit()

        # Assignment must work from project geography_scope alone.
        db.execute(
            text("delete from farmers where id = :farmer_id"),
            {"farmer_id": farmer_id},
        )
        db.commit()

        url = (
            "/api/v1/master-data/geography/"
            f"nwdp-boundary-project-matching/projects/{project_id}/"
            f"villages/{candidate['village_id']}"
        )
        body = {
            "candidate_id": candidate["candidate_id"],
            "rollback_token": ROLLBACK_TOKEN,
            "reason": "Regression assignment",
            "supersede_existing": False,
        }

        denied = client.put(url, json=body, headers={"X-Tenant-ID": TENANT_ID})
        check(denied.status_code in {401, 403}, "Unauthenticated assignment denied")

        viewer, viewer_headers = create_test_admin(
            db, role="ADMIN_VIEWER", tenant_id=TENANT_ID
        )
        denied = client.put(url, json=body, headers=viewer_headers)
        check(denied.status_code == 403, "VIEW-only assignment denied", denied.text)

        admin, headers = create_test_admin(
            db, role="ENTERPRISE_ADMIN", tenant_id=TENANT_ID
        )

        preview = client.get(
            "/api/v1/master-data/geography/"
            "nwdp-boundary-project-matching/project-preview",
            params={"project_id": project_id, "limit": 25},
            headers=headers,
        )
        preview_data = preview.json()
        check(
            preview.status_code == 200,
            "Scope-only project preview succeeds",
            preview_data,
        )
        check(
            preview_data["summary"]["project_village_count"] == 2,
            "Project preview combines scope and relational villages",
            preview_data["summary"],
        )
        check(
            preview_data["summary"]["villages_with_eligible_boundary"] == 1,
            "Geography-scope village has validated boundary",
            preview_data["summary"],
        )
        check(
            preview_data["summary"]["villages_without_eligible_boundary"] == 1,
            "Unsafe relational village remains ineligible",
            preview_data["summary"],
        )
        check(
            any(
                item["village_id"] == candidate["village_id"]
                and item["sample_candidate_id"] == candidate["candidate_id"]
                for item in preview_data["items"]
            ),
            "Scope village selects exact validated candidate",
            preview_data["items"],
        )
        check(
            any(
                item["village_id"] == unsafe_candidate["village_id"]
                and item["sample_candidate_id"] is None
                for item in preview_data["items"]
            ),
            "Non-validated relational village has no eligible candidate",
            preview_data["items"],
        )

        wrong_tenant_headers = dict(headers)
        wrong_tenant_headers["X-Tenant-ID"] = "wrong-tenant"
        wrong_tenant = client.put(url, json=body, headers=wrong_tenant_headers)
        check(
            wrong_tenant.status_code == 403,
            "Cross-tenant assignment is denied",
            wrong_tenant.text,
        )

        unsafe_url = (
            "/api/v1/master-data/geography/"
            f"nwdp-boundary-project-matching/projects/{project_id}/"
            f"villages/{unsafe_candidate['village_id']}"
        )
        unsafe_body = {
            "candidate_id": unsafe_candidate["candidate_id"],
            "rollback_token": ROLLBACK_TOKEN,
            "reason": "Must reject non-validated geometry",
            "supersede_existing": False,
        }
        unsafe_response = client.put(
            unsafe_url,
            json=unsafe_body,
            headers=headers,
        )
        check(
            unsafe_response.status_code == 409,
            "Non-validated boundary candidate is rejected",
            unsafe_response.text,
        )
        check(
            unsafe_response.json()["detail"]
            == "BOUNDARY_CANDIDATE_NOT_ASSIGNABLE",
            "Non-validated rejection reason is stable",
            unsafe_response.json(),
        )
        check(counts(db) == baseline, "Rejected safety cases write no matches")

        response = client.put(url, json=body, headers=headers)
        data = response.json()
        check(response.status_code == 200, "PROJECT_EDIT assignment succeeds", data)
        check(data["action"] == "APPLIED", "Assignment action is APPLIED", data)
        check(data["assignment"]["is_active"] is True, "Assignment is active", data)
        check(
            data["assignment"]["boundary_candidate_id"] == candidate["candidate_id"],
            "Exact candidate assigned",
            data,
        )
        check(
            data["assignment"]["geometry_validation_status"] == "VALIDATED",
            "Assigned candidate has validated geometry",
            data,
        )

        applied = counts(db)
        check(applied["matches"] == baseline["matches"] + 1, "One match created")
        check(
            applied["active_matches"] == baseline["active_matches"] + 1,
            "One active match created",
        )

        repeated = client.put(url, json=body, headers=headers)
        repeated_data = repeated.json()
        check(repeated.status_code == 200, "Repeated assignment succeeds")
        check(
            repeated_data["action"] == "IDEMPOTENT_NO_OP",
            "Repeated assignment is idempotent",
            repeated_data,
        )
        check(counts(db) == applied, "Idempotent assignment changes no counts")

        listed = client.get(
            f"/api/v1/master-data/geography/"
            f"nwdp-boundary-project-matching/projects/{project_id}/assignments",
            headers=headers,
        )
        listed_data = listed.json()
        check(listed.status_code == 200, "Project assignments can be listed")
        check(listed_data["active_count"] == 1, "List reports one active assignment")
        check(
            listed_data["items"][0]["village_id"] == candidate["village_id"],
            "Listed assignment has expected village",
        )

        wrong = client.delete(
            url,
            params={"rollback_token": "wrong-token"},
            headers=headers,
        )
        check(wrong.status_code == 409, "Wrong rollback token rejected", wrong.text)
        check(counts(db) == applied, "Wrong token changes no counts")

        rollback = client.delete(
            url,
            params={"rollback_token": ROLLBACK_TOKEN},
            headers=headers,
        )
        rollback_data = rollback.json()
        check(rollback.status_code == 200, "Token-protected unassignment succeeds")
        check(rollback_data["action"] == "ROLLED_BACK", "Assignment rolled back")
        check(
            rollback_data["assignment"]["is_active"] is False,
            "Rolled-back assignment is inactive",
        )

        final = counts(db)
        check(final["matches"] == baseline["matches"] + 1, "History is retained")
        check(
            final["active_matches"] == baseline["active_matches"],
            "No fixture assignment remains active",
        )
        for key in [
            "active_candidates",
            "promoted_candidates",
            "runtime_features",
            "runtime_crosswalks",
        ]:
            check(final[key] == baseline[key], f"Guarded count unchanged: {key}")

        repeated_rollback = client.delete(
            url,
            params={"rollback_token": ROLLBACK_TOKEN},
            headers=headers,
        )
        check(repeated_rollback.status_code == 200, "Repeated rollback succeeds")
        check(
            repeated_rollback.json()["action"] == "IDEMPOTENT_ROLLBACK_NO_OP",
            "Repeated rollback is idempotent",
        )

        print("=" * 72)
        print("NWDP PROJECT BOUNDARY ASSIGNMENT API REGRESSION PASSED")
        return 0
    finally:
        if viewer is not None:
            delete_test_admin(db, viewer.id)
        if admin is not None:
            delete_test_admin(db, admin.id)
        if "unsafe_farmer_id" in locals():
            db.rollback()
            db.execute(
                text("delete from farmers where id = :farmer_id"),
                {"farmer_id": unsafe_farmer_id},
            )
            db.commit()
        cleanup(db, project_id, farmer_id)
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

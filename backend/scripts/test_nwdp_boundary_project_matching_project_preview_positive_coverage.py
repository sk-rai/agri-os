#!/usr/bin/env python3
"""Regression for positive NWDP project boundary coverage preview.

Creates temporary project/farmer/enrollment rows against an existing eligible
NWDP DIRECT_VLCODE_MATCH candidate, verifies project preview coverage > 0, and
cleans up the temporary rows. It does not mutate NWDP staging candidates.
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import SessionLocal
from app.main import app
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin


TENANT_ID = "default"


def check(condition: bool, label: str, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print("   ", json.dumps(detail, indent=2, sort_keys=True, default=str)[:1800])
    if not condition:
        raise AssertionError(label)


def staging_summary(db):
    return db.execute(text("""
        select
          count(*) as candidates,
          sum(case when is_active then 1 else 0 end) as active_candidates,
          sum(case when promotion_status <> 'NOT_PROMOTED' then 1 else 0 end) as promoted_candidates
        from geography_boundary_crosswalk_candidates
    """)).mappings().one()


def eligible_village(db):
    row = db.execute(text("""
        select
          c.id::text as candidate_id,
          c.proposed_village_id::text as village_id,
          c.proposed_village_lgd_code,
          gv.canonical_name as village_name,
          b.state_or_ut
        from geography_boundary_import_batches b
        join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
        join geography_villages gv on gv.id = c.proposed_village_id
        where b.source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
          and c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
          and c.review_status = 'AUTO_CANDIDATE'
          and c.is_active = false
          and c.promotion_status = 'NOT_PROMOTED'
          and c.proposed_village_id is not null
        order by b.state_or_ut, c.source_feature_index
        limit 1
    """)).mappings().first()
    if not row:
        raise RuntimeError("No eligible NWDP direct-code candidate available")
    return row


def cleanup(db, project_id: str, farmer_id: str):
    db.rollback()
    db.execute(text("delete from farmer_project_enrollments where project_id = :project_id"), {"project_id": project_id})
    db.execute(text("delete from farmers where id = :farmer_id"), {"farmer_id": farmer_id})
    db.execute(text("delete from projects where id = :project_id"), {"project_id": project_id})
    db.commit()


def main() -> int:
    print("=" * 72)
    print("NWDP BOUNDARY PROJECT MATCHING PROJECT PREVIEW POSITIVE COVERAGE REGRESSION")
    print("=" * 72)

    client = TestClient(app)
    db = SessionLocal()
    admin = None

    project_id = str(uuid.uuid4())
    farmer_id = str(uuid.uuid4())
    enrollment_id = str(uuid.uuid4())

    try:
        before = staging_summary(db)
        village = eligible_village(db)

        db.execute(text("""
            insert into projects (
              id, tenant_id, name, description, start_date, end_date, status,
              geography_scope, crop_scope, config, created_at, updated_at, version, is_active
            )
            values (
              :project_id, :tenant_id, 'NWDP Boundary Positive Coverage Test',
              'Temporary regression project for read-only boundary coverage preview.',
              :start_date, :end_date, 'ACTIVE',
              cast(:geography_scope as jsonb), cast('[]' as jsonb), cast('{}' as jsonb),
              now(), now(), 'v1.0', true
            )
        """), {
            "project_id": project_id,
            "tenant_id": TENANT_ID,
            "start_date": date(2026, 1, 1),
            "end_date": date(2026, 12, 31),
            "geography_scope": json.dumps({
                "source": "nwdp_boundary_positive_coverage_regression",
                "state_or_ut": village["state_or_ut"],
                "village_id": village["village_id"],
                "village_lgd_code": village["proposed_village_lgd_code"],
            }),
        })

        db.execute(text("""
            insert into farmers (
              id, tenant_id, project_id, mobile_number, village_id, display_name,
              status, created_at, updated_at, version, is_active
            )
            values (
              :farmer_id, :tenant_id, :project_id, :mobile_number, :village_id,
              'NWDP Boundary Positive Coverage Farmer', 'ACTIVE', now(), now(), 'v1.0', true
            )
        """), {
            "farmer_id": farmer_id,
            "tenant_id": TENANT_ID,
            "project_id": project_id,
            "mobile_number": "9999900001",
            "village_id": village["village_id"],
        })

        db.execute(text("""
            insert into farmer_project_enrollments (
              id, tenant_id, farmer_id, project_id, enrollment_method, enrollment_source,
              status, metadata, created_at, updated_at, version, is_active
            )
            values (
              :enrollment_id, :tenant_id, :farmer_id, :project_id, 'REGRESSION',
              'NWDP_BOUNDARY_POSITIVE_COVERAGE_TEST', 'ACTIVE',
              cast(:metadata as jsonb), now(), now(), 'v1.0', true
            )
        """), {
            "enrollment_id": enrollment_id,
            "tenant_id": TENANT_ID,
            "farmer_id": farmer_id,
            "project_id": project_id,
            "metadata": json.dumps({"temporary": True}),
        })
        db.commit()

        admin, headers = create_test_admin(db, role="ADMIN_VIEWER", tenant_id=TENANT_ID)

        response = client.get(
            f"/api/v1/master-data/geography/nwdp-boundary-project-matching/project-preview?project_id={project_id}&limit=10",
            headers=headers,
        )
        data = response.json()

        check(response.status_code == 200, "Admin viewer can read positive project preview", response.text[:1000])
        check(data["schema_version"] == "nwdp_boundary_project_matching_project_preview.v1", "Schema version is stable", data)
        check(data["project"]["project_id"] == project_id, "Preview is scoped to temporary project", data["project"])

        summary = data["summary"]
        check(summary["project_village_count"] == 1, "Preview sees one temporary project village", summary)
        check(summary["villages_with_eligible_boundary"] == 1, "Preview finds covered project village", summary)
        check(summary["eligible_candidate_count"] >= 1, "Preview finds eligible boundary candidate", summary)
        check(summary["coverage_ratio"] == 1, "Preview reports full coverage for one-village fixture", summary)
        check(len(data["items"]) >= 1, "Preview returns coverage row", data["items"])
        check(data["items"][0]["eligible_candidate_count"] >= 1, "Coverage row has eligible candidate", data["items"][0])

        guardrails = data["guardrails"]
        check(guardrails["db_writes_attempted"] is False, "Endpoint attempts no DB writes", guardrails)
        check(guardrails["candidate_activation_changed"] is False, "Endpoint does not activate candidates", guardrails)
        check(guardrails["candidate_promotion_changed"] is False, "Endpoint does not promote candidates", guardrails)
        check(guardrails["runtime_tables_written"] is False, "Endpoint writes no runtime tables", guardrails)
        check(guardrails["runtime_spatial_matching_changed"] is False, "Endpoint keeps spatial matching disabled", guardrails)
        check(guardrails["lookup_api_enabled"] is False, "Endpoint keeps lookup disabled", guardrails)
        check(guardrails["android_behavior_changed"] is False, "Endpoint keeps Android unchanged", guardrails)

        after = staging_summary(db)
        check(after["candidates"] == before["candidates"], "Regression did not create/delete NWDP candidates", dict(after))
        check(after["active_candidates"] == 0, "Regression did not activate NWDP candidates", dict(after))
        check(after["promoted_candidates"] == 0, "Regression did not promote NWDP candidates", dict(after))

        print("=" * 72)
        print("NWDP BOUNDARY PROJECT MATCHING PROJECT PREVIEW POSITIVE COVERAGE REGRESSION PASSED")
        print("=" * 72)
        return 0
    finally:
        if admin is not None:
            delete_test_admin(db, admin.id)
        cleanup(db, project_id, farmer_id)
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

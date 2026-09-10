#!/usr/bin/env python3
"""Regression for tenant-scoped batched project geography readiness."""

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
from scripts.admin_auth_test_utils import (
    create_test_admin,
    delete_test_admin,
)

ENDPOINT = "/api/v1/master-data/geography/project-geography-readiness"


def check(condition, label, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if not condition:
        print(json.dumps(detail, indent=2, default=str))
        raise AssertionError(label)


def main():
    print("=" * 72)
    print("PROJECT GEOGRAPHY READINESS API REGRESSION")
    print("=" * 72)

    db = SessionLocal()
    client = TestClient(app)
    admin = None
    project_id = str(uuid.uuid4())
    other_project_id = str(uuid.uuid4())

    try:
        village = db.execute(text("""
            select v.id::text, v.lgd_code
            from geography_villages v
            where v.lgd_code is not null
              and v.is_active = true
              and exists (
                select 1
                from geography_boundary_crosswalk_candidates c
                join geography_boundary_import_batches b
                  on b.id = c.import_batch_id
                join geography_boundary_source_features f
                  on f.id = c.source_feature_id
                where c.proposed_village_id = v.id
                  and b.source_system =
                      'NWDP_GSI_VILLAGE_BOUNDARY'
                  and f.geometry_validation_status = 'VALIDATED'
                  and c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
                  and c.review_status = 'AUTO_CANDIDATE'
                  and c.promotion_status = 'NOT_PROMOTED'
                  and c.is_active = false
              )
            limit 1
        """)).mappings().one()

        db.execute(text("""
            insert into tenants (
              id, name, type, config, created_at, updated_at,
              version, is_active
            )
            values (
              'tenant-isolation-fixture',
              'Tenant Isolation Fixture',
              'ENTERPRISE',
              '{}'::jsonb,
              now(),
              now(),
              'v1.0',
              true
            )
        """))

        db.execute(text("""
            insert into projects (
              id, tenant_id, name, start_date, end_date, status,
              geography_scope, crop_scope, config,
              created_at, updated_at, version, is_active
            ) values
            (
              cast(:project_id as uuid), 'default',
              'Batch Geography Readiness Fixture',
              :start_date, :end_date, 'PLANNED',
              cast(:scope as jsonb), '[]'::jsonb, '{}'::jsonb,
              now(), now(), 'v1.0', true
            ),
            (
              cast(:other_project_id as uuid), 'tenant-isolation-fixture',
              'Other Tenant Geography Fixture',
              :start_date, :end_date, 'PLANNED',
              cast(:scope as jsonb), '[]'::jsonb, '{}'::jsonb,
              now(), now(), 'v1.0', true
            )
        """), {
            "project_id": project_id,
            "other_project_id": other_project_id,
            "start_date": date(2026, 1, 1),
            "end_date": date(2026, 12, 31),
            "scope": json.dumps({
                "village_lgd_codes": [
                    village["lgd_code"],
                    "999999999",
                ],
            }),
        })
        db.commit()

        admin, headers = create_test_admin(
            db,
            role="ADMIN_VIEWER",
            tenant_id="default",
        )

        response = client.get(ENDPOINT, headers=headers)
        payload = response.json()

        check(response.status_code == 200, "Batch endpoint succeeds", payload)
        check(
            payload["tenant_id"] == "default",
            "Response is tenant scoped",
            payload,
        )

        item = next(
            row for row in payload["items"]
            if row["project_id"] == project_id
        )

        check(
            item["scoped_village_code_count"] == 2,
            "Saved scope codes are counted",
            item,
        )
        check(
            item["resolved_village_count"] == 1,
            "Canonical village is resolved",
            item,
        )
        check(
            item["unresolved_village_code_count"] == 1,
            "Unknown LGD code is reported",
            item,
        )
        check(
            item["villages_with_eligible_boundary"] == 1,
            "Eligible boundary is counted",
            item,
        )
        check(
            bool(item["state_names"] and item["district_names"]),
            "Hierarchy labels are returned",
            item,
        )
        check(
            all(
                row["project_id"] != other_project_id
                for row in payload["items"]
            ),
            "Other tenant project is excluded",
            payload["items"],
        )
        check(
            payload["guardrails"]["db_writes_attempted"] is False,
            "Endpoint remains read-only",
            payload["guardrails"],
        )

        print("=" * 72)
        print("PROJECT GEOGRAPHY READINESS API REGRESSION PASSED")
        return 0
    finally:
        db.rollback()
        db.execute(text("""
            delete from projects
            where id in (
              cast(:project_id as uuid),
              cast(:other_project_id as uuid)
            )
        """), {
            "project_id": project_id,
            "other_project_id": other_project_id,
        })
        db.execute(text("""
            delete from tenants
            where id = 'tenant-isolation-fixture'
        """))
        db.commit()
        if admin is not None:
            delete_test_admin(db, admin.id)
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

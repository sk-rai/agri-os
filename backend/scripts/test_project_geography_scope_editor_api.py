#!/usr/bin/env python3
"""Regression for guarded project geography-scope editing."""

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

TENANT_ID = "default"


def check(condition, label, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(
            "   ",
            json.dumps(
                detail,
                indent=2,
                sort_keys=True,
                default=str,
            )[:1800],
        )
    if not condition:
        raise AssertionError(label)


def main() -> int:
    print("=" * 72)
    print("PROJECT GEOGRAPHY SCOPE EDITOR API REGRESSION")
    print("=" * 72)

    client = TestClient(app)
    db = SessionLocal()
    project_id = str(uuid.uuid4())
    admin = viewer = None

    try:
        villages = db.execute(text("""
            select
              v.id::text as village_id,
              v.lgd_code::text as village_lgd_code,
              v.canonical_name as village_name,
              s.canonical_name as state_name
            from geography_villages v
            join geography_districts d on d.id = v.district_id
            join geography_states s on s.id = d.state_id
            where v.is_active = true
              and d.is_active = true
              and s.is_active = true
              and v.lgd_code is not null
            order by v.lgd_code::text
            limit 2
        """)).mappings().all()

        check(
            len(villages) == 2,
            "Two canonical LGD villages are available",
        )
        villages = [dict(row) for row in villages]
        codes = [row["village_lgd_code"] for row in villages]

        baseline_audits = db.execute(text("""
            select count(*)
            from project_app_config_audit_events
        """)).scalar_one()

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
              :project_id,
              :tenant_id,
              'Project Geography Scope Regression',
              'Temporary geography-scope editor fixture.',
              :start_date,
              :end_date,
              'PLANNED',
              '{}'::jsonb,
              '[]'::jsonb,
              '{}'::jsonb,
              now(),
              now(),
              'v1.0',
              true
            )
        """), {
            "project_id": project_id,
            "tenant_id": TENANT_ID,
            "start_date": date(2026, 1, 1),
            "end_date": date(2027, 12, 31),
        })
        db.commit()

        url = f"/api/v1/projects/{project_id}/geography-scope"
        body = {
            "village_lgd_codes": codes,
            "reason": "Configure canonical villages for boundary assignment",
        }

        denied = client.patch(
            url,
            json=body,
            headers={"X-Tenant-ID": TENANT_ID},
        )
        check(
            denied.status_code in {401, 403},
            "Unauthenticated scope update is denied",
            denied.text,
        )

        viewer, viewer_headers = create_test_admin(
            db,
            role="ADMIN_VIEWER",
            tenant_id=TENANT_ID,
        )
        denied = client.patch(url, json=body, headers=viewer_headers)
        check(
            denied.status_code == 403,
            "VIEW-only scope update is denied",
            denied.text,
        )

        admin, headers = create_test_admin(
            db,
            role="ENTERPRISE_ADMIN",
            tenant_id=TENANT_ID,
        )

        unknown = client.patch(
            url,
            json={
                "village_lgd_codes": ["999999999"],
                "reason": "Reject unknown canonical village",
            },
            headers=headers,
        )
        check(
            unknown.status_code == 422,
            "Unknown village LGD code is rejected",
            unknown.text,
        )
        check(
            unknown.json()["detail"]["error"]
            == "UNKNOWN_VILLAGE_LGD_CODES",
            "Unknown-code rejection reason is stable",
            unknown.json(),
        )

        unchanged = db.execute(text("""
            select geography_scope
            from projects
            where id = :project_id
        """), {"project_id": project_id}).scalar_one()
        check(
            unchanged == {},
            "Rejected update leaves project scope unchanged",
            unchanged,
        )

        applied = client.patch(url, json=body, headers=headers)
        data = applied.json()
        check(
            applied.status_code == 200,
            "PROJECT_EDIT scope update succeeds",
            data,
        )
        check(
            data["geography_scope"]["village_lgd_codes"] == sorted(codes),
            "Canonical village codes are stored",
            data["geography_scope"],
        )
        check(
            set(data["geography_scope"]["village_ids"])
            == {row["village_id"] for row in villages},
            "Canonical village IDs are resolved",
            data["geography_scope"],
        )
        check(
            data["geography_scope"]["source"]
            == "admin_project_geography_scope_editor",
            "Scope source is recorded",
            data["geography_scope"],
        )

        audit = db.execute(text("""
            select
              action,
              patched_sections,
              before_config,
              after_config,
              config_patch,
              reason
            from project_app_config_audit_events
            where project_id = :project_id
            order by created_at desc
            limit 1
        """), {"project_id": project_id}).mappings().first()

        check(audit is not None, "Scope update writes an audit event")
        audit = dict(audit)
        check(
            audit["action"] == "UPDATE_PROJECT_GEOGRAPHY_SCOPE",
            "Audit action is stable",
            audit,
        )
        check(
            audit["patched_sections"] == ["geography_scope"],
            "Audit identifies geography scope",
            audit,
        )
        check(
            audit["before_config"]["geography_scope"] == {},
            "Audit preserves prior scope",
            audit,
        )
        check(
            audit["after_config"]["geography_scope"]
            == data["geography_scope"],
            "Audit preserves resulting scope",
            audit,
        )

        db.execute(text("""
            update projects
            set status = 'ACTIVE', updated_at = now()
            where id = :project_id
        """), {"project_id": project_id})
        db.commit()

        locked = client.patch(
            url,
            json={
                "village_lgd_codes": [codes[0]],
                "reason": "Must reject active project scope change",
            },
            headers=headers,
        )
        check(
            locked.status_code == 409,
            "Active project geography scope is locked",
            locked.text,
        )
        check(
            locked.json()["detail"]["error"]
            == "PROJECT_GEOGRAPHY_SCOPE_LOCKED",
            "Locked-scope rejection reason is stable",
            locked.json(),
        )

        final_scope = db.execute(text("""
            select geography_scope
            from projects
            where id = :project_id
        """), {"project_id": project_id}).scalar_one()
        check(
            final_scope == data["geography_scope"],
            "Locked update leaves applied scope unchanged",
            final_scope,
        )

        final_audits = db.execute(text("""
            select count(*)
            from project_app_config_audit_events
        """)).scalar_one()
        check(
            final_audits == baseline_audits + 1,
            "Exactly one scope audit event is created",
        )

        print("=" * 72)
        print("PROJECT GEOGRAPHY SCOPE EDITOR API REGRESSION PASSED")
        return 0
    finally:
        db.rollback()
        db.execute(text("""
            delete from project_app_config_audit_events
            where project_id = :project_id
        """), {"project_id": project_id})
        db.execute(text("""
            delete from projects
            where id = :project_id
        """), {"project_id": project_id})
        db.commit()

        if viewer is not None:
            delete_test_admin(db, viewer.id)
        if admin is not None:
            delete_test_admin(db, admin.id)
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

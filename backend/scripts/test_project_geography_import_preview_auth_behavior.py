#!/usr/bin/env python3
"""Behavior regression for project geography import-preview authorization."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import (
    Project,
    ProjectAppConfigAuditEvent,
    Tenant,
)
from scripts.admin_auth_test_utils import (
    create_test_admin,
    delete_test_admin,
)


def check(condition, label, detail=None):
    print(f"  {'PASS' if condition else 'FAIL'} {label}")
    if detail is not None:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(label)


def main() -> int:
    print("=" * 72)
    print("PROJECT GEOGRAPHY IMPORT PREVIEW AUTHORIZATION")
    print("=" * 72)

    tenant_id = f"geography-preview-auth-{uuid.uuid4().hex[:8]}"
    foreign_tenant_id = (
        f"geography-preview-auth-foreign-{uuid.uuid4().hex[:8]}"
    )
    project_id = uuid.uuid4()
    foreign_project_id = uuid.uuid4()

    db = SessionLocal()
    enterprise = None
    manager = None
    viewer = None

    try:
        village = db.execute(text("""
            SELECT lgd_code::text AS lgd_code
            FROM geography_villages
            WHERE is_active = true
              AND lgd_code IS NOT NULL
            ORDER BY lgd_code
            LIMIT 1
        """)).mappings().first()
        check(
            village is not None,
            "At least one active canonical village exists",
        )
        village_code = village["lgd_code"]
        now = datetime.now(timezone.utc)

        db.add(Tenant(
            id=tenant_id,
            name="Geography Preview Auth Tenant",
            type="ENTERPRISE",
            created_at=now,
            updated_at=now,
        ))
        db.add(Tenant(
            id=foreign_tenant_id,
            name="Geography Preview Foreign Tenant",
            type="ENTERPRISE",
            created_at=now,
            updated_at=now,
        ))
        db.add(Project(
            id=project_id,
            tenant_id=tenant_id,
            name="Geography Preview Project",
            start_date=date(2026, 10, 1),
            end_date=date(2027, 3, 31),
            status="PLANNED",
            geography_scope={},
            crop_scope=["RICE"],
            config={},
            created_at=now,
            updated_at=now,
        ))
        db.add(Project(
            id=foreign_project_id,
            tenant_id=foreign_tenant_id,
            name="Foreign Geography Preview Project",
            start_date=date(2026, 10, 1),
            end_date=date(2027, 3, 31),
            status="PLANNED",
            geography_scope={},
            crop_scope=["RICE"],
            config={},
            created_at=now,
            updated_at=now,
        ))
        db.commit()

        enterprise, enterprise_headers = create_test_admin(
            db,
            role="ENTERPRISE_ADMIN",
            tenant_id=tenant_id,
        )
        manager, manager_headers = create_test_admin(
            db,
            role="MANAGER",
            tenant_id=tenant_id,
        )
        viewer, viewer_headers = create_test_admin(
            db,
            role="ADMIN_VIEWER",
            tenant_id=tenant_id,
        )

        client = TestClient(app)
        endpoint = (
            f"/api/v1/projects/{project_id}/"
            "geography-scope/import-preview"
        )
        payload = {
            "village_lgd_codes": [
                village_code,
                village_code,
                "NOT_NUMERIC",
                "999999999999999999999999",
            ],
        }

        missing_bearer = client.post(
            endpoint,
            headers={"X-Tenant-ID": tenant_id},
            json=payload,
        )
        check(
            missing_bearer.status_code == 401,
            "Geography preview rejects missing bearer",
            missing_bearer.text,
        )

        viewer_denied = client.post(
            endpoint,
            headers=viewer_headers,
            json=payload,
        )
        check(
            viewer_denied.status_code == 403,
            "Geography preview rejects view-only administrator",
            viewer_denied.text,
        )

        unassigned_manager = client.post(
            endpoint,
            headers=manager_headers,
            json=payload,
        )
        check(
            unassigned_manager.status_code == 403,
            "Geography preview rejects unassigned manager",
            unassigned_manager.text,
        )

        impersonated_headers = dict(enterprise_headers)
        impersonated_headers["X-Actor-ID"] = str(uuid.uuid4())
        impersonated = client.post(
            endpoint,
            headers=impersonated_headers,
            json=payload,
        )
        check(
            impersonated.status_code == 403,
            "Geography preview rejects actor impersonation",
            impersonated.text,
        )
        check(
            impersonated.json()["detail"]["error"]
            == "ACTOR_ID_MISMATCH",
            "Actor impersonation has stable error code",
        )

        mismatched_headers = dict(enterprise_headers)
        mismatched_headers["X-Tenant-ID"] = foreign_tenant_id
        tenant_mismatch = client.post(
            endpoint,
            headers=mismatched_headers,
            json=payload,
        )
        check(
            tenant_mismatch.status_code == 403,
            "Geography preview rejects tenant mismatch",
            tenant_mismatch.text,
        )
        check(
            tenant_mismatch.json()["detail"]["error"]
            == "ADMIN_PERMISSION_DENIED",
            "Tenant mismatch has stable permission error",
        )

        foreign_endpoint = (
            f"/api/v1/projects/{foreign_project_id}/"
            "geography-scope/import-preview"
        )
        foreign_project = client.post(
            foreign_endpoint,
            headers=enterprise_headers,
            json=payload,
        )
        check(
            foreign_project.status_code == 404,
            "Geography preview hides foreign-tenant project",
            foreign_project.text,
        )

        project_before = (
            db.query(Project)
            .filter(Project.id == project_id)
            .one()
        )
        config_before = dict(project_before.config or {})
        scope_before = dict(project_before.geography_scope or {})
        audit_count_before = (
            db.query(ProjectAppConfigAuditEvent)
            .filter(
                ProjectAppConfigAuditEvent.project_id == project_id
            )
            .count()
        )

        response = client.post(
            endpoint,
            headers=enterprise_headers,
            json=payload,
        )
        check(
            response.status_code == 200,
            "Enterprise administrator previews geography import",
            response.text[:800],
        )
        body = response.json()
        check(
            body["schema_version"]
            == "project_geography_scope_import_preview.v1",
            "Preview schema version is stable",
        )
        check(
            body["tenant_id"] == tenant_id,
            "Preview reports verified tenant",
        )
        check(
            body["previewed_by"] == str(enterprise.id),
            "Preview reports verified administrator",
        )
        check(
            body["project"]["id"] == str(project_id),
            "Preview reports tenant-bounded project",
        )
        check(
            body["mode"] == "READ_ONLY_IMPORT_PREVIEW",
            "Preview reports read-only mode",
        )
        check(
            body["summary"]["duplicate_count"] == 1,
            "Preview reports duplicate code",
        )
        check(
            body["summary"]["invalid_count"] == 1,
            "Preview reports non-numeric code",
        )
        check(
            body["summary"]["accepted_count"] == 1,
            "Preview resolves canonical village",
            body["summary"],
        )
        check(
            body["governance"]["database_write_performed"]
            is False,
            "Preview governance confirms no database write",
        )

        db.expire_all()
        project_after = (
            db.query(Project)
            .filter(Project.id == project_id)
            .one()
        )
        audit_count_after = (
            db.query(ProjectAppConfigAuditEvent)
            .filter(
                ProjectAppConfigAuditEvent.project_id == project_id
            )
            .count()
        )
        check(
            (project_after.config or {}) == config_before,
            "Preview does not change project config",
        )
        check(
            (project_after.geography_scope or {}) == scope_before,
            "Preview does not change project geography scope",
        )
        check(
            audit_count_after == audit_count_before,
            "Read-only preview creates no audit event",
            {
                "before": audit_count_before,
                "after": audit_count_after,
            },
        )

        print("=" * 72)
        print(
            "Project geography import-preview authorization validated"
        )
        print("=" * 72)
        return 0
    finally:
        db.rollback()
        db.query(ProjectAppConfigAuditEvent).filter(
            ProjectAppConfigAuditEvent.project_id.in_(
                [project_id, foreign_project_id]
            )
        ).delete(synchronize_session=False)
        db.query(Project).filter(
            Project.id.in_([project_id, foreign_project_id])
        ).delete(synchronize_session=False)
        db.commit()

        if enterprise:
            delete_test_admin(db, enterprise.id)
        if manager:
            delete_test_admin(db, manager.id)
        if viewer:
            delete_test_admin(db, viewer.id)

        db.query(Tenant).filter(
            Tenant.id.in_([tenant_id, foreign_tenant_id])
        ).delete(synchronize_session=False)
        db.commit()
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

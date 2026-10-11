#!/usr/bin/env python3
"""Behavior coverage for authenticated crop suitability override publishing."""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Project, Tenant
from app.modules.master_data.models import (
    Crop,
    CropClimateSuitabilityOverride,
    GeographyClimateRegion,
)
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin


def now():
    return datetime.now(timezone.utc)


def check(condition, label, detail=""):
    if not condition:
        raise AssertionError(f"{label}: {detail}")
    print(f"PASS {label}")
    if detail:
        print(f"     {detail}")


def main():
    tenant_id = f"suitability-auth-{uuid.uuid4().hex[:8]}"
    foreign_tenant_id = f"suitability-foreign-{uuid.uuid4().hex[:8]}"
    project_id = uuid.uuid4()
    foreign_project_id = uuid.uuid4()
    user_ids = []

    db = SessionLocal()
    db.expire_on_commit = False
    try:
        crop = db.query(Crop).filter(Crop.is_active == True).first()
        region = (
            db.query(GeographyClimateRegion)
            .filter(GeographyClimateRegion.is_active == True)
            .first()
        )
        check(crop is not None, "Active crop fixture exists")
        check(region is not None, "Active climate region fixture exists")

        db.add_all([
            Tenant(
                id=tenant_id,
                name="Suitability Authorization Tenant",
                type="ENTERPRISE",
                created_at=now(),
                updated_at=now(),
            ),
            Tenant(
                id=foreign_tenant_id,
                name="Suitability Foreign Tenant",
                type="ENTERPRISE",
                created_at=now(),
                updated_at=now(),
            ),
        ])
        db.commit()

        publisher, publisher_headers = create_test_admin(
            db,
            tenant_id=tenant_id,
            role="ADMIN_PUBLISHER",
        )
        editor, editor_headers = create_test_admin(
            db,
            tenant_id=tenant_id,
            role="ADMIN_EDITOR",
        )
        user_ids.extend([publisher.id, editor.id])

        db.add_all([
            Project(
                id=project_id,
                tenant_id=tenant_id,
                name="Suitability Project",
                start_date=date.today(),
                end_date=date.today() + timedelta(days=180),
                status="ACTIVE",
                crop_scope=[crop.code],
                geography_scope={},
                config={},
                is_active=True,
                created_at=now(),
                updated_at=now(),
            ),
            Project(
                id=foreign_project_id,
                tenant_id=foreign_tenant_id,
                name="Foreign Suitability Project",
                start_date=date.today(),
                end_date=date.today() + timedelta(days=180),
                status="ACTIVE",
                crop_scope=[crop.code],
                geography_scope={},
                config={},
                is_active=True,
                created_at=now(),
                updated_at=now(),
            ),
        ])
        db.commit()

        payload = {
            "crop_code": crop.code,
            "season_code": "KHARIF",
            "region_code": region.region_code,
            "project_id": str(project_id),
            "suitability_status": "CONDITIONAL",
            "confidence": "ADMIN_REVIEWED",
            "warning_rules": [{
                "code": "REGRESSION_WARNING",
                "severity": "INFO",
                "message": "Regression authorization warning",
            }],
            "reason": "Authorization regression",
        }

        client = TestClient(app)

        missing = client.post(
            "/api/v1/crop-catalog/suitability-overrides",
            headers={"X-Tenant-ID": tenant_id},
            json=payload,
        )
        check(
            missing.status_code == 401,
            "Suitability publishing rejects missing bearer",
            missing.text,
        )

        insufficient = client.post(
            "/api/v1/crop-catalog/suitability-overrides",
            headers=editor_headers,
            json=payload,
        )
        check(
            insufficient.status_code == 403,
            "Suitability publishing rejects editor without publish permission",
            insufficient.text,
        )

        impersonation = client.post(
            "/api/v1/crop-catalog/suitability-overrides",
            headers={
                **publisher_headers,
                "X-Actor-ID": str(uuid.uuid4()),
            },
            json=payload,
        )
        check(
            impersonation.status_code == 403
            and impersonation.json().get("detail", {}).get("error")
            == "ACTOR_ID_MISMATCH",
            "Suitability publishing rejects actor impersonation",
            impersonation.text,
        )

        tenant_mismatch = client.post(
            "/api/v1/crop-catalog/suitability-overrides",
            headers={
                **publisher_headers,
                "X-Tenant-ID": foreign_tenant_id,
            },
            json=payload,
        )
        check(
            tenant_mismatch.status_code == 403,
            "Suitability publishing rejects tenant mismatch",
            tenant_mismatch.text,
        )

        foreign_project = client.post(
            "/api/v1/crop-catalog/suitability-overrides",
            headers=publisher_headers,
            json={**payload, "project_id": str(foreign_project_id)},
        )
        check(
            foreign_project.status_code == 404,
            "Suitability publishing rejects foreign-tenant project",
            foreign_project.text,
        )

        published = client.post(
            "/api/v1/crop-catalog/suitability-overrides",
            headers=publisher_headers,
            json=payload,
        )
        check(
            published.status_code == 200,
            "Authorized publisher creates suitability override",
            published.text,
        )
        body = published.json()["override"]
        check(
            body["tenant_id"] == tenant_id,
            "Override uses authenticated tenant",
        )
        check(
            body["project_id"] == str(project_id),
            "Override preserves tenant-bounded project",
        )

        stored = (
            db.query(CropClimateSuitabilityOverride)
            .filter(
                CropClimateSuitabilityOverride.tenant_id == tenant_id,
                CropClimateSuitabilityOverride.project_id == project_id,
                CropClimateSuitabilityOverride.reason
                == "Authorization regression",
            )
            .first()
        )
        check(stored is not None, "Override is persisted")
        check(
            stored.published_by == str(publisher.id),
            "Override records authenticated publisher",
        )
    finally:
        db.rollback()
        db.query(CropClimateSuitabilityOverride).filter(
            CropClimateSuitabilityOverride.tenant_id.in_([
                tenant_id,
                foreign_tenant_id,
            ])
        ).delete(synchronize_session=False)
        db.query(Project).filter(
            Project.tenant_id.in_([tenant_id, foreign_tenant_id])
        ).delete(synchronize_session=False)
        db.commit()

        for user_id in user_ids:
            delete_test_admin(db, user_id)

        db.query(Tenant).filter(
            Tenant.id.in_([tenant_id, foreign_tenant_id])
        ).delete(synchronize_session=False)
        db.commit()
        db.close()
        print("PASS Suitability authorization rows are cleaned")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Behavior regression for authorized soil-enrichment operations."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Farmer, Parcel, Project, Tenant
from app.modules.farmer.soil_profile import (
    SoilEnrichmentJobAudit,
    SoilEnrichmentSnapshot,
)
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin


def check(condition, label, detail=None):
    print(f"  {'PASS' if condition else 'FAIL'} {label}")
    if detail is not None:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(label)


def main() -> int:
    print("=" * 72)
    print("SOIL ENRICHMENT OPERATIONS AUTHORIZATION REGRESSION")
    print("=" * 72)

    tenant_id = f"soil-enrichment-ops-{uuid.uuid4().hex[:8]}"
    foreign_tenant_id = (
        f"soil-enrichment-ops-foreign-{uuid.uuid4().hex[:8]}"
    )

    project_id = uuid.uuid4()
    farmer_id = uuid.uuid4()
    parcel_id = uuid.uuid4()
    foreign_project_id = uuid.uuid4()
    foreign_farmer_id = uuid.uuid4()
    foreign_parcel_id = uuid.uuid4()

    admin_user_id = None
    viewer_user_id = None

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        db.add_all([
            Tenant(
                id=tenant_id,
                name="Soil Enrichment Operations Tenant",
                type="ENTERPRISE",
                created_at=now,
                updated_at=now,
            ),
            Tenant(
                id=foreign_tenant_id,
                name="Foreign Soil Enrichment Tenant",
                type="ENTERPRISE",
                created_at=now,
                updated_at=now,
            ),
            Project(
                id=project_id,
                tenant_id=tenant_id,
                name="Soil Enrichment Operations Project",
                start_date=date.today(),
                end_date=date.today() + timedelta(days=180),
                status="ACTIVE",
                geography_scope={},
                crop_scope=[],
                config={},
                created_at=now,
                updated_at=now,
            ),
            Project(
                id=foreign_project_id,
                tenant_id=foreign_tenant_id,
                name="Foreign Soil Enrichment Project",
                start_date=date.today(),
                end_date=date.today() + timedelta(days=180),
                status="ACTIVE",
                geography_scope={},
                crop_scope=[],
                config={},
                created_at=now,
                updated_at=now,
            ),
        ])
        db.flush()

        db.add_all([
            Farmer(
                id=farmer_id,
                tenant_id=tenant_id,
                project_id=project_id,
                mobile_number=f"+9191{uuid.uuid4().int % 100000000:08d}",
                display_name="Soil Enrichment Farmer",
                village_name_manual="Operations Village",
                pin_code="560001",
                status="ACTIVE",
                created_at=now,
                updated_at=now,
            ),
            Farmer(
                id=foreign_farmer_id,
                tenant_id=foreign_tenant_id,
                project_id=foreign_project_id,
                mobile_number=f"+9192{uuid.uuid4().int % 100000000:08d}",
                display_name="Foreign Soil Enrichment Farmer",
                village_name_manual="Foreign Operations Village",
                pin_code="560002",
                status="ACTIVE",
                created_at=now,
                updated_at=now,
            ),
        ])
        db.flush()

        db.add_all([
            Parcel(
                id=parcel_id,
                tenant_id=tenant_id,
                farmer_id=farmer_id,
                project_id=project_id,
                village_name_manual="Operations Village",
                pin_code="560001",
                reported_area=Decimal("1.00"),
                reported_area_unit="ACRE",
                ownership_type="OWNED",
                geometry_source="PIN_DROP",
                centroid_lat=Decimal("12.971600"),
                centroid_lng=Decimal("77.594600"),
                status="ACTIVE",
                created_at=now,
                updated_at=now,
            ),
            Parcel(
                id=foreign_parcel_id,
                tenant_id=foreign_tenant_id,
                farmer_id=foreign_farmer_id,
                project_id=foreign_project_id,
                village_name_manual="Foreign Operations Village",
                pin_code="560002",
                reported_area=Decimal("1.00"),
                reported_area_unit="ACRE",
                ownership_type="OWNED",
                geometry_source="PIN_DROP",
                centroid_lat=Decimal("13.082700"),
                centroid_lng=Decimal("80.270700"),
                status="ACTIVE",
                created_at=now,
                updated_at=now,
            ),
        ])
        db.commit()

        admin, admin_headers = create_test_admin(
            db,
            role="ENTERPRISE_ADMIN",
            tenant_id=tenant_id,
        )
        viewer, viewer_headers = create_test_admin(
            db,
            role="ADMIN_VIEWER",
            tenant_id=tenant_id,
        )
        admin_user_id = admin.id
        viewer_user_id = viewer.id
    finally:
        db.close()

    client = TestClient(app)
    audit_url = (
        "/api/v1/soil-profiles/enrichments/jobs/audit"
    )
    audit_payload = {
        "farmer_id": str(farmer_id),
        "parcel_id": str(parcel_id),
        "project_id": str(project_id),
        "job_type": "FETCH_SOIL_BASELINE",
        "provider": "soilgrids",
        "status": "FAILED",
        "attempt_count": 1,
        "reason": "Authorization regression event",
        "error_code": "AUTH_REGRESSION",
        "metadata": {"source": "auth_regression"},
    }

    try:
        missing = client.post(
            audit_url,
            headers={"X-Tenant-ID": tenant_id},
            json=audit_payload,
        )
        check(
            missing.status_code == 401,
            "Manual enrichment audit rejects missing bearer",
            missing.text,
        )

        viewer_create = client.post(
            audit_url,
            headers=viewer_headers,
            json=audit_payload,
        )
        check(
            viewer_create.status_code == 403,
            "Manual enrichment audit rejects view-only administrator",
            viewer_create.text,
        )

        impersonated_headers = {
            **admin_headers,
            "X-Actor-ID": str(uuid.uuid4()),
        }
        impersonated = client.post(
            audit_url,
            headers=impersonated_headers,
            json=audit_payload,
        )
        check(
            impersonated.status_code == 403,
            "Manual enrichment audit rejects actor impersonation",
            impersonated.text,
        )

        mismatched_headers = {
            **admin_headers,
            "X-Tenant-ID": foreign_tenant_id,
        }
        mismatched = client.post(
            audit_url,
            headers=mismatched_headers,
            json=audit_payload,
        )
        check(
            mismatched.status_code == 403,
            "Manual enrichment audit rejects tenant mismatch",
            mismatched.text,
        )

        foreign_payload = {
            **audit_payload,
            "farmer_id": str(foreign_farmer_id),
            "parcel_id": str(foreign_parcel_id),
            "project_id": str(foreign_project_id),
        }
        foreign = client.post(
            audit_url,
            headers=admin_headers,
            json=foreign_payload,
        )
        check(
            foreign.status_code == 404,
            "Manual enrichment audit hides foreign references",
            foreign.text,
        )

        created = client.post(
            audit_url,
            headers=admin_headers,
            json=audit_payload,
        )
        check(
            created.status_code == 201,
            "Authorized administrator records enrichment audit",
            created.text,
        )
        created_body = created.json()
        check(
            created_body["tenant_id"] == tenant_id,
            "Manual audit uses verified tenant",
        )
        check(
            created_body["metadata"]["recorded_by"]
            == str(admin_user_id),
            "Manual audit records verified administrator",
        )
        check(
            created_body["metadata"]["source"]
            == "auth_regression",
            "Manual audit preserves caller metadata",
        )

        worker_url = (
            "/api/v1/soil-profiles/enrichments/worker/run-queue"
        )

        worker_missing = client.post(
            worker_url,
            params={
                "farmer_id": str(farmer_id),
                "missing": "ANY",
                "dry_run": "true",
            },
            headers={"X-Tenant-ID": tenant_id},
            json={},
        )
        check(
            worker_missing.status_code == 401,
            "Enrichment worker rejects missing bearer",
            worker_missing.text,
        )

        worker_viewer = client.post(
            worker_url,
            params={
                "farmer_id": str(farmer_id),
                "missing": "ANY",
                "dry_run": "true",
            },
            headers=viewer_headers,
            json={},
        )
        check(
            worker_viewer.status_code == 403,
            "Enrichment worker rejects view-only administrator",
            worker_viewer.text,
        )

        worker_impersonated = client.post(
            worker_url,
            params={
                "farmer_id": str(farmer_id),
                "missing": "ANY",
                "dry_run": "true",
            },
            headers=impersonated_headers,
            json={},
        )
        check(
            worker_impersonated.status_code == 403,
            "Enrichment worker rejects actor impersonation",
            worker_impersonated.text,
        )

        worker_foreign_filter = client.post(
            worker_url,
            params={
                "farmer_id": str(foreign_farmer_id),
                "missing": "ANY",
                "dry_run": "true",
            },
            headers=admin_headers,
            json={},
        )
        check(
            worker_foreign_filter.status_code == 404,
            "Enrichment worker hides foreign farmer filter",
            worker_foreign_filter.text,
        )

        worker_foreign_target = client.post(
            worker_url,
            params={"missing": "ANY", "dry_run": "false"},
            headers=admin_headers,
            json={
                "demo_target": {
                    "farmer_id": str(foreign_farmer_id),
                    "parcel_id": str(foreign_parcel_id),
                    "project_id": str(foreign_project_id),
                }
            },
        )
        check(
            worker_foreign_target.status_code == 404,
            "Enrichment worker hides foreign demo target",
            worker_foreign_target.text,
        )

        invalid_target = client.post(
            worker_url,
            params={"missing": "ANY", "dry_run": "false"},
            headers=admin_headers,
            json={
                "demo_target": {
                    "parcel_id": "not-a-uuid",
                }
            },
        )
        check(
            invalid_target.status_code == 422,
            "Enrichment worker rejects malformed demo target",
            invalid_target.text,
        )

        dry_run = client.post(
            worker_url,
            params={
                "farmer_id": str(farmer_id),
                "project_id": str(project_id),
                "missing": "ANY",
                "dry_run": "true",
            },
            headers=admin_headers,
            json={},
        )
        check(
            dry_run.status_code == 200,
            "Authorized administrator previews enrichment queue",
            dry_run.text[:1000],
        )
        dry_body = dry_run.json()
        check(
            dry_body["tenant_id"] == tenant_id,
            "Worker preview uses verified tenant",
        )
        check(
            dry_body["requested_by"] == str(admin_user_id),
            "Worker preview reports verified administrator",
        )
        check(
            dry_body["dry_run"] is True,
            "Worker preview remains write-free",
        )

        run = client.post(
            worker_url,
            params={
                "farmer_id": str(farmer_id),
                "project_id": str(project_id),
                "missing": "ANY",
                "dry_run": "false",
            },
            headers=admin_headers,
            json={},
        )
        check(
            run.status_code == 200,
            "Authorized administrator runs enrichment queue",
            run.text[:1000],
        )
        run_body = run.json()
        check(
            run_body["requested_by"] == str(admin_user_id),
            "Worker run reports verified administrator",
        )
        check(
            run_body["queued_job_count"] >= 1,
            "Worker run creates operational audit rows",
            run_body,
        )

        verify = SessionLocal()
        try:
            worker_events = (
                verify.query(SoilEnrichmentJobAudit)
                .filter(
                    SoilEnrichmentJobAudit.tenant_id == tenant_id,
                    SoilEnrichmentJobAudit.parcel_id == parcel_id,
                    SoilEnrichmentJobAudit.status == "QUEUED",
                )
                .all()
            )
            check(
                bool(worker_events),
                "Worker audit rows are persisted",
            )
            check(
                all(
                    event.metadata_.get("requested_by")
                    == str(admin_user_id)
                    for event in worker_events
                ),
                "Worker audit rows record verified administrator",
                [
                    event.metadata_.get("requested_by")
                    for event in worker_events
                ],
            )
        finally:
            verify.close()

    finally:
        cleanup = SessionLocal()
        try:
            cleanup.query(SoilEnrichmentJobAudit).filter(
                SoilEnrichmentJobAudit.tenant_id.in_(
                    [tenant_id, foreign_tenant_id]
                )
            ).delete(synchronize_session=False)
            cleanup.query(SoilEnrichmentSnapshot).filter(
                SoilEnrichmentSnapshot.tenant_id.in_(
                    [tenant_id, foreign_tenant_id]
                )
            ).delete(synchronize_session=False)
            cleanup.query(Parcel).filter(
                Parcel.tenant_id.in_([tenant_id, foreign_tenant_id])
            ).delete(synchronize_session=False)
            cleanup.query(Farmer).filter(
                Farmer.tenant_id.in_([tenant_id, foreign_tenant_id])
            ).delete(synchronize_session=False)
            cleanup.query(Project).filter(
                Project.tenant_id.in_([tenant_id, foreign_tenant_id])
            ).delete(synchronize_session=False)
            cleanup.commit()

            for user_id in (viewer_user_id, admin_user_id):
                if user_id:
                    delete_test_admin(cleanup, user_id)

            cleanup.query(Tenant).filter(
                Tenant.id.in_([tenant_id, foreign_tenant_id])
            ).delete(synchronize_session=False)
            cleanup.commit()
        finally:
            cleanup.close()

    print("=" * 72)
    print("Soil enrichment operations authorization validated")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

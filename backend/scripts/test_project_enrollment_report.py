"""Regression for read-only admin project enrollment visibility report."""

from datetime import date, datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Farmer, FarmerProjectEnrollment, Parcel, Project, ProjectAppConfigAuditEvent, Tenant
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin


def check(condition, label, detail=None):
    print(f"  {'PASS' if condition else 'FAIL'} {label}")
    if detail is not None:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(label)


def now():
    return datetime.now(timezone.utc)


def main():
    print("=" * 72)
    print("PROJECT ENROLLMENT REPORT REGRESSION")
    print("=" * 72)

    tenant_id = "default"
    farmer_id = uuid.uuid4()
    project_id = uuid.uuid4()
    bulk_project_id = uuid.uuid4()
    parcel_id = uuid.uuid4()
    enrollment_id = uuid.uuid4()
    bulk_farmer_ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
    bulk_enrollment_ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
    mobile = f"+9196{uuid.uuid4().int % 100000000:08d}"
    admin = None

    db = SessionLocal()
    try:
        if not db.query(Tenant).filter(Tenant.id == tenant_id).first():
            db.add(Tenant(id=tenant_id, name="Default", type="ENTERPRISE", created_at=now(), updated_at=now()))
            db.flush()
        project = Project(
            id=project_id,
            tenant_id=tenant_id,
            name="Enrollment Report Project",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 12, 31),
            status="ACTIVE",
            crop_scope=["RICE"],
            geography_scope={},
            created_at=now(),
            updated_at=now(),
        )
        db.add(project)
        db.flush()
        farmer = Farmer(
            id=farmer_id,
            tenant_id=tenant_id,
            project_id=project_id,
            mobile_number=mobile,
            display_name="Enrollment Report Farmer",
            village_name_manual="Report Village",
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        )
        db.add(farmer)
        db.flush()
        parcel = Parcel(
            id=parcel_id,
            tenant_id=tenant_id,
            farmer_id=farmer_id,
            project_id=project_id,
            survey_number="ENR-001",
            reported_area=2,
            reported_area_unit="ACRE",
            ownership_type="OWNED",
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        )
        enrollment = FarmerProjectEnrollment(
            id=enrollment_id,
            tenant_id=tenant_id,
            farmer_id=farmer_id,
            project_id=project_id,
            enrollment_method="SYNC_MATERIALIZED",
            enrollment_source="android_sync_regression",
            status="ACTIVE",
            parcel_ids=[str(parcel_id)],
            assigned_user_ids=[],
            metadata_={"source": "report_regression"},
            notes="report test",
            created_at=now(),
            updated_at=now(),
        )
        db.add_all([parcel, enrollment])
        admin, headers = create_test_admin(db, role="ADMIN_VIEWER", tenant_id=tenant_id)
        db.commit()

        client = TestClient(app)
        unauth = client.get("/api/v1/reports/project-enrollments", headers={"X-Tenant-ID": tenant_id})
        check(unauth.status_code == 401, "Project enrollment report requires admin auth", unauth.text)

        response = client.get(f"/api/v1/reports/project-enrollments?project_id={project_id}&status=ACTIVE", headers=headers)
        check(response.status_code == 200, "Project enrollment report returns 200", response.text[:500])
        payload = response.json()
        check(payload["schema_version"] == "project_enrollment_report.v1", "Schema version is stable")
        check(payload["tenant_id"] == tenant_id, "Tenant is echoed")
        check(payload["filters"]["project_id"] == str(project_id), "Project filter is echoed")
        check(payload["summary"]["active_count"] >= 1, "Summary counts active enrollment")
        rows = [row for row in payload["enrollments"] if row["id"] == str(enrollment_id)]
        check(len(rows) == 1, "Report includes seeded enrollment")
        row = rows[0]
        check(row["farmer_id"] == str(farmer_id), "Row includes farmer id")
        check(row["project_id"] == str(project_id), "Row includes project id")
        check(row["enrollment_method"] == "SYNC_MATERIALIZED", "Row includes enrollment method")
        check(row["enrollment_source"] == "android_sync_regression", "Row includes enrollment source")
        check(row["parcel_labels"] == ["ENR-001"], "Row includes linked parcel label")
        check(row["launch_context"]["recommended_navigation"] == "SHOW_HOME", "Launch decision is reported")
        check(row["launch_context"]["project_selection_required"] is False, "Launch picker flag is reported")
        check(row["launch_context"]["profile_completion"]["is_complete_for_home"] is True, "Profile completion is reported")

        source_response = client.get("/api/v1/reports/project-enrollments?enrollment_source=android_sync", headers=headers)
        check(source_response.status_code == 200, "Enrollment source filter returns 200", source_response.text[:300])
        check(any(item["id"] == str(enrollment_id) for item in source_response.json()["enrollments"]), "Source filter includes seeded row")

        editor, editor_headers = create_test_admin(db, role="ENTERPRISE_ADMIN", tenant_id=tenant_id)
        complete_response = client.patch(
            f"/api/v1/farmer-project-enrollments/{enrollment_id}/status",
            headers=editor_headers,
            json={"status": "COMPLETED", "reason": "Regression project completed"},
        )
        check(complete_response.status_code == 200, "Enrollment lifecycle status update returns 200", complete_response.text[:500])
        complete_payload = complete_response.json()
        check(complete_payload["status"] == "COMPLETED", "Enrollment status is completed")
        check(complete_payload["metadata"]["last_lifecycle_change"]["to_status"] == "COMPLETED", "Lifecycle metadata records new status")
        check(complete_payload["metadata"]["last_lifecycle_change"]["reason"] == "Regression project completed", "Lifecycle metadata records reason")

        hydration = client.get(f"/api/v1/farmers/by-mobile/{mobile}", headers={"X-Tenant-ID": tenant_id})
        check(hydration.status_code == 200, "Hydration returns after lifecycle update", hydration.text[:300])
        check(hydration.json()["farmer_context"]["mode"] == "SELF_SERVICE", "Farmer falls back to self-service after completed enrollment")

        audit_event = db.query(ProjectAppConfigAuditEvent).filter(
            ProjectAppConfigAuditEvent.project_id == project_id,
            ProjectAppConfigAuditEvent.action == "UPDATE_PROJECT_ENROLLMENT_STATUS",
        ).order_by(ProjectAppConfigAuditEvent.created_at.desc()).first()
        check(audit_event is not None, "Enrollment lifecycle status update is audited")
        check(audit_event.after_config["status"] == "COMPLETED", "Audit stores after status")
        check(audit_event.reason == "Regression project completed", "Audit stores reason")

        bulk_project = Project(
            id=bulk_project_id,
            tenant_id=tenant_id,
            name="Bulk Enrollment Lifecycle Project",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 12, 31),
            status="ACTIVE",
            crop_scope=["RICE"],
            geography_scope={},
            created_at=now(),
            updated_at=now(),
        )
        db.add(bulk_project)
        db.flush()
        bulk_statuses = ["ACTIVE", "PENDING", "COMPLETED"]
        for index, farmer_uuid in enumerate(bulk_farmer_ids):
            db.add(Farmer(
                id=farmer_uuid,
                tenant_id=tenant_id,
                project_id=bulk_project_id,
                mobile_number=f"+9197{uuid.uuid4().int % 100000000:08d}",
                display_name=f"Bulk Lifecycle Farmer {index + 1}",
                village_name_manual="Bulk Village",
                status="ACTIVE",
                created_at=now(),
                updated_at=now(),
            ))
            db.add(FarmerProjectEnrollment(
                id=bulk_enrollment_ids[index],
                tenant_id=tenant_id,
                farmer_id=farmer_uuid,
                project_id=bulk_project_id,
                enrollment_method="WEB_ADMIN",
                enrollment_source="bulk_lifecycle_regression",
                status=bulk_statuses[index],
                parcel_ids=[],
                assigned_user_ids=[],
                metadata_={"source": "bulk_lifecycle_regression"},
                notes="bulk lifecycle test",
                created_at=now(),
                updated_at=now(),
            ))
        db.commit()

        preview = client.get(
            f"/api/v1/projects/{bulk_project_id}/farmer-enrollments/lifecycle-preview?target_status=COMPLETED",
            headers=editor_headers,
        )
        check(preview.status_code == 200, "Bulk lifecycle preview returns 200", preview.text[:500])
        preview_payload = preview.json()
        check(preview_payload["affected_count"] == 2, "Bulk preview counts active and pending enrollments")
        check(preview_payload["can_apply"] is True, "Bulk preview is applyable")

        bulk_apply = client.post(
            f"/api/v1/projects/{bulk_project_id}/farmer-enrollments/lifecycle-apply",
            headers=editor_headers,
            json={"target_status": "COMPLETED", "reason": "Regression bulk project completed"},
        )
        check(bulk_apply.status_code == 200, "Bulk lifecycle apply returns 200", bulk_apply.text[:500])
        bulk_payload = bulk_apply.json()
        check(bulk_payload["updated_count"] == 2, "Bulk apply updates two enrollments")
        check(bulk_payload["skipped_count"] == 1, "Bulk apply skips already terminal rows")

        db.expire_all()
        bulk_rows = db.query(FarmerProjectEnrollment).filter(FarmerProjectEnrollment.project_id == bulk_project_id).all()
        statuses = {str(row.id): row.status for row in bulk_rows}
        check(statuses[str(bulk_enrollment_ids[0])] == "COMPLETED", "Bulk active row completed")
        check(statuses[str(bulk_enrollment_ids[1])] == "COMPLETED", "Bulk pending row completed")
        check(statuses[str(bulk_enrollment_ids[2])] == "COMPLETED", "Bulk pre-completed row remains completed")

        bulk_hydration = client.get(f"/api/v1/farmers/by-mobile/{db.query(Farmer).filter(Farmer.id == bulk_farmer_ids[0]).first().mobile_number}", headers={"X-Tenant-ID": tenant_id})
        check(bulk_hydration.status_code == 200, "Hydration returns after bulk lifecycle update", bulk_hydration.text[:300])
        check(bulk_hydration.json()["farmer_context"]["mode"] == "SELF_SERVICE", "Bulk completed farmer falls back to self-service")

        bulk_audit = db.query(ProjectAppConfigAuditEvent).filter(
            ProjectAppConfigAuditEvent.project_id == bulk_project_id,
            ProjectAppConfigAuditEvent.action == "BULK_UPDATE_PROJECT_ENROLLMENT_STATUS_SUMMARY",
        ).order_by(ProjectAppConfigAuditEvent.created_at.desc()).first()
        check(bulk_audit is not None, "Bulk lifecycle summary is audited")
        check(bulk_audit.after_config["updated_count"] == 2, "Bulk audit stores update count")
        delete_test_admin(db, editor.id)

        invalid = client.get("/api/v1/reports/project-enrollments?status=BAD", headers=headers)
        check(invalid.status_code == 400, "Invalid status is rejected", invalid.text)
    finally:
        cleanup = SessionLocal()
        try:
            cleanup.query(ProjectAppConfigAuditEvent).filter(ProjectAppConfigAuditEvent.project_id.in_([project_id, bulk_project_id])).delete(synchronize_session=False)
            cleanup.query(FarmerProjectEnrollment).filter(FarmerProjectEnrollment.project_id.in_([project_id, bulk_project_id])).delete(synchronize_session=False)
            cleanup.query(Parcel).filter(Parcel.id == parcel_id).delete(synchronize_session=False)
            cleanup.query(Farmer).filter(Farmer.id.in_([farmer_id] + bulk_farmer_ids)).delete(synchronize_session=False)
            cleanup.query(Project).filter(Project.id.in_([project_id, bulk_project_id])).delete(synchronize_session=False)
            cleanup.commit()
            if admin:
                delete_test_admin(cleanup, admin.id)
        finally:
            cleanup.close()
        db.close()

    print("=" * 72)
    print("Project enrollment report validated")
    print("=" * 72)


if __name__ == "__main__":
    main()

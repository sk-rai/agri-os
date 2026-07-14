"""Regression for farmer project enrollment memberships.

Validates the Phase 2 enrollment foundation:
- a direct/self farmer can exist without farmers.project_id
- farmer can be attached to a project through farmer_project_enrollments
- first active enrollment backfills legacy farmers.project_id for compatibility
- hydration includes project_enrollments
- farmer/project listing endpoints expose the membership
- repeat POST updates the existing membership instead of duplicating it
"""

from datetime import date, datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Farmer, FarmerProjectEnrollment, Parcel, Project, Tenant


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
    print("FARMER PROJECT ENROLLMENT REGRESSION")
    print("=" * 72)

    tenant_id = f"membership-test-{uuid.uuid4().hex[:8]}"
    actor_id = str(uuid.uuid4())
    farmer_id = uuid.uuid4()
    project_id = uuid.uuid4()
    parcel_id = uuid.uuid4()
    mobile = f"+9198{uuid.uuid4().int % 100000000:08d}"
    headers = {"X-Tenant-ID": tenant_id, "X-Actor-ID": actor_id}

    db = SessionLocal()
    try:
        db.add(Tenant(
            id=tenant_id,
            name="Membership Test Tenant",
            type="ENTERPRISE",
            created_at=now(),
            updated_at=now(),
        ))
        db.flush()
        db.add(Project(
            id=project_id,
            tenant_id=tenant_id,
            name="Membership Test Project",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 12, 31),
            status="PLANNED",
            crop_scope=["RICE"],
            geography_scope={},
            created_at=now(),
            updated_at=now(),
        ))
        db.flush()
        db.add(Farmer(
            id=farmer_id,
            tenant_id=tenant_id,
            project_id=None,
            mobile_number=mobile,
            display_name="Direct Farmer",
            village_name_manual="Membership Village",
            enrollment_method="SELF",
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        ))
        db.flush()
        db.add(Parcel(
            id=parcel_id,
            tenant_id=tenant_id,
            farmer_id=farmer_id,
            village_name_manual="Membership Village",
            reported_area=5,
            reported_area_unit="ACRE",
            ownership_type="OWNED",
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        ))
        db.commit()
    finally:
        db.close()

    client = TestClient(app)

    print("\n[1] Create project enrollment")
    response = client.post(
        f"/api/v1/farmers/{farmer_id}/project-enrollments",
        headers=headers,
        json={
            "project_id": str(project_id),
            "enrollment_method": "PROJECT_INVITE",
            "enrollment_source": "regression",
            "status": "ACTIVE",
            "parcel_ids": [str(parcel_id)],
            "assigned_user_ids": [actor_id],
            "metadata": {"channel": "test"},
            "notes": "initial enrollment",
        },
    )
    check(response.status_code == 201, "Create enrollment returns 201", response.text)
    payload = response.json()
    check(payload["farmer_id"] == str(farmer_id), "Enrollment references farmer")
    check(payload["project_id"] == str(project_id), "Enrollment references project")
    check(payload["project_name"] == "Membership Test Project", "Enrollment includes project name")
    check(payload["parcel_ids"] == [str(parcel_id)], "Enrollment preserves parcel links")
    check(payload["assigned_user_ids"] == [actor_id], "Enrollment preserves assigned users")

    db = SessionLocal()
    try:
        farmer = db.query(Farmer).filter(Farmer.id == farmer_id, Farmer.tenant_id == tenant_id).first()
        check(str(farmer.project_id) == str(project_id), "Legacy farmer.project_id is backfilled for first active enrollment")
        enrollment_count = db.query(FarmerProjectEnrollment).filter(
            FarmerProjectEnrollment.tenant_id == tenant_id,
            FarmerProjectEnrollment.farmer_id == farmer_id,
            FarmerProjectEnrollment.project_id == project_id,
        ).count()
        check(enrollment_count == 1, "Only one membership row exists")
    finally:
        db.close()

    print("\n[2] Hydration includes project memberships")
    hydration = client.get(f"/api/v1/farmers/by-mobile/{mobile}", headers={"X-Tenant-ID": tenant_id})
    check(hydration.status_code == 200, "Hydration returns 200", hydration.text[:300])
    body = hydration.json()
    check(body["summary"]["project_enrollment_count"] == 1, "Hydration summary counts project enrollment")
    check(body["summary"]["active_project_enrollment_count"] == 1, "Hydration summary counts active enrollment")
    check(body["project_enrollments"][0]["project_id"] == str(project_id), "Hydration includes enrollment project id")

    print("\n[3] List endpoints expose membership")
    farmer_list = client.get(f"/api/v1/farmers/{farmer_id}/project-enrollments", headers=headers)
    check(farmer_list.status_code == 200, "Farmer membership list returns 200", farmer_list.text)
    check(len(farmer_list.json()) == 1, "Farmer membership list has one row")

    project_list = client.get(f"/api/v1/projects/{project_id}/farmer-enrollments", headers=headers)
    check(project_list.status_code == 200, "Project membership list returns 200", project_list.text)
    check(len(project_list.json()) == 1, "Project membership list has one row")

    print("\n[4] Repeat POST updates existing membership")
    update_response = client.post(
        f"/api/v1/farmers/{farmer_id}/project-enrollments",
        headers=headers,
        json={
            "project_id": str(project_id),
            "enrollment_method": "WEB_ADMIN",
            "enrollment_source": "regression-update",
            "status": "PENDING",
            "parcel_ids": [str(parcel_id)],
            "assigned_user_ids": [],
            "metadata": {"channel": "updated"},
            "notes": "updated enrollment",
        },
    )
    check(update_response.status_code == 201, "Update enrollment returns 201", update_response.text)
    updated = update_response.json()
    check(updated["enrollment_method"] == "WEB_ADMIN", "Enrollment method updated")
    check(updated["status"] == "PENDING", "Enrollment status updated")
    db = SessionLocal()
    try:
        enrollment_count = db.query(FarmerProjectEnrollment).filter(
            FarmerProjectEnrollment.tenant_id == tenant_id,
            FarmerProjectEnrollment.farmer_id == farmer_id,
            FarmerProjectEnrollment.project_id == project_id,
        ).count()
        check(enrollment_count == 1, "Repeat POST does not duplicate membership")
    finally:
        db.close()

    print("\n[5] Cleanup")
    db = SessionLocal()
    try:
        db.query(FarmerProjectEnrollment).filter(FarmerProjectEnrollment.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Parcel).filter(Parcel.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Farmer).filter(Farmer.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Project).filter(Project.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Tenant).filter(Tenant.id == tenant_id).delete(synchronize_session=False)
        db.commit()
        check(True, "Temporary rows cleaned up")
    finally:
        db.close()

    print("=" * 72)
    print("Farmer project enrollment validated")
    print("=" * 72)


if __name__ == "__main__":
    main()

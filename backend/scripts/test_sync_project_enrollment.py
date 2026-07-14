"""Regression for sync materialization of farmer project enrollments.

Validates Phase 9:
- accepted FARMER_PROJECT_ENROLLMENT sync events create membership rows
- entity_id is preserved as farmer_project_enrollments.id
- repeat/update sync events update the same row instead of duplicating
- profile hydration includes the synced membership
- farmer launch context reflects the synced active project membership
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
from app.modules.sync.models import AuditChainEntry, SyncConflict, SyncProcessedEvent


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
    print("SYNC PROJECT ENROLLMENT MATERIALIZATION REGRESSION")
    print("=" * 72)

    tenant_id = f"sync-membership-{uuid.uuid4().hex[:8]}"
    actor_id = str(uuid.uuid4())
    farmer_id = uuid.uuid4()
    project_id = uuid.uuid4()
    parcel_id = uuid.uuid4()
    enrollment_id = uuid.uuid4()
    mobile = f"+9197{uuid.uuid4().int % 100000000:08d}"
    headers = {"X-Tenant-ID": tenant_id, "X-Actor-ID": actor_id}

    db = SessionLocal()
    try:
        db.add(Tenant(
            id=tenant_id,
            name="Sync Membership Test Tenant",
            type="ENTERPRISE",
            created_at=now(),
            updated_at=now(),
        ))
        db.flush()
        db.add(Project(
            id=project_id,
            tenant_id=tenant_id,
            name="Sync Membership Test Project",
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
            display_name="Synced Membership Farmer",
            village_name_manual="Sync Village",
            language_preference="en",
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
            village_name_manual="Sync Village",
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

    print("\n[1] Sync creates project enrollment")
    create_event_id = str(uuid.uuid4())
    create_response = client.post(
        "/api/v1/sync/events",
        headers=headers,
        json={
            "events": [
                {
                    "event_id": create_event_id,
                    "entity_type": "FARMER_PROJECT_ENROLLMENT",
                    "entity_id": str(enrollment_id),
                    "operation": "CREATE",
                    "payload": {
                        "farmer_id": str(farmer_id),
                        "project_id": str(project_id),
                        "enrollment_method": "PROJECT_INVITE",
                        "enrollment_source": "android_sync_regression",
                        "status": "ACTIVE",
                        "parcel_ids": [str(parcel_id)],
                        "assigned_user_ids": [actor_id],
                        "metadata": {"channel": "sync"},
                        "notes": "created from sync",
                    },
                    "version": 1,
                    "dependency_ids": [],
                    "metadata": {"source": "sync_membership_regression"},
                }
            ]
        },
    )
    check(create_response.status_code == 200, "Sync create returns 200", create_response.text)
    body = create_response.json()
    check(body["accepted"] == [create_event_id], "Create event accepted", body)
    check(body["failed"] == [], "Create event has no failures", body)

    db = SessionLocal()
    try:
        enrollment = db.query(FarmerProjectEnrollment).filter(
            FarmerProjectEnrollment.id == enrollment_id,
            FarmerProjectEnrollment.tenant_id == tenant_id,
        ).first()
        check(enrollment is not None, "Membership row is materialized")
        check(enrollment.farmer_id == farmer_id, "Membership preserves farmer id")
        check(enrollment.project_id == project_id, "Membership preserves project id")
        check(enrollment.enrollment_method == "PROJECT_INVITE", "Membership stores enrollment method")
        check(enrollment.enrollment_source == "android_sync_regression", "Membership stores enrollment source")
        check(enrollment.parcel_ids == [str(parcel_id)], "Membership stores parcel ids")
        check(enrollment.assigned_user_ids == [actor_id], "Membership stores assigned user ids")
        farmer = db.query(Farmer).filter(Farmer.id == farmer_id, Farmer.tenant_id == tenant_id).first()
        check(farmer.project_id == project_id, "Legacy farmer.project_id is backfilled")
    finally:
        db.close()

    print("\n[2] Sync update changes same membership row")
    update_event_id = str(uuid.uuid4())
    update_response = client.post(
        "/api/v1/sync/events",
        headers=headers,
        json={
            "events": [
                {
                    "event_id": update_event_id,
                    "entity_type": "PROJECT_ENROLLMENT",
                    "entity_id": str(enrollment_id),
                    "operation": "UPDATE",
                    "payload": {
                        "farmer_id": str(farmer_id),
                        "project_id": str(project_id),
                        "enrollment_method": "WEB_ADMIN",
                        "enrollment_source": "android_sync_update",
                        "status": "ACTIVE",
                        "parcel_ids": [str(parcel_id)],
                        "assigned_user_ids": [],
                        "metadata": {"channel": "sync", "updated": True},
                        "notes": "updated from sync",
                    },
                    "version": 2,
                    "dependency_ids": [create_event_id],
                    "metadata": {"source": "sync_membership_regression"},
                }
            ]
        },
    )
    check(update_response.status_code == 200, "Sync update returns 200", update_response.text)
    update_body = update_response.json()
    check(update_body["accepted"] == [update_event_id], "Update event accepted", update_body)

    db = SessionLocal()
    try:
        rows = db.query(FarmerProjectEnrollment).filter(
            FarmerProjectEnrollment.tenant_id == tenant_id,
            FarmerProjectEnrollment.farmer_id == farmer_id,
            FarmerProjectEnrollment.project_id == project_id,
        ).all()
        check(len(rows) == 1, "Update does not duplicate membership")
        check(rows[0].enrollment_method == "WEB_ADMIN", "Update changes enrollment method")
        check(rows[0].notes == "updated from sync", "Update changes notes")
        check(rows[0].assigned_user_ids == [], "Update changes assigned user ids")
    finally:
        db.close()

    print("\n[3] Hydration and launch context include synced membership")
    hydration = client.get(f"/api/v1/farmers/by-mobile/{mobile}", headers={"X-Tenant-ID": tenant_id})
    check(hydration.status_code == 200, "Hydration returns 200", hydration.text[:300])
    hydration_body = hydration.json()
    check(hydration_body["summary"]["project_enrollment_count"] == 1, "Hydration counts synced membership")
    check(hydration_body["project_enrollments"][0]["id"] == str(enrollment_id), "Hydration preserves enrollment id")

    launch = client.get(f"/api/v1/farmers/{farmer_id}/launch-context", headers={"X-Tenant-ID": tenant_id})
    check(launch.status_code == 200, "Launch context returns 200", launch.text[:300])
    launch_body = launch.json()
    check(launch_body["active_project_count"] == 1, "Launch context counts one active project")
    check(launch_body["active_project_candidate"]["project_id"] == str(project_id), "Launch context exposes active project")
    check(launch_body["recommended_navigation"] in {"SHOW_HOME", "SHOW_PROFILE_COMPLETION"}, "Launch context gives actionable navigation")

    print("\n[4] Cleanup")
    db = SessionLocal()
    try:
        db.query(SyncConflict).filter(SyncConflict.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(AuditChainEntry).filter(AuditChainEntry.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(SyncProcessedEvent).filter(SyncProcessedEvent.tenant_id == tenant_id).delete(synchronize_session=False)
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
    print("Sync project enrollment materialization validated")
    print("=" * 72)


if __name__ == "__main__":
    main()
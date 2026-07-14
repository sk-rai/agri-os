"""Regression for Android farmer launch context."""

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


def create_project(db, tenant_id: str, name: str) -> Project:
    project = Project(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name=name,
        start_date=date(2026, 7, 1),
        end_date=date(2026, 12, 31),
        status="PLANNED",
        crop_scope=["RICE"],
        geography_scope={},
        created_at=now(),
        updated_at=now(),
    )
    db.add(project)
    db.flush()
    return project


def create_enrollment(db, tenant_id: str, farmer_id: uuid.UUID, project_id: uuid.UUID) -> FarmerProjectEnrollment:
    enrollment = FarmerProjectEnrollment(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        farmer_id=farmer_id,
        project_id=project_id,
        enrollment_method="PROJECT_INVITE",
        enrollment_source="launch_context_regression",
        status="ACTIVE",
        created_at=now(),
        updated_at=now(),
    )
    db.add(enrollment)
    return enrollment


def main():
    print("=" * 72)
    print("FARMER LAUNCH CONTEXT REGRESSION")
    print("=" * 72)

    tenant_id = f"launch-test-{uuid.uuid4().hex[:8]}"
    complete_farmer_id = uuid.uuid4()
    incomplete_farmer_id = uuid.uuid4()
    parcel_id = uuid.uuid4()

    db = SessionLocal()
    try:
        db.add(Tenant(
            id=tenant_id,
            name="Launch Context Tenant",
            type="ENTERPRISE",
            created_at=now(),
            updated_at=now(),
        ))
        project_one = create_project(db, tenant_id, "Launch Project One")
        project_two = create_project(db, tenant_id, "Launch Project Two")
        db.add(Farmer(
            id=complete_farmer_id,
            tenant_id=tenant_id,
            mobile_number=f"+9198{uuid.uuid4().int % 100000000:08d}",
            display_name="Launch Farmer",
            village_name_manual="Launch Village",
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        ))
        db.add(Farmer(
            id=incomplete_farmer_id,
            tenant_id=tenant_id,
            mobile_number=f"+9198{uuid.uuid4().int % 100000000:08d}",
            display_name=None,
            village_name_manual="Launch Village",
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        ))
        db.add(Parcel(
            id=parcel_id,
            tenant_id=tenant_id,
            farmer_id=complete_farmer_id,
            village_name_manual="Launch Village",
            reported_area=2,
            reported_area_unit="ACRE",
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        ))
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    headers = {"X-Tenant-ID": tenant_id}

    print("\n[1] Complete direct farmer with no project goes home")
    response = client.get(f"/api/v1/farmers/{complete_farmer_id}/launch-context", headers=headers)
    check(response.status_code == 200, "Launch context returns 200", response.text[:300])
    body = response.json()
    check(body["schema_version"] == "farmer_launch_context.v1", "Schema version is stable")
    check(body["recommended_navigation"] == "SHOW_HOME", "Direct complete farmer can show home")
    check(body["project_selection_required"] is False, "No project selection required without projects")
    check(body["active_project_count"] == 0, "No active project enrollments")
    check(body["active_project_candidate"] is None, "No active project candidate")
    check(body["endpoints"]["bootstrap"] == "/api/v1/app-config/bootstrap", "Bootstrap endpoint has no project for direct farmer")

    print("\n[2] Incomplete farmer is routed to profile completion")
    incomplete = client.get(f"/api/v1/farmers/{incomplete_farmer_id}/launch-context", headers=headers)
    check(incomplete.status_code == 200, "Incomplete launch context returns 200", incomplete.text[:300])
    incomplete_body = incomplete.json()
    check(incomplete_body["recommended_navigation"] == "SHOW_PROFILE_COMPLETION", "Incomplete farmer routes to profile completion")
    check("display_name" in incomplete_body["profile_completion"]["missing_fields"], "Missing display name is reported")
    check("parcel" in incomplete_body["profile_completion"]["missing_fields"], "Missing parcel is reported")

    print("\n[3] Single active project selects project candidate")
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.tenant_id == tenant_id, Project.name == "Launch Project One").first()
        create_enrollment(db, tenant_id, complete_farmer_id, project.id)
        db.commit()
        project_id = project.id
    finally:
        db.close()
    single = client.get(f"/api/v1/farmers/{complete_farmer_id}/launch-context", headers=headers)
    check(single.status_code == 200, "Single-project launch context returns 200", single.text[:300])
    single_body = single.json()
    check(single_body["recommended_navigation"] == "SHOW_HOME", "Single active project can still show home")
    check(single_body["active_project_count"] == 1, "Single active project counted")
    check(single_body["active_project_candidate"]["project_id"] == str(project_id), "Single active project candidate selected")
    check(f"project_id={project_id}" in single_body["endpoints"]["bootstrap"], "Bootstrap endpoint includes selected project")

    print("\n[4] Multiple active projects require project picker")
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.tenant_id == tenant_id, Project.name == "Launch Project Two").first()
        create_enrollment(db, tenant_id, complete_farmer_id, project.id)
        db.commit()
    finally:
        db.close()
    multiple = client.get(f"/api/v1/farmers/{complete_farmer_id}/launch-context", headers=headers)
    check(multiple.status_code == 200, "Multi-project launch context returns 200", multiple.text[:300])
    multiple_body = multiple.json()
    check(multiple_body["recommended_navigation"] == "SHOW_PROJECT_PICKER", "Multiple active projects route to picker")
    check(multiple_body["project_selection_required"] is True, "Project selection required")
    check(multiple_body["active_project_count"] == 2, "Two active projects counted")
    check(len(multiple_body["project_enrollments"]) == 2, "Both project enrollments returned")

    print("\n[5] Missing farmer returns 404")
    missing = client.get(f"/api/v1/farmers/{uuid.uuid4()}/launch-context", headers=headers)
    check(missing.status_code == 404, "Missing farmer returns 404", missing.text)

    print("\n[6] Cleanup")
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
    print("Farmer launch context validated")
    print("=" * 72)


if __name__ == "__main__":
    main()

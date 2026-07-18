"""Regression for field-agent assisted profile worklist."""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Farmer, FarmerProjectEnrollment, Parcel, Project, Tenant
from app.modules.farmer.soil_profile import SoilProfile


def now():
    return datetime.now(timezone.utc)


def check(condition, label, payload=None):
    if not condition:
        print(f"  FAIL {label}")
        if payload is not None:
            print(f"       {payload}")
        raise AssertionError(label)
    print(f"  PASS {label}")
    if payload is not None:
        print(f"       {payload}")


def main():
    print("=" * 72)
    print("FIELD AGENT WORKLIST REGRESSION")
    print("=" * 72)

    tenant_id = f"agent-worklist-{uuid.uuid4().hex[:8]}"
    project_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    assigned_farmer_id = uuid.uuid4()
    unassigned_farmer_id = uuid.uuid4()
    parcel_id = uuid.uuid4()

    db = SessionLocal()
    try:
        db.add(Tenant(
            id=tenant_id,
            name="Agent Worklist Tenant",
            type="ENTERPRISE",
            created_at=now(),
            updated_at=now(),
        ))
        db.add(Project(
            id=project_id,
            tenant_id=tenant_id,
            name="Agent Worklist Project",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=120),
            status="ACTIVE",
            geography_scope={},
            crop_scope=["RICE"],
            config={},
            created_at=now(),
            updated_at=now(),
        ))
        db.flush()

        db.add(Farmer(
            id=assigned_farmer_id,
            tenant_id=tenant_id,
            project_id=project_id,
            mobile_number=f"+9188{uuid.uuid4().int % 100000000:08d}",
            display_name="Assigned Farmer",
            village_name_manual="Agent Village",
            language_preference="hi",
            total_land_unit="ACRE",
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        ))
        db.add(Farmer(
            id=unassigned_farmer_id,
            tenant_id=tenant_id,
            project_id=project_id,
            mobile_number=f"+9187{uuid.uuid4().int % 100000000:08d}",
            display_name="Unassigned Farmer",
            village_name_manual="Agent Village",
            language_preference="en",
            total_land_unit="ACRE",
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        ))
        db.flush()

        db.add(Parcel(
            id=parcel_id,
            tenant_id=tenant_id,
            farmer_id=assigned_farmer_id,
            project_id=project_id,
            village_name_manual="Agent Village",
            reported_area=1.5,
            reported_area_unit="ACRE",
            ownership_type="OWNED",
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        ))
        db.flush()

        db.add(FarmerProjectEnrollment(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            farmer_id=assigned_farmer_id,
            project_id=project_id,
            enrollment_method="ASSISTED",
            status="ACTIVE",
            parcel_ids=[str(parcel_id)],
            assigned_user_ids=[str(actor_id)],
            metadata_={"assignment_reason": "regression"},
            created_at=now(),
            updated_at=now(),
        ))
        db.add(FarmerProjectEnrollment(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            farmer_id=unassigned_farmer_id,
            project_id=project_id,
            enrollment_method="ASSISTED",
            status="ACTIVE",
            parcel_ids=[],
            assigned_user_ids=[],
            created_at=now(),
            updated_at=now(),
        ))
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    headers = {"X-Tenant-ID": tenant_id, "X-Actor-ID": str(actor_id)}

    assigned = client.get(f"/api/v1/field-agent/worklist?project_id={project_id}&assigned_only=true", headers=headers)
    check(assigned.status_code == 200, "Assigned worklist returns 200", assigned.text)
    body = assigned.json()
    check(body["schema_version"] == "field_agent_worklist.v1", "Worklist schema stable")
    check(body["filters"]["assigned_only"] is True, "Worklist preserves assigned_only filter")
    check(body["summary"]["farmer_count"] == 1, "Assigned worklist includes only assigned farmer")
    row = body["farmers"][0]
    check(row["farmer"]["id"] == str(assigned_farmer_id), "Assigned worklist preserves farmer id")
    check(row["parcel_count"] == 1, "Assigned worklist includes parcel count")
    check(row["soil_profile_count"] == 0, "Assigned worklist includes soil profile count")
    action_codes = {action["code"] for action in row["capture_actions"]}
    check("ADD_SOIL_PROFILE" in action_codes, "Assigned worklist recommends soil capture")
    check("REPORT_FIELD_EVENT" in action_codes, "Assigned worklist includes field-event capture option")
    check(row["project_enrollments"][0]["assigned_user_ids"] == [str(actor_id)], "Worklist exposes assignment context")
    check("profile_hydration" in row["endpoints"], "Worklist includes Android handoff endpoints")

    all_rows = client.get(f"/api/v1/field-agent/worklist?project_id={project_id}", headers=headers)
    check(all_rows.status_code == 200, "Project worklist returns 200", all_rows.text)
    all_body = all_rows.json()
    check(all_body["summary"]["farmer_count"] == 2, "Project worklist includes assigned and unassigned farmers")
    check(any(item["farmer"]["id"] == str(unassigned_farmer_id) for item in all_body["farmers"]), "Project worklist includes unassigned farmer when assigned_only=false")

    missing_actor = client.get(f"/api/v1/field-agent/worklist?project_id={project_id}&assigned_only=true", headers={"X-Tenant-ID": tenant_id})
    check(missing_actor.status_code == 400, "Assigned-only worklist requires actor context", missing_actor.text)

    db = SessionLocal()
    try:
        db.query(SoilProfile).filter(SoilProfile.tenant_id == tenant_id).delete(synchronize_session=False)
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
    print("Field agent worklist validated")
    print("=" * 72)


if __name__ == "__main__":
    main()

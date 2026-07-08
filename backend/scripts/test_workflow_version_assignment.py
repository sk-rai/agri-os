"""Regression for crop-cycle workflow version pinning."""

from datetime import date, datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.modules.farmer.models import Farmer, Parcel, Tenant
from app.modules.workflow.models import (
    CropActivity,
    CropCycle,
    CropStageInstance,
    WorkflowTemplate,
    WorkflowTemplateVersion,
)

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"
TENANT_ID = "default"


def now():
    return datetime.now(timezone.utc)


def check(condition, label, detail=None):
    icon = f"{GREEN}✅{RESET}" if condition else f"{RED}❌{RESET}"
    print(f"  {icon} {label}")
    if detail is not None:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(label)


def ensure_default_tenant(db):
    tenant = db.query(Tenant).filter(Tenant.id == TENANT_ID).first()
    if not tenant:
        db.add(Tenant(id=TENANT_ID, name="Default", type="ENTERPRISE", created_at=now(), updated_at=now()))
        db.flush()


def get_rice_workflow(db):
    template = db.query(WorkflowTemplate).filter(WorkflowTemplate.code == "WF_RICE_KHARIF_DEFAULT").first()
    check(template is not None, "Rice workflow template exists")
    version = db.query(WorkflowTemplateVersion).filter(
        WorkflowTemplateVersion.template_id == template.id,
        WorkflowTemplateVersion.status == "PUBLISHED",
        WorkflowTemplateVersion.is_active == True,
    ).order_by(
        WorkflowTemplateVersion.published_at.desc().nullslast(),
        WorkflowTemplateVersion.created_at.desc(),
    ).first()
    check(version is not None, "Rice workflow has a published version")
    return template, version


def cleanup(db, farmer_id, parcel_id, cycle_id=None):
    if cycle_id:
        db.query(CropActivity).filter(CropActivity.crop_cycle_id == cycle_id).delete(synchronize_session=False)
        db.query(CropStageInstance).filter(CropStageInstance.crop_cycle_id == cycle_id).delete(synchronize_session=False)
        db.query(CropCycle).filter(CropCycle.id == cycle_id).delete(synchronize_session=False)
    db.query(Parcel).filter(Parcel.id == parcel_id).delete(synchronize_session=False)
    db.query(Farmer).filter(Farmer.id == farmer_id).delete(synchronize_session=False)
    db.commit()


def main():
    print("=" * 72)
    print("WORKFLOW VERSION ASSIGNMENT REGRESSION")
    print("=" * 72)

    client = TestClient(app)
    headers = {"X-Tenant-ID": TENANT_ID, "X-Actor-ID": str(uuid.uuid4())}
    farmer_id = uuid.uuid4()
    parcel_id = uuid.uuid4()
    cycle_id = None

    db = SessionLocal()
    try:
        ensure_default_tenant(db)
        workflow_template, published_version = get_rice_workflow(db)
        farmer = Farmer(
            id=farmer_id,
            tenant_id=TENANT_ID,
            mobile_number="999" + str(farmer_id.int)[-7:],
            village_name_manual="Workflow Pin Test Village",
            primary_crop_code="RICE",
            display_name="Workflow Pin Test Farmer",
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        )
        parcel = Parcel(
            id=parcel_id,
            tenant_id=TENANT_ID,
            farmer_id=farmer_id,
            village_name_manual="Workflow Pin Test Village",
            reported_area=1,
            reported_area_unit="ACRE",
            survey_number="PIN-" + str(parcel_id)[:8],
            ownership_type="OWNED",
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        )
        db.add(farmer)
        db.add(parcel)
        db.commit()

        response = client.post(
            "/api/v1/crop-cycles",
            headers=headers,
            json={
                "farmer_id": str(farmer_id),
                "parcel_id": str(parcel_id),
                "crop_code": "RICE",
                "season_code": "KHARIF",
                "planned_sowing_date": "2027-06-15",
            },
        )
        check(response.status_code == 201, "Crop cycle creation returns 201", f"Status: {response.status_code}, Body: {response.text[:300]}")
        payload = response.json()
        cycle_id = uuid.UUID(payload["id"])
        check(payload["workflow_template_version_id"] == str(published_version.id), "Creation response pins published workflow version")
        check(payload["workflow_template_pinning_status"] == "PINNED", "Creation response reports PINNED")

        db.expire_all()
        cycle = db.query(CropCycle).filter(CropCycle.id == cycle_id).first()
        check(cycle is not None, "Crop cycle persisted")
        check(cycle.workflow_template_version_id == published_version.id, "Crop cycle row stores workflow_template_version_id")
        db.commit()

        recs = client.get(f"/api/v1/crop-cycles/{cycle_id}/recommended-activities", headers=headers)
        check(recs.status_code == 200, "Recommended activities endpoint returns 200", f"Status: {recs.status_code}")
        rec_payload = recs.json()
        check(rec_payload["workflow_template_version_id"] == str(published_version.id), "Recommendations are rendered from pinned version")
        check(rec_payload["workflow_template_pinning_status"] == "PINNED", "Recommendations report PINNED")

        versions = client.get(f"/api/v1/workflow-catalog/templates/{workflow_template.id}/versions", headers={"X-Tenant-ID": TENANT_ID})
        check(versions.status_code == 200, "Version history endpoint returns 200", f"Status: {versions.status_code}")
        version_rows = versions.json()["versions"]
        row = next((item for item in version_rows if item["workflow_template_version_id"] == str(published_version.id)), None)
        check(row is not None, "Pinned version appears in version history")
        check(row.get("pinned_cycle_count", 0) >= 1, "Version history shows pinned cycle usage", row)
        check(row.get("active_pinned_cycle_count", 0) >= 1, "Version history shows active pinned cycle usage", row)
        check(row.get("is_read_only_for_existing_cycles") is True, "Used version is marked read-only for existing cycles")
    finally:
        cleanup(db, farmer_id, parcel_id, cycle_id)
        db.close()

    print("\n" + "=" * 72)
    print("🟢 Workflow version assignment validated")
    print("=" * 72)


if __name__ == "__main__":
    main()

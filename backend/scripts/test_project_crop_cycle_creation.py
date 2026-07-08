"""Regression for project-aware crop-cycle creation assignment rules."""

from datetime import date, datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.modules.farmer.models import Farmer, Parcel, Project, Tenant
from app.modules.workflow.models import (
    CropActivity,
    CropCycle,
    CropStageInstance,
    WorkflowTemplate,
    WorkflowTemplateEnablement,
    WorkflowTemplateVersion,
)

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"
TENANT_ID = "default"


def now():
    return datetime.now(timezone.utc)


def check(condition, label, detail=None):
    icon = f"{GREEN}?{RESET}" if condition else f"{RED}?{RESET}"
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


def get_template_and_version(db, code):
    template = db.query(WorkflowTemplate).filter(WorkflowTemplate.code == code).first()
    check(template is not None, f"{code} exists")
    version = db.query(WorkflowTemplateVersion).filter(
        WorkflowTemplateVersion.template_id == template.id,
        WorkflowTemplateVersion.status == "PUBLISHED",
        WorkflowTemplateVersion.is_active == True,
    ).order_by(
        WorkflowTemplateVersion.published_at.desc().nullslast(),
        WorkflowTemplateVersion.created_at.desc(),
    ).first()
    check(version is not None, f"{code} has a published version")
    return template, version


def cleanup(db, *, farmer_id, parcel_id, project_id, cycle_ids):
    db.rollback()
    for cycle_id in cycle_ids:
        db.query(CropActivity).filter(CropActivity.crop_cycle_id == cycle_id).delete(synchronize_session=False)
        db.query(CropStageInstance).filter(CropStageInstance.crop_cycle_id == cycle_id).delete(synchronize_session=False)
        db.query(CropCycle).filter(CropCycle.id == cycle_id).delete(synchronize_session=False)
    db.query(WorkflowTemplateEnablement).filter(WorkflowTemplateEnablement.project_id == project_id).delete(synchronize_session=False)
    db.query(Parcel).filter(Parcel.id == parcel_id).delete(synchronize_session=False)
    db.query(Farmer).filter(Farmer.id == farmer_id).delete(synchronize_session=False)
    db.query(Project).filter(Project.id == project_id).delete(synchronize_session=False)
    db.commit()


def main():
    print("=" * 72)
    print("PROJECT-AWARE CROP CYCLE CREATION REGRESSION")
    print("=" * 72)

    client = TestClient(app)
    headers = {"X-Tenant-ID": TENANT_ID, "X-Actor-ID": str(uuid.uuid4())}
    farmer_id = uuid.uuid4()
    parcel_id = uuid.uuid4()
    project_id = uuid.uuid4()
    cycle_ids = []

    db = SessionLocal()
    try:
        ensure_default_tenant(db)
        rice_template, rice_version = get_template_and_version(db, "WF_RICE_KHARIF_DEFAULT")
        sugar_template, _ = get_template_and_version(db, "WF_SUGARCANE_DEFAULT")
        project = Project(
            id=project_id,
            tenant_id=TENANT_ID,
            name="Project Cycle Assignment Test",
            crop_scope=["RICE"],
            start_date=date(2027, 1, 1),
            end_date=date(2027, 12, 31),
            status="PLANNED",
            created_at=now(),
            updated_at=now(),
        )
        farmer = Farmer(
            id=farmer_id,
            tenant_id=TENANT_ID,
            project_id=project_id,
            mobile_number="998" + str(farmer_id.int)[-7:],
            village_name_manual="Project Cycle Test Village",
            primary_crop_code="RICE",
            display_name="Project Cycle Test Farmer",
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        )
        parcel = Parcel(
            id=parcel_id,
            tenant_id=TENANT_ID,
            farmer_id=farmer_id,
            project_id=project_id,
            village_name_manual="Project Cycle Test Village",
            reported_area=1,
            reported_area_unit="ACRE",
            survey_number="PROJECT-CYCLE-" + str(parcel_id)[:8],
            ownership_type="OWNED",
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        )
        db.add(project)
        db.flush()
        db.add(farmer)
        db.add(parcel)
        db.add(WorkflowTemplateEnablement(
            id=uuid.uuid4(),
            tenant_id=TENANT_ID,
            project_id=project_id,
            template_id=rice_template.id,
            enabled=True,
            display_order=1,
            display_label={"en": "Project Rice", "hi": "Project Rice"},
            created_at=now(),
            updated_at=now(),
        ))
        db.add(WorkflowTemplateEnablement(
            id=uuid.uuid4(),
            tenant_id=TENANT_ID,
            project_id=project_id,
            template_id=sugar_template.id,
            enabled=False,
            display_order=2,
            created_at=now(),
            updated_at=now(),
        ))
        db.commit()

        catalog = client.get(
            f"/api/v1/workflow-catalog/enabled-crop-workflows?project_id={project_id}",
            headers={"X-Tenant-ID": TENANT_ID},
        )
        check(catalog.status_code == 200, "Project Android catalog returns 200", f"Status: {catalog.status_code}")
        catalog_codes = [workflow["crop_code"] for workflow in catalog.json()["workflows"]]
        check(catalog_codes == ["RICE"], "Project Android catalog only exposes Rice", catalog_codes)

        rice_response = client.post(
            "/api/v1/crop-cycles",
            headers=headers,
            json={
                "farmer_id": str(farmer_id),
                "parcel_id": str(parcel_id),
                "project_id": str(project_id),
                "crop_code": "RICE",
                "season_code": "KHARIF",
                "planned_sowing_date": "2027-06-15",
            },
        )
        check(rice_response.status_code == 201, "Project-allowed Rice cycle creation succeeds", f"Status: {rice_response.status_code}, Body: {rice_response.text[:300]}")
        rice_payload = rice_response.json()
        rice_cycle_id = uuid.UUID(rice_payload["id"])
        cycle_ids.append(rice_cycle_id)
        check(rice_payload["workflow_template_version_id"] == str(rice_version.id), "Rice cycle pins the project-visible workflow version")

        recs_response = client.get(f"/api/v1/crop-cycles/{rice_cycle_id}/recommended-activities", headers={"X-Tenant-ID": TENANT_ID})
        check(recs_response.status_code == 200, "Project Rice recommendations return 200", f"Status: {recs_response.status_code}")
        recs_payload = recs_response.json()
        check(recs_payload["input_filter_policy"] == "PROJECT_CROP_SCOPE", "Recommendations report project input filter policy")
        check(
            all(rec.get("input_assignment_rule") in {"INPUT_ALLOWED_FOR_PROJECT_CROP", "CUSTOM_OR_UNCODED_INPUT"} for rec in recs_payload["recommendations"]),
            "Returned recommendations are project-input allowed or uncoded",
        )

        blocked_input = client.post(
            f"/api/v1/crop-cycles/{rice_cycle_id}/activities",
            headers=headers,
            json={
                "activity_type": "SEED",
                "input_code": "HEALTHY_CANE_SETTS",
                "input_name": "Healthy Cane Setts",
                "activity_date": "2027-06-16",
            },
        )
        check(blocked_input.status_code == 409, "Catalog input outside cycle crop/project scope is rejected", f"Status: {blocked_input.status_code}")
        check(blocked_input.json()["detail"]["assignment_rule"] == "INPUT_NOT_ALLOWED_FOR_PROJECT_CROP", "Blocked input returns assignment rule")

        custom_input = client.post(
            f"/api/v1/crop-cycles/{rice_cycle_id}/activities",
            headers=headers,
            json={
                "activity_type": "OTHER",
                "input_name": "Local farmer-supplied item",
                "activity_date": "2027-06-16",
            },
        )
        check(custom_input.status_code == 201, "Manual uncatalogued activity input remains accepted", f"Status: {custom_input.status_code}")

        db.query(CropActivity).filter(CropActivity.crop_cycle_id == rice_cycle_id).delete(synchronize_session=False)
        db.query(CropStageInstance).filter(CropStageInstance.crop_cycle_id == rice_cycle_id).delete(synchronize_session=False)
        db.query(CropCycle).filter(CropCycle.id == rice_cycle_id).delete(synchronize_session=False)
        db.commit()
        cycle_ids.remove(rice_cycle_id)

        sugar_response = client.post(
            "/api/v1/crop-cycles",
            headers=headers,
            json={
                "farmer_id": str(farmer_id),
                "parcel_id": str(parcel_id),
                "project_id": str(project_id),
                "crop_code": "SUGARCANE",
                "season_code": "KHARIF",
                "planned_sowing_date": "2027-07-01",
            },
        )
        check(sugar_response.status_code == 409, "Project-blocked Sugarcane cycle creation is rejected", f"Status: {sugar_response.status_code}")
        detail = sugar_response.json()["detail"]
        check(detail["assignment_rule"] == "WORKFLOW_NOT_ASSIGNED_TO_PROJECT", "Blocked cycle response returns assignment rule", detail)
        check(detail["crop_code"] == "SUGARCANE", "Blocked cycle response includes crop code")
    finally:
        cleanup(db, farmer_id=farmer_id, parcel_id=parcel_id, project_id=project_id, cycle_ids=cycle_ids)
        db.close()

    print("\nAll project-aware crop-cycle creation checks passed.")


if __name__ == "__main__":
    main()
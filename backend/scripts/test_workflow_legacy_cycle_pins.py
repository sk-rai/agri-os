"""Regression for reporting/backfilling legacy crop-cycle workflow pins."""

from datetime import date, datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin
from app.modules.farmer.models import Farmer, Parcel, Project, Tenant
from app.modules.workflow.models import CropActivity, CropCycle, CropStageInstance, WorkflowTemplate, WorkflowTemplateAuditEvent, WorkflowTemplateVersion

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
    db.rollback()
    db.query(WorkflowTemplateAuditEvent).filter(
        WorkflowTemplateAuditEvent.action == "LEGACY_CYCLE_PIN_BACKFILL",
        WorkflowTemplateAuditEvent.reason == "Regression test",
    ).delete(synchronize_session=False)
    if cycle_id:
        db.query(CropActivity).filter(CropActivity.crop_cycle_id == cycle_id).delete(synchronize_session=False)
        db.query(CropStageInstance).filter(CropStageInstance.crop_cycle_id == cycle_id).delete(synchronize_session=False)
        db.query(CropCycle).filter(CropCycle.id == cycle_id).delete(synchronize_session=False)
    project_id = None
    parcel = db.query(Parcel).filter(Parcel.id == parcel_id).first()
    if parcel:
        project_id = parcel.project_id
    db.query(Parcel).filter(Parcel.id == parcel_id).delete(synchronize_session=False)
    db.query(Farmer).filter(Farmer.id == farmer_id).delete(synchronize_session=False)
    if project_id:
        db.query(Project).filter(Project.id == project_id).delete(synchronize_session=False)
    db.commit()


def main():
    print("=" * 72)
    print("WORKFLOW LEGACY CYCLE PIN BACKFILL REGRESSION")
    print("=" * 72)

    client = TestClient(app)
    headers = {"X-Tenant-ID": TENANT_ID, "X-Actor-ID": str(uuid.uuid4())}
    farmer_id = uuid.uuid4()
    parcel_id = uuid.uuid4()
    cycle_id = uuid.uuid4()
    project_id = uuid.uuid4()

    db = SessionLocal()
    admin_user, headers = create_test_admin(db)
    try:
        ensure_default_tenant(db)
        workflow_template, published_version = get_rice_workflow(db)
        check(workflow_template.lifecycle_template_id is not None, "Workflow template is linked to legacy lifecycle template")
        db.add(Project(
            id=project_id,
            tenant_id=TENANT_ID,
            name="Legacy Pin Test Project",
            start_date=date(2027, 1, 1),
            end_date=date(2027, 12, 31),
            status="PLANNED",
            created_at=now(),
            updated_at=now(),
        ))
        db.flush()
        db.add(Farmer(
            id=farmer_id,
            tenant_id=TENANT_ID,
            project_id=project_id,
            mobile_number="998" + str(farmer_id.int)[-7:],
            village_name_manual="Legacy Pin Test Village",
            primary_crop_code="RICE",
            display_name="Legacy Pin Test Farmer",
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        ))
        db.add(Parcel(
            id=parcel_id,
            tenant_id=TENANT_ID,
            farmer_id=farmer_id,
            project_id=project_id,
            village_name_manual="Legacy Pin Test Village",
            reported_area=1,
            reported_area_unit="ACRE",
            survey_number="LEGACY-PIN-" + str(parcel_id)[:8],
            ownership_type="OWNED",
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        ))
        db.add(CropCycle(
            id=cycle_id,
            tenant_id=TENANT_ID,
            farmer_id=farmer_id,
            parcel_id=parcel_id,
            project_id=project_id,
            crop_code="RICE",
            season_code="KHARIF",
            lifecycle_template_id=workflow_template.lifecycle_template_id,
            workflow_template_version_id=None,
            planned_sowing_date=date(2027, 7, 1),
            status="PLANNED",
            created_at=now(),
            updated_at=now(),
        ))
        db.commit()

        report = client.get(
            f"/api/v1/workflow-catalog/legacy-cycle-pins?project_id={project_id}&crop_code=RICE&season_code=KHARIF&limit=100",
            headers={"X-Tenant-ID": TENANT_ID},
        )
        check(report.status_code == 200, "Legacy pin report returns 200", f"Status: {report.status_code}")
        rows = report.json()["cycles"]
        row = next((item for item in rows if item["cycle_id"] == str(cycle_id)), None)
        check(row is not None, "Legacy cycle appears in report")
        check(row["eligible_for_backfill"] is True, "Legacy cycle is eligible for backfill", row)
        check(row["workflow_template_version_id"] == str(published_version.id), "Report resolves matching published version")

        dry_run = client.post(
            "/api/v1/workflow-catalog/legacy-cycle-pins/backfill",
            headers=headers,
            json={"dry_run": True, "project_id": str(project_id), "crop_code": "RICE", "season_code": "KHARIF", "limit": 100},
        )
        check(dry_run.status_code == 200, "Dry-run backfill returns 200", f"Status: {dry_run.status_code}")
        check(dry_run.json()["counts"]["eligible"] >= 1, "Dry-run reports eligible cycle")
        db.expire_all()
        cycle = db.query(CropCycle).filter(CropCycle.id == cycle_id).first()
        check(cycle.workflow_template_version_id is None, "Dry-run does not mutate cycle")
        db.commit()

        backfill = client.post(
            "/api/v1/workflow-catalog/legacy-cycle-pins/backfill",
            headers=headers,
            json={"dry_run": False, "project_id": str(project_id), "crop_code": "RICE", "season_code": "KHARIF", "limit": 100, "reason": "Regression test"},
        )
        check(backfill.status_code == 200, "Backfill returns 200", f"Status: {backfill.status_code}, Body: {backfill.text[:300]}")
        check(backfill.json()["counts"]["pinned"] >= 1, "Backfill pins at least one cycle")
        db.expire_all()
        cycle = db.query(CropCycle).filter(CropCycle.id == cycle_id).first()
        check(cycle.workflow_template_version_id == published_version.id, "Legacy cycle row is pinned after backfill")
    finally:
        cleanup(db, farmer_id, parcel_id, cycle_id)
        delete_test_admin(db, admin_user.id)
        db.close()

    print("\n" + "=" * 72)
    print("🟢 Workflow legacy cycle pin backfill validated")
    print("=" * 72)


if __name__ == "__main__":
    main()

"""Regression for project workflow enablement summary endpoint."""

from datetime import date, datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.modules.farmer.models import Project, Tenant
from app.modules.workflow.models import WorkflowTemplate, WorkflowTemplateEnablement

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


def ensure_tenant(db):
    tenant = db.query(Tenant).filter(Tenant.id == TENANT_ID).first()
    if not tenant:
        db.add(Tenant(id=TENANT_ID, name="Default", type="ENTERPRISE", created_at=now(), updated_at=now()))
        db.flush()


def cleanup(db, project_id):
    db.query(WorkflowTemplateEnablement).filter(WorkflowTemplateEnablement.project_id == project_id).delete(synchronize_session=False)
    db.query(Project).filter(Project.id == project_id).delete(synchronize_session=False)
    db.commit()


def main():
    print("=" * 72)
    print("PROJECT WORKFLOW ENABLEMENT SUMMARY REGRESSION")
    print("=" * 72)

    db = SessionLocal()
    project_id = uuid.uuid4()
    try:
        ensure_tenant(db)
        rice = db.query(WorkflowTemplate).filter(WorkflowTemplate.code == "WF_RICE_KHARIF_DEFAULT").first()
        sugar = db.query(WorkflowTemplate).filter(WorkflowTemplate.code == "WF_SUGARCANE_DEFAULT").first()
        check(rice is not None, "Rice workflow template exists")
        check(sugar is not None, "Sugarcane workflow template exists")

        db.add(Project(
            id=project_id,
            tenant_id=TENANT_ID,
            name="Enablement Summary Test Project",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            status="ACTIVE",
            crop_scope=["RICE"],
            geography_scope={},
            created_at=now(),
            updated_at=now(),
        ))
        db.flush()
        db.add(WorkflowTemplateEnablement(
            id=uuid.uuid4(),
            tenant_id=TENANT_ID,
            project_id=project_id,
            template_id=rice.id,
            enabled=True,
            display_order=1,
            created_at=now(),
            updated_at=now(),
        ))
        db.add(WorkflowTemplateEnablement(
            id=uuid.uuid4(),
            tenant_id=TENANT_ID,
            project_id=project_id,
            template_id=sugar.id,
            enabled=False,
            display_order=2,
            created_at=now(),
            updated_at=now(),
        ))
        db.commit()

        client = TestClient(app)
        response = client.get(
            f"/api/v1/workflow-catalog/projects/{project_id}/workflow-enablements",
            headers={"X-Tenant-ID": TENANT_ID},
        )
        check(response.status_code == 200, "Project enablement summary returns 200", f"Status: {response.status_code}")
        payload = response.json()
        check(payload["project"]["id"] == str(project_id), "Response contains project identity")
        check(payload["explicit_scope"] is True, "Response marks explicit scope")
        by_crop = {item["crop_code"]: item for item in payload["workflows"]}
        check(by_crop["RICE"]["visibility_status"] == "ENABLED", "Rice is enabled")
        check(by_crop["SUGARCANE"]["visibility_status"] == "DISABLED", "Sugarcane is disabled")
        check(payload["counts"]["enabled"] >= 1, "Enabled count is populated")
        check(payload["counts"]["disabled"] >= 1, "Disabled count is populated")

        disable_response = client.put(
            f"/api/v1/workflow-catalog/projects/{project_id}/workflow-enablements/{rice.id}",
            headers={"X-Tenant-ID": TENANT_ID},
            json={"enabled": False, "display_order": 5},
        )
        check(disable_response.status_code == 200, "Disable workflow action returns 200", f"Status: {disable_response.status_code}")
        disabled_by_crop = {item["crop_code"]: item for item in disable_response.json()["workflows"]}
        check(disabled_by_crop["RICE"]["visibility_status"] == "DISABLED", "Rice becomes disabled after action")

        enable_response = client.put(
            f"/api/v1/workflow-catalog/projects/{project_id}/workflow-enablements/{rice.id}",
            headers={"X-Tenant-ID": TENANT_ID},
            json={"enabled": True, "display_order": 3, "display_label": {"en": "Project Rice"}},
        )
        check(enable_response.status_code == 200, "Enable workflow action returns 200", f"Status: {enable_response.status_code}")
        enabled_by_crop = {item["crop_code"]: item for item in enable_response.json()["workflows"]}
        check(enabled_by_crop["RICE"]["visibility_status"] == "ENABLED", "Rice becomes enabled after action")
        check(enabled_by_crop["RICE"]["display_order"] == 3, "Display order is updated")
        check(enabled_by_crop["RICE"]["label"]["en"] == "Project Rice", "Display label is updated")
    finally:
        cleanup(db, project_id)
        db.close()

    print("\n" + "=" * 72)
    print("🟢 Project workflow enablement summary validated")
    print("=" * 72)


if __name__ == "__main__":
    main()

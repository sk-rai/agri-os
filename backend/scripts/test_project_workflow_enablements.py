"""Regression for project workflow enablement summary endpoint."""

from datetime import date, datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.modules.farmer.models import Farmer, Project, Tenant
from app.modules.workflow.models import WorkflowTemplate, WorkflowTemplateEnablement
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin

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
    db.query(Farmer).filter(Farmer.project_id == project_id).delete(synchronize_session=False)
    db.query(WorkflowTemplateEnablement).filter(WorkflowTemplateEnablement.project_id == project_id).delete(synchronize_session=False)
    db.query(Project).filter(Project.id == project_id).delete(synchronize_session=False)
    db.commit()


def main():
    print("=" * 72)
    print("PROJECT WORKFLOW ENABLEMENT SUMMARY REGRESSION")
    print("=" * 72)

    db = SessionLocal()
    project_id = uuid.uuid4()
    admin_user = None
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

        admin_user, admin_headers = create_test_admin(db, tenant_id=TENANT_ID)
        client = TestClient(app)
        client.headers.update(admin_headers)
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
        check(by_crop["SUGARCANE"]["visibility_status"] == "CROP_SCOPE_BLOCKED", "Sugarcane is blocked by project crop scope")
        check(by_crop["SUGARCANE"]["assignment_rule"] == "BLOCKED_BY_PROJECT_CROP_SCOPE", "Sugarcane Android visibility is blocked by crop scope")
        check(payload["counts"]["enabled"] >= 1, "Enabled count is populated")
        check(payload["counts"]["crop_scope_blocked"] >= 1, "Crop scope blocked count is populated")

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

        open_lifecycle = enable_response.json()["safe_edit_lifecycle"]
        check(open_lifecycle["can_edit_project_workflows"] is True, "Empty active project workflow config remains editable")
        check(open_lifecycle["lock_state"] == "OPEN", "Empty active project workflow lifecycle is OPEN")

        db.add(Farmer(
            id=uuid.uuid4(),
            tenant_id=TENANT_ID,
            project_id=project_id,
            mobile_number="+919999999992",
            village_name_manual="Workflow Policy Village",
            display_name="Workflow Policy Farmer",
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        ))
        db.commit()

        locked_summary = client.get(
            f"/api/v1/workflow-catalog/projects/{project_id}/workflow-enablements",
            headers={"X-Tenant-ID": TENANT_ID},
        )
        check(locked_summary.status_code == 200, "Locked project workflow summary still returns 200", f"Status: {locked_summary.status_code}")
        locked_lifecycle = locked_summary.json()["safe_edit_lifecycle"]
        check(locked_lifecycle["can_edit_project_workflows"] is False, "Project workflow config locks after farmer enrollment")
        check(locked_lifecycle["counts"]["farmers"] == 1, "Workflow lifecycle counts enrolled farmers")
        check(any(reason["code"] == "FARMERS_ENROLLED" for reason in locked_lifecycle["reasons"]), "Workflow lifecycle reports farmer enrollment lock reason")

        locked_update = client.put(
            f"/api/v1/workflow-catalog/projects/{project_id}/workflow-enablements/{rice.id}",
            headers={"X-Tenant-ID": TENANT_ID},
            json={"enabled": False},
        )
        check(locked_update.status_code == 409, "Workflow enablement update is blocked after enrollment", f"Status: {locked_update.status_code}")
        check(locked_update.json()["detail"]["safe_edit_lifecycle"]["lock_state"] == "LOCKED", "Blocked response includes lifecycle detail")
    finally:
        cleanup(db, project_id)
        if admin_user:
            delete_test_admin(db, admin_user.id)
        db.close()

    print("\n" + "=" * 72)
    print("🟢 Project workflow enablement summary validated")
    print("=" * 72)


if __name__ == "__main__":
    main()

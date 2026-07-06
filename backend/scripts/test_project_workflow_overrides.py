"""Regression for project workflow override create/delete endpoints."""

from datetime import date, datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.modules.farmer.models import Project, Tenant
from app.modules.workflow.models import WorkflowTemplate, WorkflowTemplateEnablement, WorkflowTemplateOverride, WorkflowTemplateVersion

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
    db.query(WorkflowTemplateOverride).filter(WorkflowTemplateOverride.project_id == project_id).delete(synchronize_session=False)
    db.query(WorkflowTemplateEnablement).filter(WorkflowTemplateEnablement.project_id == project_id).delete(synchronize_session=False)
    db.query(Project).filter(Project.id == project_id).delete(synchronize_session=False)
    db.commit()


def stage_codes(preview_payload):
    return [stage["code"] for stage in preview_payload["android_preview"]["stages"]]


def main():
    print("=" * 72)
    print("PROJECT WORKFLOW OVERRIDE REGRESSION")
    print("=" * 72)

    db = SessionLocal()
    project_id = uuid.uuid4()
    try:
        ensure_tenant(db)
        rice = db.query(WorkflowTemplate).filter(WorkflowTemplate.code == "WF_RICE_KHARIF_DEFAULT").first()
        version = db.query(WorkflowTemplateVersion).filter(
            WorkflowTemplateVersion.template_id == rice.id,
            WorkflowTemplateVersion.status == "PUBLISHED",
        ).first()
        check(rice is not None and version is not None, "Rice workflow/version exist")

        db.add(Project(
            id=project_id,
            tenant_id=TENANT_ID,
            name="Override Test Project",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            status="ACTIVE",
            crop_scope=["RICE"],
            geography_scope={},
            created_at=now(),
            updated_at=now(),
        ))
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
        db.commit()

        client = TestClient(app)
        base = client.get(
            f"/api/v1/workflow-catalog/workflow-preview/{version.id}?project_id={project_id}",
            headers={"X-Tenant-ID": TENANT_ID},
        )
        check(base.status_code == 200, "Base project preview returns 200", f"Status: {base.status_code}")
        check("FLOWERING" in stage_codes(base.json()), "FLOWERING stage initially visible")

        created = client.post(
            f"/api/v1/workflow-catalog/projects/{project_id}/workflow-overrides",
            headers={"X-Tenant-ID": TENANT_ID},
            json={
                "template_version_id": str(version.id),
                "target_type": "STAGE",
                "target_code": "FLOWERING",
                "operation": "HIDE",
                "override_payload": {},
                "priority": 10,
                "reason": "Regression hide flowering",
            },
        )
        check(created.status_code == 200, "Create override returns 200", f"Status: {created.status_code}")
        created_payload = created.json()
        check("FLOWERING" not in stage_codes(created_payload), "FLOWERING hidden after override")
        check(len(created_payload["applied_overrides"]) == 1, "Preview reports applied override")
        override_id = created_payload["applied_overrides"][0]["id"]

        deleted = client.delete(
            f"/api/v1/workflow-catalog/projects/{project_id}/workflow-overrides/{override_id}",
            headers={"X-Tenant-ID": TENANT_ID},
        )
        check(deleted.status_code == 200, "Delete override returns 200", f"Status: {deleted.status_code}")
        deleted_payload = deleted.json()
        check("FLOWERING" in stage_codes(deleted_payload), "FLOWERING visible again after override removal")
        check(len(deleted_payload["applied_overrides"]) == 0, "Preview has no applied overrides after delete")
    finally:
        cleanup(db, project_id)
        db.close()

    print("\n" + "=" * 72)
    print("🟢 Project workflow override create/delete validated")
    print("=" * 72)


if __name__ == "__main__":
    main()

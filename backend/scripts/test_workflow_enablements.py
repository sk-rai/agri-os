"""Regression for workflow enablements and scoped overrides."""

from datetime import date, datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.modules.farmer.models import Tenant, Project
from app.modules.workflow.models import (
    WorkflowTemplate,
    WorkflowTemplateVersion,
    WorkflowTemplateEnablement,
    WorkflowTemplateOverride,
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


def get_template_and_version(db, code):
    template = db.query(WorkflowTemplate).filter(WorkflowTemplate.code == code).first()
    check(template is not None, f"{code} exists")
    version = db.query(WorkflowTemplateVersion).filter(
        WorkflowTemplateVersion.template_id == template.id,
        WorkflowTemplateVersion.status == "PUBLISHED",
    ).first()
    check(version is not None, f"{code} has published version")
    return template, version


def cleanup(db, project_id):
    db.query(WorkflowTemplateOverride).filter(WorkflowTemplateOverride.project_id == project_id).delete(synchronize_session=False)
    db.query(WorkflowTemplateEnablement).filter(WorkflowTemplateEnablement.project_id == project_id).delete(synchronize_session=False)
    db.query(Project).filter(Project.id == project_id).delete(synchronize_session=False)
    db.commit()


def main():
    print("=" * 72)
    print("WORKFLOW ENABLEMENT / OVERRIDE REGRESSION")
    print("=" * 72)

    client = TestClient(app)
    headers = {"X-Tenant-ID": TENANT_ID}

    print("\n[1] Default implicit workflow catalog")
    response = client.get("/api/v1/workflow-catalog/enabled-crop-workflows", headers=headers)
    check(response.status_code == 200, "Default catalog returns 200", f"Status: {response.status_code}")
    payload = response.json()
    codes = {item["crop_code"] for item in payload["workflows"]}
    check("RICE" in codes, "Default catalog includes Rice")
    check("SUGARCANE" in codes, "Default catalog includes Sugarcane")
    check(all(item["enablement_source"] == "implicit_default" for item in payload["workflows"]), "Default catalog uses implicit default source")

    print("\n[2] Project explicit allow-list and stage override")
    db = SessionLocal()
    project_id = uuid.uuid4()
    try:
        ensure_default_tenant(db)
        rice_template, rice_version = get_template_and_version(db, "WF_RICE_KHARIF_DEFAULT")
        sugar_template, _ = get_template_and_version(db, "WF_SUGARCANE_DEFAULT")
        project = Project(
            id=project_id,
            tenant_id=TENANT_ID,
            name="Workflow Test Project",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        )
        db.add(project)
        db.flush()
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
        db.add(WorkflowTemplateOverride(
            id=uuid.uuid4(),
            tenant_id=TENANT_ID,
            project_id=project_id,
            template_version_id=rice_version.id,
            target_type="STAGE",
            target_code="FLOWERING",
            operation="HIDE",
            override_payload={},
            priority=10,
            reason="Project-specific visibility test",
            created_at=now(),
            updated_at=now(),
        ))
        db.commit()

        scoped = client.get(
            f"/api/v1/workflow-catalog/enabled-crop-workflows?project_id={project_id}&include_stages=true",
            headers=headers,
        )
        check(scoped.status_code == 200, "Project catalog returns 200", f"Status: {scoped.status_code}")
        scoped_payload = scoped.json()
        scoped_codes = [item["crop_code"] for item in scoped_payload["workflows"]]
        check(scoped_codes == ["RICE"], "Project explicit allow-list hides disabled Sugarcane", f"Crops: {scoped_codes}")
        rice_item = scoped_payload["workflows"][0]
        check(rice_item["enablement_source"] == "explicit", "Project catalog marks explicit enablement")
        check(rice_item["label"]["en"] == "Project Rice", "Project display label is returned")
        stage_codes = [stage["code"] for stage in rice_item["stages"]]
        check("FLOWERING" not in stage_codes, "Project override hides FLOWERING stage")
        check("TRANSPLANTING" in stage_codes, "Other Rice stages remain visible")
    finally:
        cleanup(db, project_id)
        db.close()

    print("\n" + "=" * 72)
    print("🟢 Workflow enablements and overrides validated")
    print("=" * 72)


if __name__ == "__main__":
    main()

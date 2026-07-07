"""Regression for project edit policy / core configuration locking."""

from datetime import date, datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.modules.farmer.models import Farmer, Project, Tenant

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


def ensure_tenant(db):
    tenant = db.query(Tenant).filter(Tenant.id == TENANT_ID).first()
    if not tenant:
        db.add(Tenant(id=TENANT_ID, name="Default", type="ENTERPRISE", created_at=now(), updated_at=now()))
        db.flush()


def cleanup(db, project_id):
    db.query(Farmer).filter(Farmer.project_id == project_id).delete(synchronize_session=False)
    db.query(Project).filter(Project.id == project_id).delete(synchronize_session=False)
    db.commit()


def main():
    print("=" * 72)
    print("PROJECT EDIT POLICY REGRESSION")
    print("=" * 72)

    db = SessionLocal()
    project_id = uuid.uuid4()
    try:
        ensure_tenant(db)
        project = Project(
            id=project_id,
            tenant_id=TENANT_ID,
            name="Edit Policy Test Project",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            status="PLANNED",
            geography_scope={},
            crop_scope=["RICE"],
            created_at=now(),
            updated_at=now(),
        )
        db.add(project)
        db.commit()

        client = TestClient(app)
        headers = {"X-Tenant-ID": TENANT_ID}
        open_policy = client.get(f"/api/v1/projects/{project_id}/edit-policy", headers=headers)
        check(open_policy.status_code == 200, "Edit policy returns 200 for planned empty project", f"Status: {open_policy.status_code}")
        open_payload = open_policy.json()
        check(open_payload["can_edit_core_config"] is True, "Planned empty project can edit core config")
        check(open_payload["lock_state"] == "OPEN", "Planned empty project lock state is OPEN")

        project.status = "ACTIVE"
        project.updated_at = now()
        db.commit()
        active_policy = client.get(f"/api/v1/projects/{project_id}/edit-policy", headers=headers)
        active_payload = active_policy.json()
        check(active_payload["can_edit_core_config"] is False, "Active project cannot edit core config")
        check(any(reason["code"] == "PROJECT_ACTIVE" for reason in active_payload["reasons"]), "Active lock reason is reported")

        project.status = "PLANNED"
        db.add(Farmer(
            id=uuid.uuid4(),
            tenant_id=TENANT_ID,
            project_id=project_id,
            mobile_number="+919999999991",
            village_name_manual="Policy Village",
            display_name="Policy Farmer",
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        ))
        db.commit()
        enrolled_policy = client.get(f"/api/v1/projects/{project_id}/edit-policy", headers=headers)
        enrolled_payload = enrolled_policy.json()
        check(enrolled_payload["can_edit_core_config"] is False, "Project with enrolled farmer cannot edit core config")
        check(enrolled_payload["counts"]["farmers"] == 1, "Policy counts enrolled farmers")
        check(any(reason["code"] == "FARMERS_ENROLLED" for reason in enrolled_payload["reasons"]), "Farmer enrollment lock reason is reported")
        check("crop_scope" in enrolled_payload["locked_fields"], "Core scope fields are locked")
    finally:
        cleanup(db, project_id)
        db.close()

    print("\n" + "=" * 72)
    print("Project edit policy validated")
    print("=" * 72)


if __name__ == "__main__":
    main()

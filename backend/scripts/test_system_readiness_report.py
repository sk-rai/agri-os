"""Regression for the admin system readiness report."""

from datetime import date, datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Project, Tenant
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin


REQUIRED_CHECKS = {
    "PROJECT_SETUP",
    "WORKFLOW_RUNTIME",
    "WORKFLOW_ASSIGNMENTS",
    "INPUT_CATALOG",
    "PRODUCT_CATALOG",
    "FARMER_SYNC",
    "PARCEL_GEOMETRY",
    "ACTIVITY_EVIDENCE",
    "SYNC_HEALTH",
}


def check(condition, label, detail=None):
    print(f"  {'PASS' if condition else 'FAIL'} {label}")
    if detail is not None:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(label)


def ensure_tenant(db):
    if db.query(Tenant).filter(Tenant.id == "default").first():
        return
    db.add(Tenant(
        id="default",
        name="Default",
        type="ENTERPRISE",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    ))
    db.commit()


def create_project(db) -> Project:
    project = Project(
        id=uuid.uuid4(),
        tenant_id="default",
        name="System Readiness Regression Project",
        start_date=date(2027, 1, 1),
        end_date=date(2027, 12, 31),
        status="PLANNED",
        crop_scope=["RICE"],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(project)
    db.commit()
    return project


def main():
    print("=" * 72)
    print("SYSTEM READINESS REPORT REGRESSION")
    print("=" * 72)
    db = SessionLocal()
    admin = None
    project = None
    try:
        ensure_tenant(db)
        client = TestClient(app)
        unauthenticated = client.get("/api/v1/reports/system-readiness", headers={"X-Tenant-ID": "default"})
        check(unauthenticated.status_code == 401, "system readiness requires admin authentication", unauthenticated.text)

        admin, headers = create_test_admin(db, role="ADMIN_VIEWER", tenant_id="default")
        response = client.get("/api/v1/reports/system-readiness", headers=headers)
        check(response.status_code == 200, "ADMIN_VIEWER can read system readiness", response.text[:500])
        payload = response.json()
        check(payload["schema_version"] == "system_readiness.v1", "schema version is stable")
        check(payload["tenant_id"] == "default", "tenant id is returned")
        check("summary" in payload and "checks" in payload, "payload has summary and checks")
        check(payload["summary"]["check_count"] == len(payload["checks"]), "summary check_count matches checks length")
        check(0 <= payload["summary"]["ready_count"] <= payload["summary"]["check_count"], "ready_count is in range")
        check(REQUIRED_CHECKS.issubset({item["code"] for item in payload["checks"]}), "required readiness checks are present")
        for item in payload["checks"]:
            check(isinstance(item["ready"], bool), f"{item['code']} ready is boolean")
            check(item["severity"] in {"OK", "WARN", "INFO"}, f"{item['code']} severity is valid")
            check(bool(item["label"]) and bool(item["detail"]) and bool(item["href"]), f"{item['code']} has label/detail/href")

        project = create_project(db)
        scoped_response = client.get(f"/api/v1/reports/system-readiness?project_id={project.id}", headers=headers)
        check(scoped_response.status_code == 200, "project-scoped system readiness returns 200", scoped_response.text[:500])
        scoped = scoped_response.json()
        check(scoped["filters"]["project_id"] == str(project.id), "project-scoped readiness echoes project id")
        check(scoped["summary"]["check_count"] == len(scoped["checks"]), "project-scoped check_count matches checks length")
        scoped_by_code = {item["code"]: item for item in scoped["checks"]}
        check(scoped_by_code["PROJECT_SETUP"]["ready"] is True, "project-scoped project setup is ready for seeded project")
        check(scoped_by_code["WORKFLOW_ASSIGNMENTS"]["severity"] in {"OK", "INFO"}, "project-scoped workflow assignment check is informational or ready")
        check(scoped_by_code["FARMER_SYNC"]["href"].startswith(f"/lookup?projectId={project.id}"), "project-scoped farmer sync links to project lookup")

        missing_project_id = uuid.uuid4()
        missing_response = client.get(f"/api/v1/reports/system-readiness?project_id={missing_project_id}", headers=headers)
        check(missing_response.status_code == 404, "missing project readiness returns 404", missing_response.text)
    finally:
        db.rollback()
        if project:
            db.query(Project).filter(Project.id == project.id).delete(synchronize_session=False)
            db.commit()
        if admin:
            delete_test_admin(db, admin.id)
        db.close()

    print("=" * 72)
    print("System readiness report validated")
    print("=" * 72)


if __name__ == "__main__":
    main()

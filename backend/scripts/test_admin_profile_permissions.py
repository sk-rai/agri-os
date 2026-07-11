"""Regression for /api/v1/admin/me permission payloads across admin roles."""

from datetime import date, datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.auth.models import User
from app.modules.farmer.models import Project, ProjectRole, Tenant
from scripts.admin_auth_test_utils import create_test_admin


TENANT_ID = "default"

EXPECTED_ROLE_PERMISSIONS = {
    "ENTERPRISE_ADMIN": ["EDIT", "MANAGE_USERS", "PROJECT_EDIT", "PUBLISH", "VIEW"],
    "MANAGER": ["EDIT", "PROJECT_EDIT", "PUBLISH", "VIEW"],
    "AGRONOMIST": ["EDIT", "PROJECT_EDIT", "VIEW"],
    "ADMIN_EDITOR": ["EDIT", "VIEW"],
    "ADMIN_PUBLISHER": ["EDIT", "PUBLISH", "VIEW"],
    "ADMIN_VIEWER": ["VIEW"],
    "VIEWER": ["VIEW"],
}

PROJECT_ROLE_EXPECTATIONS = {
    "ADMIN_VIEWER": ["VIEW"],
    "AGRONOMIST": ["EDIT", "PROJECT_EDIT", "VIEW"],
    "MANAGER": ["EDIT", "PROJECT_EDIT", "PUBLISH", "VIEW"],
}


def check(condition, label, detail=None):
    print(f"  {'PASS' if condition else 'FAIL'} {label}")
    if detail is not None:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(label)


def ensure_tenant(db):
    if db.query(Tenant).filter(Tenant.id == TENANT_ID).first():
        return
    db.add(Tenant(
        id=TENANT_ID,
        name="Default",
        type="ENTERPRISE",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    ))
    db.commit()


def create_project(db) -> Project:
    project = Project(
        id=uuid.uuid4(),
        tenant_id=TENANT_ID,
        name="Admin Profile Permission Regression",
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


def cleanup(db, user_ids, project_id):
    db.rollback()
    if project_id:
        db.query(ProjectRole).filter(ProjectRole.project_id == project_id).delete(synchronize_session=False)
        db.query(Project).filter(Project.id == project_id).delete(synchronize_session=False)
    for user_id in user_ids:
        db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
    db.commit()


def main():
    print("=" * 72)
    print("ADMIN PROFILE PERMISSION REGRESSION")
    print("=" * 72)
    client = TestClient(app)
    db = SessionLocal()
    created_user_ids = []
    project_id = None
    try:
        ensure_tenant(db)
        role_headers = {}
        for role in EXPECTED_ROLE_PERMISSIONS:
            user, headers = create_test_admin(db, role=role, tenant_id=TENANT_ID)
            created_user_ids.append(user.id)
            role_headers[role] = headers

            response = client.get("/api/v1/admin/me", headers=headers)
            check(response.status_code == 200, f"{role} can read /admin/me", response.text)
            payload = response.json()
            check(payload["schema_version"] == "admin_profile.v1", f"{role} profile schema version")
            check(payload["role"] == role, f"{role} profile returns role")
            check(payload["tenant_id"] == TENANT_ID, f"{role} profile returns tenant")
            check(payload["permissions"] == EXPECTED_ROLE_PERMISSIONS[role], f"{role} exact tenant permissions", payload["permissions"])

        viewer_users = client.get("/api/v1/admin/users", headers=role_headers["ADMIN_VIEWER"])
        check(viewer_users.status_code == 403, "ADMIN_VIEWER cannot manage users", viewer_users.text)
        enterprise_users = client.get("/api/v1/admin/users", headers=role_headers["ENTERPRISE_ADMIN"])
        check(enterprise_users.status_code == 200, "ENTERPRISE_ADMIN can manage users", enterprise_users.text)

        project = create_project(db)
        project_id = project.id
        project_user, project_headers = create_test_admin(db, role="ADMIN_VIEWER", tenant_id=TENANT_ID)
        created_user_ids.append(project_user.id)
        for project_role, expected_permissions in PROJECT_ROLE_EXPECTATIONS.items():
            existing = db.query(ProjectRole).filter(
                ProjectRole.project_id == project.id,
                ProjectRole.user_id == project_user.id,
            ).first()
            if not existing:
                existing = ProjectRole(
                    id=uuid.uuid4(),
                    project_id=project.id,
                    user_id=project_user.id,
                    role=project_role,
                    territory_scope={},
                    is_active=True,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                db.add(existing)
            existing.role = project_role
            existing.updated_at = datetime.now(timezone.utc)
            db.commit()

            response = client.get("/api/v1/admin/me", headers=project_headers)
            check(response.status_code == 200, f"Project role {project_role} profile returns 200", response.text)
            access = response.json()["project_access"]
            check(len(access) == 1, f"Project role {project_role} profile returns one project access row", access)
            check(access[0]["project_id"] == str(project.id), f"Project role {project_role} project id")
            check(access[0]["role"] == project_role, f"Project role {project_role} role is returned")
            check(access[0]["permissions"] == expected_permissions, f"Project role {project_role} exact permissions", access[0]["permissions"])
    finally:
        cleanup(db, created_user_ids, project_id)
        db.close()

    print("=" * 72)
    print("Admin profile permissions validated")
    print("=" * 72)


if __name__ == "__main__":
    main()

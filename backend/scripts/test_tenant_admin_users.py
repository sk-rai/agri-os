"""Regression for tenant-admin delegation and project access management."""

from datetime import date, datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.auth.models import TenantUserAccessAuditEvent, User
from app.modules.auth.service import create_jwt
from app.modules.farmer.models import Project, ProjectRole, Tenant
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin


TENANT_ID = "default"
INVITED_MOBILE = "+919811112222"


def check(condition, label, detail=None):
    print(f"  {'PASS' if condition else 'FAIL'} {label}")
    if detail is not None:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(label)


def headers_for(user: User) -> dict[str, str]:
    token, _ = create_jwt(user, "tenant-admin-regression")
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-ID": TENANT_ID,
        "X-Actor-ID": str(user.id),
    }


def cleanup(db, principal_id: uuid.UUID, invited_id, project_id):
    db.rollback()
    db.query(TenantUserAccessAuditEvent).filter(
        TenantUserAccessAuditEvent.tenant_id == TENANT_ID,
        TenantUserAccessAuditEvent.actor_id == principal_id,
    ).delete(synchronize_session=False)
    if invited_id:
        db.query(ProjectRole).filter(ProjectRole.user_id == invited_id).delete(synchronize_session=False)
    db.query(Project).filter(Project.id == project_id).delete(synchronize_session=False)
    if invited_id:
        db.query(User).filter(User.id == invited_id).delete(synchronize_session=False)
    db.commit()
    delete_test_admin(db, principal_id)


def main():
    print("=" * 72)
    print("TENANT ADMIN USER MANAGEMENT REGRESSION")
    print("=" * 72)
    client = TestClient(app)
    db = SessionLocal()
    principal = None
    invited_id = None
    project_id = uuid.uuid4()
    try:
        if not db.query(Tenant).filter(Tenant.id == TENANT_ID).first():
            db.add(Tenant(
                id=TENANT_ID,
                name="Default",
                type="ENTERPRISE",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ))
            db.commit()
        principal, admin_headers = create_test_admin(db, role="ENTERPRISE_ADMIN")

        invite = client.put(
            "/api/v1/admin/users/by-mobile",
            headers=admin_headers,
            json={
                "mobile_number": INVITED_MOBILE,
                "display_name": "Tenant Viewer Regression",
                "role": "ADMIN_VIEWER",
                "reason": "Regression invite",
            },
        )
        check(invite.status_code == 200, "Enterprise admin can invite tenant viewer", invite.text)
        invited_id = uuid.UUID(invite.json()["user"]["id"])
        check(invite.json()["created"] is True, "Invite creates missing user")
        invited = db.query(User).filter(User.id == invited_id).first()
        viewer_headers = headers_for(invited)

        viewer_list = client.get("/api/v1/admin/users", headers=viewer_headers)
        check(viewer_list.status_code == 403, "Viewer cannot manage tenant users", viewer_list.text)
        admin_list = client.get("/api/v1/admin/users", headers=admin_headers)
        check(admin_list.status_code == 200, "Enterprise admin can list tenant admins", admin_list.text)
        check(
            any(row["id"] == str(invited_id) for row in admin_list.json()["users"]),
            "Invited viewer appears in tenant list",
        )

        role_change = client.put(
            f"/api/v1/admin/users/{invited_id}/role",
            headers=admin_headers,
            json={
                "display_name": "Tenant Agronomist Regression",
                "role": "AGRONOMIST",
                "reason": "Promote for workflow editing",
            },
        )
        check(role_change.status_code == 200, "Enterprise admin can change tenant role", role_change.text)
        check(role_change.json()["user"]["role"] == "AGRONOMIST", "Role change is returned")

        db.add(Project(
            id=project_id,
            tenant_id=TENANT_ID,
            name="Tenant Access Regression Project",
            start_date=date(2027, 1, 1),
            end_date=date(2027, 12, 31),
            status="PLANNED",
            crop_scope=["RICE"],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ))
        db.commit()
        project_grant = client.put(
            f"/api/v1/admin/users/{invited_id}/projects/{project_id}",
            headers=admin_headers,
            json={
                "role": "AGRONOMIST",
                "territory_scope": {"district_ids": ["regression"]},
                "reason": "Assign agronomist to project",
            },
        )
        check(project_grant.status_code == 200, "Enterprise admin can grant project access", project_grant.text)
        access_rows = project_grant.json()["user"]["project_access"]
        check(len(access_rows) == 1 and access_rows[0]["project_id"] == str(project_id), "Project access appears on user")

        project_revoke = client.request(
            "DELETE",
            f"/api/v1/admin/users/{invited_id}/projects/{project_id}",
            headers=admin_headers,
            json={"reason": "Project assignment complete"},
        )
        check(project_revoke.status_code == 200, "Enterprise admin can revoke project access", project_revoke.text)
        check(project_revoke.json()["user"]["project_access"] == [], "Revoked project is absent")

        self_revoke = client.request(
            "DELETE",
            f"/api/v1/admin/users/{principal.id}",
            headers=admin_headers,
            json={"reason": "Must not allow self lockout"},
        )
        check(self_revoke.status_code == 409, "Enterprise admin cannot revoke self", self_revoke.text)

        audit = client.get(
            f"/api/v1/admin/user-access-audit?user_id={invited_id}",
            headers=admin_headers,
        )
        check(audit.status_code == 200, "User access audit returns 200", audit.text)
        actions = {event["action"] for event in audit.json()["events"]}
        for action in {
            "INVITE_TENANT_USER",
            "CHANGE_TENANT_ROLE",
            "ASSIGN_PROJECT_ACCESS",
            "REVOKE_PROJECT_ACCESS",
        }:
            check(action in actions, f"Audit includes {action}")

        tenant_revoke = client.request(
            "DELETE",
            f"/api/v1/admin/users/{invited_id}",
            headers=admin_headers,
            json={"reason": "Regression tenant revoke"},
        )
        check(tenant_revoke.status_code == 200, "Enterprise admin can revoke tenant access", tenant_revoke.text)
        db.expire_all()
        invited = db.query(User).filter(User.id == invited_id).first()
        check(invited.tenant_id is None and invited.role == "FARMER", "Revoked user loses tenant admin role")
    finally:
        if principal:
            cleanup(db, principal.id, invited_id, project_id)
        db.close()

    print("=" * 72)
    print("Tenant admin user management validated")
    print("=" * 72)


if __name__ == "__main__":
    main()

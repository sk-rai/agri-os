#!/usr/bin/env python3
"""Behavior regression for authenticated identity-administration mutations."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.auth.models import (
    AgentProfile,
    TenantUserAccessAuditEvent,
)
from app.modules.farmer.models import Project, ProjectRole, Tenant
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin


def check(condition, label, detail=None):
    print(f"  {'PASS' if condition else 'FAIL'} {label}")
    if detail is not None:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(label)


def main() -> int:
    print("=" * 72)
    print("IDENTITY ADMINISTRATION AUTHORIZATION REGRESSION")
    print("=" * 72)

    tenant_id = f"identity-admin-{uuid.uuid4().hex[:8]}"
    foreign_tenant_id = f"identity-admin-foreign-{uuid.uuid4().hex[:8]}"
    project_id = uuid.uuid4()
    foreign_project_id = uuid.uuid4()

    admin_user_id = None
    viewer_user_id = None
    target_user_id = None
    profile_id = None

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        db.add_all([
            Tenant(
                id=tenant_id,
                name="Identity Administration Tenant",
                type="ENTERPRISE",
                created_at=now,
                updated_at=now,
            ),
            Tenant(
                id=foreign_tenant_id,
                name="Foreign Identity Administration Tenant",
                type="ENTERPRISE",
                created_at=now,
                updated_at=now,
            ),
            Project(
                id=project_id,
                tenant_id=tenant_id,
                name="Identity Administration Project",
                start_date=date.today(),
                end_date=date.today() + timedelta(days=180),
                status="ACTIVE",
                geography_scope={},
                crop_scope=[],
                config={},
                created_at=now,
                updated_at=now,
            ),
            Project(
                id=foreign_project_id,
                tenant_id=foreign_tenant_id,
                name="Foreign Identity Administration Project",
                start_date=date.today(),
                end_date=date.today() + timedelta(days=180),
                status="ACTIVE",
                geography_scope={},
                crop_scope=[],
                config={},
                created_at=now,
                updated_at=now,
            ),
        ])
        db.commit()

        admin, admin_headers = create_test_admin(
            db,
            role="ENTERPRISE_ADMIN",
            tenant_id=tenant_id,
        )
        viewer, viewer_headers = create_test_admin(
            db,
            role="ADMIN_VIEWER",
            tenant_id=tenant_id,
        )
        target, _ = create_test_admin(
            db,
            role="AGRONOMIST",
            tenant_id=tenant_id,
        )
        admin_user_id = admin.id
        viewer_user_id = viewer.id
        target_user_id = target.id
    finally:
        db.close()

    client = TestClient(app)
    profile_payload = {
        "user_id": str(target_user_id),
        "agent_code": "IDENTITY-REGRESSION",
        "role_type": "AGRONOMIST",
        "display_name": "Identity Regression Agent",
        "status": "ACTIVE",
        "skills": ["CROP_ADVISORY"],
        "languages": ["hi"],
        "territory_scope": {"district_codes": ["001"]},
        "metadata": {"source": "identity_admin_regression"},
        "reason": "create identity regression profile",
    }

    missing_bearer = client.post(
        "/api/v1/admin/agent-profiles",
        headers={
            "X-Tenant-ID": tenant_id,
            "X-Actor-ID": str(admin_user_id),
        },
        json=profile_payload,
    )
    check(
        missing_bearer.status_code == 401,
        "Identity administration rejects missing bearer",
        missing_bearer.text,
    )

    viewer_create = client.post(
        "/api/v1/admin/agent-profiles",
        headers=viewer_headers,
        json=profile_payload,
    )
    check(
        viewer_create.status_code == 403,
        "Identity administration rejects view-only administrator",
        viewer_create.text,
    )

    impersonated = client.post(
        "/api/v1/admin/agent-profiles",
        headers={**admin_headers, "X-Actor-ID": str(uuid.uuid4())},
        json=profile_payload,
    )
    impersonation_detail = impersonated.json().get("detail", {})
    check(
        impersonated.status_code in {401, 403}
        and isinstance(impersonation_detail, dict)
        and impersonation_detail.get("error") == "ACTOR_ID_MISMATCH",
        "Identity administration rejects actor impersonation",
        impersonated.text,
    )

    mismatched = client.post(
        "/api/v1/admin/agent-profiles",
        headers={**admin_headers, "X-Tenant-ID": foreign_tenant_id},
        json=profile_payload,
    )
    check(
        mismatched.status_code == 403,
        "Identity administration rejects tenant mismatch",
        mismatched.text,
    )

    created = client.post(
        "/api/v1/admin/agent-profiles",
        headers=admin_headers,
        json=profile_payload,
    )
    check(created.status_code == 201, "Agent profile creation returns 201", created.text)
    created_body = created.json()
    profile_id = uuid.UUID(created_body["agent_profile"]["id"])
    check(created_body["created"] is True, "Agent profile is newly created")
    check(
        created_body["agent_profile"]["tenant_id"] == tenant_id,
        "Agent profile uses verified tenant",
    )

    updated = client.patch(
        f"/api/v1/admin/agent-profiles/{profile_id}",
        headers=admin_headers,
        json={
            "status": "INACTIVE",
            "skills": ["SOIL_HEALTH"],
            "reason": "update identity regression profile",
        },
    )
    check(updated.status_code == 200, "Agent profile update returns 200", updated.text)
    check(
        updated.json()["agent_profile"]["status"] == "INACTIVE",
        "Agent profile update is persisted",
    )

    foreign_assignment = client.put(
        f"/api/v1/admin/users/{target_user_id}/projects/{foreign_project_id}",
        headers=admin_headers,
        json={
            "role": "AGRONOMIST",
            "territory_scope": {},
            "reason": "foreign project must be rejected",
        },
    )
    check(
        foreign_assignment.status_code == 404,
        "Project access assignment rejects foreign-tenant project",
        foreign_assignment.text,
    )

    assigned = client.put(
        f"/api/v1/admin/users/{target_user_id}/projects/{project_id}",
        headers=admin_headers,
        json={
            "role": "AGRONOMIST",
            "territory_scope": {"village_codes": ["V001"]},
            "reason": "assign identity regression project",
        },
    )
    check(assigned.status_code == 200, "Project access assignment returns 200", assigned.text)
    access = assigned.json()["user"]["project_access"]
    check(len(access) == 1, "Project access assignment creates one active role", access)
    check(access[0]["project_id"] == str(project_id), "Assigned project is tenant scoped")

    revoked = client.request(
        "DELETE",
        f"/api/v1/admin/users/{target_user_id}/projects/{project_id}",
        headers=admin_headers,
        json={"reason": "revoke identity regression project"},
    )
    check(revoked.status_code == 200, "Project access revocation returns 200", revoked.text)
    check(
        revoked.json()["user"]["project_access"] == [],
        "Revoked project access is no longer active",
    )

    verify = SessionLocal()
    try:
        audits = (
            verify.query(TenantUserAccessAuditEvent)
            .filter(TenantUserAccessAuditEvent.tenant_id == tenant_id)
            .order_by(TenantUserAccessAuditEvent.created_at)
            .all()
        )
        actions = [row.action for row in audits]
        for action in (
            "CREATE_AGENT_PROFILE",
            "UPDATE_AGENT_PROFILE",
            "ASSIGN_PROJECT_ACCESS",
            "REVOKE_PROJECT_ACCESS",
        ):
            check(action in actions, f"Audit includes {action}", actions)

        check(
            all(row.actor_id == admin_user_id for row in audits),
            "All identity administration audits record verified administrator",
            [(row.action, str(row.actor_id)) for row in audits],
        )
        check(
            all(row.target_user_id == target_user_id for row in audits),
            "All identity administration audits record target user",
        )

        role = verify.query(ProjectRole).filter(
            ProjectRole.project_id == project_id,
            ProjectRole.user_id == target_user_id,
        ).first()
        check(role is not None and role.is_active is False, "Project role is retained as inactive audit state")
    finally:
        verify.close()

    cleanup = SessionLocal()
    try:
        cleanup.query(TenantUserAccessAuditEvent).filter(
            TenantUserAccessAuditEvent.tenant_id.in_([tenant_id, foreign_tenant_id])
        ).delete(synchronize_session=False)
        cleanup.query(AgentProfile).filter(
            AgentProfile.tenant_id.in_([tenant_id, foreign_tenant_id])
        ).delete(synchronize_session=False)
        cleanup.query(ProjectRole).filter(
            ProjectRole.project_id.in_([project_id, foreign_project_id])
        ).delete(synchronize_session=False)
        cleanup.query(Project).filter(
            Project.id.in_([project_id, foreign_project_id])
        ).delete(synchronize_session=False)
        cleanup.commit()

        for user_id in (viewer_user_id, target_user_id, admin_user_id):
            if user_id:
                delete_test_admin(cleanup, user_id)

        cleanup.query(Tenant).filter(
            Tenant.id.in_([tenant_id, foreign_tenant_id])
        ).delete(synchronize_session=False)
        cleanup.commit()
        check(True, "Temporary identity administration rows cleaned up")
    finally:
        cleanup.close()

    print("=" * 72)
    print("Identity administration authorization validated")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

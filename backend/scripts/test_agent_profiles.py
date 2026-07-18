"""Regression for agent profiles that can coexist with farmer profiles."""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.auth.models import AgentProfile, TenantUserAccessAuditEvent, User
from app.modules.auth.service import create_jwt
from app.modules.farmer.models import Farmer, Project, ProjectRole, Tenant
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin


def now():
    return datetime.now(timezone.utc)


def check(condition, label, payload=None):
    print(f"  {'PASS' if condition else 'FAIL'} {label}")
    if payload is not None:
        print(f"       {payload}")
    if not condition:
        raise AssertionError(label)


def headers_for(user: User, tenant_id: str) -> dict[str, str]:
    token, _ = create_jwt(user, "agent-profile-regression")
    return {"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id, "X-Actor-ID": str(user.id)}


def main():
    print("=" * 72)
    print("AGENT PROFILE REGRESSION")
    print("=" * 72)

    tenant_id = f"agent-profile-{uuid.uuid4().hex[:8]}"
    project_id = uuid.uuid4()
    farmer_id = uuid.uuid4()
    agent_user_id = uuid.uuid4()
    principal = None

    db = SessionLocal()
    try:
        db.add(Tenant(id=tenant_id, name="Agent Profile Tenant", type="ENTERPRISE", created_at=now(), updated_at=now()))
        db.commit()
        principal, admin_headers = create_test_admin(db, role="ENTERPRISE_ADMIN", tenant_id=tenant_id)
        agent_user = User(
            id=agent_user_id,
            mobile_number=f"+9197{uuid.uuid4().int % 100000000:08d}",
            role="AGRONOMIST",
            display_name="Agent Farmer User",
            language_preference="hi",
            tenant_id=tenant_id,
            created_at=now(),
            updated_at=now(),
        )
        db.add(agent_user)
        db.add(Project(
            id=project_id,
            tenant_id=tenant_id,
            name="Agent Profile Project",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=180),
            status="ACTIVE",
            crop_scope=["RICE"],
            geography_scope={},
            config={},
            created_at=now(),
            updated_at=now(),
        ))
        db.flush()
        db.add(Farmer(
            id=farmer_id,
            tenant_id=tenant_id,
            project_id=project_id,
            user_id=agent_user_id,
            mobile_number=agent_user.mobile_number,
            display_name="Agent Personal Farm",
            village_name_manual="Agent Village",
            language_preference="hi",
            total_land_unit="ACRE",
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        ))
        db.add(ProjectRole(
            id=uuid.uuid4(),
            project_id=project_id,
            user_id=agent_user_id,
            role="AGRONOMIST",
            territory_scope={"village_names": ["Agent Village"]},
            created_at=now(),
            updated_at=now(),
        ))
        db.commit()

        client = TestClient(app)
        create = client.post("/api/v1/admin/agent-profiles", headers=admin_headers, json={
            "user_id": str(agent_user_id),
            "farmer_id": str(farmer_id),
            "agent_code": "AGENT-001",
            "role_type": "AGRONOMIST",
            "display_name": "Agent Farmer User",
            "skills": ["CROP_HEALTH", "SOIL_SAMPLING"],
            "languages": ["hi"],
            "territory_scope": {"village_names": ["Agent Village"]},
            "availability": {"mode": "FIELD_VISITS"},
            "certification": {"agronomy": "LEVEL_1"},
            "metadata": {"can_assist_without_farmer_smartphone": True},
            "reason": "Regression agent profile create",
        })
        check(create.status_code == 201, "Create linked agent profile returns 201", create.text)
        body = create.json()
        profile = body["agent_profile"]
        profile_id = profile["id"]
        check(body["created"] is True, "Agent profile create reports created")
        check(profile["user_id"] == str(agent_user_id), "Agent profile preserves user id")
        check(profile["farmer_id"] == str(farmer_id), "Agent profile can link same person farmer profile")
        check(profile["can_also_act_as_farmer"] is True, "Agent profile flags farmer dual-capacity")
        check(profile["farmer"]["id"] == str(farmer_id), "Agent profile embeds farmer context")
        check(profile["project_access"][0]["project_id"] == str(project_id), "Agent profile exposes project access")

        listing = client.get("/api/v1/admin/agent-profiles?role_type=AGRONOMIST&status=ACTIVE", headers=admin_headers)
        check(listing.status_code == 200, "List agent profiles returns 200", listing.text)
        check(listing.json()["schema_version"] == "agent_profiles.v1", "Agent profile list schema stable")
        check(listing.json()["count"] == 1, "List includes one active agronomist")

        update = client.patch(f"/api/v1/admin/agent-profiles/{profile_id}", headers=admin_headers, json={
            "status": "SUSPENDED",
            "skills": ["CROP_HEALTH"],
            "reason": "Regression suspend agent",
        })
        check(update.status_code == 200, "Update agent profile returns 200", update.text)
        check(update.json()["agent_profile"]["status"] == "SUSPENDED", "Agent profile update changes status")

        isolated = client.get(f"/api/v1/admin/agent-profiles/{profile_id}", headers={**admin_headers, "X-Tenant-ID": "default"})
        check(isolated.status_code in {401, 403, 404}, "Agent profile is tenant isolated", isolated.text)

        audit_actions = {row.action for row in db.query(TenantUserAccessAuditEvent).filter(TenantUserAccessAuditEvent.tenant_id == tenant_id, TenantUserAccessAuditEvent.target_user_id == agent_user_id).all()}
        check("CREATE_AGENT_PROFILE" in audit_actions, "Agent profile create is audited")
        check("UPDATE_AGENT_PROFILE" in audit_actions, "Agent profile update is audited")
    finally:
        db.rollback()
        db.query(TenantUserAccessAuditEvent).filter(TenantUserAccessAuditEvent.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(AgentProfile).filter(AgentProfile.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(ProjectRole).filter(ProjectRole.user_id == agent_user_id).delete(synchronize_session=False)
        db.query(Farmer).filter(Farmer.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Project).filter(Project.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(User).filter(User.id == agent_user_id).delete(synchronize_session=False)
        if principal:
            delete_test_admin(db, principal.id)
        db.query(Tenant).filter(Tenant.id == tenant_id).delete(synchronize_session=False)
        db.commit()
        db.close()

    print("=" * 72)
    print("Agent profiles validated")
    print("=" * 72)


if __name__ == "__main__":
    main()

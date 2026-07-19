"""Regression for Android post-login mode bootstrap."""

import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.auth.models import AgentProfile, User
from app.modules.auth.service import create_jwt
from app.modules.farmer.models import Farmer, Project, ProjectRole, Tenant


def now():
    return datetime.now(timezone.utc)


def check(condition, label, payload=None):
    if not condition:
        print(f"  FAIL {label}")
        if payload is not None:
            print(f"       {payload}")
        raise AssertionError(label)
    print(f"  PASS {label}")
    if payload is not None:
        print(f"       {payload}")


def bearer(user: User) -> str:
    token, _ = create_jwt(user, "mode-bootstrap-regression")
    return f"Bearer {token}"


def main():
    print("=" * 72)
    print("AUTH MODE BOOTSTRAP REGRESSION")
    print("=" * 72)

    tenant_id = f"mode-bootstrap-{uuid.uuid4().hex[:8]}"
    project_id = uuid.uuid4()
    farmer_user_id = uuid.uuid4()
    agent_user_id = uuid.uuid4()
    dual_user_id = uuid.uuid4()
    farmer_id = uuid.uuid4()
    dual_farmer_id = uuid.uuid4()

    db = SessionLocal()
    try:
        db.add(Tenant(id=tenant_id, name="Mode Bootstrap Tenant", type="ENTERPRISE", created_at=now(), updated_at=now()))
        db.add(Project(
            id=project_id,
            tenant_id=tenant_id,
            name="Mode Bootstrap Project",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=180),
            status="ACTIVE",
            geography_scope={},
            crop_scope=["RICE"],
            config={},
            created_at=now(),
            updated_at=now(),
        ))
        farmer_user = User(id=farmer_user_id, mobile_number=f"+9191{uuid.uuid4().int % 100000000:08d}", role="FARMER", tenant_id=tenant_id, display_name="Farmer Only", language_preference="hi", created_at=now(), updated_at=now())
        agent_user = User(id=agent_user_id, mobile_number=f"+9192{uuid.uuid4().int % 100000000:08d}", role="AGRONOMIST", tenant_id=tenant_id, display_name="Agent Only", language_preference="en", created_at=now(), updated_at=now())
        dual_user = User(id=dual_user_id, mobile_number=f"+9193{uuid.uuid4().int % 100000000:08d}", role="AGRONOMIST", tenant_id=tenant_id, display_name="Dual User", language_preference="hi", created_at=now(), updated_at=now())
        db.add_all([farmer_user, agent_user, dual_user])
        db.flush()
        db.add(Farmer(id=farmer_id, tenant_id=tenant_id, project_id=project_id, user_id=farmer_user_id, mobile_number=farmer_user.mobile_number, display_name="Farmer Only Farm", village_name_manual="Mode Village", total_land_unit="ACRE", status="ACTIVE", created_at=now(), updated_at=now()))
        db.add(Farmer(id=dual_farmer_id, tenant_id=tenant_id, project_id=project_id, user_id=dual_user_id, mobile_number=dual_user.mobile_number, display_name="Dual Personal Farm", village_name_manual="Mode Village", total_land_unit="ACRE", status="ACTIVE", created_at=now(), updated_at=now()))
        db.flush()
        db.add(AgentProfile(id=uuid.uuid4(), tenant_id=tenant_id, user_id=agent_user_id, agent_code="AGENT-ONLY", role_type="AGRONOMIST", display_name="Agent Only", mobile_number=agent_user.mobile_number, status="ACTIVE", skills=["SOIL"], languages=["en"], territory_scope={"village_names": ["Mode Village"]}, availability={}, certification={}, metadata_={}, created_at=now(), updated_at=now()))
        db.add(AgentProfile(id=uuid.uuid4(), tenant_id=tenant_id, user_id=dual_user_id, farmer_id=dual_farmer_id, agent_code="DUAL-1", role_type="FIELD_AGENT", display_name="Dual User", mobile_number=dual_user.mobile_number, status="ACTIVE", skills=["CROP_HEALTH"], languages=["hi"], territory_scope={"village_names": ["Mode Village"]}, availability={}, certification={}, metadata_={}, created_at=now(), updated_at=now()))
        db.add(ProjectRole(id=uuid.uuid4(), project_id=project_id, user_id=agent_user_id, role="AGRONOMIST", territory_scope={"village_names": ["Mode Village"]}, created_at=now(), updated_at=now()))
        db.add(ProjectRole(id=uuid.uuid4(), project_id=project_id, user_id=dual_user_id, role="FIELD_AGENT", territory_scope={"village_names": ["Mode Village"]}, created_at=now(), updated_at=now()))
        db.commit()

        client = TestClient(app)
        farmer_boot = client.get("/api/v1/auth/mode-bootstrap", headers={"Authorization": bearer(farmer_user), "X-Tenant-ID": tenant_id})
        check(farmer_boot.status_code == 200, "Farmer-only mode bootstrap returns 200", farmer_boot.text)
        farmer_body = farmer_boot.json()
        check(farmer_body["schema_version"] == "auth_mode_bootstrap.v1", "Mode bootstrap schema stable")
        check(farmer_body["modes"]["farmer"]["available"] is True, "Farmer mode available for farmer user")
        check(farmer_body["modes"]["agent"]["available"] is False, "Agent mode unavailable for farmer-only user")
        check(farmer_body["first_screen_hint"] == "FARMER_HOME", "Farmer-only bootstrap points to farmer home")
        check(farmer_body["farmer_profile"]["id"] == str(farmer_id), "Farmer bootstrap links farmer profile")

        agent_boot = client.get("/api/v1/auth/mode-bootstrap", headers={"Authorization": bearer(agent_user), "X-Tenant-ID": tenant_id})
        check(agent_boot.status_code == 200, "Agent-only mode bootstrap returns 200", agent_boot.text)
        agent_body = agent_boot.json()
        check(agent_body["modes"]["agent"]["available"] is True, "Agent mode available for agent user")
        check(agent_body["modes"]["farmer"]["available"] is False, "Farmer mode unavailable for agent-only user")
        check(agent_body["first_screen_hint"] == "AGENT_WORKLIST", "Agent-only bootstrap points to agent worklist")
        check(agent_body["agent_profile"]["user_id"] == str(agent_user_id), "Agent bootstrap links agent profile")
        check(agent_body["project_access"][0]["project_id"] == str(project_id), "Agent bootstrap includes assigned projects")
        check(agent_body["endpoints"]["agent_worklist"].startswith("/api/v1/field-agent/worklist"), "Agent bootstrap returns worklist endpoint")

        dual_boot = client.get("/api/v1/auth/mode-bootstrap", headers={"Authorization": bearer(dual_user), "X-Tenant-ID": tenant_id})
        check(dual_boot.status_code == 200, "Dual mode bootstrap returns 200", dual_boot.text)
        dual_body = dual_boot.json()
        check(dual_body["modes"]["farmer"]["available"] is True, "Dual user has farmer mode")
        check(dual_body["modes"]["agent"]["available"] is True, "Dual user has agent mode")
        check(dual_body["first_screen_hint"] == "MODE_CHOOSER", "Dual bootstrap points to mode chooser")
        check(dual_body["modes"]["farmer"]["farmer_id"] == str(dual_farmer_id), "Dual bootstrap returns personal farmer id")
        check(dual_body["agent_profile"]["can_also_act_as_farmer"] is True, "Dual bootstrap flags linked farmer mode")

        query_boot = client.get(f"/api/v1/auth/mode-bootstrap?user_id={dual_user_id}", headers={"X-Tenant-ID": tenant_id})
        check(query_boot.status_code == 200, "Mode bootstrap supports user_id query fallback for dev/test", query_boot.text)
        check(query_boot.json()["first_screen_hint"] == "MODE_CHOOSER", "Query fallback returns same mode hint")

        isolated = client.get("/api/v1/auth/mode-bootstrap", headers={"Authorization": bearer(dual_user), "X-Tenant-ID": "default"})
        check(isolated.status_code == 403, "Mode bootstrap is tenant isolated", isolated.text)
    finally:
        db.rollback()
        db.query(AgentProfile).filter(AgentProfile.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(ProjectRole).filter(ProjectRole.project_id == project_id).delete(synchronize_session=False)
        db.query(Farmer).filter(Farmer.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_([farmer_user_id, agent_user_id, dual_user_id])).delete(synchronize_session=False)
        db.query(Project).filter(Project.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Tenant).filter(Tenant.id == tenant_id).delete(synchronize_session=False)
        db.commit()
        db.close()
        check(True, "Temporary rows cleaned up")

    print("=" * 72)
    print("Auth mode bootstrap validated")
    print("=" * 72)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Direct HTTP behavior for authenticated query-thread mutations."""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.auth.models import AgentProfile
from app.modules.farmer.models import (
    Farmer,
    FarmerProjectEnrollment,
    Parcel,
    Project,
    ProjectRole,
    Tenant,
)
from app.modules.media.models import (
    MediaAsset,
    MediaAttachment,
    QueryMessage,
    QueryThread,
    QueryThreadAudit,
)
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin


def now():
    return datetime.now(timezone.utc)


def require(condition, label, detail=None):
    if not condition:
        if detail is not None:
            print(detail)
        raise AssertionError(label)
    print(f"PASS {label}")


def make_farmer(tenant_id, project_id, name, user_id=None):
    return Farmer(
        id=uuid.uuid4(), tenant_id=tenant_id, project_id=project_id,
        user_id=user_id, mobile_number=f"+9194{uuid.uuid4().int % 100000000:08d}",
        display_name=name, village_name_manual="Query Persona Village",
        status="ACTIVE", is_active=True, created_at=now(), updated_at=now(),
    )


def make_asset(tenant_id, project_id, farmer_id, uploaded_by, suffix):
    return MediaAsset(
        id=uuid.uuid4(), tenant_id=tenant_id, project_id=project_id,
        farmer_id=farmer_id, uploaded_by=uploaded_by, media_type="AUDIO",
        mime_type="audio/mpeg", upload_status="UPLOADED",
        storage_key=f"queries/{suffix}.mp3", metadata_={},
        created_at=now(), updated_at=now(),
    )


def create_body(project_id, farmer_id, parcel_id, asset_id, sender_type, sender_id, subject):
    return {
        "project_id": str(project_id), "farmer_id": str(farmer_id),
        "parcel_id": str(parcel_id), "subject": subject,
        "category": "CROP_HEALTH", "priority": "HIGH",
        "initial_message": {
            "sender_type": sender_type, "sender_id": str(sender_id),
            "message_type": "AUDIO", "body_text": subject,
            "media_attachments": [{"media_asset_id": str(asset_id), "purpose": "AUDIO_NOTE"}],
        },
    }


def main():
    tenant_id = f"query-persona-{uuid.uuid4().hex[:8]}"
    project_id = uuid.uuid4()
    created_user_ids = []
    db = SessionLocal()
    db.expire_on_commit = False
    try:
        db.add(Tenant(id=tenant_id, name="Query Persona Tenant", type="ENTERPRISE", created_at=now(), updated_at=now()))
        db.commit()
        farmer_user, farmer_headers = create_test_admin(db, tenant_id=tenant_id, role="FARMER")
        agent_user, agent_headers = create_test_admin(db, tenant_id=tenant_id, role="FIELD_AGENT")
        unassigned_user, unassigned_headers = create_test_admin(db, tenant_id=tenant_id, role="FIELD_AGENT")
        admin_user, admin_headers = create_test_admin(db, tenant_id=tenant_id, role="ENTERPRISE_ADMIN")
        created_user_ids.extend([farmer_user.id, agent_user.id, unassigned_user.id, admin_user.id])

        project = Project(
            id=project_id, tenant_id=tenant_id, name="Query Persona Project",
            start_date=date.today(), end_date=date.today() + timedelta(days=180),
            status="ACTIVE", geography_scope={}, crop_scope=["RICE"], config={},
            is_active=True, created_at=now(), updated_at=now(),
        )
        db.add(project)
        db.flush()
        personal = make_farmer(tenant_id, project_id, "Personal Query Farmer", farmer_user.id)
        assisted = make_farmer(tenant_id, project_id, "Assisted Query Farmer")
        unrelated = make_farmer(tenant_id, project_id, "Unrelated Query Farmer")
        db.add_all([personal, assisted, unrelated])
        db.flush()
        personal_parcel = Parcel(
            id=uuid.uuid4(), tenant_id=tenant_id, farmer_id=personal.id,
            project_id=project_id, village_name_manual="Query Persona Village",
            reported_area=1, reported_area_unit="ACRE", survey_number="QUERY-PERSONAL",
            ownership_type="OWNED", status="ACTIVE", is_active=True,
            created_at=now(), updated_at=now(),
        )
        assisted_parcel = Parcel(
            id=uuid.uuid4(), tenant_id=tenant_id, farmer_id=assisted.id,
            project_id=project_id, village_name_manual="Query Persona Village",
            reported_area=1, reported_area_unit="ACRE", survey_number="QUERY-ASSISTED",
            ownership_type="OWNED", status="ACTIVE", is_active=True,
            created_at=now(), updated_at=now(),
        )
        db.add_all([personal_parcel, assisted_parcel])
        db.add_all([
            AgentProfile(
                id=uuid.uuid4(), tenant_id=tenant_id, user_id=agent_user.id,
                agent_code="QUERY-AGENT", role_type="FIELD_AGENT", display_name="Query Agent",
                mobile_number=agent_user.mobile_number, status="ACTIVE", skills=[], languages=["en"],
                territory_scope={}, availability={}, certification={}, metadata_={},
                is_active=True, created_at=now(), updated_at=now(),
            ),
            AgentProfile(
                id=uuid.uuid4(), tenant_id=tenant_id, user_id=unassigned_user.id,
                agent_code="QUERY-UNASSIGNED", role_type="FIELD_AGENT", display_name="Unassigned Query Agent",
                mobile_number=unassigned_user.mobile_number, status="ACTIVE", skills=[], languages=["en"],
                territory_scope={}, availability={}, certification={}, metadata_={},
                is_active=True, created_at=now(), updated_at=now(),
            ),
        ])
        db.add_all([
            ProjectRole(id=uuid.uuid4(), project_id=project_id, user_id=agent_user.id, role="FIELD_AGENT", territory_scope={}, is_active=True, created_at=now(), updated_at=now()),
            ProjectRole(id=uuid.uuid4(), project_id=project_id, user_id=unassigned_user.id, role="FIELD_AGENT", territory_scope={}, is_active=True, created_at=now(), updated_at=now()),
        ])
        db.add(FarmerProjectEnrollment(
            id=uuid.uuid4(), tenant_id=tenant_id, farmer_id=assisted.id,
            project_id=project_id, enrollment_method="ASSISTED",
            enrollment_source="QUERY_PERSONA_REGRESSION", status="ACTIVE",
            parcel_ids=[str(assisted_parcel.id)], assigned_user_ids=[str(agent_user.id)],
            metadata_={}, is_active=True, created_at=now(), updated_at=now(),
        ))
        personal_asset = make_asset(tenant_id, project_id, personal.id, farmer_user.id, "personal")
        assisted_asset = make_asset(tenant_id, project_id, assisted.id, agent_user.id, "assisted")
        db.add_all([personal_asset, assisted_asset])
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    try:
        farmer_create = client.post("/api/v1/query-threads", headers=farmer_headers, json=create_body(project_id, personal.id, personal_parcel.id, personal_asset.id, "FARMER", farmer_user.id, "Personal farmer question"))
        require(farmer_create.status_code == 201, "Farmer creates a personal query thread", farmer_create.text)
        farmer_thread_id = farmer_create.json()["id"]
        require(farmer_create.json()["messages"][0]["sender_id"] == str(farmer_user.id), "Farmer message records authenticated user")
        require(farmer_create.json()["messages"][0]["sender_type"] == "FARMER", "Farmer message records resolved persona")

        agent_create = client.post("/api/v1/query-threads", headers=agent_headers, json=create_body(project_id, assisted.id, assisted_parcel.id, assisted_asset.id, "FIELD_AGENT", agent_user.id, "Assigned agent question"))
        require(agent_create.status_code == 201, "Assigned agent creates an assisted-farmer query", agent_create.text)
        agent_thread_id = agent_create.json()["id"]
        require(agent_create.json()["messages"][0]["sender_id"] == str(agent_user.id), "Agent message records authenticated user")
        require(agent_create.json()["messages"][0]["sender_type"] == "FIELD_AGENT", "Agent message records resolved persona")

        missing_list = client.get(
            "/api/v1/query-threads",
            headers={"X-Tenant-ID": tenant_id},
        )
        require(missing_list.status_code == 401, "Query list rejects missing bearer", missing_list.text)

        farmer_list = client.get("/api/v1/query-threads", headers=farmer_headers)
        require(farmer_list.status_code == 200, "Farmer lists visible query threads", farmer_list.text)
        require(
            {row["id"] for row in farmer_list.json()["threads"]} == {farmer_thread_id},
            "Farmer list is restricted to personal farmer",
            farmer_list.text,
        )
        farmer_detail = client.get(f"/api/v1/query-threads/{farmer_thread_id}", headers=farmer_headers)
        require(farmer_detail.status_code == 200, "Farmer reads personal query detail", farmer_detail.text)
        require(len(farmer_detail.json()["messages"]) == 1, "Farmer detail includes personal messages")
        farmer_assisted_list = client.get(
            "/api/v1/query-threads",
            headers=farmer_headers,
            params={"farmer_id": str(assisted.id)},
        )
        require(
            farmer_assisted_list.status_code == 200 and farmer_assisted_list.json()["count"] == 0,
            "Farmer cannot discover assisted-farmer queries in list",
            farmer_assisted_list.text,
        )
        farmer_assisted_detail = client.get(f"/api/v1/query-threads/{agent_thread_id}", headers=farmer_headers)
        require(farmer_assisted_detail.status_code == 404, "Farmer cannot discover assisted-farmer query detail", farmer_assisted_detail.text)

        agent_list = client.get("/api/v1/query-threads", headers=agent_headers)
        require(agent_list.status_code == 200, "Assigned agent lists visible query threads", agent_list.text)
        require(
            {row["id"] for row in agent_list.json()["threads"]} == {agent_thread_id},
            "Agent list is restricted to assigned farmer",
            agent_list.text,
        )
        agent_detail = client.get(f"/api/v1/query-threads/{agent_thread_id}", headers=agent_headers)
        require(agent_detail.status_code == 200, "Assigned agent reads assisted-farmer query detail", agent_detail.text)
        agent_personal_detail = client.get(f"/api/v1/query-threads/{farmer_thread_id}", headers=agent_headers)
        require(agent_personal_detail.status_code == 404, "Assigned agent cannot discover unrelated farmer query", agent_personal_detail.text)

        unassigned_list = client.get("/api/v1/query-threads", headers=unassigned_headers)
        require(
            unassigned_list.status_code == 200 and unassigned_list.json()["count"] == 0,
            "Unassigned agent receives an empty query list",
            unassigned_list.text,
        )
        unassigned_detail = client.get(f"/api/v1/query-threads/{agent_thread_id}", headers=unassigned_headers)
        require(unassigned_detail.status_code == 404, "Unassigned agent cannot discover query detail", unassigned_detail.text)

        admin_list = client.get("/api/v1/query-threads", headers=admin_headers)
        require(admin_list.status_code == 200, "Web administrator lists tenant query threads", admin_list.text)
        require(
            {row["id"] for row in admin_list.json()["threads"]} == {farmer_thread_id, agent_thread_id},
            "Web administrator sees both operational farmer scopes",
            admin_list.text,
        )
        admin_detail = client.get(f"/api/v1/query-threads/{agent_thread_id}", headers=admin_headers)
        require(admin_detail.status_code == 200, "Web administrator reads tenant query detail", admin_detail.text)

        read_tenant_mismatch = client.get(
            "/api/v1/query-threads",
            headers={**farmer_headers, "X-Tenant-ID": "default"},
        )
        require(read_tenant_mismatch.status_code == 403, "Query list rejects token/header tenant mismatch", read_tenant_mismatch.text)

        impersonation = client.post("/api/v1/query-threads", headers=farmer_headers, json=create_body(project_id, personal.id, personal_parcel.id, personal_asset.id, "FARMER", agent_user.id, "Impersonated question"))
        require(impersonation.status_code == 403, "Farmer cannot impersonate another sender", impersonation.text)

        unassigned_create = client.post("/api/v1/query-threads", headers=unassigned_headers, json=create_body(project_id, assisted.id, assisted_parcel.id, assisted_asset.id, "FIELD_AGENT", unassigned_user.id, "Unassigned question"))
        require(unassigned_create.status_code == 403, "Unassigned agent cannot create assisted-farmer query", unassigned_create.text)

        cross_asset = client.post("/api/v1/query-threads", headers=farmer_headers, json=create_body(project_id, personal.id, personal_parcel.id, assisted_asset.id, "FARMER", farmer_user.id, "Cross farmer asset"))
        require(cross_asset.status_code == 403, "Cross-farmer inline query asset is rejected", cross_asset.text)

        farmer_reply = client.post(f"/api/v1/query-threads/{farmer_thread_id}/messages", headers=farmer_headers, json={"sender_type": "FARMER", "sender_id": str(farmer_user.id), "message_type": "TEXT", "body_text": "Farmer follow-up"})
        require(farmer_reply.status_code == 201, "Farmer adds a message to personal thread", farmer_reply.text)

        agent_reply = client.post(f"/api/v1/query-threads/{agent_thread_id}/messages", headers=agent_headers, json={"sender_type": "FIELD_AGENT", "sender_id": str(agent_user.id), "message_type": "TEXT", "body_text": "Assigned agent response"})
        require(agent_reply.status_code == 201, "Assigned agent replies on assisted-farmer thread", agent_reply.text)

        unrelated_reply = client.post(f"/api/v1/query-threads/{farmer_thread_id}/messages", headers=agent_headers, json={"sender_type": "FIELD_AGENT", "sender_id": str(agent_user.id), "message_type": "TEXT", "body_text": "Unrelated response"})
        require(unrelated_reply.status_code == 403, "Assigned agent cannot reply outside farmer assignment", unrelated_reply.text)

        farmer_status = client.patch(f"/api/v1/query-threads/{farmer_thread_id}/status", headers=farmer_headers, json={"status": "CLOSED", "reason": "Farmer close"})
        require(farmer_status.status_code == 403, "Farmer cannot perform query workflow transition", farmer_status.text)

        unassigned_status = client.patch(f"/api/v1/query-threads/{agent_thread_id}/status", headers=unassigned_headers, json={"status": "CLOSED", "reason": "Unassigned close"})
        require(unassigned_status.status_code == 403, "Unassigned agent cannot change assisted query status", unassigned_status.text)

        agent_assignment = client.patch(f"/api/v1/query-threads/{agent_thread_id}/status", headers=agent_headers, json={"status": "ANSWERED", "assigned_to": str(agent_user.id), "reason": "Self assignment"})
        require(agent_assignment.status_code == 403, "Assigned agent cannot change query assignment", agent_assignment.text)

        agent_status = client.patch(f"/api/v1/query-threads/{agent_thread_id}/status", headers=agent_headers, json={"status": "CLOSED", "reason": "Resolved in field"})
        require(agent_status.status_code == 200, "Assigned agent closes assisted-farmer query", agent_status.text)
        history = agent_status.json()["metadata"]["status_history"][-1]
        require(history["actor_user_id"] == str(agent_user.id), "Query status history records authenticated agent")
        require(history["actor_type"] == "FIELD_AGENT", "Query status history records resolved agent persona")

        admin_status = client.patch(f"/api/v1/query-threads/{farmer_thread_id}/status", headers=admin_headers, json={"status": "ASSIGNED", "assigned_to": str(agent_user.id), "reason": "Administrative assignment"})
        require(admin_status.status_code == 200, "Web administrator assigns query thread", admin_status.text)
        require(admin_status.json()["assigned_to"] == str(agent_user.id), "Administrative assignment is persisted")

        print({
            "schema_version": "query_thread_persona_behavior.v1",
            "farmer_create": True, "assigned_agent_create": True,
            "farmer_read_scope": True, "assigned_agent_read_scope": True,
            "unassigned_read_denied": True, "admin_tenant_read": True,
            "sender_impersonation_denied": True, "unassigned_denied": True,
            "cross_farmer_asset_denied": True, "farmer_reply": True,
            "assigned_agent_reply": True, "farmer_status_denied": True,
            "assigned_agent_status": True, "admin_assignment": True,
        })
        print("QUERY THREAD PERSONA BEHAVIOR PASSED")
    finally:
        cleanup = SessionLocal()
        try:
            cleanup.query(MediaAttachment).filter(MediaAttachment.tenant_id == tenant_id).delete(synchronize_session=False)
            cleanup.query(QueryThreadAudit).filter(QueryThreadAudit.tenant_id == tenant_id).delete(synchronize_session=False)
            cleanup.query(QueryMessage).filter(QueryMessage.tenant_id == tenant_id).delete(synchronize_session=False)
            cleanup.query(QueryThread).filter(QueryThread.tenant_id == tenant_id).delete(synchronize_session=False)
            cleanup.query(MediaAsset).filter(MediaAsset.tenant_id == tenant_id).delete(synchronize_session=False)
            cleanup.query(Parcel).filter(Parcel.tenant_id == tenant_id).delete(synchronize_session=False)
            cleanup.query(FarmerProjectEnrollment).filter(FarmerProjectEnrollment.tenant_id == tenant_id).delete(synchronize_session=False)
            cleanup.query(Farmer).filter(Farmer.tenant_id == tenant_id).delete(synchronize_session=False)
            cleanup.query(ProjectRole).filter(ProjectRole.project_id == project_id).delete(synchronize_session=False)
            cleanup.query(AgentProfile).filter(AgentProfile.tenant_id == tenant_id).delete(synchronize_session=False)
            cleanup.query(Project).filter(Project.tenant_id == tenant_id).delete(synchronize_session=False)
            cleanup.commit()
            for user_id in created_user_ids:
                delete_test_admin(cleanup, user_id)
            cleanup.query(Tenant).filter(Tenant.id == tenant_id).delete(synchronize_session=False)
            cleanup.commit()
            print("PASS Query persona rows are cleaned")
        finally:
            cleanup.close()


if __name__ == "__main__":
    main()

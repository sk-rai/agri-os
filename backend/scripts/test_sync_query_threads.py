"""Regression for query thread/message sync materialization."""

from datetime import date, datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Farmer, Parcel, Project, Tenant
from app.modules.media.models import MediaAsset, MediaAttachment, QueryMessage, QueryThread, QueryThreadAudit


def now():
    return datetime.now(timezone.utc)


def check(condition, label, detail=None):
    print(f"  {'PASS' if condition else 'FAIL'} {label}")
    if detail is not None:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(label)


def sync_event(entity_type, entity_id, payload):
    return {
        "event_id": str(uuid.uuid4()),
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "operation": "CREATE",
        "payload": payload,
        "version": 1,
        "dependency_ids": [],
        "metadata": {},
    }


def main():
    print("=" * 72)
    print("SYNC QUERY THREAD MATERIALIZATION REGRESSION")
    print("=" * 72)

    tenant_id = f"sync-query-{uuid.uuid4().hex[:8]}"
    project_id = uuid.uuid4()
    farmer_id = uuid.uuid4()
    parcel_id = uuid.uuid4()
    thread_id = uuid.uuid4()
    message_id = uuid.uuid4()
    reply_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    audio_asset_id = uuid.uuid4()
    headers = {"X-Tenant-ID": tenant_id, "X-Actor-ID": str(actor_id)}

    db = SessionLocal()
    try:
        db.add(Tenant(id=tenant_id, name="Sync Query Tenant", type="ENTERPRISE", created_at=now(), updated_at=now()))
        db.flush()
        db.add(Project(id=project_id, tenant_id=tenant_id, name="Sync Query Project", start_date=date(2026, 7, 1), end_date=date(2026, 12, 31), status="PLANNED", crop_scope=["RICE"], geography_scope={}, created_at=now(), updated_at=now()))
        db.flush()
        db.add(Farmer(id=farmer_id, tenant_id=tenant_id, project_id=project_id, mobile_number=f"+9194{uuid.uuid4().int % 100000000:08d}", display_name="Sync Query Farmer", village_name_manual="Sync Village", status="ACTIVE", created_at=now(), updated_at=now()))
        db.flush()
        db.add(Parcel(id=parcel_id, tenant_id=tenant_id, farmer_id=farmer_id, project_id=project_id, village_name_manual="Sync Village", reported_area=1, reported_area_unit="ACRE", survey_number="SYNC-Q-1", ownership_type="OWNED", status="ACTIVE", created_at=now(), updated_at=now()))
        db.flush()
        db.add(MediaAsset(id=audio_asset_id, tenant_id=tenant_id, project_id=project_id, farmer_id=farmer_id, uploaded_by=farmer_id, media_type="AUDIO", mime_type="audio/mpeg", upload_status="UPLOADED", storage_key="queries/sync-audio.mp3", created_at=now(), updated_at=now()))
        db.commit()
    finally:
        db.close()

    client = TestClient(app)

    print("\n[1] Sync creates query thread")
    create_thread = client.post("/api/v1/sync/events", headers=headers, json={"events": [sync_event("QUERY_THREAD", thread_id, {
        "id": str(thread_id),
        "project_id": str(project_id),
        "farmer_id": str(farmer_id),
        "parcel_id": str(parcel_id),
        "stage_code": "TILLERING",
        "subject": "Offline farmer question",
        "category": "CROP_HEALTH",
        "priority": "HIGH",
        "status": "OPEN",
        "metadata": {"source": "android_sync"},
    })]})
    check(create_thread.status_code == 200, "Sync query thread returns 200", create_thread.text)
    check(len(create_thread.json().get("accepted", [])) == 1, "Query thread event accepted", create_thread.json())

    print("\n[2] Sync creates farmer audio message")
    create_message = client.post("/api/v1/sync/events", headers=headers, json={"events": [sync_event("QUERY_MESSAGE", message_id, {
        "id": str(message_id),
        "thread_id": str(thread_id),
        "sender_type": "FARMER",
        "sender_id": str(farmer_id),
        "message_type": "AUDIO",
        "body_text": "Audio question created offline.",
        "media_attachments": [{"media_asset_id": str(audio_asset_id), "purpose": "AUDIO_NOTE", "caption": "Offline audio"}],
    })]})
    check(create_message.status_code == 200, "Sync query message returns 200", create_message.text)
    check(len(create_message.json().get("accepted", [])) == 1, "Query message event accepted", create_message.json())

    print("\n[3] Sync creates agronomist reply")
    create_reply = client.post("/api/v1/sync/events", headers=headers, json={"events": [sync_event("QUERY_MESSAGE", reply_id, {
        "id": str(reply_id),
        "thread_id": str(thread_id),
        "sender_type": "AGRONOMIST",
        "sender_id": str(actor_id),
        "message_type": "TEXT",
        "body_text": "Synced reply from field staff.",
    })]})
    check(create_reply.status_code == 200, "Sync query reply returns 200", create_reply.text)
    check(len(create_reply.json().get("accepted", [])) == 1, "Query reply event accepted", create_reply.json())

    detail = client.get(f"/api/v1/query-threads/{thread_id}", headers=headers)
    check(detail.status_code == 200, "Query detail returns synced thread", detail.text)
    body = detail.json()
    check(body["id"] == str(thread_id), "Thread id preserved")
    check(body["status"] == "ANSWERED", "Agronomist sync reply marks thread answered")
    check(len(body["messages"]) == 2, "Synced messages are returned")
    check(body["messages"][0]["media_attachment_count"] == 1, "Synced audio attachment counted")
    check(body["messages"][0]["media_attachments"][0]["asset"]["media_type"] == "AUDIO", "Synced audio asset embedded")
    actions = [event["action"] for event in body.get("audit_events", [])]
    check("SYNC_CREATE_THREAD" in actions, "Audit includes sync thread create")
    check("SYNC_ADD_MESSAGE" in actions, "Audit includes sync message create")

    print("\n[4] Cleanup")
    db = SessionLocal()
    try:
        db.query(MediaAttachment).filter(MediaAttachment.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(MediaAsset).filter(MediaAsset.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(QueryThreadAudit).filter(QueryThreadAudit.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(QueryMessage).filter(QueryMessage.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(QueryThread).filter(QueryThread.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Parcel).filter(Parcel.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Farmer).filter(Farmer.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Project).filter(Project.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Tenant).filter(Tenant.id == tenant_id).delete(synchronize_session=False)
        db.commit()
        check(True, "Temporary rows cleaned up")
    finally:
        db.close()

    print("=" * 72)
    print("Sync query thread materialization validated")
    print("=" * 72)


if __name__ == "__main__":
    main()
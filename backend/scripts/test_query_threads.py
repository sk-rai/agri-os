"""Regression for farmer query thread/message APIs."""

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


def main():
    print("=" * 72)
    print("QUERY THREAD REGRESSION")
    print("=" * 72)

    tenant_id = f"query-test-{uuid.uuid4().hex[:8]}"
    project_id = uuid.uuid4()
    farmer_id = uuid.uuid4()
    parcel_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    audio_asset_id = uuid.uuid4()
    headers = {"X-Tenant-ID": tenant_id}

    db = SessionLocal()
    try:
        db.add(Tenant(id=tenant_id, name="Query Test Tenant", type="ENTERPRISE", created_at=now(), updated_at=now()))
        db.flush()
        db.add(Project(id=project_id, tenant_id=tenant_id, name="Query Test Project", start_date=date(2026, 7, 1), end_date=date(2026, 12, 31), status="PLANNED", crop_scope=["RICE"], geography_scope={}, created_at=now(), updated_at=now()))
        db.flush()
        db.add(Farmer(id=farmer_id, tenant_id=tenant_id, project_id=project_id, mobile_number=f"+9195{uuid.uuid4().int % 100000000:08d}", display_name="Query Farmer", village_name_manual="Query Village", status="ACTIVE", created_at=now(), updated_at=now()))
        db.flush()
        db.add(Parcel(id=parcel_id, tenant_id=tenant_id, farmer_id=farmer_id, project_id=project_id, village_name_manual="Query Village", reported_area=1, reported_area_unit="ACRE", survey_number="QUERY-1", ownership_type="OWNED", status="ACTIVE", created_at=now(), updated_at=now()))
        db.flush()
        db.add(MediaAsset(id=audio_asset_id, tenant_id=tenant_id, project_id=project_id, farmer_id=farmer_id, uploaded_by=actor_id, media_type="AUDIO", mime_type="audio/mpeg", upload_status="UPLOADED", storage_key="queries/audio-note.mp3", created_at=now(), updated_at=now()))
        db.commit()
    finally:
        db.close()

    client = TestClient(app)

    print("\n[1] Create thread with farmer audio initial message")
    create = client.post("/api/v1/query-threads", headers=headers, json={
        "project_id": str(project_id),
        "farmer_id": str(farmer_id),
        "parcel_id": str(parcel_id),
        "stage_code": "TILLERING",
        "subject": "Leaves turning yellow",
        "category": "crop_health",
        "priority": "high",
        "metadata": {"source": "android"},
        "initial_message": {
            "sender_type": "farmer",
            "sender_id": str(farmer_id),
            "message_type": "audio",
            "body_text": "Please listen to the attached audio note.",
            "media_attachments": [{"media_asset_id": str(audio_asset_id), "purpose": "AUDIO_NOTE", "caption": "Farmer question audio", "is_primary": True}],
        },
    })
    check(create.status_code == 201, "Create query thread returns 201", create.text)
    thread = create.json()
    thread_id = thread["id"]
    check(thread["category"] == "CROP_HEALTH", "Category normalized")
    check(thread["priority"] == "HIGH", "Priority normalized")
    check(thread["message_count"] == 1, "Initial message counted")
    check(thread["messages"][0]["media_attachment_count"] == 1, "Initial message media counted")
    check(thread["messages"][0]["media_attachments"][0]["asset"]["media_type"] == "AUDIO", "Initial message embeds audio")

    print("\n[2] List and detail")
    listing = client.get(f"/api/v1/query-threads?project_id={project_id}&status=OPEN&category=CROP_HEALTH", headers=headers)
    check(listing.status_code == 200, "List query threads returns 200", listing.text)
    check(listing.json()["count"] == 1, "Filtered list returns one thread")
    detail = client.get(f"/api/v1/query-threads/{thread_id}", headers=headers)
    check(detail.status_code == 200, "Query thread detail returns 200", detail.text)
    detail_body = detail.json()
    check(len(detail_body["messages"]) == 1, "Detail includes messages")
    check(detail_body["media_attachment_count"] == 1, "Detail aggregates message attachments")
    audit_actions = [event["action"] for event in detail_body.get("audit_events", [])]
    check("CREATE_THREAD" in audit_actions, "Audit includes thread creation")

    print("\n[3] Add agronomist text reply")
    reply = client.post(f"/api/v1/query-threads/{thread_id}/messages", headers=headers, json={
        "sender_type": "AGRONOMIST",
        "sender_id": str(actor_id),
        "message_type": "TEXT",
        "body_text": "Please check for nitrogen deficiency and share one leaf photo.",
    })
    check(reply.status_code == 201, "Add query reply returns 201", reply.text)
    check(reply.json()["sender_type"] == "AGRONOMIST", "Reply sender type stored")
    updated = client.get(f"/api/v1/query-threads/{thread_id}", headers=headers).json()
    check(updated["status"] == "ANSWERED", "Agronomist reply marks open thread answered")
    check(len(updated["messages"]) == 2, "Detail includes reply")
    audit_actions = [event["action"] for event in updated.get("audit_events", [])]
    check("ADD_MESSAGE" in audit_actions, "Audit includes admin/agronomist reply")

    print("\n[4] Status transition and isolation")
    status = client.patch(f"/api/v1/query-threads/{thread_id}/status", headers=headers, json={"status": "CLOSED", "reason": "Resolved by agronomist"})
    check(status.status_code == 200, "Close query thread returns 200", status.text)
    check(status.json()["status"] == "CLOSED", "Thread status closed")
    status_audit = [event for event in status.json().get("audit_events", []) if event["action"] == "UPDATE_STATUS"]
    check(bool(status_audit), "Audit includes status update")
    check(status_audit[-1]["reason"] == "Resolved by agronomist", "Status audit stores reason")
    invalid = client.post("/api/v1/query-threads", headers=headers, json={"farmer_id": str(farmer_id), "subject": "Bad", "category": "ALIEN"})
    check(invalid.status_code == 422, "Invalid category rejected", invalid.text[:200])
    isolated = client.get(f"/api/v1/query-threads/{thread_id}", headers={"X-Tenant-ID": "default"})
    check(isolated.status_code == 404, "Thread is tenant isolated", isolated.text)

    print("\n[5] Cleanup")
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
    print("Query threads validated")
    print("=" * 72)


if __name__ == "__main__":
    main()
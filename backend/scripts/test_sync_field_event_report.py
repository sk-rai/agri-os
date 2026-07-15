"""Regression for sync materialization of offline field event reports."""

from datetime import date, datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Farmer, Parcel, Project, Tenant
from app.modules.media.models import FieldEventReport, MediaAsset, MediaAttachment
from app.modules.sync.models import AuditChainEntry, SyncConflict, SyncProcessedEvent


def check(condition, label, detail=None):
    print(f"  {'PASS' if condition else 'FAIL'} {label}")
    if detail is not None:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(label)


def now():
    return datetime.now(timezone.utc)


def main():
    print("=" * 72)
    print("SYNC FIELD EVENT REPORT MATERIALIZATION REGRESSION")
    print("=" * 72)

    tenant_id = f"sync-field-event-{uuid.uuid4().hex[:8]}"
    actor_id = str(uuid.uuid4())
    farmer_id = uuid.uuid4()
    project_id = uuid.uuid4()
    parcel_id = uuid.uuid4()
    report_id = uuid.uuid4()
    media_asset_id = uuid.uuid4()
    headers = {"X-Tenant-ID": tenant_id, "X-Actor-ID": actor_id}

    db = SessionLocal()
    try:
        db.add(Tenant(id=tenant_id, name="Sync Field Event Tenant", type="ENTERPRISE", created_at=now(), updated_at=now()))
        db.flush()
        db.add(Project(id=project_id, tenant_id=tenant_id, name="Sync Field Event Project", start_date=date(2026, 7, 1), end_date=date(2026, 12, 31), status="PLANNED", crop_scope=["RICE"], geography_scope={}, created_at=now(), updated_at=now()))
        db.flush()
        db.add(Farmer(id=farmer_id, tenant_id=tenant_id, mobile_number=f"+9198{uuid.uuid4().int % 100000000:08d}", display_name="Field Event Farmer", village_name_manual="Event Village", status="ACTIVE", created_at=now(), updated_at=now()))
        db.flush()
        db.add(Parcel(id=parcel_id, tenant_id=tenant_id, farmer_id=farmer_id, village_name_manual="Event Village", reported_area=5, reported_area_unit="ACRE", ownership_type="OWNED", status="ACTIVE", created_at=now(), updated_at=now()))
        db.flush()
        db.add(MediaAsset(id=media_asset_id, tenant_id=tenant_id, project_id=project_id, farmer_id=farmer_id, uploaded_by=uuid.UUID(actor_id), media_type="AUDIO", mime_type="audio/mpeg", upload_status="UPLOADED", storage_key="sync-field-events/audio-note.mp3", created_at=now(), updated_at=now()))
        db.commit()
    finally:
        db.close()

    client = TestClient(app)

    create_event_id = str(uuid.uuid4())
    response = client.post(
        "/api/v1/sync/events",
        headers=headers,
        json={
            "events": [{
                "event_id": create_event_id,
                "entity_type": "FIELD_EVENT_REPORT",
                "entity_id": str(report_id),
                "operation": "CREATE",
                "payload": {
                    "project_id": str(project_id),
                    "farmer_id": str(farmer_id),
                    "parcel_id": str(parcel_id),
                    "stage_code": "TILLERING",
                    "event_type": "rain",
                    "severity": "high",
                    "event_date": "2026-07-15T09:30:00+05:30",
                    "reported_at": "2026-07-15T09:35:00+05:30",
                    "lat": "18.5204",
                    "lng": "73.8567",
                    "accuracy_meters": "12",
                    "description": "Heavy rainfall reported offline",
                    "estimated_area_affected": "1.5",
                    "estimated_loss_percent": "10",
                    "source": "farmer_android",
                    "status": "reported",
                    "metadata": {"offline": True},
                    "media_attachments": [{
                        "media_asset_id": str(media_asset_id),
                        "purpose": "AUDIO_NOTE",
                        "caption": "Offline farmer audio note",
                        "is_primary": True,
                        "metadata": {"source": "android_room"},
                    }],
                },
                "version": 1,
                "dependency_ids": [],
                "metadata": {"source": "sync_field_event_regression"},
            }]
        },
    )
    check(response.status_code == 200, "Sync create returns 200", response.text)
    body = response.json()
    check(body["accepted"] == [create_event_id], "Create event accepted", body)
    check(body["failed"] == [], "Create event has no failures", body)

    db = SessionLocal()
    try:
        report = db.query(FieldEventReport).filter(FieldEventReport.id == report_id, FieldEventReport.tenant_id == tenant_id).first()
        check(report is not None, "Field event row is materialized")
        check(report.farmer_id == farmer_id, "Farmer id preserved")
        check(report.project_id == project_id, "Project id preserved")
        check(report.parcel_id == parcel_id, "Parcel id preserved")
        check(report.event_type == "RAIN", "Event type normalized")
        check(report.severity == "HIGH", "Severity normalized")
        check(report.source == "FARMER_ANDROID", "Source normalized")
        check(report.status == "REPORTED", "Status normalized")
        check(report.metadata_ == {"offline": True}, "Metadata stored")
        attachment = db.query(MediaAttachment).filter(MediaAttachment.tenant_id == tenant_id, MediaAttachment.entity_type == "FIELD_EVENT", MediaAttachment.entity_id == report_id).first()
        check(attachment is not None, "Field event media attachment is materialized")
        check(attachment.media_asset_id == media_asset_id, "Attachment links synced media asset")
        check(attachment.purpose == "AUDIO_NOTE", "Attachment stores purpose")
    finally:
        db.close()

    update_event_id = str(uuid.uuid4())
    update = client.post(
        "/api/v1/sync/events",
        headers=headers,
        json={
            "events": [{
                "event_id": update_event_id,
                "entity_type": "FIELD_EVENT",
                "entity_id": str(report_id),
                "operation": "UPDATE",
                "payload": {
                    "project_id": str(project_id),
                    "farmer_id": str(farmer_id),
                    "parcel_id": str(parcel_id),
                    "event_type": "pest",
                    "severity": "critical",
                    "description": "Pest severity updated offline",
                    "status": "under_review",
                    "metadata": {"offline": True, "updated": True},
                },
                "version": 2,
                "dependency_ids": [create_event_id],
                "metadata": {"source": "sync_field_event_regression"},
            }]
        },
    )
    check(update.status_code == 200, "Sync update returns 200", update.text)
    check(update.json()["accepted"] == [update_event_id], "Update event accepted", update.json())

    db = SessionLocal()
    try:
        rows = db.query(FieldEventReport).filter(FieldEventReport.tenant_id == tenant_id, FieldEventReport.farmer_id == farmer_id).all()
        check(len(rows) == 1, "Update does not duplicate field event")
        check(rows[0].event_type == "PEST", "Update changes event type")
        check(rows[0].severity == "CRITICAL", "Update changes severity")
        check(rows[0].status == "UNDER_REVIEW", "Update changes status")
    finally:
        db.close()

    list_response = client.get(f"/api/v1/field-events?farmer_id={farmer_id}", headers={"X-Tenant-ID": tenant_id})
    check(list_response.status_code == 200, "Field events API lists synced report", list_response.text[:300])
    check(list_response.json()["events"][0]["id"] == str(report_id), "List response preserves report id")
    detail_response = client.get(f"/api/v1/field-events/{report_id}", headers={"X-Tenant-ID": tenant_id})
    check(detail_response.status_code == 200, "Field event detail returns synced attachment", detail_response.text[:300])
    detail = detail_response.json()
    check(detail["media_attachment_count"] == 1, "Detail counts synced media attachment")
    check(detail["media_attachments"][0]["asset"]["media_type"] == "AUDIO", "Detail embeds synced audio asset")

    db = SessionLocal()
    try:
        db.query(MediaAttachment).filter(MediaAttachment.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(MediaAsset).filter(MediaAsset.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(FieldEventReport).filter(FieldEventReport.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(SyncProcessedEvent).filter(SyncProcessedEvent.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(SyncConflict).filter(SyncConflict.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(AuditChainEntry).filter(AuditChainEntry.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Parcel).filter(Parcel.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Farmer).filter(Farmer.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Project).filter(Project.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Tenant).filter(Tenant.id == tenant_id).delete(synchronize_session=False)
        db.commit()
        check(True, "Temporary rows cleaned up")
    finally:
        db.close()

    print("=" * 72)
    print("Sync field event report materialization validated")
    print("=" * 72)


if __name__ == "__main__":
    main()

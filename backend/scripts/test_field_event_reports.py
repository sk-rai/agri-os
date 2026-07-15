"""Regression for field event reporting API."""

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
    print("FIELD EVENT REPORT REGRESSION")
    print("=" * 72)

    tenant_id = f"field-event-test-{uuid.uuid4().hex[:8]}"
    project_id = uuid.uuid4()
    farmer_id = uuid.uuid4()
    parcel_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    headers = {"X-Tenant-ID": tenant_id}

    db = SessionLocal()
    try:
        db.add(Tenant(id=tenant_id, name="Field Event Test Tenant", type="ENTERPRISE", created_at=now(), updated_at=now()))
        db.commit()
        db.add(Project(id=project_id, tenant_id=tenant_id, name="Field Event Test Project", start_date=date(2026, 7, 1), end_date=date(2026, 12, 31), status="PLANNED", crop_scope=["RICE"], geography_scope={}, created_at=now(), updated_at=now()))
        db.commit()
        db.add(Farmer(id=farmer_id, tenant_id=tenant_id, project_id=project_id, mobile_number=f"+9196{uuid.uuid4().int % 100000000:08d}", display_name="Event Farmer", village_name_manual="Event Village", status="ACTIVE", created_at=now(), updated_at=now()))
        db.commit()
        db.add(Parcel(id=parcel_id, tenant_id=tenant_id, farmer_id=farmer_id, project_id=project_id, village_name_manual="Event Village", reported_area=1, reported_area_unit="ACRE", survey_number="EVENT-1", ownership_type="OWNED", status="ACTIVE", created_at=now(), updated_at=now()))
        db.commit()
    finally:
        db.close()

    client = TestClient(app)

    print("\n[1] Create field event")
    create_response = client.post("/api/v1/field-events", headers=headers, json={
        "project_id": str(project_id),
        "farmer_id": str(farmer_id),
        "parcel_id": str(parcel_id),
        "stage_code": "TILLERING",
        "event_type": "pest",
        "severity": "high",
        "lat": "26.8467",
        "lng": "80.9462",
        "accuracy_meters": "12.5",
        "description": "Brown planthopper observed in patches",
        "estimated_area_affected": "0.25",
        "estimated_loss_percent": "10",
        "source": "farmer_android",
        "metadata": {"offline_temp_id": "field-event-1"},
    })
    check(create_response.status_code == 201, "Create field event returns 201", create_response.text)
    event = create_response.json()
    event_id = event["id"]
    check(event["event_type"] == "PEST", "Event type normalized")
    check(event["severity"] == "HIGH", "Severity normalized")
    check(event["status"] == "REPORTED", "Event starts reported")

    print("\n[2] Create field event with inline media attachment")
    inline_asset_response = client.post("/api/v1/media/assets", headers=headers, json={
        "project_id": str(project_id),
        "farmer_id": str(farmer_id),
        "uploaded_by": str(actor_id),
        "media_type": "AUDIO",
        "mime_type": "audio/mpeg",
        "upload_status": "UPLOADED",
        "storage_key": "field-events/farmer-note.mp3",
    })
    check(inline_asset_response.status_code == 201, "Create inline evidence media asset returns 201", inline_asset_response.text)
    inline_response = client.post("/api/v1/field-events", headers=headers, json={
        "project_id": str(project_id),
        "farmer_id": str(farmer_id),
        "parcel_id": str(parcel_id),
        "event_type": "rain",
        "severity": "medium",
        "description": "Farmer submitted audio note with rainfall report",
        "media_attachments": [{
            "media_asset_id": inline_asset_response.json()["id"],
            "purpose": "AUDIO_NOTE",
            "caption": "Rainfall audio note",
            "is_primary": True,
        }],
    })
    check(inline_response.status_code == 201, "Create field event with inline media returns 201", inline_response.text)
    inline_event = inline_response.json()
    check(inline_event["media_attachment_count"] == 1, "Inline create counts attached media")
    check(inline_event["media_attachments"][0]["asset"]["media_type"] == "AUDIO", "Inline create embeds attached audio")

    print("\n[3] List filters")
    list_response = client.get(f"/api/v1/field-events?project_id={project_id}&event_type=PEST&severity=HIGH", headers=headers)
    check(list_response.status_code == 200, "List field events returns 200", list_response.text)
    listed = list_response.json()
    check(listed["count"] == 1, "Filtered list returns one event")
    check(listed["events"][0]["id"] == event_id, "Filtered list returns created event")

    print("\n[4] Attach media to field event")
    asset_response = client.post("/api/v1/media/assets", headers=headers, json={
        "project_id": str(project_id),
        "farmer_id": str(farmer_id),
        "uploaded_by": str(actor_id),
        "media_type": "PHOTO",
        "mime_type": "image/jpeg",
        "upload_status": "UPLOADED",
        "storage_key": "field-events/pest.jpg",
    })
    check(asset_response.status_code == 201, "Create evidence media asset returns 201", asset_response.text)
    attachment_response = client.post("/api/v1/media/attachments", headers=headers, json={
        "media_asset_id": asset_response.json()["id"],
        "entity_type": "FIELD_EVENT",
        "entity_id": event_id,
        "purpose": "DISEASE_PHOTO",
        "caption": "Pest evidence photo",
    })
    check(attachment_response.status_code == 201, "Attach media to field event returns 201", attachment_response.text)

    detail_response = client.get(f"/api/v1/field-events/{event_id}", headers=headers)
    check(detail_response.status_code == 200, "Field event detail returns 200", detail_response.text)
    detail = detail_response.json()
    check(detail["media_attachment_count"] == 1, "Field event detail counts media")
    check(detail["media_attachments"][0]["asset"]["media_type"] == "PHOTO", "Field event detail embeds media")

    print("\n[5] Status transition")
    status_response = client.patch(f"/api/v1/field-events/{event_id}/status", headers=headers, json={"status": "UNDER_REVIEW", "reason": "Assigned to agronomist"})
    check(status_response.status_code == 200, "Field event status patch returns 200", status_response.text)
    patched = status_response.json()
    check(patched["status"] == "UNDER_REVIEW", "Field event status updated")

    print("\n[6] Validation and isolation")
    invalid_response = client.post("/api/v1/field-events", headers=headers, json={"farmer_id": str(farmer_id), "event_type": "METEOR", "severity": "HIGH"})
    check(invalid_response.status_code == 422, "Invalid field event type rejected", invalid_response.text[:200])
    other_tenant_detail = client.get(f"/api/v1/field-events/{event_id}", headers={"X-Tenant-ID": "default"})
    check(other_tenant_detail.status_code == 404, "Field event is tenant isolated", other_tenant_detail.text)

    print("\n[7] Cleanup")
    db = SessionLocal()
    try:
        db.query(MediaAttachment).filter(MediaAttachment.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(MediaAsset).filter(MediaAsset.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(FieldEventReport).filter(FieldEventReport.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Parcel).filter(Parcel.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Farmer).filter(Farmer.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Project).filter(Project.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Tenant).filter(Tenant.id == tenant_id).delete(synchronize_session=False)
        db.commit()
        check(True, "Temporary rows cleaned up")
    finally:
        db.close()

    print("=" * 72)
    print("Field event reports validated")
    print("=" * 72)


if __name__ == "__main__":
    main()

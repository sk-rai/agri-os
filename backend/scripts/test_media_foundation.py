"""Regression for shared media asset and attachment foundation."""

from datetime import date, datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Farmer, Parcel, Project, Tenant
from app.modules.media.models import MediaAsset, MediaAttachment


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
    print("MEDIA FOUNDATION REGRESSION")
    print("=" * 72)

    tenant_id = f"media-test-{uuid.uuid4().hex[:8]}"
    project_id = uuid.uuid4()
    farmer_id = uuid.uuid4()
    parcel_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    headers = {"X-Tenant-ID": tenant_id}

    db = SessionLocal()
    try:
        db.add(Tenant(id=tenant_id, name="Media Test Tenant", type="ENTERPRISE", created_at=now(), updated_at=now()))
        db.commit()
        db.add(Project(id=project_id, tenant_id=tenant_id, name="Media Test Project", start_date=date(2026, 7, 1), end_date=date(2026, 12, 31), status="PLANNED", crop_scope=["RICE"], geography_scope={}, created_at=now(), updated_at=now()))
        db.commit()
        db.add(Farmer(id=farmer_id, tenant_id=tenant_id, project_id=project_id, mobile_number=f"+9197{uuid.uuid4().int % 100000000:08d}", display_name="Media Farmer", village_name_manual="Media Village", status="ACTIVE", created_at=now(), updated_at=now()))
        db.commit()
        db.add(Parcel(id=parcel_id, tenant_id=tenant_id, farmer_id=farmer_id, project_id=project_id, village_name_manual="Media Village", reported_area=1, reported_area_unit="ACRE", survey_number="MEDIA-1", ownership_type="OWNED", status="ACTIVE", created_at=now(), updated_at=now()))
        db.commit()
    finally:
        db.close()

    client = TestClient(app)

    print("\n[1] Create pending photo asset")
    asset_response = client.post("/api/v1/media/assets", headers=headers, json={
        "project_id": str(project_id),
        "farmer_id": str(farmer_id),
        "uploaded_by": str(actor_id),
        "media_type": "photo",
        "mime_type": "image/jpeg",
        "sha256_hash": "abc123",
        "size_bytes": 12345,
        "width": 1024,
        "height": 768,
        "capture_lat": "26.8467",
        "capture_lng": "80.9462",
        "capture_accuracy_meters": "8.5",
        "metadata": {"offline_temp_id": "local-photo-1", "purpose_hint": "parcel proof"},
    })
    check(asset_response.status_code == 201, "Create asset returns 201", asset_response.text)
    asset = asset_response.json()
    asset_id = asset["id"]
    check(asset["media_type"] == "PHOTO", "Media type normalized")
    check(asset["upload_status"] == "PENDING", "Asset starts pending")
    check(asset["metadata"]["offline_temp_id"] == "local-photo-1", "Asset keeps offline metadata")

    print("\n[2] Complete upload metadata")
    complete_response = client.post(f"/api/v1/media/assets/{asset_id}/complete", headers=headers, json={
        "storage_url": "https://storage.example/media/photo.jpg",
        "thumbnail_url": "https://storage.example/media/photo-thumb.jpg",
        "upload_status": "UPLOADED",
        "metadata": {"storage_provider": "test"},
    })
    check(complete_response.status_code == 200, "Complete asset returns 200", complete_response.text)
    completed = complete_response.json()
    check(completed["upload_status"] == "UPLOADED", "Asset marked uploaded")
    check(completed["metadata"]["offline_temp_id"] == "local-photo-1" and completed["metadata"]["storage_provider"] == "test", "Completion merges metadata")

    print("\n[3] Attach photo to parcel")
    attachment_response = client.post("/api/v1/media/attachments", headers=headers, json={
        "media_asset_id": asset_id,
        "entity_type": "parcel",
        "entity_id": str(parcel_id),
        "purpose": "parcel_boundary",
        "caption": "Parcel boundary proof",
        "display_order": 1,
        "is_primary": True,
    })
    check(attachment_response.status_code == 201, "Create attachment returns 201", attachment_response.text)
    attachment = attachment_response.json()
    check(attachment["entity_type"] == "PARCEL" and attachment["purpose"] == "PARCEL_BOUNDARY", "Attachment enums normalized")
    check(attachment["asset"]["id"] == asset_id, "Attachment embeds asset")

    print("\n[4] Attach audio note to farmer")
    audio_response = client.post("/api/v1/media/assets", headers=headers, json={
        "project_id": str(project_id),
        "farmer_id": str(farmer_id),
        "uploaded_by": str(actor_id),
        "media_type": "AUDIO",
        "mime_type": "audio/aac",
        "duration_seconds": 42,
        "upload_status": "UPLOADED",
        "storage_key": "media/audio-note.aac",
    })
    check(audio_response.status_code == 201, "Create audio asset returns 201", audio_response.text)
    audio = audio_response.json()
    audio_attachment_response = client.post("/api/v1/media/attachments", headers=headers, json={
        "media_asset_id": audio["id"],
        "entity_type": "FARMER",
        "entity_id": str(farmer_id),
        "purpose": "AUDIO_NOTE",
    })
    check(audio_attachment_response.status_code == 201, "Create audio attachment returns 201", audio_attachment_response.text)

    print("\n[5] List attachments by entity")
    list_response = client.get(f"/api/v1/media/attachments?entity_type=PARCEL&entity_id={parcel_id}", headers=headers)
    check(list_response.status_code == 200, "List parcel attachments returns 200", list_response.text)
    listed = list_response.json()
    check(listed["count"] == 1, "Parcel listing returns one attachment")
    check(listed["attachments"][0]["asset"]["upload_status"] == "UPLOADED", "Listing includes asset upload status")

    print("\n[6] Validation and tenant isolation")
    invalid_response = client.post("/api/v1/media/assets", headers=headers, json={"media_type": "BINARY", "mime_type": "application/octet-stream"})
    check(invalid_response.status_code == 422, "Invalid media type rejected", invalid_response.text[:200])
    missing_asset_attach = client.post("/api/v1/media/attachments", headers=headers, json={"media_asset_id": str(uuid.uuid4()), "entity_type": "FARMER", "entity_id": str(farmer_id), "purpose": "GENERAL"})
    check(missing_asset_attach.status_code == 404, "Missing asset attachment rejected", missing_asset_attach.text)
    other_tenant_get = client.get(f"/api/v1/media/assets/{asset_id}", headers={"X-Tenant-ID": "default"})
    check(other_tenant_get.status_code == 404, "Asset is tenant isolated", other_tenant_get.text)

    print("\n[7] Cleanup")
    db = SessionLocal()
    try:
        db.query(MediaAttachment).filter(MediaAttachment.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(MediaAsset).filter(MediaAsset.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Parcel).filter(Parcel.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Farmer).filter(Farmer.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Project).filter(Project.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Tenant).filter(Tenant.id == tenant_id).delete(synchronize_session=False)
        db.commit()
        check(True, "Temporary rows cleaned up")
    finally:
        db.close()

    print("=" * 72)
    print("Media foundation validated")
    print("=" * 72)


if __name__ == "__main__":
    main()

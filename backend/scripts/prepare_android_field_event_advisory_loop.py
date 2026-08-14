"""Prepare and verify field-event media to advisory broadcast loop.

Flow:
1. create a farmer/field-agent pest field event with an uploaded photo;
2. mark the event UNDER_REVIEW then ADVISORY_SENT;
3. publish a crop-targeted advisory broadcast reusing the same media asset;
4. verify field event detail, admin/advisory detail, and Android farmer feed all
   carry the expected source-event/media linkage.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.media.models import (
    BroadcastAuditEvent,
    BroadcastAudienceRule,
    BroadcastCampaign,
    BroadcastContent,
    BroadcastDelivery,
    FieldEventReport,
    MediaAsset,
    MediaAttachment,
)
from scripts.prepare_android_fpo_multi_village_workflow import PROJECT_ID, TENANT_ID, farmer_id, parcel_id, cycle_id

ACTOR_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000002099")
FIELD_EVENT_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000002994")
MEDIA_ASSET_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000002995")
CAMPAIGN_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000002996")
ADVISORY_ATTACHMENT_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000002997")

REPORTING_FARMER_ID = farmer_id(6)
REPORTING_FARMER_MOBILE = "+919900002106"
REPORTING_PARCEL_ID = parcel_id(6)
REPORTING_CYCLE_ID = cycle_id(6)
INCLUDED_MAIZE_FARMER_ID = farmer_id(6)
EXCLUDED_RICE_FARMER_ID = farmer_id(1)

FIELD_EVENT_TITLE = "FPO pest field event photo"
FIELD_EVENT_DESCRIPTION = "Farmer reports pest marks on maize leaves with a field photo. FPO should convert this into an advisory."
ADVISORY_TITLE = "Maize pest photo advisory"
ADVISORY_BODY = "A maize pest photo was reviewed by the FPO. Scout nearby plots and contact the advisor before applying inputs."
ADVISORY_CAPTION = "Source field event pest photo"
STORAGE_URL = "https://static.example.test/agrios/smoke/fpo-field-event-pest-photo.jpg"
THUMBNAIL_URL = "https://static.example.test/agrios/smoke/fpo-field-event-pest-photo-thumb.jpg"


def check(condition: bool, label: str, detail=None) -> None:
    print(f"{'PASS' if condition else 'FAIL'} {label}")
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str) if not isinstance(detail, str) else detail)
    if not condition:
        raise AssertionError(label)


def request_json(client: TestClient, method: str, path: str, *, expected: int = 200, body: dict | None = None) -> dict:
    response = client.request(method, path, headers={"X-Tenant-ID": TENANT_ID}, json=body)
    check(response.status_code == expected, f"{method} {path} returns {expected}", response.text[:1400])
    return response.json()


def cleanup_state() -> dict:
    db = SessionLocal()
    try:
        content_ids = [
            row.id
            for row in db.query(BroadcastContent.id).filter(
                BroadcastContent.tenant_id == TENANT_ID,
                BroadcastContent.campaign_id == CAMPAIGN_ID,
            ).all()
        ]
        attachment_ids = [
            row.id
            for row in db.query(MediaAttachment).filter(
                MediaAttachment.tenant_id == TENANT_ID,
                MediaAttachment.media_asset_id == MEDIA_ASSET_ID,
            ).all()
        ]
        if content_ids:
            attachment_ids.extend(
                row.id
                for row in db.query(MediaAttachment).filter(
                    MediaAttachment.tenant_id == TENANT_ID,
                    MediaAttachment.entity_id.in_(content_ids),
                ).all()
            )
        attachment_ids = sorted(set(attachment_ids))
        counts = {}
        counts["media_attachments"] = db.query(MediaAttachment).filter(MediaAttachment.id.in_(attachment_ids)).delete(synchronize_session=False) if attachment_ids else 0
        counts["broadcast_deliveries"] = db.query(BroadcastDelivery).filter(BroadcastDelivery.tenant_id == TENANT_ID, BroadcastDelivery.campaign_id == CAMPAIGN_ID).delete(synchronize_session=False)
        counts["broadcast_audit_events"] = db.query(BroadcastAuditEvent).filter(BroadcastAuditEvent.tenant_id == TENANT_ID, BroadcastAuditEvent.campaign_id == CAMPAIGN_ID).delete(synchronize_session=False)
        counts["broadcast_audience_rules"] = db.query(BroadcastAudienceRule).filter(BroadcastAudienceRule.tenant_id == TENANT_ID, BroadcastAudienceRule.campaign_id == CAMPAIGN_ID).delete(synchronize_session=False)
        counts["broadcast_contents"] = db.query(BroadcastContent).filter(BroadcastContent.tenant_id == TENANT_ID, BroadcastContent.campaign_id == CAMPAIGN_ID).delete(synchronize_session=False)
        counts["broadcast_campaigns"] = db.query(BroadcastCampaign).filter(BroadcastCampaign.tenant_id == TENANT_ID, BroadcastCampaign.id == CAMPAIGN_ID).delete(synchronize_session=False)
        counts["field_event_reports"] = db.query(FieldEventReport).filter(FieldEventReport.tenant_id == TENANT_ID, FieldEventReport.id == FIELD_EVENT_ID).delete(synchronize_session=False)
        counts["media_assets"] = db.query(MediaAsset).filter(MediaAsset.tenant_id == TENANT_ID, MediaAsset.id == MEDIA_ASSET_ID).delete(synchronize_session=False)
        db.commit()
        return {key: int(value or 0) for key, value in counts.items()}
    finally:
        db.close()


def link_event_metadata() -> None:
    db = SessionLocal()
    try:
        event = db.query(FieldEventReport).filter(FieldEventReport.tenant_id == TENANT_ID, FieldEventReport.id == FIELD_EVENT_ID).first()
        check(event is not None, "Field event exists for metadata link")
        metadata = dict(event.metadata_ or {})
        metadata.update({
            "advisory_campaign_id": str(CAMPAIGN_ID),
            "advisory_media_asset_id": str(MEDIA_ASSET_ID),
            "advisory_loop_status": "ADVISORY_SENT",
            "android_contract": "field_event_advisory_loop.v1",
        })
        event.metadata_ = metadata
        db.add(event)
        db.commit()
    finally:
        db.close()


def create_loop(client: TestClient) -> dict:
    asset = request_json(
        client,
        "POST",
        "/api/v1/media/assets",
        expected=201,
        body={
            "id": str(MEDIA_ASSET_ID),
            "project_id": str(PROJECT_ID),
            "farmer_id": str(REPORTING_FARMER_ID),
            "uploaded_by": str(ACTOR_ID),
            "media_type": "PHOTO",
            "mime_type": "image/jpeg",
            "storage_url": STORAGE_URL,
            "storage_key": "smoke/fpo-field-event-pest-photo.jpg",
            "thumbnail_url": THUMBNAIL_URL,
            "sha256_hash": "field-event-advisory-loop-smoke-sha256",
            "size_bytes": 307200,
            "width": 1600,
            "height": 900,
            "capture_lat": "12.97160000",
            "capture_lng": "77.59460000",
            "capture_accuracy_meters": "8",
            "upload_status": "UPLOADED",
            "metadata": {
                "android_contract": "field_event_advisory_loop.v1",
                "source": "FIELD_EVENT_REPORT",
                "reuse_in_advisory": True,
            },
        },
    )
    check(asset["upload_status"] == "UPLOADED", "Field event source media asset is uploaded", asset)

    event = request_json(
        client,
        "POST",
        "/api/v1/field-events",
        expected=201,
        body={
            "id": str(FIELD_EVENT_ID),
            "project_id": str(PROJECT_ID),
            "farmer_id": str(REPORTING_FARMER_ID),
            "parcel_id": str(REPORTING_PARCEL_ID),
            "crop_cycle_id": str(REPORTING_CYCLE_ID),
            "stage_code": "VEGETATIVE",
            "event_type": "PEST",
            "severity": "HIGH",
            "lat": "12.97160000",
            "lng": "77.59460000",
            "accuracy_meters": "8",
            "description": FIELD_EVENT_DESCRIPTION,
            "estimated_area_affected": "0.40",
            "estimated_loss_percent": "12",
            "source": "FIELD_AGENT_ANDROID",
            "status": "REPORTED",
            "metadata": {
                "android_contract": "field_event_advisory_loop.v1",
                "source_photo_media_asset_id": str(MEDIA_ASSET_ID),
                "requires_advisory_followup": True,
            },
            "media_attachments": [
                {
                    "media_asset_id": str(MEDIA_ASSET_ID),
                    "purpose": "DISEASE_PHOTO",
                    "caption": FIELD_EVENT_TITLE,
                    "display_order": 1,
                    "is_primary": True,
                    "metadata": {"reported_from_android": True, "crop_code": "MAIZE"},
                }
            ],
        },
    )
    check(event["media_attachment_count"] == 1 and event["status"] == "REPORTED", "Field event created with one media attachment", event)

    under_review = request_json(client, "PATCH", f"/api/v1/field-events/{FIELD_EVENT_ID}/status", body={"status": "UNDER_REVIEW", "reason": "FPO reviewing pest photo for advisory"})
    check(under_review["status"] == "UNDER_REVIEW", "Field event enters UNDER_REVIEW", under_review)

    campaign = request_json(
        client,
        "POST",
        "/api/v1/broadcasts",
        expected=201,
        body={
            "id": str(CAMPAIGN_ID),
            "project_id": str(PROJECT_ID),
            "title": "Field event pest advisory broadcast",
            "category": "ADVISORY",
            "priority": "HIGH",
            "created_by": str(ACTOR_ID),
            "metadata": {
                "android_contract": "field_event_advisory_loop.v1",
                "event_type": "FIELD_EVENT_ADVISORY_CREATED",
                "source_field_event_id": str(FIELD_EVENT_ID),
                "source_media_asset_id": str(MEDIA_ASSET_ID),
                "targeting_backend_owned": True,
                "audience_match_mode": "ANY",
            },
            "contents": [
                {
                    "language_code": "en",
                    "title": ADVISORY_TITLE,
                    "body_text": ADVISORY_BODY,
                    "cta_label": "Open pest advisory",
                    "deeplink_url": f"agrios://field-event-advisory/{FIELD_EVENT_ID}",
                    "metadata": {
                        "android_copy_role": "field_event_advisory",
                        "source_field_event_id": str(FIELD_EVENT_ID),
                        "source_media_asset_id": str(MEDIA_ASSET_ID),
                    },
                }
            ],
            "audience_rules": [
                {"rule_type": "CROP", "operator": "IN", "values": ["MAIZE"], "metadata": {"source_field_event_id": str(FIELD_EVENT_ID)}}
            ],
        },
    )
    content_id = campaign["contents"][0]["id"]
    advisory_attachment = request_json(
        client,
        "POST",
        "/api/v1/media/attachments",
        expected=201,
        body={
            "id": str(ADVISORY_ATTACHMENT_ID),
            "media_asset_id": str(MEDIA_ASSET_ID),
            "entity_type": "ADVISORY",
            "entity_id": content_id,
            "purpose": "ADVISORY_ATTACHMENT",
            "caption": ADVISORY_CAPTION,
            "display_order": 1,
            "is_primary": True,
            "metadata": {"source_field_event_id": str(FIELD_EVENT_ID), "reused_field_event_media": True},
        },
    )
    check(advisory_attachment["media_asset_id"] == str(MEDIA_ASSET_ID), "Advisory reuses field event media asset", advisory_attachment)

    published = request_json(client, "POST", f"/api/v1/broadcasts/{CAMPAIGN_ID}/publish", body={"approved_by": str(ACTOR_ID), "reason": "FPO sends advisory from field event pest photo"})
    generated = request_json(client, "POST", f"/api/v1/broadcasts/{CAMPAIGN_ID}/generate-deliveries")
    check(published["status"] == "PUBLISHED", "Advisory broadcast is PUBLISHED", published)
    check((generated.get("delivery_summary") or {}).get("total") == 2, "Maize advisory targets two active Maize farmers", generated.get("delivery_summary"))

    advisory_sent = request_json(client, "PATCH", f"/api/v1/field-events/{FIELD_EVENT_ID}/status", body={"status": "ADVISORY_SENT", "reason": "Advisory broadcast created from field event media"})
    check(advisory_sent["status"] == "ADVISORY_SENT", "Field event status becomes ADVISORY_SENT", advisory_sent)
    link_event_metadata()
    return {"asset": asset, "event": event, "campaign": campaign, "published": published, "generated": generated, "advisory_attachment": advisory_attachment, "advisory_sent": advisory_sent}


def farmer_feed(client: TestClient, farmer_id_value: uuid.UUID) -> dict:
    return request_json(client, "GET", f"/api/v1/broadcasts/farmers/{farmer_id_value}/broadcasts?language_code=en&include_read=true")


def feed_item_for_campaign(feed: dict) -> dict | None:
    return next((row for row in feed.get("broadcasts", []) if row.get("campaign", {}).get("id") == str(CAMPAIGN_ID)), None)


def verify_loop(client: TestClient) -> dict:
    event_detail = request_json(client, "GET", f"/api/v1/field-events/{FIELD_EVENT_ID}")
    field_media = event_detail.get("media_attachments") or []
    check(event_detail["status"] == "ADVISORY_SENT", "Field event detail is ADVISORY_SENT", event_detail)
    check(event_detail["event_type"] == "PEST" and event_detail["severity"] == "HIGH", "Field event type/severity preserved", event_detail)
    check(len(field_media) == 1, "Field event detail exposes one media attachment", field_media)
    check(field_media[0]["media_asset_id"] == str(MEDIA_ASSET_ID), "Field event media asset id matches deterministic asset", field_media[0])
    check((event_detail.get("metadata") or {}).get("advisory_campaign_id") == str(CAMPAIGN_ID), "Field event metadata links advisory campaign", event_detail.get("metadata"))

    campaign_detail = request_json(client, "GET", f"/api/v1/broadcasts/{CAMPAIGN_ID}")
    content = campaign_detail["contents"][0]
    advisory_media = content.get("media_attachments") or []
    check(campaign_detail["status"] == "PUBLISHED", "Advisory campaign remains PUBLISHED", campaign_detail)
    check((campaign_detail.get("delivery_summary") or {}).get("total") == 2, "Advisory campaign has two Maize deliveries", campaign_detail.get("delivery_summary"))
    check((campaign_detail.get("metadata") or {}).get("source_field_event_id") == str(FIELD_EVENT_ID), "Advisory campaign metadata links source field event", campaign_detail.get("metadata"))
    check(len(advisory_media) == 1 and advisory_media[0]["id"] == str(MEDIA_ASSET_ID), "Advisory content reuses same media asset", advisory_media)
    check((advisory_media[0].get("attachment") or {}).get("purpose") == "ADVISORY_ATTACHMENT", "Advisory media purpose is ADVISORY_ATTACHMENT", advisory_media[0])

    included_feed = farmer_feed(client, INCLUDED_MAIZE_FARMER_ID)
    included_item = feed_item_for_campaign(included_feed)
    check(included_item is not None, "Reporting Maize farmer sees advisory", included_feed)
    feed_media = included_item["content"].get("media_attachments") or []
    check(included_item["content"]["title"] == ADVISORY_TITLE, "Android feed advisory title is present", included_item["content"])
    check(len(feed_media) == 1 and feed_media[0]["id"] == str(MEDIA_ASSET_ID), "Android feed receives reused media asset", feed_media)
    check((included_item["campaign"].get("metadata") or {}).get("source_field_event_id") == str(FIELD_EVENT_ID), "Android feed campaign metadata includes source field event", included_item["campaign"].get("metadata"))

    excluded_feed = farmer_feed(client, EXCLUDED_RICE_FARMER_ID)
    check(feed_item_for_campaign(excluded_feed) is None, "Excluded Rice farmer does not see Maize field-event advisory", excluded_feed)

    deliveries = request_json(client, "GET", f"/api/v1/broadcasts/{CAMPAIGN_ID}/deliveries?limit=100")
    delivered_ids = sorted(row["farmer_id"] for row in deliveries.get("deliveries", []))
    check(delivered_ids == sorted([str(farmer_id(6)), str(farmer_id(7))]), "Advisory delivered to active Maize farmers only", delivered_ids)
    return {"event_detail": event_detail, "campaign_detail": campaign_detail, "included_feed": included_feed, "excluded_feed": excluded_feed, "deliveries": deliveries}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()

    print("=" * 72)
    print("ANDROID FIELD EVENT ADVISORY LOOP VERIFIER")
    print("=" * 72)

    reset_counts = {}
    if args.reset or args.cleanup:
        reset_counts = cleanup_state()
        check(True, "Cleaned deterministic field-event advisory loop state", reset_counts)
    if args.cleanup:
        print(json.dumps({
            "schema_version": "android_field_event_advisory_loop_verification.v1",
            "mode": "CLEANUP",
            "tenant_id": TENANT_ID,
            "project_id": str(PROJECT_ID),
            "field_event_id": str(FIELD_EVENT_ID),
            "campaign_id": str(CAMPAIGN_ID),
            "reset": reset_counts,
        }, indent=2, sort_keys=True, default=str))
        return 0

    client = TestClient(app)
    created = create_loop(client) if args.apply else {}
    verified = verify_loop(client)
    result = {
        "schema_version": "android_field_event_advisory_loop_verification.v1",
        "tenant_id": TENANT_ID,
        "project_id": str(PROJECT_ID),
        "field_event_id": str(FIELD_EVENT_ID),
        "campaign_id": str(CAMPAIGN_ID),
        "media_asset_id": str(MEDIA_ASSET_ID),
        "reporting_farmer_id": str(REPORTING_FARMER_ID),
        "reporting_farmer_mobile": REPORTING_FARMER_MOBILE,
        "included_farmer_id": str(INCLUDED_MAIZE_FARMER_ID),
        "excluded_farmer_id": str(EXCLUDED_RICE_FARMER_ID),
        "reset": reset_counts,
        "created_delivery_count": (created.get("generated") or {}).get("delivery_summary", {}).get("total"),
        "verified": {
            "field_event_status": verified["event_detail"]["status"],
            "field_event_media_count": len(verified["event_detail"].get("media_attachments") or []),
            "advisory_delivery_count": verified["campaign_detail"]["delivery_summary"]["total"],
            "advisory_media_asset_id": verified["campaign_detail"]["contents"][0]["media_attachments"][0]["id"],
            "included_farmer_visible": feed_item_for_campaign(verified["included_feed"]) is not None,
            "excluded_farmer_visible": feed_item_for_campaign(verified["excluded_feed"]) is not None,
        },
        "readiness": {
            "field_event_media_report_covered": True,
            "field_event_status_advisory_sent_covered": True,
            "advisory_reuses_field_event_media_covered": True,
            "android_feed_source_event_metadata_covered": True,
            "included_excluded_farmer_feed_covered": True,
            "ready_for_android_field_event_advisory_loop_maestro": True,
            "ready_for_field_event_advisory_loop_web_smoke": True,
        },
        "cleanup_command": "cd ~/projects/farmint/backend && ../venv/bin/python scripts/prepare_android_field_event_advisory_loop.py --cleanup",
    }
    print("=" * 72)
    print("ANDROID FIELD EVENT ADVISORY LOOP VERIFIED")
    print("=" * 72)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
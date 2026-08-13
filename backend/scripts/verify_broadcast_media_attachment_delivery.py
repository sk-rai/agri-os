"""Prepare and verify Android-visible broadcast media attachment delivery.

This smoke creates one deterministic published advisory broadcast targeted at
the selected FPO fixture farmer, attaches one uploaded PHOTO media asset to the
English content row, generates one delivery, and verifies both admin detail and
farmer feed expose the media attachment with text fallback.
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
    MediaAsset,
    MediaAttachment,
)
from scripts.prepare_android_fpo_multi_village_workflow import PROJECT_ID, TENANT_ID

ACTOR_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000002099")
SELECTED_FARMER_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000002106")
SELECTED_MOBILE = "+919900002106"
CAMPAIGN_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000002960")
MEDIA_ASSET_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000002961")
MEDIA_ATTACHMENT_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000002962")

TITLE = "FPO photo advisory smoke"
CONTENT_TITLE = "Pest scouting photo advisory"
BODY_TEXT = "Review the attached pest scouting photo before applying inputs. Text guidance remains available if media cannot load."
CTA_LABEL = "Open advisory media"
DEEPLINK_URL = "agrios://broadcast/media-advisory?campaign_id=0f7e0a6b-8472-5d6d-8a14-a9d000002960"
CAPTION = "Pest scouting reference photo"
STORAGE_URL = "https://static.example.test/agrios/smoke/fpo-pest-scouting-photo.jpg"
THUMBNAIL_URL = "https://static.example.test/agrios/smoke/fpo-pest-scouting-photo-thumb.jpg"


def check(condition: bool, label: str, detail=None) -> None:
    print(f"{'PASS' if condition else 'FAIL'} {label}")
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str) if not isinstance(detail, str) else detail)
    if not condition:
        raise AssertionError(label)


def request_json(client: TestClient, method: str, path: str, *, expected: int = 200, body: dict | None = None) -> dict:
    response = client.request(method, path, headers={"X-Tenant-ID": TENANT_ID}, json=body)
    check(response.status_code == expected, f"{method} {path} returns {expected}", response.text[:1200])
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
        counts: dict[str, int] = {}

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
        if attachment_ids:
            counts["media_attachments"] = db.query(MediaAttachment).filter(MediaAttachment.id.in_(attachment_ids)).delete(synchronize_session=False)
        else:
            counts["media_attachments"] = 0

        counts["broadcast_deliveries"] = db.query(BroadcastDelivery).filter(BroadcastDelivery.tenant_id == TENANT_ID, BroadcastDelivery.campaign_id == CAMPAIGN_ID).delete(synchronize_session=False)
        counts["broadcast_audit_events"] = db.query(BroadcastAuditEvent).filter(BroadcastAuditEvent.tenant_id == TENANT_ID, BroadcastAuditEvent.campaign_id == CAMPAIGN_ID).delete(synchronize_session=False)
        counts["broadcast_audience_rules"] = db.query(BroadcastAudienceRule).filter(BroadcastAudienceRule.tenant_id == TENANT_ID, BroadcastAudienceRule.campaign_id == CAMPAIGN_ID).delete(synchronize_session=False)
        counts["broadcast_contents"] = db.query(BroadcastContent).filter(BroadcastContent.tenant_id == TENANT_ID, BroadcastContent.campaign_id == CAMPAIGN_ID).delete(synchronize_session=False)
        counts["broadcast_campaigns"] = db.query(BroadcastCampaign).filter(BroadcastCampaign.tenant_id == TENANT_ID, BroadcastCampaign.id == CAMPAIGN_ID).delete(synchronize_session=False)
        counts["media_assets"] = db.query(MediaAsset).filter(MediaAsset.tenant_id == TENANT_ID, MediaAsset.id == MEDIA_ASSET_ID).delete(synchronize_session=False)
        db.commit()
        return counts
    finally:
        db.close()


def create_media_broadcast(client: TestClient) -> dict:
    asset = request_json(
        client,
        "POST",
        "/api/v1/media/assets",
        expected=201,
        body={
            "id": str(MEDIA_ASSET_ID),
            "project_id": str(PROJECT_ID),
            "farmer_id": str(SELECTED_FARMER_ID),
            "uploaded_by": str(ACTOR_ID),
            "media_type": "PHOTO",
            "mime_type": "image/jpeg",
            "storage_url": STORAGE_URL,
            "storage_key": "smoke/fpo-pest-scouting-photo.jpg",
            "thumbnail_url": THUMBNAIL_URL,
            "sha256_hash": "broadcast-media-attachment-smoke-sha256",
            "size_bytes": 204800,
            "width": 1280,
            "height": 720,
            "upload_status": "UPLOADED",
            "metadata": {
                "android_contract": "broadcast_media_attachment.v1",
                "fixture": "broadcast_media_attachment_delivery",
                "external_media_fetch_required": False,
            },
        },
    )
    check(asset["upload_status"] == "UPLOADED", "Media asset is uploaded", asset)

    campaign = request_json(
        client,
        "POST",
        "/api/v1/broadcasts",
        expected=201,
        body={
            "id": str(CAMPAIGN_ID),
            "project_id": str(PROJECT_ID),
            "title": TITLE,
            "category": "ADVISORY",
            "priority": "HIGH",
            "created_by": str(ACTOR_ID),
            "metadata": {
                "android_contract": "broadcast_media_attachment.v1",
                "event_type": "MEDIA_ADVISORY_WITH_ATTACHMENT",
                "requires_text_fallback": True,
                "media_optional_for_home": True,
                "audience_match_mode": "ALL",
            },
            "contents": [
                {
                    "language_code": "en",
                    "title": CONTENT_TITLE,
                    "body_text": BODY_TEXT,
                    "cta_label": CTA_LABEL,
                    "deeplink_url": DEEPLINK_URL,
                    "metadata": {
                        "android_copy_role": "media_advisory",
                        "display_as_actionable_info": True,
                        "does_not_block_home": True,
                    },
                }
            ],
            "audience_rules": [
                {
                    "rule_type": "FARMER",
                    "operator": "IN",
                    "values": [str(SELECTED_FARMER_ID)],
                    "metadata": {"reason": "single selected Android FPO farmer for media attachment smoke"},
                }
            ],
        },
    )
    content_id = campaign["contents"][0]["id"]
    attachment = request_json(
        client,
        "POST",
        "/api/v1/media/attachments",
        expected=201,
        body={
            "id": str(MEDIA_ATTACHMENT_ID),
            "media_asset_id": str(MEDIA_ASSET_ID),
            "entity_type": "ADVISORY",
            "entity_id": content_id,
            "purpose": "ADVISORY_ATTACHMENT",
            "caption": CAPTION,
            "display_order": 1,
            "is_primary": True,
            "metadata": {
                "android_render_hint": "thumbnail_then_fullscreen",
                "text_fallback_required": True,
            },
        },
    )
    check(attachment["entity_type"] == "ADVISORY" and attachment["purpose"] == "ADVISORY_ATTACHMENT", "Attachment is linked as ADVISORY content", attachment)

    published = request_json(
        client,
        "POST",
        f"/api/v1/broadcasts/{CAMPAIGN_ID}/publish",
        body={"approved_by": str(ACTOR_ID), "reason": "Android media attachment smoke publish"},
    )
    generated = request_json(client, "POST", f"/api/v1/broadcasts/{CAMPAIGN_ID}/generate-deliveries")
    check(published["status"] == "PUBLISHED", "Campaign published", published)
    check(generated["delivery_summary"]["total"] == 1, "Single FARMER-targeted delivery generated", generated["delivery_summary"])
    return {"asset": asset, "campaign": campaign, "content_id": content_id, "attachment": attachment, "published": published, "generated": generated}


def verify_media_payloads(client: TestClient) -> dict:
    detail = request_json(client, "GET", f"/api/v1/broadcasts/{CAMPAIGN_ID}")
    check(detail["status"] == "PUBLISHED", "Admin detail keeps campaign PUBLISHED", detail)
    check(detail["delivery_summary"]["total"] == 1, "Admin detail has one delivery", detail["delivery_summary"])
    content = detail["contents"][0]
    media = content.get("media_attachments") or []
    check(content["title"] == CONTENT_TITLE and content["body_text"] == BODY_TEXT, "Text fallback remains in content", content)
    check(len(media) == 1, "Admin detail exposes one media attachment", media)
    check(media[0]["media_type"] == "PHOTO", "Admin media type is PHOTO", media[0])
    check(media[0]["mime_type"] == "image/jpeg", "Admin media MIME is image/jpeg", media[0])
    check(media[0]["upload_status"] == "UPLOADED", "Admin media upload status is UPLOADED", media[0])
    check(media[0]["storage_url"] == STORAGE_URL and media[0]["thumbnail_url"] == THUMBNAIL_URL, "Admin media URLs are present", media[0])
    check((media[0].get("attachment") or {}).get("caption") == CAPTION, "Admin media caption is present", media[0])

    feed = request_json(client, "GET", f"/api/v1/broadcasts/farmers/{SELECTED_FARMER_ID}/broadcasts?language_code=en&include_read=true")
    items = [row for row in feed.get("broadcasts", []) if row.get("campaign", {}).get("id") == str(CAMPAIGN_ID)]
    check(len(items) == 1, "Selected farmer feed has one media advisory", feed)
    item = items[0]
    feed_media = (item.get("content") or {}).get("media_attachments") or []
    check(item["delivery"]["delivery_status"] == "PENDING", "Farmer delivery starts PENDING", item["delivery"])
    check(len(feed_media) == 1, "Farmer feed exposes one media attachment", feed_media)
    check(feed_media[0]["storage_url"] == STORAGE_URL, "Farmer feed media storage URL is present", feed_media[0])
    check((feed_media[0].get("attachment") or {}).get("purpose") == "ADVISORY_ATTACHMENT", "Farmer feed attachment purpose is advisory", feed_media[0])
    check((item.get("content") or {}).get("body_text") == BODY_TEXT, "Farmer feed keeps text fallback", item.get("content"))

    media_listing = request_json(client, "GET", f"/api/v1/media/attachments?entity_type=ADVISORY&entity_id={content['id']}&purpose=ADVISORY_ATTACHMENT")
    check(media_listing["count"] == 1, "Media attachment listing can retrieve advisory attachment", media_listing)

    return {"detail": detail, "feed": feed, "media_listing": media_listing, "selected_item": item}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Delete prior deterministic media smoke state before running.")
    parser.add_argument("--apply", action="store_true", help="Create deterministic media smoke state before verifying.")
    parser.add_argument("--cleanup", action="store_true", help="Delete deterministic media smoke state and exit.")
    args = parser.parse_args()

    print("=" * 72)
    print("BROADCAST MEDIA ATTACHMENT DELIVERY VERIFIER")
    print("=" * 72)

    reset_counts = {}
    if args.reset or args.cleanup:
        reset_counts = cleanup_state()
        check(True, "Cleaned deterministic media attachment smoke state", reset_counts)
    if args.cleanup:
        print(json.dumps({
            "schema_version": "broadcast_media_attachment_delivery_verification.v1",
            "mode": "CLEANUP",
            "tenant_id": TENANT_ID,
            "project_id": str(PROJECT_ID),
            "campaign_id": str(CAMPAIGN_ID),
            "reset": reset_counts,
        }, indent=2, sort_keys=True))
        return 0

    client = TestClient(app)
    created = create_media_broadcast(client) if args.apply else {}
    verified = verify_media_payloads(client)
    selected_media = verified["selected_item"]["content"]["media_attachments"][0]

    result = {
        "schema_version": "broadcast_media_attachment_delivery_verification.v1",
        "tenant_id": TENANT_ID,
        "project_id": str(PROJECT_ID),
        "campaign_id": str(CAMPAIGN_ID),
        "media_asset_id": str(MEDIA_ASSET_ID),
        "media_attachment_id": str(MEDIA_ATTACHMENT_ID),
        "selected_farmer_id": str(SELECTED_FARMER_ID),
        "selected_mobile": SELECTED_MOBILE,
        "reset": reset_counts,
        "created": {
            "content_id": created.get("content_id"),
            "delivery_count": (created.get("generated") or {}).get("delivery_summary", {}).get("total"),
        },
        "verified": {
            "admin_media_count": len(verified["detail"]["contents"][0].get("media_attachments") or []),
            "farmer_feed_count": verified["feed"]["count"],
            "farmer_media_count": len(verified["selected_item"]["content"].get("media_attachments") or []),
            "media_type": selected_media["media_type"],
            "mime_type": selected_media["mime_type"],
            "upload_status": selected_media["upload_status"],
            "text_fallback_present": verified["selected_item"]["content"]["body_text"] == BODY_TEXT,
        },
        "readiness": {
            "admin_media_attachment_detail_covered": True,
            "android_farmer_feed_media_attachment_covered": True,
            "text_fallback_covered": True,
            "single_farmer_targeting_covered": True,
            "ready_for_android_broadcast_media_attachment_maestro": True,
            "ready_for_broadcast_media_attachment_web_smoke": True,
        },
        "cleanup_command": "cd ~/projects/farmint/backend && ../venv/bin/python scripts/verify_broadcast_media_attachment_delivery.py --cleanup",
    }
    print("=" * 72)
    print("BROADCAST MEDIA ATTACHMENT DELIVERY VERIFIED")
    print("=" * 72)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
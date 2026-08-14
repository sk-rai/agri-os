"""Prepare and verify Android-visible broadcast language selection and fallback.

This smoke creates one deterministic published advisory broadcast targeted at the
selected FPO fixture farmer. It has English and Hindi content. The verifier
checks that the farmer feed returns Hindi when requested and falls back to
English, including the English media attachment, when an unsupported language is
requested.
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
CAMPAIGN_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000002970")
MEDIA_ASSET_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000002971")
MEDIA_ATTACHMENT_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000002972")

TITLE = "FPO language fallback advisory smoke"
EN_TITLE = "Pest scouting language fallback advisory"
EN_BODY = "English fallback guidance with an attached scouting photo is available when requested language content is missing."
HI_TITLE = "कीट फोटो सलाह"
HI_BODY = "कीट की पहचान के लिए संलग्न फोटो देखें। जरूरत हो तो सलाहकार से संपर्क करें।"
CTA_LABEL = "Open language advisory"
DEEPLINK_URL = "agrios://broadcast/language-fallback?campaign_id=0f7e0a6b-8472-5d6d-8a14-a9d000002970"
CAPTION = "Fallback scouting reference photo"
STORAGE_URL = "https://static.example.test/agrios/smoke/fpo-language-fallback-photo.jpg"
THUMBNAIL_URL = "https://static.example.test/agrios/smoke/fpo-language-fallback-photo-thumb.jpg"


def check(condition: bool, label: str, detail=None) -> None:
    print(f"{'PASS' if condition else 'FAIL'} {label}")
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str, ensure_ascii=False) if not isinstance(detail, str) else detail)
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
        counts["media_attachments"] = db.query(MediaAttachment).filter(MediaAttachment.id.in_(attachment_ids)).delete(synchronize_session=False) if attachment_ids else 0
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


def create_language_campaign(client: TestClient) -> dict:
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
            "storage_key": "smoke/fpo-language-fallback-photo.jpg",
            "thumbnail_url": THUMBNAIL_URL,
            "sha256_hash": "broadcast-language-fallback-smoke-sha256",
            "size_bytes": 102400,
            "width": 1024,
            "height": 576,
            "upload_status": "UPLOADED",
            "metadata": {
                "android_contract": "broadcast_language_fallback.v1",
                "fixture": "broadcast_language_fallback_delivery",
                "fallback_media_attachment": True,
            },
        },
    )
    check(asset["upload_status"] == "UPLOADED", "Fallback media asset is uploaded", asset)

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
                "android_contract": "broadcast_language_fallback.v1",
                "event_type": "LANGUAGE_FALLBACK_ADVISORY",
                "language_selection_backend_owned": True,
                "fallback_language_code": "en",
                "audience_match_mode": "ALL",
            },
            "contents": [
                {
                    "language_code": "en",
                    "title": EN_TITLE,
                    "body_text": EN_BODY,
                    "cta_label": CTA_LABEL,
                    "deeplink_url": DEEPLINK_URL,
                    "metadata": {"android_copy_role": "language_fallback_advisory", "fallback_content": True},
                },
                {
                    "language_code": "hi",
                    "title": HI_TITLE,
                    "body_text": HI_BODY,
                    "cta_label": CTA_LABEL,
                    "deeplink_url": DEEPLINK_URL,
                    "metadata": {"android_copy_role": "language_fallback_advisory", "native_language_content": True},
                },
            ],
            "audience_rules": [
                {
                    "rule_type": "FARMER",
                    "operator": "IN",
                    "values": [str(SELECTED_FARMER_ID)],
                    "metadata": {"reason": "single selected Android FPO farmer for language fallback smoke"},
                }
            ],
        },
    )
    english_content = next(row for row in campaign["contents"] if row["language_code"] == "en")
    attachment = request_json(
        client,
        "POST",
        "/api/v1/media/attachments",
        expected=201,
        body={
            "id": str(MEDIA_ATTACHMENT_ID),
            "media_asset_id": str(MEDIA_ASSET_ID),
            "entity_type": "ADVISORY",
            "entity_id": english_content["id"],
            "purpose": "ADVISORY_ATTACHMENT",
            "caption": CAPTION,
            "display_order": 1,
            "is_primary": True,
            "metadata": {"fallback_media_attachment": True, "text_fallback_required": True},
        },
    )
    check(attachment["entity_type"] == "ADVISORY" and attachment["purpose"] == "ADVISORY_ATTACHMENT", "English fallback content has media attachment", attachment)

    published = request_json(
        client,
        "POST",
        f"/api/v1/broadcasts/{CAMPAIGN_ID}/publish",
        body={"approved_by": str(ACTOR_ID), "reason": "Android language fallback smoke publish"},
    )
    generated = request_json(client, "POST", f"/api/v1/broadcasts/{CAMPAIGN_ID}/generate-deliveries")
    check(published["status"] == "PUBLISHED", "Campaign published", published)
    check(generated["delivery_summary"]["total"] == 1, "Single FARMER-targeted delivery generated", generated["delivery_summary"])
    return {"campaign": campaign, "english_content_id": english_content["id"], "attachment": attachment}


def select_campaign_item(feed: dict) -> dict:
    items = [row for row in feed.get("broadcasts", []) if row.get("campaign", {}).get("id") == str(CAMPAIGN_ID)]
    check(len(items) == 1, "Selected farmer feed includes exactly one language fallback campaign", feed)
    return items[0]


def verify_language_payloads(client: TestClient) -> dict:
    detail = request_json(client, "GET", f"/api/v1/broadcasts/{CAMPAIGN_ID}")
    languages = sorted(row["language_code"] for row in detail.get("contents", []))
    check(detail["status"] == "PUBLISHED", "Admin detail keeps campaign PUBLISHED", detail)
    check(languages == ["en", "hi"], "Admin detail exposes English and Hindi content", languages)
    check(detail["delivery_summary"]["total"] == 1, "Admin detail has one delivery", detail["delivery_summary"])

    hi_feed = request_json(client, "GET", f"/api/v1/broadcasts/farmers/{SELECTED_FARMER_ID}/broadcasts?language_code=hi&include_read=true")
    hi_item = select_campaign_item(hi_feed)
    check(hi_item["content"]["language_code"] == "hi", "Hindi request returns Hindi content", hi_item["content"])
    check(hi_item["content"]["title"] == HI_TITLE and hi_item["content"]["body_text"] == HI_BODY, "Hindi copy is backend-selected", hi_item["content"])

    fallback_feed = request_json(client, "GET", f"/api/v1/broadcasts/farmers/{SELECTED_FARMER_ID}/broadcasts?language_code=kn&include_read=true")
    fallback_item = select_campaign_item(fallback_feed)
    fallback_media = fallback_item["content"].get("media_attachments") or []
    check(fallback_item["content"]["language_code"] == "en", "Unsupported language request falls back to English", fallback_item["content"])
    check(fallback_item["content"]["title"] == EN_TITLE and fallback_item["content"]["body_text"] == EN_BODY, "English fallback copy is backend-selected", fallback_item["content"])
    check(len(fallback_media) == 1, "English fallback preserves media attachment", fallback_media)
    check(fallback_media[0]["storage_url"] == STORAGE_URL, "Fallback media storage URL is backend-provided", fallback_media[0])
    check((fallback_media[0].get("attachment") or {}).get("caption") == CAPTION, "Fallback media caption is present", fallback_media[0])

    default_feed = request_json(client, "GET", f"/api/v1/broadcasts/farmers/{SELECTED_FARMER_ID}/broadcasts?include_read=true")
    default_item = select_campaign_item(default_feed)
    check(default_item["content"]["language_code"] == "en", "Missing language_code defaults to English", default_item["content"])

    return {"detail": detail, "hi_feed": hi_feed, "fallback_feed": fallback_feed, "default_feed": default_feed, "hi_item": hi_item, "fallback_item": fallback_item}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Delete prior deterministic language fallback smoke state before running.")
    parser.add_argument("--apply", action="store_true", help="Create deterministic language fallback smoke state before verifying.")
    parser.add_argument("--cleanup", action="store_true", help="Delete deterministic language fallback smoke state and exit.")
    args = parser.parse_args()

    print("=" * 72)
    print("BROADCAST LANGUAGE FALLBACK DELIVERY VERIFIER")
    print("=" * 72)

    reset_counts = {}
    if args.reset or args.cleanup:
        reset_counts = cleanup_state()
        check(True, "Cleaned deterministic language fallback smoke state", reset_counts)
    if args.cleanup:
        print(json.dumps({
            "schema_version": "broadcast_language_fallback_delivery_verification.v1",
            "mode": "CLEANUP",
            "tenant_id": TENANT_ID,
            "project_id": str(PROJECT_ID),
            "campaign_id": str(CAMPAIGN_ID),
            "reset": reset_counts,
        }, indent=2, sort_keys=True, ensure_ascii=False))
        return 0

    client = TestClient(app)
    created = create_language_campaign(client) if args.apply else {}
    verified = verify_language_payloads(client)
    fallback_media = verified["fallback_item"]["content"].get("media_attachments") or []

    result = {
        "schema_version": "broadcast_language_fallback_delivery_verification.v1",
        "tenant_id": TENANT_ID,
        "project_id": str(PROJECT_ID),
        "campaign_id": str(CAMPAIGN_ID),
        "media_asset_id": str(MEDIA_ASSET_ID),
        "media_attachment_id": str(MEDIA_ATTACHMENT_ID),
        "selected_farmer_id": str(SELECTED_FARMER_ID),
        "selected_mobile": SELECTED_MOBILE,
        "reset": reset_counts,
        "created": {
            "english_content_id": created.get("english_content_id"),
        },
        "verified": {
            "content_languages": sorted(row["language_code"] for row in verified["detail"].get("contents", [])),
            "hi_request_language_code": verified["hi_item"]["content"]["language_code"],
            "unsupported_kn_request_language_code": verified["fallback_item"]["content"]["language_code"],
            "fallback_media_count": len(fallback_media),
            "fallback_media_type": fallback_media[0]["media_type"],
            "fallback_text_present": bool(verified["fallback_item"]["content"].get("body_text")),
        },
        "readiness": {
            "hindi_content_selection_covered": True,
            "unsupported_language_english_fallback_covered": True,
            "missing_language_english_default_covered": True,
            "fallback_media_attachment_covered": True,
            "backend_owned_language_selection_covered": True,
            "ready_for_android_broadcast_language_fallback_maestro": True,
            "ready_for_broadcast_language_fallback_web_smoke": True,
        },
        "cleanup_command": "cd ~/projects/farmint/backend && ../venv/bin/python scripts/verify_broadcast_language_fallback_delivery.py --cleanup",
    }
    print("=" * 72)
    print("BROADCAST LANGUAGE FALLBACK DELIVERY VERIFIED")
    print("=" * 72)
    print(json.dumps(result, indent=2, sort_keys=True, default=str, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
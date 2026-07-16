"""Regression for read-only broadcast campaign API."""

from datetime import datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Tenant
from app.modules.media.models import BroadcastAudienceRule, BroadcastCampaign, BroadcastContent, BroadcastDelivery


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
    print("BROADCAST API REGRESSION")
    print("=" * 72)

    tenant_id = f"broadcast-api-{uuid.uuid4().hex[:8]}"
    campaign_id = uuid.uuid4()
    farmer_id = uuid.uuid4()
    headers = {"X-Tenant-ID": tenant_id}

    db = SessionLocal()
    try:
        db.add(Tenant(id=tenant_id, name="Broadcast API Tenant", type="ENTERPRISE", created_at=now(), updated_at=now()))
        db.flush()

        db.add(BroadcastCampaign(
            id=campaign_id,
            tenant_id=tenant_id,
            title="Rice pest advisory",
            category="ADVISORY",
            priority="HIGH",
            status="DRAFT",
            metadata_={"targeting_mode": "RULE_BASED"},
            created_at=now(),
            updated_at=now(),
        ))
        db.flush()

        db.add(BroadcastContent(
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            language_code="en",
            title="Rice pest advisory",
            body_text="Inspect crop for pests.",
            cta_label="View",
            deeplink_url="agrios://broadcast/rice-pest",
            created_at=now(),
            updated_at=now(),
        ))
        db.add(BroadcastContent(
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            language_code="hi",
            title="Rice pest advisory Hindi",
            body_text="Inspect crop for pests.",
            created_at=now(),
            updated_at=now(),
        ))
        db.add(BroadcastAudienceRule(
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            rule_type="CROP",
            operator="IN",
            values=["RICE"],
            created_at=now(),
        ))
        db.add(BroadcastDelivery(
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            farmer_id=farmer_id,
            delivery_status="PENDING",
            created_at=now(),
            updated_at=now(),
        ))
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    print("\n[1] Create draft campaign via API")
    created_id = uuid.uuid4()
    create = client.post("/api/v1/broadcasts", headers=headers, json={
        "id": str(created_id),
        "title": "Weather alert draft",
        "category": "WEATHER",
        "priority": "URGENT",
        "metadata": {"targeting_mode": "RULE_BASED"},
        "contents": [
            {
                "language_code": "en",
                "title": "Weather alert",
                "body_text": "Heavy rainfall expected.",
                "cta_label": "View details",
                "deeplink_url": "agrios://broadcast/weather-alert"
            },
            {
                "language_code": "hi",
                "title": "Weather alert Hindi",
                "body_text": "Heavy rainfall expected."
            }
        ],
        "audience_rules": [
            {
                "rule_type": "LOCATION",
                "operator": "IN",
                "values": ["KARNATAKA"]
            },
            {
                "rule_type": "CROP",
                "operator": "IN",
                "values": ["RICE"]
            }
        ]
    })
    check(create.status_code == 201, "Create broadcast draft returns 201", create.text)
    created = create.json()
    check(created["id"] == str(created_id), "Create preserves requested campaign id")
    check(created["status"] == "DRAFT", "Created campaign starts as draft")
    check(created["category"] == "WEATHER", "Create normalizes category")
    check(created["priority"] == "URGENT", "Create normalizes priority")
    check(len(created["contents"]) == 2, "Create returns content rows")
    check(len(created["audience_rules"]) == 2, "Create returns audience rules")
    check(created["delivery_summary"]["total"] == 0, "Create does not generate deliveries yet")

    listing = client.get("/api/v1/broadcasts?status=DRAFT", headers=headers)
    check(listing.status_code == 200, "Broadcast list returns 200", listing.text)
    body = listing.json()
    check(body["schema_version"] == "broadcast_campaigns.v1", "Schema version stable")
    check(body["count"] >= 2, "List returns seeded and created campaigns")
    row = next(item for item in body["campaigns"] if item["id"] == str(campaign_id))
    check(row["id"] == str(campaign_id), "List preserves seeded campaign id")
    check(row["content_count"] == 2, "List includes content count")
    check(row["audience_rule_count"] == 1, "List includes rule count")
    check(row["delivery_count"] == 1, "List includes delivery count")

    detail = client.get(f"/api/v1/broadcasts/{campaign_id}", headers=headers)
    check(detail.status_code == 200, "Broadcast detail returns 200", detail.text)
    detail_body = detail.json()
    check(len(detail_body["contents"]) == 2, "Detail includes localized content")
    check({item["language_code"] for item in detail_body["contents"]} == {"en", "hi"}, "Detail preserves languages")
    check(len(detail_body["audience_rules"]) == 1, "Detail includes audience rules")
    check(detail_body["delivery_summary"]["total"] == 1, "Detail includes delivery summary")

    isolated = client.get(f"/api/v1/broadcasts/{campaign_id}", headers={"X-Tenant-ID": "default"})
    check(isolated.status_code == 404, "Broadcast detail tenant isolated", isolated.text)

    db = SessionLocal()
    try:
        db.query(BroadcastDelivery).filter(BroadcastDelivery.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(BroadcastAudienceRule).filter(BroadcastAudienceRule.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(BroadcastContent).filter(BroadcastContent.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(BroadcastCampaign).filter(BroadcastCampaign.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Tenant).filter(Tenant.id == tenant_id).delete(synchronize_session=False)
        db.commit()
        check(True, "Temporary rows cleaned up")
    finally:
        db.close()

    print("=" * 72)
    print("Broadcast API validated")
    print("=" * 72)


if __name__ == "__main__":
    main()
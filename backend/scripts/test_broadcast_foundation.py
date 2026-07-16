"""Regression for broadcast/advisory foundation tables."""

from datetime import datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
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
    print("BROADCAST FOUNDATION REGRESSION")
    print("=" * 72)

    tenant_id = f"broadcast-test-{uuid.uuid4().hex[:8]}"
    campaign_id = uuid.uuid4()
    farmer_id = uuid.uuid4()

    db = SessionLocal()
    try:
        db.add(Tenant(id=tenant_id, name="Broadcast Test Tenant", type="ENTERPRISE", created_at=now(), updated_at=now()))
        db.flush()

        campaign = BroadcastCampaign(
            id=campaign_id,
            tenant_id=tenant_id,
            title="Rice pest alert",
            category="ADVISORY",
            priority="HIGH",
            status="DRAFT",
            metadata_={"targeting_mode": "RULE_BASED"},
            created_at=now(),
            updated_at=now(),
        )
        db.add(campaign)
        db.flush()

        db.add(BroadcastContent(
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            language_code="en",
            title="Rice pest alert",
            body_text="Inspect fields for pest symptoms.",
            cta_label="View advisory",
            deeplink_url="agrios://advisory/rice-pest-alert",
            metadata_={"media_ready": False},
            created_at=now(),
            updated_at=now(),
        ))

        db.add(BroadcastAudienceRule(
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            rule_type="CROP",
            operator="IN",
            values=["RICE"],
            metadata_={"scope": "crop_specific"},
            created_at=now(),
        ))

        db.add(BroadcastAudienceRule(
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            rule_type="LOCATION",
            operator="IN",
            values=["KARNATAKA"],
            metadata_={"scope": "location_specific"},
            created_at=now(),
        ))

        db.add(BroadcastDelivery(
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            farmer_id=farmer_id,
            delivery_status="PENDING",
            metadata_={"channel": "IN_APP"},
            created_at=now(),
            updated_at=now(),
        ))

        db.commit()

        stored = db.query(BroadcastCampaign).filter(BroadcastCampaign.id == campaign_id, BroadcastCampaign.tenant_id == tenant_id).first()
        check(stored is not None, "Campaign stored")
        check(stored.title == "Rice pest alert", "Campaign title stored")
        check(stored.metadata_["targeting_mode"] == "RULE_BASED", "Campaign metadata stored")

        contents = db.query(BroadcastContent).filter(BroadcastContent.campaign_id == campaign_id).all()
        check(len(contents) == 1, "Localized content stored")
        check(contents[0].language_code == "en", "Content language stored")

        rules = db.query(BroadcastAudienceRule).filter(BroadcastAudienceRule.campaign_id == campaign_id).all()
        check(len(rules) == 2, "Audience rules stored")
        check({rule.rule_type for rule in rules} == {"CROP", "LOCATION"}, "Crop/location targeting stored")

        delivery = db.query(BroadcastDelivery).filter(BroadcastDelivery.campaign_id == campaign_id).first()
        check(delivery is not None, "Delivery row stored")
        check(delivery.delivery_status == "PENDING", "Delivery status stored")

    finally:
        db.query(BroadcastDelivery).filter(BroadcastDelivery.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(BroadcastAudienceRule).filter(BroadcastAudienceRule.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(BroadcastContent).filter(BroadcastContent.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(BroadcastCampaign).filter(BroadcastCampaign.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Tenant).filter(Tenant.id == tenant_id).delete(synchronize_session=False)
        db.commit()
        db.close()

    print("=" * 72)
    print("Broadcast foundation validated")
    print("=" * 72)


if __name__ == "__main__":
    main()
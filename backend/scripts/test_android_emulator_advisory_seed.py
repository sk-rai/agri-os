#!/usr/bin/env python3
"""Regression checks for the Android emulator advisory seed helper."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Farmer
from app.modules.media.models import BroadcastCampaign, BroadcastDelivery
from scripts.seed_android_emulator_advisories import SEED_PACK, seed_android_emulator_advisories


def check(condition, label, detail=None):
    if condition:
        print(f"  PASS {label}")
        if detail is not None:
            print(f"       {detail}")
        return
    print(f"  FAIL {label}")
    if detail is not None:
        print(f"       {detail}")
    raise AssertionError(label)


def main() -> int:
    print("=" * 72)
    print("ANDROID EMULATOR ADVISORY SEED REGRESSION")
    print("=" * 72)

    tenant_id = "default"
    db = SessionLocal()
    try:
        farmer = (
            db.query(Farmer)
            .filter(Farmer.tenant_id == tenant_id, Farmer.status == "ACTIVE")
            .order_by(Farmer.created_at.desc())
            .first()
        )
        check(farmer is not None, "At least one active default-tenant farmer exists")

        actor_id = uuid.uuid4()
        first = seed_android_emulator_advisories(
            db,
            tenant_id=tenant_id,
            project_id=None,
            farmer_ids=[farmer.id],
            limit_farmers=1,
            actor_id=actor_id,
            apply=True,
        )
        db.commit()
        check(first["selected_farmer_count"] == 1, "Seed selects requested farmer", first["selected_farmer_ids"])
        check(first["created_campaigns"] + first["updated_campaigns"] == 4, "Four advisory campaigns are upserted")

        second = seed_android_emulator_advisories(
            db,
            tenant_id=tenant_id,
            project_id=None,
            farmer_ids=[farmer.id],
            limit_farmers=1,
            actor_id=actor_id,
            apply=True,
        )
        db.commit()
        check(second["created_deliveries"] == 0, "Second seed run is delivery-idempotent", second)
        check(second["existing_deliveries"] >= 4, "Existing seeded deliveries are detected")

        campaign_count = (
            db.query(BroadcastCampaign)
            .filter(
                BroadcastCampaign.tenant_id == tenant_id,
                BroadcastCampaign.status == "PUBLISHED",
                BroadcastCampaign.is_active == True,
            )
            .all()
        )
        seeded_campaigns = [
            row for row in campaign_count
            if (row.metadata_ or {}).get("seed_pack") == SEED_PACK
        ]
        check(len(seeded_campaigns) >= 4, "Published seeded campaigns exist", len(seeded_campaigns))

        delivery_count = (
            db.query(BroadcastDelivery)
            .filter(
                BroadcastDelivery.tenant_id == tenant_id,
                BroadcastDelivery.farmer_id == farmer.id,
            )
            .count()
        )
        check(delivery_count >= 4, "Seeded farmer has broadcast deliveries", delivery_count)

        client = TestClient(app)
        for language_code in ("en", "hi"):
            response = client.get(
                f"/api/v1/broadcasts/farmers/{farmer.id}/broadcasts",
                params={"language_code": language_code, "include_read": True},
                headers={"X-Tenant-ID": tenant_id},
            )
            check(response.status_code == 200, f"Farmer broadcast feed returns 200 for {language_code}", response.text[:500])
            payload = response.json()
            check(payload["count"] >= 4, f"Farmer feed includes seeded advisories for {language_code}", payload["count"])
            first_titles = [
                item["content"]["title"]
                for item in payload["broadcasts"][:4]
                if item.get("content")
            ]
            check(bool(first_titles), f"Farmer feed returns localized content for {language_code}", first_titles)

    finally:
        db.close()

    print("=" * 72)
    print("Android emulator advisory seed validated")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

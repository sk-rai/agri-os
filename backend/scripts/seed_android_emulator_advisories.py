#!/usr/bin/env python3
"""Seed generic broadcast advisories for Android emulator testing.

The seed is intentionally operational-data only. It creates published broadcast
campaigns and pending farmer deliveries so Android can test feed/read/ack flows
without waiting for live advisory/provider integrations.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
from app.modules.farmer.models import Farmer, FarmerProjectEnrollment, Project
from app.modules.media.models import (
    BroadcastAudienceRule,
    BroadcastAuditEvent,
    BroadcastCampaign,
    BroadcastContent,
    BroadcastDelivery,
)


SEED_PACK = "ANDROID_EMULATOR_GENERIC_ADVISORIES"


ADVISORY_TEMPLATES: list[dict[str, Any]] = [
    {
        "seed_key": "weather-rain-irrigation-check",
        "title": "Android Emulator: Rain and irrigation advisory",
        "category": "WEATHER",
        "priority": "HIGH",
        "deeplink_url": "agrios://broadcasts/weather-rain-irrigation-check",
        "contents": {
            "en": {
                "title": "Rain likely: review irrigation",
                "body_text": "Light to moderate rain is expected. Avoid unnecessary irrigation and delay spraying until leaves are dry.",
                "cta_label": "View advisory",
            },
            "hi": {
                "title": "बारिश संभव: सिंचाई जांचें",
                "body_text": "हल्की से मध्यम बारिश की संभावना है। अनावश्यक सिंचाई न करें और पत्ते सूखने तक छिड़काव टालें।",
                "cta_label": "सलाह देखें",
            },
        },
    },
    {
        "seed_key": "crop-stage-pest-scouting",
        "title": "Android Emulator: Pest scouting reminder",
        "category": "ADVISORY",
        "priority": "NORMAL",
        "deeplink_url": "agrios://broadcasts/crop-stage-pest-scouting",
        "contents": {
            "en": {
                "title": "Scout crop for pest signs",
                "body_text": "Check 5 random spots in the field for leaf damage, larvae, or disease spots. Upload a photo if damage is visible.",
                "cta_label": "Open crop stage",
            },
            "hi": {
                "title": "कीट के लक्षण देखें",
                "body_text": "खेत में 5 जगह पत्ती की क्षति, सुंडी या रोग के धब्बे देखें। नुकसान दिखे तो फोटो अपलोड करें।",
                "cta_label": "फसल चरण खोलें",
            },
        },
    },
    {
        "seed_key": "input-application-safe-window",
        "title": "Android Emulator: Input application reminder",
        "category": "INPUT",
        "priority": "NORMAL",
        "deeplink_url": "agrios://broadcasts/input-application-safe-window",
        "contents": {
            "en": {
                "title": "Apply inputs in a safe window",
                "body_text": "Apply fertilizer or pesticide only when wind is low and rain is not immediate. Record input quantity and cost after application.",
                "cta_label": "Log activity",
            },
            "hi": {
                "title": "सुरक्षित समय में इनपुट डालें",
                "body_text": "हवा कम हो और तुरंत बारिश न हो तभी खाद या दवा डालें। बाद में मात्रा और खर्च जरूर दर्ज करें।",
                "cta_label": "गतिविधि दर्ज करें",
            },
        },
    },
    {
        "seed_key": "finance-cost-log-reminder",
        "title": "Android Emulator: Cost log reminder",
        "category": "GENERAL",
        "priority": "LOW",
        "deeplink_url": "agrios://broadcasts/finance-cost-log-reminder",
        "contents": {
            "en": {
                "title": "Keep crop costs updated",
                "body_text": "Add seed, fertilizer, labour, irrigation, and transport expenses by crop stage so P&L analytics stay accurate.",
                "cta_label": "Review costs",
            },
            "hi": {
                "title": "फसल खर्च अपडेट रखें",
                "body_text": "बीज, खाद, मजदूरी, सिंचाई और परिवहन खर्च फसल चरण के अनुसार जोड़ें ताकि P&L सही रहे।",
                "cta_label": "खर्च देखें",
            },
        },
    },
]


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, uuid.UUID)):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _load_project(db: Session, tenant_id: str, project_id: uuid.UUID | None) -> Project | None:
    if not project_id:
        return None
    project = (
        db.query(Project)
        .filter(Project.tenant_id == tenant_id, Project.id == project_id)
        .first()
    )
    if not project:
        raise SystemExit(f"Project {project_id} not found for tenant {tenant_id}")
    return project


def _select_farmers(
    db: Session,
    *,
    tenant_id: str,
    project_id: uuid.UUID | None,
    farmer_ids: list[uuid.UUID],
    limit_farmers: int,
) -> list[Farmer]:
    query = db.query(Farmer).filter(Farmer.tenant_id == tenant_id, Farmer.status == "ACTIVE")

    if farmer_ids:
        query = query.filter(Farmer.id.in_(farmer_ids))
    elif project_id:
        enrolled_ids = (
            db.query(FarmerProjectEnrollment.farmer_id)
            .filter(
                FarmerProjectEnrollment.tenant_id == tenant_id,
                FarmerProjectEnrollment.project_id == project_id,
                FarmerProjectEnrollment.status == "ACTIVE",
            )
        )
        query = query.filter(or_(Farmer.project_id == project_id, Farmer.id.in_(enrolled_ids)))

    return query.order_by(Farmer.created_at.desc()).limit(limit_farmers).all()


def _campaign_for_seed(db: Session, tenant_id: str, seed_key: str) -> BroadcastCampaign | None:
    rows = (
        db.query(BroadcastCampaign)
        .filter(BroadcastCampaign.tenant_id == tenant_id, BroadcastCampaign.is_active == True)
        .all()
    )
    for row in rows:
        metadata = row.metadata_ or {}
        if metadata.get("seed_pack") == SEED_PACK and metadata.get("seed_key") == seed_key:
            return row
    return None


def _upsert_content(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: uuid.UUID,
    language_code: str,
    content: dict[str, str],
    deeplink_url: str,
    now_ts: datetime,
    dry_run: bool,
) -> str:
    row = (
        db.query(BroadcastContent)
        .filter(
            BroadcastContent.tenant_id == tenant_id,
            BroadcastContent.campaign_id == campaign_id,
            BroadcastContent.language_code == language_code,
        )
        .first()
    )
    if row:
        if not dry_run:
            row.title = content["title"]
            row.body_text = content["body_text"]
            row.cta_label = content["cta_label"]
            row.deeplink_url = deeplink_url
            row.metadata_ = {"seed_pack": SEED_PACK}
            row.updated_at = now_ts
        return "updated"

    if not dry_run:
        db.add(BroadcastContent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            language_code=language_code,
            title=content["title"],
            body_text=content["body_text"],
            cta_label=content["cta_label"],
            deeplink_url=deeplink_url,
            metadata_={"seed_pack": SEED_PACK},
            created_at=now_ts,
            updated_at=now_ts,
        ))
    return "created"


def seed_android_emulator_advisories(
    db: Session,
    *,
    tenant_id: str,
    project_id: uuid.UUID | None,
    farmer_ids: list[uuid.UUID],
    limit_farmers: int,
    actor_id: uuid.UUID | None,
    apply: bool,
) -> dict[str, Any]:
    now_ts = datetime.now(timezone.utc)
    expires_at = now_ts + timedelta(days=45)
    dry_run = not apply

    project = _load_project(db, tenant_id, project_id)
    farmers = _select_farmers(
        db,
        tenant_id=tenant_id,
        project_id=project_id,
        farmer_ids=farmer_ids,
        limit_farmers=limit_farmers,
    )
    if not farmers:
        return {
            "schema_version": "android_emulator_advisory_seed_result.v1",
            "tenant_id": tenant_id,
            "project_id": str(project_id) if project_id else None,
            "mode": "APPLY" if apply else "DRY_RUN",
            "seed_pack": SEED_PACK,
            "selected_farmer_count": 0,
            "created_campaigns": 0,
            "updated_campaigns": 0,
            "created_deliveries": 0,
            "existing_deliveries": 0,
            "warnings": ["No active farmers matched the requested tenant/project/farmer filter."],
            "campaigns": [],
        }

    created_campaigns = 0
    updated_campaigns = 0
    created_deliveries = 0
    existing_deliveries = 0
    campaign_results = []

    for template in ADVISORY_TEMPLATES:
        seed_key = template["seed_key"]
        campaign = _campaign_for_seed(db, tenant_id, seed_key)
        campaign_was_created = campaign is None
        if campaign is None:
            campaign = BroadcastCampaign(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                project_id=project_id,
                title=template["title"],
                category=template["category"],
                priority=template["priority"],
                status="PUBLISHED",
                starts_at=now_ts - timedelta(minutes=5),
                expires_at=expires_at,
                created_by=actor_id,
                approved_by=actor_id,
                metadata_={
                    "seed_pack": SEED_PACK,
                    "seed_key": seed_key,
                    "android_emulator_seed": True,
                    "targeting_match_mode": "ANY",
                    "project_name": project.name if project else None,
                },
                is_active=True,
                created_at=now_ts,
                updated_at=now_ts,
            )
            if not dry_run:
                db.add(campaign)
                db.flush()
            created_campaigns += 1
        else:
            if not dry_run:
                metadata = dict(campaign.metadata_ or {})
                metadata.update({
                    "seed_pack": SEED_PACK,
                    "seed_key": seed_key,
                    "android_emulator_seed": True,
                    "targeting_match_mode": "ANY",
                    "project_name": project.name if project else metadata.get("project_name"),
                    "refreshed_at": now_ts.isoformat(),
                })
                campaign.project_id = project_id or campaign.project_id
                campaign.title = template["title"]
                campaign.category = template["category"]
                campaign.priority = template["priority"]
                campaign.status = "PUBLISHED"
                campaign.starts_at = now_ts - timedelta(minutes=5)
                campaign.expires_at = expires_at
                campaign.metadata_ = metadata
                campaign.is_active = True
                campaign.updated_at = now_ts
            updated_campaigns += 1

        content_actions = {}
        for language_code, content in template["contents"].items():
            content_actions[language_code] = _upsert_content(
                db,
                tenant_id=tenant_id,
                campaign_id=campaign.id,
                language_code=language_code,
                content=content,
                deeplink_url=template["deeplink_url"],
                now_ts=now_ts,
                dry_run=dry_run,
            )

        if not dry_run:
            existing_rule = (
                db.query(BroadcastAudienceRule)
                .filter(
                    BroadcastAudienceRule.tenant_id == tenant_id,
                    BroadcastAudienceRule.campaign_id == campaign.id,
                    BroadcastAudienceRule.rule_type == "FARMER",
                )
                .first()
            )
            farmer_id_values = [str(farmer.id) for farmer in farmers]
            if existing_rule:
                existing_rule.operator = "IN"
                existing_rule.values = farmer_id_values
                existing_rule.metadata_ = {"seed_pack": SEED_PACK, "seed_key": seed_key}
            else:
                db.add(BroadcastAudienceRule(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    campaign_id=campaign.id,
                    rule_type="FARMER",
                    operator="IN",
                    values=farmer_id_values,
                    metadata_={"seed_pack": SEED_PACK, "seed_key": seed_key},
                    created_at=now_ts,
                ))

        campaign_delivery_created = 0
        campaign_delivery_existing = 0
        for farmer in farmers:
            existing_delivery = (
                db.query(BroadcastDelivery)
                .filter(
                    BroadcastDelivery.tenant_id == tenant_id,
                    BroadcastDelivery.campaign_id == campaign.id,
                    BroadcastDelivery.farmer_id == farmer.id,
                )
                .first()
            )
            if existing_delivery:
                campaign_delivery_existing += 1
                if not dry_run:
                    metadata = dict(existing_delivery.metadata_ or {})
                    metadata.update({"seed_pack": SEED_PACK, "seed_key": seed_key, "refreshed_at": now_ts.isoformat()})
                    existing_delivery.delivery_status = existing_delivery.delivery_status or "PENDING"
                    existing_delivery.metadata_ = metadata
                    existing_delivery.updated_at = now_ts
                continue

            campaign_delivery_created += 1
            if not dry_run:
                db.add(BroadcastDelivery(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    campaign_id=campaign.id,
                    farmer_id=farmer.id,
                    user_id=farmer.user_id,
                    delivery_status="PENDING",
                    metadata_={
                        "seed_pack": SEED_PACK,
                        "seed_key": seed_key,
                        "generation_rule": "ANDROID_EMULATOR_SEED",
                    },
                    created_at=now_ts,
                    updated_at=now_ts,
                ))

        created_deliveries += campaign_delivery_created
        existing_deliveries += campaign_delivery_existing

        if not dry_run:
            db.add(BroadcastAuditEvent(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                campaign_id=campaign.id,
                action="ANDROID_EMULATOR_SEED_UPSERT",
                actor_type="ADMIN_WEB",
                actor_id=actor_id,
                before=None,
                after={
                    "campaign_created": campaign_was_created,
                    "farmer_count": len(farmers),
                    "delivery_created_count": campaign_delivery_created,
                    "delivery_existing_count": campaign_delivery_existing,
                },
                reason="Seed generic advisories for Android emulator testing.",
                metadata_={"seed_pack": SEED_PACK, "seed_key": seed_key},
                created_at=now_ts,
            ))

        campaign_results.append({
            "seed_key": seed_key,
            "campaign_id": str(campaign.id),
            "title": template["title"],
            "category": template["category"],
            "priority": template["priority"],
            "campaign_action": "created" if campaign_was_created else "updated",
            "content_actions": content_actions,
            "delivery_created_count": campaign_delivery_created,
            "delivery_existing_count": campaign_delivery_existing,
        })

    return {
        "schema_version": "android_emulator_advisory_seed_result.v1",
        "tenant_id": tenant_id,
        "project_id": str(project_id) if project_id else None,
        "mode": "APPLY" if apply else "DRY_RUN",
        "seed_pack": SEED_PACK,
        "selected_farmer_count": len(farmers),
        "selected_farmer_ids": [str(farmer.id) for farmer in farmers],
        "created_campaigns": created_campaigns,
        "updated_campaigns": updated_campaigns,
        "created_deliveries": created_deliveries,
        "existing_deliveries": existing_deliveries,
        "campaigns": campaign_results,
        "next_actions": [
            "Run with --apply to persist the seed pack." if dry_run else "Open Android broadcast feed for one selected_farmer_id.",
            "Use /api/v1/broadcasts/farmers/{farmer_id}/broadcasts?language_code=hi to verify Hindi content fallback.",
            "Use read and acknowledge endpoints to test delivery lifecycle.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed generic advisories for Android emulator broadcast testing.")
    parser.add_argument("--tenant-id", default="default")
    parser.add_argument("--project-id", type=uuid.UUID)
    parser.add_argument("--farmer-id", action="append", type=uuid.UUID, default=[], help="Specific farmer recipient. Can be repeated.")
    parser.add_argument("--limit-farmers", type=int, default=10)
    parser.add_argument("--actor-id", type=uuid.UUID)
    parser.add_argument("--apply", action="store_true", help="Persist seed data. Default is dry-run.")
    args = parser.parse_args()

    if args.limit_farmers < 1 or args.limit_farmers > 100:
        raise SystemExit("--limit-farmers must be between 1 and 100")

    db = SessionLocal()
    try:
        result = seed_android_emulator_advisories(
            db,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            farmer_ids=args.farmer_id,
            limit_farmers=args.limit_farmers,
            actor_id=args.actor_id,
            apply=args.apply,
        )
        if args.apply:
            db.commit()
        else:
            db.rollback()
        print(json.dumps(result, indent=2, sort_keys=True, default=_json_default, ensure_ascii=False))
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

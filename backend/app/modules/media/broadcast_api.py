"""Read-only broadcast/advisory campaign API."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.farmer.models import Farmer, Parcel
from app.modules.media.api import _iso
from app.modules.media.models import BroadcastAuditEvent, BroadcastAudienceRule, BroadcastCampaign, BroadcastContent, BroadcastDelivery, MediaAsset, MediaAttachment

router = APIRouter(prefix="/api/v1/broadcasts", tags=["broadcasts"])

BROADCAST_CATEGORIES = {"GENERAL", "ADVISORY", "WEATHER", "MARKET", "INPUT", "EMERGENCY"}
BROADCAST_PRIORITIES = {"LOW", "NORMAL", "HIGH", "URGENT"}
BROADCAST_STATUSES = {"DRAFT", "PUBLISHED", "EXPIRED", "CANCELLED", "ARCHIVED"}
AUDIENCE_RULE_TYPES = {"ALL", "PROJECT", "FARMER", "CROP", "STAGE", "LOCATION", "WEATHER", "FIELD_EVENT", "INPUT", "PRODUCT", "ROLE", "LANGUAGE"}
AUDIENCE_OPERATORS = {"IN", "NOT_IN", "EQUALS", "RADIUS", "ANY"}


class BroadcastContentCreate(BaseModel):
    language_code: str = Field("en", min_length=1, max_length=20)
    title: str = Field(..., min_length=1, max_length=200)
    body_text: str | None = None
    cta_label: str | None = None
    deeplink_url: str | None = None
    metadata: dict = Field(default_factory=dict)


class BroadcastAudienceRuleCreate(BaseModel):
    rule_type: str
    operator: str = "IN"
    values: list = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)

    @field_validator("rule_type")
    @classmethod
    def validate_rule_type(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in AUDIENCE_RULE_TYPES:
            raise ValueError(f"rule_type must be one of {sorted(AUDIENCE_RULE_TYPES)}")
        return normalized

    @field_validator("operator")
    @classmethod
    def validate_operator(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in AUDIENCE_OPERATORS:
            raise ValueError(f"operator must be one of {sorted(AUDIENCE_OPERATORS)}")
        return normalized


class BroadcastPublishRequest(BaseModel):
    approved_by: uuid.UUID | None = None
    reason: str | None = None


class BroadcastLifecycleRequest(BaseModel):
    actor_id: uuid.UUID | None = None
    reason: str | None = None


class BroadcastCampaignCreate(BaseModel):
    id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    title: str = Field(..., min_length=1, max_length=200)
    category: str = "GENERAL"
    priority: str = "NORMAL"
    starts_at: str | None = None
    expires_at: str | None = None
    created_by: uuid.UUID | None = None
    metadata: dict = Field(default_factory=dict)
    contents: list[BroadcastContentCreate] = Field(default_factory=list)
    audience_rules: list[BroadcastAudienceRuleCreate] = Field(default_factory=list)

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in BROADCAST_CATEGORIES:
            raise ValueError(f"category must be one of {sorted(BROADCAST_CATEGORIES)}")
        return normalized

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in BROADCAST_PRIORITIES:
            raise ValueError(f"priority must be one of {sorted(BROADCAST_PRIORITIES)}")
        return normalized



def _parse_optional_datetime(value):
    if not value:
        return None
    from datetime import datetime, timezone
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _media_asset_payload(row: MediaAsset, attachment: MediaAttachment | None = None) -> dict:
    payload = {
        "id": str(row.id),
        "tenant_id": row.tenant_id,
        "project_id": str(row.project_id) if row.project_id else None,
        "farmer_id": str(row.farmer_id) if row.farmer_id else None,
        "media_type": row.media_type,
        "mime_type": row.mime_type,
        "storage_url": row.storage_url,
        "storage_key": row.storage_key,
        "thumbnail_url": row.thumbnail_url,
        "sha256_hash": row.sha256_hash,
        "size_bytes": row.size_bytes,
        "duration_seconds": row.duration_seconds,
        "width": row.width,
        "height": row.height,
        "upload_status": row.upload_status,
        "metadata": row.metadata_ or {},
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }
    if attachment:
        payload["attachment"] = {
            "id": str(attachment.id),
            "entity_type": attachment.entity_type,
            "entity_id": str(attachment.entity_id),
            "purpose": attachment.purpose,
            "caption": attachment.caption,
            "display_order": attachment.display_order,
            "is_primary": attachment.is_primary,
            "metadata": attachment.metadata_ or {},
        }
    return payload


def _content_media_payloads(db: Session, *, tenant_id: str, content_id: uuid.UUID) -> list[dict]:
    rows = db.query(MediaAttachment, MediaAsset).join(
        MediaAsset,
        MediaAsset.id == MediaAttachment.media_asset_id,
    ).filter(
        MediaAttachment.tenant_id == tenant_id,
        MediaAttachment.entity_type == "ADVISORY",
        MediaAttachment.entity_id == content_id,
        MediaAsset.tenant_id == tenant_id,
    ).order_by(MediaAttachment.display_order.asc(), MediaAttachment.created_at.asc()).all()
    return [_media_asset_payload(asset, attachment) for attachment, asset in rows]


def _content_payload(row: BroadcastContent, db: Session | None = None) -> dict:
    payload = {
        "id": str(row.id),
        "tenant_id": row.tenant_id,
        "campaign_id": str(row.campaign_id),
        "language_code": row.language_code,
        "title": row.title,
        "body_text": row.body_text,
        "cta_label": row.cta_label,
        "deeplink_url": row.deeplink_url,
        "metadata": row.metadata_ or {},
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }
    if db is not None:
        payload["media_attachments"] = _content_media_payloads(db, tenant_id=row.tenant_id, content_id=row.id)
    return payload


def _rule_payload(row: BroadcastAudienceRule) -> dict:
    return {
        "id": str(row.id),
        "tenant_id": row.tenant_id,
        "campaign_id": str(row.campaign_id),
        "rule_type": row.rule_type,
        "operator": row.operator,
        "values": row.values or [],
        "metadata": row.metadata_ or {},
        "created_at": _iso(row.created_at),
    }


def _select_content_for_language(contents: list[BroadcastContent], language_code: str | None) -> BroadcastContent | None:
    if not contents:
        return None
    preferred = (language_code or "en").lower()
    for row in contents:
        if row.language_code.lower() == preferred:
            return row
    for row in contents:
        if row.language_code.lower() == "en":
            return row
    return contents[0]


def _delivery_payload(row: BroadcastDelivery) -> dict:
    return {
        "id": str(row.id),
        "tenant_id": row.tenant_id,
        "campaign_id": str(row.campaign_id),
        "farmer_id": str(row.farmer_id) if row.farmer_id else None,
        "user_id": str(row.user_id) if row.user_id else None,
        "delivery_status": row.delivery_status,
        "delivered_at": _iso(row.delivered_at),
        "read_at": _iso(row.read_at),
        "acknowledged_at": _iso(row.acknowledged_at),
        "failure_reason": row.failure_reason,
        "metadata": row.metadata_ or {},
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _delivery_summary(rows: list[BroadcastDelivery]) -> dict:
    return {
        "total": len(rows),
        "pending": sum(1 for row in rows if row.delivery_status == "PENDING"),
        "delivered": sum(1 for row in rows if row.delivery_status == "DELIVERED"),
        "read": sum(1 for row in rows if row.read_at is not None),
        "acknowledged": sum(1 for row in rows if row.acknowledged_at is not None),
        "failed": sum(1 for row in rows if row.delivery_status == "FAILED"),
    }


def _audit_payload(row: BroadcastAuditEvent) -> dict:
    return {
        "id": str(row.id),
        "tenant_id": row.tenant_id,
        "campaign_id": str(row.campaign_id),
        "delivery_id": str(row.delivery_id) if row.delivery_id else None,
        "action": row.action,
        "actor_type": row.actor_type,
        "actor_id": str(row.actor_id) if row.actor_id else None,
        "before": row.before or {},
        "after": row.after or {},
        "reason": row.reason,
        "metadata": row.metadata_ or {},
        "created_at": _iso(row.created_at),
    }


def _record_broadcast_audit(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: uuid.UUID,
    action: str,
    delivery_id: uuid.UUID | None = None,
    actor_type: str | None = None,
    actor_id: uuid.UUID | None = None,
    before: dict | None = None,
    after: dict | None = None,
    reason: str | None = None,
    metadata: dict | None = None,
):
    from datetime import datetime, timezone

    db.add(BroadcastAuditEvent(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        delivery_id=delivery_id,
        action=action,
        actor_type=actor_type,
        actor_id=actor_id,
        before=before or {},
        after=after or {},
        reason=reason,
        metadata_=metadata or {},
        created_at=datetime.now(timezone.utc),
    ))


def _campaign_payload(row: BroadcastCampaign, *, content_count: int = 0, rule_count: int = 0, delivery_count: int = 0) -> dict:
    return {
        "id": str(row.id),
        "tenant_id": row.tenant_id,
        "project_id": str(row.project_id) if row.project_id else None,
        "title": row.title,
        "category": row.category,
        "priority": row.priority,
        "status": row.status,
        "starts_at": _iso(row.starts_at),
        "expires_at": _iso(row.expires_at),
        "created_by": str(row.created_by) if row.created_by else None,
        "approved_by": str(row.approved_by) if row.approved_by else None,
        "metadata": row.metadata_ or {},
        "is_active": row.is_active,
        "content_count": content_count,
        "audience_rule_count": rule_count,
        "delivery_count": delivery_count,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


@router.post("", status_code=201)
def create_broadcast_campaign(
    body: BroadcastCampaignCreate,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    from datetime import datetime, timezone
    now_ts = datetime.now(timezone.utc)
    campaign = BroadcastCampaign(
        id=body.id or uuid.uuid4(),
        tenant_id=x_tenant_id,
        project_id=body.project_id,
        title=body.title,
        category=body.category,
        priority=body.priority,
        status="DRAFT",
        starts_at=_parse_optional_datetime(body.starts_at),
        expires_at=_parse_optional_datetime(body.expires_at),
        created_by=body.created_by,
        metadata_=body.metadata or {},
        is_active=True,
        created_at=now_ts,
        updated_at=now_ts,
    )
    db.add(campaign)
    db.flush()

    for content_body in body.contents:
        db.add(BroadcastContent(
            id=uuid.uuid4(),
            tenant_id=x_tenant_id,
            campaign_id=campaign.id,
            language_code=content_body.language_code,
            title=content_body.title,
            body_text=content_body.body_text,
            cta_label=content_body.cta_label,
            deeplink_url=content_body.deeplink_url,
            metadata_=content_body.metadata or {},
            created_at=now_ts,
            updated_at=now_ts,
        ))

    for rule_body in body.audience_rules:
        db.add(BroadcastAudienceRule(
            id=uuid.uuid4(),
            tenant_id=x_tenant_id,
            campaign_id=campaign.id,
            rule_type=rule_body.rule_type,
            operator=rule_body.operator,
            values=rule_body.values or [],
            metadata_=rule_body.metadata or {},
            created_at=now_ts,
        ))

    _record_broadcast_audit(db, tenant_id=x_tenant_id, campaign_id=campaign.id, action="CREATE_CAMPAIGN", actor_type="ADMIN_WEB", actor_id=body.created_by, after={"status": campaign.status, "title": campaign.title, "category": campaign.category, "priority": campaign.priority}, metadata={"content_count": len(body.contents), "audience_rule_count": len(body.audience_rules)})
    db.commit()
    db.refresh(campaign)
    payload = _campaign_payload(campaign, content_count=len(body.contents), rule_count=len(body.audience_rules), delivery_count=0)
    payload["contents"] = [_content_payload(row, db) for row in db.query(BroadcastContent).filter(BroadcastContent.tenant_id == x_tenant_id, BroadcastContent.campaign_id == campaign.id).order_by(BroadcastContent.language_code.asc()).all()]
    payload["audience_rules"] = [_rule_payload(row) for row in db.query(BroadcastAudienceRule).filter(BroadcastAudienceRule.tenant_id == x_tenant_id, BroadcastAudienceRule.campaign_id == campaign.id).order_by(BroadcastAudienceRule.rule_type.asc()).all()]
    payload["delivery_summary"] = {"total": 0, "pending": 0, "delivered": 0, "read": 0, "acknowledged": 0, "failed": 0}
    return payload



@router.post("/{campaign_id}/contents", status_code=201)
def add_broadcast_content(
    campaign_id: uuid.UUID,
    body: BroadcastContentCreate,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    from datetime import datetime, timezone

    campaign = db.query(BroadcastCampaign).filter(BroadcastCampaign.id == campaign_id, BroadcastCampaign.tenant_id == x_tenant_id, BroadcastCampaign.is_active == True).first()
    if not campaign:
        raise HTTPException(404, "Broadcast campaign not found")
    if campaign.status != "DRAFT":
        raise HTTPException(409, "Only DRAFT broadcasts can be edited")

    now_ts = datetime.now(timezone.utc)
    row = BroadcastContent(
        id=uuid.uuid4(),
        tenant_id=x_tenant_id,
        campaign_id=campaign.id,
        language_code=body.language_code,
        title=body.title,
        body_text=body.body_text,
        cta_label=body.cta_label,
        deeplink_url=body.deeplink_url,
        metadata_=body.metadata or {},
        created_at=now_ts,
        updated_at=now_ts,
    )
    db.add(row)
    campaign.updated_at = now_ts
    _record_broadcast_audit(db, tenant_id=x_tenant_id, campaign_id=campaign.id, action="ADD_CONTENT", actor_type="ADMIN_WEB", after={"content_id": str(row.id), "language_code": row.language_code, "title": row.title})
    db.commit()
    db.refresh(campaign)
    return _broadcast_detail_payload(db, campaign, x_tenant_id)


@router.post("/{campaign_id}/audience-rules", status_code=201)
def add_broadcast_audience_rule(
    campaign_id: uuid.UUID,
    body: BroadcastAudienceRuleCreate,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    from datetime import datetime, timezone

    campaign = db.query(BroadcastCampaign).filter(BroadcastCampaign.id == campaign_id, BroadcastCampaign.tenant_id == x_tenant_id, BroadcastCampaign.is_active == True).first()
    if not campaign:
        raise HTTPException(404, "Broadcast campaign not found")
    if campaign.status != "DRAFT":
        raise HTTPException(409, "Only DRAFT broadcasts can be edited")

    now_ts = datetime.now(timezone.utc)
    row = BroadcastAudienceRule(
        id=uuid.uuid4(),
        tenant_id=x_tenant_id,
        campaign_id=campaign.id,
        rule_type=body.rule_type,
        operator=body.operator,
        values=body.values or [],
        metadata_=body.metadata or {},
        created_at=now_ts,
    )
    db.add(row)
    campaign.updated_at = now_ts
    _record_broadcast_audit(db, tenant_id=x_tenant_id, campaign_id=campaign.id, action="ADD_AUDIENCE_RULE", actor_type="ADMIN_WEB", after={"rule_id": str(row.id), "rule_type": row.rule_type, "operator": row.operator, "values": row.values or []})
    db.commit()
    db.refresh(campaign)
    return _broadcast_detail_payload(db, campaign, x_tenant_id)




def _broadcast_detail_payload(db: Session, campaign: BroadcastCampaign, tenant_id: str) -> dict:
    contents = db.query(BroadcastContent).filter(BroadcastContent.tenant_id == tenant_id, BroadcastContent.campaign_id == campaign.id).order_by(BroadcastContent.language_code.asc()).all()
    rules = db.query(BroadcastAudienceRule).filter(BroadcastAudienceRule.tenant_id == tenant_id, BroadcastAudienceRule.campaign_id == campaign.id).order_by(BroadcastAudienceRule.rule_type.asc()).all()
    deliveries = db.query(BroadcastDelivery).filter(BroadcastDelivery.tenant_id == tenant_id, BroadcastDelivery.campaign_id == campaign.id).all()

    payload = _campaign_payload(campaign, content_count=len(contents), rule_count=len(rules), delivery_count=len(deliveries))
    payload["contents"] = [_content_payload(row, db) for row in contents]
    payload["audience_rules"] = [_rule_payload(row) for row in rules]
    payload["delivery_summary"] = _delivery_summary(deliveries)
    return payload


def _resolve_broadcast_audience(db: Session, *, tenant_id: str, campaign_id: uuid.UUID) -> dict:
    rules = db.query(BroadcastAudienceRule).filter(
        BroadcastAudienceRule.tenant_id == tenant_id,
        BroadcastAudienceRule.campaign_id == campaign_id,
    ).order_by(BroadcastAudienceRule.rule_type.asc()).all()

    farmer_ids: set[str] = set()
    farmer_match_reasons: dict[str, set[str]] = {}
    rule_summaries = []
    unsupported_rule_count = 0

    for rule in rules:
        values = rule.values or []
        matched: set[str] = set()
        supported = True
        note = None

        if rule.rule_type == "ALL":
            matched.update(str(row.id) for row in db.query(Farmer.id).filter(Farmer.tenant_id == tenant_id, Farmer.status == "ACTIVE").all())
        elif rule.rule_type == "PROJECT":
            project_ids = []
            for value in values:
                try:
                    project_ids.append(uuid.UUID(str(value)))
                except ValueError:
                    continue
            if project_ids:
                matched.update(
                    str(row.id)
                    for row in db.query(Farmer.id).filter(
                        Farmer.tenant_id == tenant_id,
                        Farmer.status == "ACTIVE",
                        Farmer.project_id.in_(project_ids),
                    ).all()
                )
        elif rule.rule_type == "CROP":
            from app.modules.workflow.models import CropCycle

            crop_codes = [str(value).upper() for value in values if value]
            if crop_codes:
                matched.update(
                    str(row[0])
                    for row in db.query(CropCycle.farmer_id).filter(
                        CropCycle.tenant_id == tenant_id,
                        CropCycle.crop_code.in_(crop_codes),
                        CropCycle.status == "ACTIVE",
                    ).distinct().all()
                    if row[0]
                )
        elif rule.rule_type == "FARMER":
            for value in values:
                try:
                    matched.add(str(uuid.UUID(str(value))))
                except ValueError:
                    continue
        elif rule.rule_type == "LANGUAGE":
            language_codes = {str(value).strip().lower() for value in values if str(value).strip()}
            if language_codes:
                matched.update(
                    str(row.id)
                    for row in db.query(Farmer.id).filter(
                        Farmer.tenant_id == tenant_id,
                        Farmer.status == "ACTIVE",
                        Farmer.language_preference.in_(language_codes),
                    ).all()
                )
        elif rule.rule_type == "LOCATION":
            location_names = {str(value).strip().upper() for value in values if str(value).strip()}
            location_ids = []
            for value in values:
                try:
                    location_ids.append(uuid.UUID(str(value)))
                except ValueError:
                    continue
            if location_names:
                matched.update(
                    str(farmer_id)
                    for farmer_id, village_name in db.query(Farmer.id, Farmer.village_name_manual).filter(
                        Farmer.tenant_id == tenant_id,
                        Farmer.status == "ACTIVE",
                        Farmer.village_name_manual.isnot(None),
                    ).all()
                    if str(village_name or "").strip().upper() in location_names
                )
                matched.update(
                    str(farmer_id)
                    for farmer_id, village_name in db.query(Parcel.farmer_id, Parcel.village_name_manual).filter(
                        Parcel.tenant_id == tenant_id,
                        Parcel.status == "ACTIVE",
                        Parcel.village_name_manual.isnot(None),
                    ).distinct().all()
                    if farmer_id and str(village_name or "").strip().upper() in location_names
                )
            if location_ids:
                matched.update(
                    str(row.id)
                    for row in db.query(Farmer.id).filter(
                        Farmer.tenant_id == tenant_id,
                        Farmer.status == "ACTIVE",
                        Farmer.village_id.in_(location_ids),
                    ).all()
                )
                matched.update(
                    str(row[0])
                    for row in db.query(Parcel.farmer_id).filter(
                        Parcel.tenant_id == tenant_id,
                        Parcel.status == "ACTIVE",
                        Parcel.village_id.in_(location_ids),
                    ).distinct().all()
                    if row[0]
                )
        else:
            supported = False
            note = "Rule accepted for campaign configuration but not yet expanded into delivery recipients."
            unsupported_rule_count += 1

        if supported:
            farmer_ids.update(matched)
            for farmer_id in matched:
                farmer_match_reasons.setdefault(farmer_id, set()).add(rule.rule_type)

        rule_summaries.append({
            "rule_id": str(rule.id),
            "rule_type": rule.rule_type,
            "operator": rule.operator,
            "values": values,
            "supported": supported,
            "matched_farmer_count": len(matched),
            "sample_farmer_ids": sorted(matched)[:10],
            "note": note,
        })

    return {
        "farmer_ids": sorted(farmer_ids),
        "sample_matches": [
            {"farmer_id": farmer_id, "matched_by": sorted(farmer_match_reasons.get(farmer_id, set()))}
            for farmer_id in sorted(farmer_ids)[:25]
        ],
        "match_reason_counts": {
            rule_type: sum(1 for reasons in farmer_match_reasons.values() if rule_type in reasons)
            for rule_type in sorted({rule for reasons in farmer_match_reasons.values() for rule in reasons})
        },
        "rule_summaries": rule_summaries,
        "unsupported_rule_count": unsupported_rule_count,
    }


@router.get("")
def list_broadcast_campaigns(
    project_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    query = db.query(BroadcastCampaign).filter(BroadcastCampaign.tenant_id == x_tenant_id, BroadcastCampaign.is_active == True)
    if project_id:
        query = query.filter(BroadcastCampaign.project_id == project_id)
    if status:
        query = query.filter(BroadcastCampaign.status == status.upper())
    if category:
        query = query.filter(BroadcastCampaign.category == category.upper())
    if priority:
        query = query.filter(BroadcastCampaign.priority == priority.upper())

    rows = query.order_by(BroadcastCampaign.created_at.desc()).limit(limit).all()
    return {
        "schema_version": "broadcast_campaigns.v1",
        "tenant_id": x_tenant_id,
        "filters": {
            "project_id": str(project_id) if project_id else None,
            "status": status.upper() if status else None,
            "category": category.upper() if category else None,
            "priority": priority.upper() if priority else None,
            "limit": limit,
        },
        "count": len(rows),
        "campaigns": [
            _campaign_payload(
                row,
                content_count=db.query(BroadcastContent).filter(BroadcastContent.tenant_id == x_tenant_id, BroadcastContent.campaign_id == row.id).count(),
                rule_count=db.query(BroadcastAudienceRule).filter(BroadcastAudienceRule.tenant_id == x_tenant_id, BroadcastAudienceRule.campaign_id == row.id).count(),
                delivery_count=db.query(BroadcastDelivery).filter(BroadcastDelivery.tenant_id == x_tenant_id, BroadcastDelivery.campaign_id == row.id).count(),
            )
            for row in rows
        ],
    }


@router.post("/{campaign_id}/publish")
def publish_broadcast_campaign(
    campaign_id: uuid.UUID,
    body: BroadcastPublishRequest | None = None,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    from datetime import datetime, timezone

    campaign = db.query(BroadcastCampaign).filter(BroadcastCampaign.id == campaign_id, BroadcastCampaign.tenant_id == x_tenant_id, BroadcastCampaign.is_active == True).first()
    if not campaign:
        raise HTTPException(404, "Broadcast campaign not found")
    if campaign.status != "DRAFT":
        raise HTTPException(409, "Only DRAFT broadcasts can be published")

    content_count = db.query(BroadcastContent).filter(BroadcastContent.tenant_id == x_tenant_id, BroadcastContent.campaign_id == campaign.id).count()
    if content_count == 0:
        raise HTTPException(400, "Broadcast requires at least one content row before publishing")

    now_ts = datetime.now(timezone.utc)
    campaign.status = "PUBLISHED"
    campaign.approved_by = body.approved_by if body else None
    if campaign.starts_at is None:
        campaign.starts_at = now_ts
    metadata = dict(campaign.metadata_ or {})
    metadata["publish_reason"] = body.reason if body else None
    metadata["published_at"] = now_ts.isoformat()
    metadata["delivery_generation"] = "NOT_STARTED"
    campaign.metadata_ = metadata
    campaign.updated_at = now_ts
    _record_broadcast_audit(db, tenant_id=x_tenant_id, campaign_id=campaign.id, action="PUBLISH_CAMPAIGN", actor_type="ADMIN_WEB", actor_id=campaign.approved_by, before={"status": "DRAFT"}, after={"status": campaign.status, "starts_at": _iso(campaign.starts_at)}, reason=body.reason if body else None, metadata={"content_count": content_count})
    db.commit()
    db.refresh(campaign)

    contents = db.query(BroadcastContent).filter(BroadcastContent.tenant_id == x_tenant_id, BroadcastContent.campaign_id == campaign.id).order_by(BroadcastContent.language_code.asc()).all()
    rules = db.query(BroadcastAudienceRule).filter(BroadcastAudienceRule.tenant_id == x_tenant_id, BroadcastAudienceRule.campaign_id == campaign.id).order_by(BroadcastAudienceRule.rule_type.asc()).all()
    payload = _campaign_payload(campaign, content_count=len(contents), rule_count=len(rules), delivery_count=0)
    payload["contents"] = [_content_payload(row, db) for row in contents]
    payload["audience_rules"] = [_rule_payload(row) for row in rules]
    payload["delivery_summary"] = {"total": 0, "pending": 0, "delivered": 0, "read": 0, "acknowledged": 0, "failed": 0}
    return payload



def _transition_broadcast_status(
    db: Session,
    *,
    campaign_id: uuid.UUID,
    tenant_id: str,
    target_status: str,
    allowed_from: set[str],
    action: str,
    body: BroadcastLifecycleRequest | None = None,
):
    from datetime import datetime, timezone

    campaign = db.query(BroadcastCampaign).filter(BroadcastCampaign.id == campaign_id, BroadcastCampaign.tenant_id == tenant_id, BroadcastCampaign.is_active == True).first()
    if not campaign:
        raise HTTPException(404, "Broadcast campaign not found")
    if campaign.status not in allowed_from:
        allowed = ", ".join(sorted(allowed_from))
        raise HTTPException(409, f"Only {allowed} broadcasts can transition to {target_status}")

    now_ts = datetime.now(timezone.utc)
    before_status = campaign.status
    metadata = dict(campaign.metadata_ or {})
    metadata[f"{target_status.lower()}_reason"] = body.reason if body else None
    metadata[f"{target_status.lower()}_at"] = now_ts.isoformat()
    campaign.status = target_status
    if target_status == "EXPIRED" and campaign.expires_at is None:
        campaign.expires_at = now_ts
    campaign.metadata_ = metadata
    campaign.updated_at = now_ts

    _record_broadcast_audit(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign.id,
        action=action,
        actor_type="ADMIN_WEB",
        actor_id=body.actor_id if body else None,
        before={"status": before_status},
        after={"status": campaign.status, "expires_at": _iso(campaign.expires_at)},
        reason=body.reason if body else None,
    )
    db.commit()
    db.refresh(campaign)
    return _broadcast_detail_payload(db, campaign, tenant_id)




@router.post("/{campaign_id}/generate-deliveries")
def generate_broadcast_deliveries(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    from datetime import datetime, timezone

    campaign = db.query(BroadcastCampaign).filter(BroadcastCampaign.id == campaign_id, BroadcastCampaign.tenant_id == x_tenant_id, BroadcastCampaign.is_active == True).first()
    if not campaign:
        raise HTTPException(404, "Broadcast campaign not found")
    if campaign.status != "PUBLISHED":
        raise HTTPException(409, "Only PUBLISHED broadcasts can generate deliveries")

    resolved = _resolve_broadcast_audience(db, tenant_id=x_tenant_id, campaign_id=campaign.id)
    farmer_ids = set(resolved["farmer_ids"])

    if not resolved["rule_summaries"]:
        return _broadcast_detail_payload(db, campaign, x_tenant_id)

    now_ts = datetime.now(timezone.utc)
    existing = {
        str(row.farmer_id)
        for row in db.query(BroadcastDelivery).filter(BroadcastDelivery.tenant_id == x_tenant_id, BroadcastDelivery.campaign_id == campaign.id, BroadcastDelivery.farmer_id.isnot(None)).all()
    }
    skipped_existing = len(farmer_ids.intersection(existing))

    created = 0
    for farmer_id_text in sorted(farmer_ids):
        farmer_id = uuid.UUID(str(farmer_id_text))
        if str(farmer_id) in existing:
            continue
        farmer = db.query(Farmer).filter(Farmer.id == farmer_id, Farmer.tenant_id == x_tenant_id).first()
        if not farmer:
            continue
        db.add(BroadcastDelivery(
            id=uuid.uuid4(),
            tenant_id=x_tenant_id,
            campaign_id=campaign.id,
            farmer_id=farmer.id,
            delivery_status="PENDING",
            metadata_={"generation_rule": "BASIC_AUDIENCE_RULES"},
            created_at=now_ts,
            updated_at=now_ts,
        ))
        created += 1

    metadata = dict(campaign.metadata_ or {})
    metadata["delivery_generation"] = "GENERATED"
    metadata["last_delivery_generation_targeted"] = len(farmer_ids)
    metadata["last_delivery_generation_existing"] = len(existing)
    metadata["last_delivery_generation_created"] = created
    metadata["last_delivery_generation_skipped_existing"] = skipped_existing
    metadata["last_delivery_generation_at"] = now_ts.isoformat()
    campaign.metadata_ = metadata
    campaign.updated_at = now_ts
    _record_broadcast_audit(db, tenant_id=x_tenant_id, campaign_id=campaign.id, action="GENERATE_DELIVERIES", actor_type="ADMIN_WEB", after={"created": created, "total_targeted": len(farmer_ids), "skipped_existing": skipped_existing}, metadata={"unsupported_rule_count": resolved.get("unsupported_rule_count", 0), "existing_delivery_count": len(existing)})
    db.commit()
    db.refresh(campaign)
    return _broadcast_detail_payload(db, campaign, x_tenant_id)




@router.post("/{campaign_id}/retry-undelivered")
def retry_undelivered_broadcast_deliveries(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    from datetime import datetime, timezone

    campaign = db.query(BroadcastCampaign).filter(BroadcastCampaign.id == campaign_id, BroadcastCampaign.tenant_id == x_tenant_id, BroadcastCampaign.is_active == True).first()
    if not campaign:
        raise HTTPException(404, "Broadcast campaign not found")
    if campaign.status != "PUBLISHED":
        raise HTTPException(409, "Only PUBLISHED broadcasts can retry deliveries")

    now_ts = datetime.now(timezone.utc)
    max_retries = 3
    rows = db.query(BroadcastDelivery).filter(
        BroadcastDelivery.tenant_id == x_tenant_id,
        BroadcastDelivery.campaign_id == campaign.id,
        BroadcastDelivery.delivery_status.in_(["PENDING", "FAILED"]),
    ).all()

    retried = 0
    marked_failed = 0
    skipped_acknowledged = db.query(BroadcastDelivery).filter(
        BroadcastDelivery.tenant_id == x_tenant_id,
        BroadcastDelivery.campaign_id == campaign.id,
        BroadcastDelivery.delivery_status.in_(["DELIVERED", "ACKNOWLEDGED"]),
    ).count()

    for row in rows:
        metadata = dict(row.metadata_ or {})
        retry_count = int(metadata.get("retry_count") or 0)
        if retry_count >= max_retries:
            if row.delivery_status != "FAILED":
                row.delivery_status = "FAILED"
                row.failure_reason = "MAX_RETRIES_EXCEEDED"
                row.updated_at = now_ts
                marked_failed += 1
            continue
        retry_count += 1
        metadata["retry_count"] = retry_count
        metadata["max_retries"] = max_retries
        metadata["last_retry_at"] = now_ts.isoformat()
        row.metadata_ = metadata
        row.updated_at = now_ts
        retried += 1
        if retry_count >= max_retries:
            row.delivery_status = "FAILED"
            row.failure_reason = "MAX_RETRIES_EXCEEDED"
            marked_failed += 1

    metadata = dict(campaign.metadata_ or {})
    metadata["last_delivery_retry_at"] = now_ts.isoformat()
    metadata["last_delivery_retry_retried"] = retried
    metadata["last_delivery_retry_marked_failed"] = marked_failed
    metadata["last_delivery_retry_skipped_acknowledged"] = skipped_acknowledged
    campaign.metadata_ = metadata
    campaign.updated_at = now_ts

    _record_broadcast_audit(
        db,
        tenant_id=x_tenant_id,
        campaign_id=campaign.id,
        action="RETRY_DELIVERIES",
        actor_type="ADMIN_WEB",
        after={"retried": retried, "marked_failed": marked_failed, "skipped_acknowledged": skipped_acknowledged},
        metadata={"max_retries": max_retries},
    )
    db.commit()
    db.refresh(campaign)
    return _broadcast_detail_payload(db, campaign, x_tenant_id)




@router.post("/{campaign_id}/expire")
def expire_broadcast_campaign(
    campaign_id: uuid.UUID,
    body: BroadcastLifecycleRequest | None = None,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    return _transition_broadcast_status(
        db,
        campaign_id=campaign_id,
        tenant_id=x_tenant_id,
        target_status="EXPIRED",
        allowed_from={"PUBLISHED"},
        action="EXPIRE_CAMPAIGN",
        body=body,
    )


@router.post("/{campaign_id}/cancel")
def cancel_broadcast_campaign(
    campaign_id: uuid.UUID,
    body: BroadcastLifecycleRequest | None = None,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    return _transition_broadcast_status(
        db,
        campaign_id=campaign_id,
        tenant_id=x_tenant_id,
        target_status="CANCELLED",
        allowed_from={"DRAFT", "PUBLISHED"},
        action="CANCEL_CAMPAIGN",
        body=body,
    )




@router.get("/{campaign_id}/deliveries")
def list_broadcast_deliveries(
    campaign_id: uuid.UUID,
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    campaign = db.query(BroadcastCampaign).filter(BroadcastCampaign.id == campaign_id, BroadcastCampaign.tenant_id == x_tenant_id, BroadcastCampaign.is_active == True).first()
    if not campaign:
        raise HTTPException(404, "Broadcast campaign not found")

    query = db.query(BroadcastDelivery).filter(BroadcastDelivery.tenant_id == x_tenant_id, BroadcastDelivery.campaign_id == campaign.id)
    if status:
        query = query.filter(BroadcastDelivery.delivery_status == status.upper())

    rows = query.order_by(BroadcastDelivery.created_at.desc()).limit(limit).all()
    farmer_ids = [row.farmer_id for row in rows if row.farmer_id]
    farmers = {}
    if farmer_ids:
        farmers = {
            row.id: row
            for row in db.query(Farmer).filter(Farmer.tenant_id == x_tenant_id, Farmer.id.in_(farmer_ids)).all()
        }

    deliveries = []
    for row in rows:
        payload = _delivery_payload(row)
        farmer = farmers.get(row.farmer_id) if row.farmer_id else None
        payload["farmer"] = {
            "id": str(farmer.id),
            "display_name": farmer.display_name,
            "mobile_number": farmer.mobile_number,
            "village_name_manual": farmer.village_name_manual,
            "status": farmer.status,
        } if farmer else None
        deliveries.append(payload)

    return {
        "schema_version": "broadcast_deliveries.v1",
        "tenant_id": x_tenant_id,
        "campaign_id": str(campaign.id),
        "filters": {"status": status.upper() if status else None, "limit": limit},
        "count": len(deliveries),
        "deliveries": deliveries,
    }


@router.get("/{campaign_id}/audience-preview")
def preview_broadcast_audience(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    campaign = db.query(BroadcastCampaign).filter(BroadcastCampaign.id == campaign_id, BroadcastCampaign.tenant_id == x_tenant_id, BroadcastCampaign.is_active == True).first()
    if not campaign:
        raise HTTPException(404, "Broadcast campaign not found")

    resolved = _resolve_broadcast_audience(db, tenant_id=x_tenant_id, campaign_id=campaign.id)
    existing_delivery_count = db.query(BroadcastDelivery).filter(BroadcastDelivery.tenant_id == x_tenant_id, BroadcastDelivery.campaign_id == campaign.id).count()
    return {
        "schema_version": "broadcast_audience_preview.v1",
        "tenant_id": x_tenant_id,
        "campaign_id": str(campaign.id),
        "campaign_status": campaign.status,
        "estimated_farmer_count": len(resolved["farmer_ids"]),
        "sample_farmer_ids": resolved["farmer_ids"][:20],
        "sample_matches": resolved["sample_matches"],
        "match_reason_counts": resolved["match_reason_counts"],
        "rule_summaries": resolved["rule_summaries"],
        "unsupported_rule_count": resolved["unsupported_rule_count"],
        "existing_delivery_count": existing_delivery_count,
    }


@router.get("/{campaign_id}/audit")
def list_broadcast_audit_events(
    campaign_id: uuid.UUID,
    action: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    campaign = db.query(BroadcastCampaign).filter(BroadcastCampaign.id == campaign_id, BroadcastCampaign.tenant_id == x_tenant_id, BroadcastCampaign.is_active == True).first()
    if not campaign:
        raise HTTPException(404, "Broadcast campaign not found")

    query = db.query(BroadcastAuditEvent).filter(BroadcastAuditEvent.tenant_id == x_tenant_id, BroadcastAuditEvent.campaign_id == campaign.id)
    if action:
        query = query.filter(BroadcastAuditEvent.action == action.upper())
    rows = query.order_by(BroadcastAuditEvent.created_at.desc()).limit(limit).all()
    return {
        "schema_version": "broadcast_audit_events.v1",
        "tenant_id": x_tenant_id,
        "campaign_id": str(campaign.id),
        "filters": {"action": action.upper() if action else None, "limit": limit},
        "count": len(rows),
        "events": [_audit_payload(row) for row in rows],
    }


@router.get("/{campaign_id}")
def get_broadcast_campaign(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    campaign = db.query(BroadcastCampaign).filter(BroadcastCampaign.id == campaign_id, BroadcastCampaign.tenant_id == x_tenant_id, BroadcastCampaign.is_active == True).first()
    if not campaign:
        raise HTTPException(404, "Broadcast campaign not found")

    contents = db.query(BroadcastContent).filter(BroadcastContent.tenant_id == x_tenant_id, BroadcastContent.campaign_id == campaign.id).order_by(BroadcastContent.language_code.asc()).all()
    rules = db.query(BroadcastAudienceRule).filter(BroadcastAudienceRule.tenant_id == x_tenant_id, BroadcastAudienceRule.campaign_id == campaign.id).order_by(BroadcastAudienceRule.rule_type.asc()).all()
    deliveries = db.query(BroadcastDelivery).filter(BroadcastDelivery.tenant_id == x_tenant_id, BroadcastDelivery.campaign_id == campaign.id).all()

    payload = _campaign_payload(campaign, content_count=len(contents), rule_count=len(rules), delivery_count=len(deliveries))
    payload["contents"] = [_content_payload(row, db) for row in contents]
    payload["audience_rules"] = [_rule_payload(row) for row in rules]
    payload["delivery_summary"] = {
        "total": len(deliveries),
        "pending": sum(1 for row in deliveries if row.delivery_status == "PENDING"),
        "delivered": sum(1 for row in deliveries if row.delivery_status == "DELIVERED"),
        "read": sum(1 for row in deliveries if row.read_at is not None),
        "acknowledged": sum(1 for row in deliveries if row.acknowledged_at is not None),
        "failed": sum(1 for row in deliveries if row.delivery_status == "FAILED"),
    }
    return payload




@router.post("/deliveries/{delivery_id}/read")
def mark_broadcast_delivery_read(
    delivery_id: uuid.UUID,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    from datetime import datetime, timezone

    delivery = db.query(BroadcastDelivery).filter(BroadcastDelivery.id == delivery_id, BroadcastDelivery.tenant_id == x_tenant_id).first()
    if not delivery:
        raise HTTPException(404, "Broadcast delivery not found")

    now_ts = datetime.now(timezone.utc)
    if delivery.delivered_at is None:
        delivery.delivered_at = now_ts
    if delivery.read_at is None:
        delivery.read_at = now_ts
    if delivery.delivery_status == "PENDING":
        delivery.delivery_status = "DELIVERED"
    delivery.updated_at = now_ts
    _record_broadcast_audit(db, tenant_id=x_tenant_id, campaign_id=delivery.campaign_id, delivery_id=delivery.id, action="MARK_DELIVERY_READ", actor_type="FARMER", actor_id=delivery.farmer_id, before={"delivery_status": "PENDING"}, after={"delivery_status": delivery.delivery_status})
    db.commit()
    db.refresh(delivery)
    return _delivery_payload(delivery)


@router.post("/deliveries/{delivery_id}/acknowledge")
def acknowledge_broadcast_delivery(
    delivery_id: uuid.UUID,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    from datetime import datetime, timezone

    delivery = db.query(BroadcastDelivery).filter(BroadcastDelivery.id == delivery_id, BroadcastDelivery.tenant_id == x_tenant_id).first()
    if not delivery:
        raise HTTPException(404, "Broadcast delivery not found")

    now_ts = datetime.now(timezone.utc)
    if delivery.delivered_at is None:
        delivery.delivered_at = now_ts
    if delivery.read_at is None:
        delivery.read_at = now_ts
    if delivery.acknowledged_at is None:
        delivery.acknowledged_at = now_ts
    delivery.delivery_status = "ACKNOWLEDGED"
    delivery.updated_at = now_ts
    _record_broadcast_audit(db, tenant_id=x_tenant_id, campaign_id=delivery.campaign_id, delivery_id=delivery.id, action="ACKNOWLEDGE_DELIVERY", actor_type="FARMER", actor_id=delivery.farmer_id, before={"delivery_status": "DELIVERED"}, after={"delivery_status": delivery.delivery_status})
    db.commit()
    db.refresh(delivery)
    return _delivery_payload(delivery)


@router.get("/farmers/{farmer_id}/broadcasts")
def list_farmer_broadcasts(
    farmer_id: uuid.UUID,
    language_code: str | None = Query(None),
    include_read: bool = Query(True),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    farmer = db.query(Farmer).filter(Farmer.id == farmer_id, Farmer.tenant_id == x_tenant_id).first()
    if not farmer:
        raise HTTPException(404, "Farmer not found")

    from datetime import datetime, timezone
    from sqlalchemy import or_

    now_ts = datetime.now(timezone.utc)
    query = (
        db.query(BroadcastDelivery, BroadcastCampaign)
        .join(BroadcastCampaign, BroadcastCampaign.id == BroadcastDelivery.campaign_id)
        .filter(
            BroadcastDelivery.tenant_id == x_tenant_id,
            BroadcastDelivery.farmer_id == farmer_id,
            BroadcastCampaign.tenant_id == x_tenant_id,
            BroadcastCampaign.status == "PUBLISHED",
            BroadcastCampaign.is_active == True,
            or_(BroadcastCampaign.starts_at.is_(None), BroadcastCampaign.starts_at <= now_ts),
            or_(BroadcastCampaign.expires_at.is_(None), BroadcastCampaign.expires_at > now_ts),
        )
    )
    if not include_read:
        query = query.filter(BroadcastDelivery.read_at.is_(None))

    rows = query.order_by(BroadcastCampaign.starts_at.desc().nullslast(), BroadcastCampaign.created_at.desc()).limit(limit).all()
    items = []
    for delivery, campaign in rows:
        contents = db.query(BroadcastContent).filter(
            BroadcastContent.tenant_id == x_tenant_id,
            BroadcastContent.campaign_id == campaign.id,
        ).order_by(BroadcastContent.language_code.asc()).all()
        selected_content = _select_content_for_language(contents, language_code)
        items.append({
            "campaign": _campaign_payload(campaign, content_count=len(contents), rule_count=db.query(BroadcastAudienceRule).filter(BroadcastAudienceRule.tenant_id == x_tenant_id, BroadcastAudienceRule.campaign_id == campaign.id).count(), delivery_count=1),
            "content": _content_payload(selected_content, db) if selected_content else None,
            "delivery": _delivery_payload(delivery),
        })

    return {
        "schema_version": "farmer_broadcasts.v1",
        "tenant_id": x_tenant_id,
        "farmer_id": str(farmer_id),
        "filters": {
            "language_code": language_code,
            "include_read": include_read,
            "limit": limit,
        },
        "count": len(items),
        "broadcasts": items,
    }

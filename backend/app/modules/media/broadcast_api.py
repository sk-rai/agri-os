"""Read-only broadcast/advisory campaign API."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.media.api import _iso
from app.modules.media.models import BroadcastAudienceRule, BroadcastCampaign, BroadcastContent, BroadcastDelivery

router = APIRouter(prefix="/api/v1/broadcasts", tags=["broadcasts"])

BROADCAST_CATEGORIES = {"GENERAL", "ADVISORY", "WEATHER", "MARKET", "INPUT", "EMERGENCY"}
BROADCAST_PRIORITIES = {"LOW", "NORMAL", "HIGH", "URGENT"}
BROADCAST_STATUSES = {"DRAFT", "PUBLISHED", "EXPIRED", "ARCHIVED"}
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


def _content_payload(row: BroadcastContent) -> dict:
    return {
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

    db.commit()
    db.refresh(campaign)
    payload = _campaign_payload(campaign, content_count=len(body.contents), rule_count=len(body.audience_rules), delivery_count=0)
    payload["contents"] = [_content_payload(row) for row in db.query(BroadcastContent).filter(BroadcastContent.tenant_id == x_tenant_id, BroadcastContent.campaign_id == campaign.id).order_by(BroadcastContent.language_code.asc()).all()]
    payload["audience_rules"] = [_rule_payload(row) for row in db.query(BroadcastAudienceRule).filter(BroadcastAudienceRule.tenant_id == x_tenant_id, BroadcastAudienceRule.campaign_id == campaign.id).order_by(BroadcastAudienceRule.rule_type.asc()).all()]
    payload["delivery_summary"] = {"total": 0, "pending": 0, "delivered": 0, "read": 0, "acknowledged": 0, "failed": 0}
    return payload


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
    payload["contents"] = [_content_payload(row) for row in contents]
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

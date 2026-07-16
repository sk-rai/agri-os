"""Read-only broadcast/advisory campaign API."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.media.api import _iso
from app.modules.media.models import BroadcastAudienceRule, BroadcastCampaign, BroadcastContent, BroadcastDelivery

router = APIRouter(prefix="/api/v1/broadcasts", tags=["broadcasts"])


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

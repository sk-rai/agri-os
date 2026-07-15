"""Farmer query thread and message API."""

from datetime import datetime, timezone
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.farmer.models import Farmer, Parcel, Project
from app.modules.media.api import PURPOSES, _asset_payload, _attachment_payload, _iso
from app.modules.media.models import MediaAsset, MediaAttachment, QueryMessage, QueryThread, QueryThreadAudit

router = APIRouter(prefix="/api/v1/query-threads", tags=["query-threads"])

QUERY_CATEGORIES = {"CROP_HEALTH", "INPUT_USAGE", "IRRIGATION", "MARKET", "INSURANCE", "TECH_SUPPORT", "OTHER"}
QUERY_PRIORITIES = {"LOW", "MEDIUM", "HIGH", "URGENT"}
QUERY_STATUSES = {"OPEN", "ASSIGNED", "ANSWERED", "CLOSED"}
QUERY_SENDER_TYPES = {"FARMER", "FIELD_AGENT", "AGRONOMIST", "ADMIN", "SYSTEM"}
QUERY_MESSAGE_TYPES = {"TEXT", "AUDIO", "PHOTO", "DOCUMENT", "SYSTEM"}


def _thread_payload(thread: QueryThread, message_count: int = 0, attachment_count: int = 0) -> dict:
    return {
        "id": str(thread.id),
        "tenant_id": thread.tenant_id,
        "project_id": str(thread.project_id) if thread.project_id else None,
        "farmer_id": str(thread.farmer_id),
        "parcel_id": str(thread.parcel_id) if thread.parcel_id else None,
        "crop_cycle_id": str(thread.crop_cycle_id) if thread.crop_cycle_id else None,
        "stage_code": thread.stage_code,
        "subject": thread.subject,
        "category": thread.category,
        "priority": thread.priority,
        "status": thread.status,
        "assigned_to": str(thread.assigned_to) if thread.assigned_to else None,
        "last_message_at": _iso(thread.last_message_at),
        "metadata": thread.metadata_ or {},
        "message_count": message_count,
        "media_attachment_count": attachment_count,
        "created_at": _iso(thread.created_at),
        "updated_at": _iso(thread.updated_at),
    }


def _audit_payload(event: QueryThreadAudit) -> dict:
    return {
        "id": str(event.id),
        "tenant_id": event.tenant_id,
        "thread_id": str(event.thread_id),
        "action": event.action,
        "actor_type": event.actor_type,
        "actor_id": str(event.actor_id) if event.actor_id else None,
        "before": event.before or {},
        "after": event.after or {},
        "reason": event.reason,
        "metadata": event.metadata_ or {},
        "created_at": _iso(event.created_at),
    }


def _record_audit(
    db: Session,
    *,
    tenant_id: str,
    thread_id,
    action: str,
    actor_type: Optional[str] = None,
    actor_id=None,
    before: Optional[dict] = None,
    after: Optional[dict] = None,
    reason: Optional[str] = None,
    metadata: Optional[dict] = None,
    timestamp: Optional[datetime] = None,
):
    event = QueryThreadAudit(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        thread_id=thread_id,
        action=action,
        actor_type=actor_type,
        actor_id=actor_id,
        before=before or {},
        after=after or {},
        reason=reason,
        metadata_=metadata or {},
        created_at=timestamp or datetime.now(timezone.utc),
    )
    db.add(event)
    return event


def _message_payload(message: QueryMessage, attachment_count: int = 0) -> dict:
    return {
        "id": str(message.id),
        "tenant_id": message.tenant_id,
        "thread_id": str(message.thread_id),
        "sender_type": message.sender_type,
        "sender_id": str(message.sender_id) if message.sender_id else None,
        "message_type": message.message_type,
        "body_text": message.body_text,
        "metadata": message.metadata_ or {},
        "media_attachment_count": attachment_count,
        "created_at": _iso(message.created_at),
        "updated_at": _iso(message.updated_at),
    }


class QueryMessageAttachmentCreate(BaseModel):
    media_asset_id: uuid.UUID
    purpose: str = "QUERY_ATTACHMENT"
    caption: Optional[str] = None
    display_order: int = 0
    is_primary: bool = False
    metadata: dict = Field(default_factory=dict)

    @field_validator("purpose")
    @classmethod
    def validate_purpose(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in PURPOSES:
            raise ValueError(f"purpose must be one of {sorted(PURPOSES)}")
        return normalized


class QueryMessageCreate(BaseModel):
    id: Optional[uuid.UUID] = None
    sender_type: str = "FARMER"
    sender_id: Optional[uuid.UUID] = None
    message_type: str = "TEXT"
    body_text: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
    media_attachments: list[QueryMessageAttachmentCreate] = Field(default_factory=list)

    @field_validator("sender_type")
    @classmethod
    def validate_sender_type(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in QUERY_SENDER_TYPES:
            raise ValueError(f"sender_type must be one of {sorted(QUERY_SENDER_TYPES)}")
        return normalized

    @field_validator("message_type")
    @classmethod
    def validate_message_type(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in QUERY_MESSAGE_TYPES:
            raise ValueError(f"message_type must be one of {sorted(QUERY_MESSAGE_TYPES)}")
        return normalized


class QueryThreadCreate(BaseModel):
    id: Optional[uuid.UUID] = None
    project_id: Optional[uuid.UUID] = None
    farmer_id: uuid.UUID
    parcel_id: Optional[uuid.UUID] = None
    crop_cycle_id: Optional[uuid.UUID] = None
    stage_code: Optional[str] = Field(None, max_length=50)
    subject: str = Field(..., min_length=1, max_length=200)
    category: str = "OTHER"
    priority: str = "MEDIUM"
    assigned_to: Optional[uuid.UUID] = None
    metadata: dict = Field(default_factory=dict)
    initial_message: Optional[QueryMessageCreate] = None

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in QUERY_CATEGORIES:
            raise ValueError(f"category must be one of {sorted(QUERY_CATEGORIES)}")
        return normalized

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in QUERY_PRIORITIES:
            raise ValueError(f"priority must be one of {sorted(QUERY_PRIORITIES)}")
        return normalized


class QueryThreadStatusPatch(BaseModel):
    status: str
    assigned_to: Optional[uuid.UUID] = None
    reason: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in QUERY_STATUSES:
            raise ValueError(f"status must be one of {sorted(QUERY_STATUSES)}")
        return normalized


def _create_message(db: Session, *, tenant_id: str, thread: QueryThread, body: QueryMessageCreate, timestamp: datetime):
    message = QueryMessage(
        id=body.id or uuid.uuid4(),
        tenant_id=tenant_id,
        thread_id=thread.id,
        sender_type=body.sender_type,
        sender_id=body.sender_id,
        message_type=body.message_type,
        body_text=body.body_text,
        metadata_=body.metadata or {},
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(message)
    db.flush()
    attachments = []
    for attachment_body in body.media_attachments:
        asset = db.query(MediaAsset).filter(MediaAsset.id == attachment_body.media_asset_id, MediaAsset.tenant_id == tenant_id).first()
        if not asset:
            raise HTTPException(404, f"Media asset {attachment_body.media_asset_id} not found")
        attachment = MediaAttachment(
            tenant_id=tenant_id,
            media_asset_id=asset.id,
            entity_type="QUERY_MESSAGE",
            entity_id=message.id,
            purpose=attachment_body.purpose,
            caption=attachment_body.caption,
            display_order=attachment_body.display_order,
            is_primary=attachment_body.is_primary,
            metadata_=attachment_body.metadata or {},
            created_at=timestamp,
            updated_at=timestamp,
        )
        db.add(attachment)
        attachments.append((attachment, asset))
    thread.last_message_at = timestamp
    thread.updated_at = timestamp
    if body.sender_type in {"AGRONOMIST", "ADMIN", "FIELD_AGENT", "SYSTEM"} and thread.status == "OPEN":
        thread.status = "ANSWERED"
    return message, attachments
@router.post("", status_code=201)
def create_query_thread(
    body: QueryThreadCreate,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    farmer = db.query(Farmer).filter(Farmer.id == body.farmer_id, Farmer.tenant_id == x_tenant_id).first()
    if not farmer:
        raise HTTPException(404, "Farmer not found")
    if body.project_id and not db.query(Project).filter(Project.id == body.project_id, Project.tenant_id == x_tenant_id).first():
        raise HTTPException(404, "Project not found")
    if body.parcel_id and not db.query(Parcel).filter(Parcel.id == body.parcel_id, Parcel.tenant_id == x_tenant_id, Parcel.farmer_id == body.farmer_id).first():
        raise HTTPException(404, "Parcel not found")

    timestamp = datetime.now(timezone.utc)
    thread = QueryThread(
        id=body.id or uuid.uuid4(),
        tenant_id=x_tenant_id,
        project_id=body.project_id,
        farmer_id=body.farmer_id,
        parcel_id=body.parcel_id,
        crop_cycle_id=body.crop_cycle_id,
        stage_code=body.stage_code,
        subject=body.subject,
        category=body.category,
        priority=body.priority,
        status="ASSIGNED" if body.assigned_to else "OPEN",
        assigned_to=body.assigned_to,
        metadata_=body.metadata or {},
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(thread)
    db.flush()

    message = None
    attachments = []
    if body.initial_message:
        message, attachments = _create_message(db, tenant_id=x_tenant_id, thread=thread, body=body.initial_message, timestamp=timestamp)

    _record_audit(
        db,
        tenant_id=x_tenant_id,
        thread_id=thread.id,
        action="CREATE_THREAD",
        actor_type=body.initial_message.sender_type if body.initial_message else "SYSTEM",
        actor_id=body.initial_message.sender_id if body.initial_message else None,
        after={"status": thread.status, "subject": thread.subject, "category": thread.category, "priority": thread.priority},
        metadata={"has_initial_message": bool(body.initial_message)},
        timestamp=timestamp,
    )

    db.commit()
    db.refresh(thread)
    payload = _thread_payload(thread, 1 if message else 0, len(attachments))
    if message:
        message_payload = _message_payload(message, len(attachments))
        if attachments:
            message_payload["media_attachments"] = [_attachment_payload(attachment, asset) for attachment, asset in attachments]
        payload["messages"] = [message_payload]
    return payload


@router.get("")
def list_query_threads(
    project_id: Optional[uuid.UUID] = Query(None),
    farmer_id: Optional[uuid.UUID] = Query(None),
    parcel_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    query = db.query(QueryThread).filter(QueryThread.tenant_id == x_tenant_id, QueryThread.is_active == True)
    if project_id:
        query = query.filter(QueryThread.project_id == project_id)
    if farmer_id:
        query = query.filter(QueryThread.farmer_id == farmer_id)
    if parcel_id:
        query = query.filter(QueryThread.parcel_id == parcel_id)
    if status:
        normalized_status = status.upper()
        if normalized_status not in QUERY_STATUSES:
            raise HTTPException(400, "Invalid status")
        query = query.filter(QueryThread.status == normalized_status)
    if category:
        normalized_category = category.upper()
        if normalized_category not in QUERY_CATEGORIES:
            raise HTTPException(400, "Invalid category")
        query = query.filter(QueryThread.category == normalized_category)
    rows = query.order_by(QueryThread.last_message_at.desc().nullslast(), QueryThread.created_at.desc()).limit(limit).all()
    return {
        "schema_version": "query_threads.v1",
        "tenant_id": x_tenant_id,
        "filters": {
            "project_id": str(project_id) if project_id else None,
            "farmer_id": str(farmer_id) if farmer_id else None,
            "parcel_id": str(parcel_id) if parcel_id else None,
            "status": status.upper() if status else None,
            "category": category.upper() if category else None,
            "limit": limit,
        },
        "count": len(rows),
        "threads": [
            _thread_payload(
                row,
                db.query(QueryMessage).filter(QueryMessage.tenant_id == x_tenant_id, QueryMessage.thread_id == row.id, QueryMessage.is_active == True).count(),
                db.query(MediaAttachment).filter(MediaAttachment.tenant_id == x_tenant_id, MediaAttachment.entity_type == "QUERY_THREAD", MediaAttachment.entity_id == row.id).count(),
            )
            for row in rows
        ],
    }


@router.get("/{thread_id}")
def get_query_thread(
    thread_id: uuid.UUID,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    thread = db.query(QueryThread).filter(QueryThread.id == thread_id, QueryThread.tenant_id == x_tenant_id, QueryThread.is_active == True).first()
    if not thread:
        raise HTTPException(404, "Query thread not found")
    messages = db.query(QueryMessage).filter(QueryMessage.tenant_id == x_tenant_id, QueryMessage.thread_id == thread.id, QueryMessage.is_active == True).order_by(QueryMessage.created_at.asc()).all()
    payload = _thread_payload(thread, len(messages), 0)
    payload["messages"] = []
    for message in messages:
        attachments = (
            db.query(MediaAttachment, MediaAsset)
            .join(MediaAsset, MediaAsset.id == MediaAttachment.media_asset_id)
            .filter(MediaAttachment.tenant_id == x_tenant_id, MediaAttachment.entity_type == "QUERY_MESSAGE", MediaAttachment.entity_id == message.id)
            .order_by(MediaAttachment.display_order.asc(), MediaAttachment.created_at.desc())
            .all()
        )
        message_payload = _message_payload(message, len(attachments))
        message_payload["media_attachments"] = [_attachment_payload(attachment, asset) for attachment, asset in attachments]
        payload["messages"].append(message_payload)
    payload["media_attachment_count"] = sum(message["media_attachment_count"] for message in payload["messages"])
    audit_events = db.query(QueryThreadAudit).filter(
        QueryThreadAudit.tenant_id == x_tenant_id,
        QueryThreadAudit.thread_id == thread.id,
    ).order_by(QueryThreadAudit.created_at.asc()).all()
    payload["audit_events"] = [_audit_payload(event) for event in audit_events]
    return payload


@router.post("/{thread_id}/messages", status_code=201)
def create_query_message(
    thread_id: uuid.UUID,
    body: QueryMessageCreate,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    thread = db.query(QueryThread).filter(QueryThread.id == thread_id, QueryThread.tenant_id == x_tenant_id, QueryThread.is_active == True).first()
    if not thread:
        raise HTTPException(404, "Query thread not found")
    timestamp = datetime.now(timezone.utc)
    message, attachments = _create_message(db, tenant_id=x_tenant_id, thread=thread, body=body, timestamp=timestamp)
    _record_audit(
        db,
        tenant_id=x_tenant_id,
        thread_id=thread.id,
        action="ADD_MESSAGE",
        actor_type=body.sender_type,
        actor_id=body.sender_id,
        after={"message_id": str(message.id), "message_type": message.message_type, "status": thread.status},
        metadata={"media_attachment_count": len(attachments)},
        timestamp=timestamp,
    )
    db.commit()
    db.refresh(message)
    payload = _message_payload(message, len(attachments))
    if attachments:
        payload["media_attachments"] = [_attachment_payload(attachment, asset) for attachment, asset in attachments]
    return payload


@router.patch("/{thread_id}/status")
def update_query_thread_status(
    thread_id: uuid.UUID,
    body: QueryThreadStatusPatch,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    thread = db.query(QueryThread).filter(QueryThread.id == thread_id, QueryThread.tenant_id == x_tenant_id, QueryThread.is_active == True).first()
    if not thread:
        raise HTTPException(404, "Query thread not found")
    before = {"status": thread.status, "assigned_to": str(thread.assigned_to) if thread.assigned_to else None}
    timestamp = datetime.now(timezone.utc)
    metadata = thread.metadata_ or {}
    history = metadata.get("status_history") or []
    history.append({"from_status": thread.status, "to_status": body.status, "reason": body.reason, "at": timestamp.isoformat()})
    metadata["status_history"] = history
    thread.status = body.status
    if body.assigned_to is not None:
        thread.assigned_to = body.assigned_to
    thread.metadata_ = metadata
    thread.updated_at = timestamp
    _record_audit(
        db,
        tenant_id=x_tenant_id,
        thread_id=thread.id,
        action="UPDATE_STATUS",
        actor_type="ADMIN",
        actor_id=body.assigned_to,
        before=before,
        after={"status": thread.status, "assigned_to": str(thread.assigned_to) if thread.assigned_to else None},
        reason=body.reason,
        timestamp=timestamp,
    )
    db.add(thread)
    db.commit()
    db.refresh(thread)
    messages = db.query(QueryMessage).filter(QueryMessage.tenant_id == x_tenant_id, QueryMessage.thread_id == thread.id, QueryMessage.is_active == True).order_by(QueryMessage.created_at.asc()).all()
    payload = _thread_payload(thread, len(messages), 0)
    audit_events = db.query(QueryThreadAudit).filter(
        QueryThreadAudit.tenant_id == x_tenant_id,
        QueryThreadAudit.thread_id == thread.id,
    ).order_by(QueryThreadAudit.created_at.asc()).all()
    payload["audit_events"] = [_audit_payload(event) for event in audit_events]
    return payload

"""Shared media metadata and attachment API."""

from datetime import datetime, timezone
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.admin_auth import AdminPermission, ROLE_PERMISSIONS
from app.core.database import get_db
from app.core.human_auth import AuthenticatedPrincipal, require_authenticated_human
from app.core.human_persona_scope import resolve_human_persona_scope
from app.modules.farmer.models import Farmer, FarmerProjectEnrollment, Parcel, Project
from app.modules.media.models import (
    BroadcastCampaign,
    BroadcastContent,
    FieldEventReport,
    MediaAsset,
    MediaAttachment,
)

router = APIRouter(prefix="/api/v1/media", tags=["media"])
field_events_router = APIRouter(prefix="/api/v1/field-events", tags=["field-events"])

MEDIA_TYPES = {"PHOTO", "AUDIO", "VIDEO", "DOCUMENT"}
UPLOAD_STATUSES = {"PENDING", "UPLOADED", "FAILED", "QUARANTINED"}
ENTITY_TYPES = {"FARMER", "PARCEL", "SOIL_PROFILE", "CROP_CYCLE", "CROP_STAGE", "CROP_ACTIVITY", "FIELD_EVENT", "ADVISORY", "QUERY_THREAD", "QUERY_MESSAGE"}
PURPOSES = {"STAGE_EVIDENCE", "ACTIVITY_EVIDENCE", "DISEASE_PHOTO", "SOIL_CARD", "PARCEL_BOUNDARY", "QUERY_ATTACHMENT", "ADVISORY_ATTACHMENT", "AUDIO_NOTE", "GENERAL"}
FIELD_EVENT_TYPES = {"RAIN", "PEST", "DISEASE", "HAILSTORM", "LOCUST", "FLOOD", "DROUGHT_STRESS", "THUNDERSTORM_WIND", "HEAT_STRESS", "COLD_STRESS", "IRRIGATION_FAILURE", "OTHER"}
FIELD_EVENT_SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
FIELD_EVENT_SOURCES = {"FARMER_ANDROID", "FIELD_AGENT_ANDROID", "ADMIN_WEB", "EXTERNAL_API", "IOT_DEVICE"}
FIELD_EVENT_STATUSES = {"REPORTED", "UNDER_REVIEW", "ADVISORY_SENT", "RESOLVED", "DISMISSED"}

MEDIA_WEB_ADMIN_ROLES = {
    "ENTERPRISE_ADMIN",
    "MANAGER",
    "ADMIN_EDITOR",
    "ADMIN_PUBLISHER",
}


def _iso(value):
    return value.isoformat() if value else None


def _asset_payload(asset: MediaAsset) -> dict:
    return {
        "id": str(asset.id),
        "tenant_id": asset.tenant_id,
        "project_id": str(asset.project_id) if asset.project_id else None,
        "farmer_id": str(asset.farmer_id) if asset.farmer_id else None,
        "uploaded_by": str(asset.uploaded_by) if asset.uploaded_by else None,
        "media_type": asset.media_type,
        "mime_type": asset.mime_type,
        "storage_url": asset.storage_url,
        "storage_key": asset.storage_key,
        "thumbnail_url": asset.thumbnail_url,
        "sha256_hash": asset.sha256_hash,
        "size_bytes": asset.size_bytes,
        "duration_seconds": asset.duration_seconds,
        "width": asset.width,
        "height": asset.height,
        "capture_lat": asset.capture_lat,
        "capture_lng": asset.capture_lng,
        "capture_accuracy_meters": asset.capture_accuracy_meters,
        "captured_at": _iso(asset.captured_at),
        "upload_status": asset.upload_status,
        "metadata": asset.metadata_ or {},
        "created_at": _iso(asset.created_at),
        "updated_at": _iso(asset.updated_at),
    }


def _attachment_payload(attachment: MediaAttachment, asset: Optional[MediaAsset] = None) -> dict:
    return {
        "id": str(attachment.id),
        "tenant_id": attachment.tenant_id,
        "media_asset_id": str(attachment.media_asset_id),
        "entity_type": attachment.entity_type,
        "entity_id": str(attachment.entity_id),
        "purpose": attachment.purpose,
        "caption": attachment.caption,
        "display_order": attachment.display_order,
        "is_primary": attachment.is_primary,
        "metadata": attachment.metadata_ or {},
        "asset": _asset_payload(asset) if asset else None,
        "created_at": _iso(attachment.created_at),
        "updated_at": _iso(attachment.updated_at),
    }


def _field_event_payload(event: FieldEventReport, attachment_count: int = 0) -> dict:
    return {
        "id": str(event.id),
        "tenant_id": event.tenant_id,
        "project_id": str(event.project_id) if event.project_id else None,
        "farmer_id": str(event.farmer_id),
        "parcel_id": str(event.parcel_id) if event.parcel_id else None,
        "crop_cycle_id": str(event.crop_cycle_id) if event.crop_cycle_id else None,
        "stage_code": event.stage_code,
        "event_type": event.event_type,
        "severity": event.severity,
        "event_date": _iso(event.event_date),
        "reported_at": _iso(event.reported_at),
        "lat": event.lat,
        "lng": event.lng,
        "accuracy_meters": event.accuracy_meters,
        "description": event.description,
        "estimated_area_affected": event.estimated_area_affected,
        "estimated_loss_percent": event.estimated_loss_percent,
        "source": event.source,
        "external_source": event.external_source,
        "external_event_id": event.external_event_id,
        "status": event.status,
        "metadata": event.metadata_ or {},
        "media_attachment_count": attachment_count,
        "created_at": _iso(event.created_at),
        "updated_at": _iso(event.updated_at),
    }


class FieldEventAttachmentCreate(BaseModel):
    media_asset_id: uuid.UUID
    purpose: str = "GENERAL"
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


class FieldEventCreate(BaseModel):
    id: Optional[uuid.UUID] = None
    project_id: Optional[uuid.UUID] = None
    farmer_id: uuid.UUID
    parcel_id: Optional[uuid.UUID] = None
    crop_cycle_id: Optional[uuid.UUID] = None
    stage_code: Optional[str] = Field(None, max_length=50)
    event_type: str
    severity: str = "MEDIUM"
    event_date: Optional[datetime] = None
    lat: Optional[str] = Field(None, max_length=40)
    lng: Optional[str] = Field(None, max_length=40)
    accuracy_meters: Optional[str] = Field(None, max_length=40)
    description: Optional[str] = None
    estimated_area_affected: Optional[str] = Field(None, max_length=40)
    estimated_loss_percent: Optional[str] = Field(None, max_length=40)
    source: str = "FARMER_ANDROID"
    external_source: Optional[str] = Field(None, max_length=100)
    external_event_id: Optional[str] = Field(None, max_length=120)
    status: str = "REPORTED"
    metadata: dict = Field(default_factory=dict)
    media_attachments: list[FieldEventAttachmentCreate] = Field(default_factory=list)

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in FIELD_EVENT_TYPES:
            raise ValueError(f"event_type must be one of {sorted(FIELD_EVENT_TYPES)}")
        return normalized

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in FIELD_EVENT_SEVERITIES:
            raise ValueError(f"severity must be one of {sorted(FIELD_EVENT_SEVERITIES)}")
        return normalized

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in FIELD_EVENT_SOURCES:
            raise ValueError(f"source must be one of {sorted(FIELD_EVENT_SOURCES)}")
        return normalized

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in FIELD_EVENT_STATUSES:
            raise ValueError(f"status must be one of {sorted(FIELD_EVENT_STATUSES)}")
        return normalized


class FieldEventStatusPatch(BaseModel):
    status: str
    reason: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in FIELD_EVENT_STATUSES:
            raise ValueError(f"status must be one of {sorted(FIELD_EVENT_STATUSES)}")
        return normalized


class MediaAssetCreate(BaseModel):
    id: Optional[uuid.UUID] = None
    project_id: Optional[uuid.UUID] = None
    farmer_id: Optional[uuid.UUID] = None
    uploaded_by: Optional[uuid.UUID] = None
    media_type: str
    mime_type: str = Field(..., min_length=3, max_length=120)
    storage_url: Optional[str] = None
    storage_key: Optional[str] = None
    thumbnail_url: Optional[str] = None
    sha256_hash: Optional[str] = Field(None, max_length=128)
    size_bytes: Optional[int] = Field(None, ge=0)
    duration_seconds: Optional[int] = Field(None, ge=0)
    width: Optional[int] = Field(None, ge=0)
    height: Optional[int] = Field(None, ge=0)
    capture_lat: Optional[str] = Field(None, max_length=40)
    capture_lng: Optional[str] = Field(None, max_length=40)
    capture_accuracy_meters: Optional[str] = Field(None, max_length=40)
    captured_at: Optional[datetime] = None
    upload_status: str = "PENDING"
    metadata: dict = Field(default_factory=dict)

    @field_validator("media_type")
    @classmethod
    def validate_media_type(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in MEDIA_TYPES:
            raise ValueError(f"media_type must be one of {sorted(MEDIA_TYPES)}")
        return normalized

    @field_validator("upload_status")
    @classmethod
    def validate_upload_status(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in UPLOAD_STATUSES:
            raise ValueError(f"upload_status must be one of {sorted(UPLOAD_STATUSES)}")
        return normalized


class MediaAssetComplete(BaseModel):
    storage_url: Optional[str] = None
    storage_key: Optional[str] = None
    thumbnail_url: Optional[str] = None
    sha256_hash: Optional[str] = Field(None, max_length=128)
    size_bytes: Optional[int] = Field(None, ge=0)
    upload_status: str = "UPLOADED"
    metadata: Optional[dict] = None

    @field_validator("upload_status")
    @classmethod
    def validate_upload_status(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"UPLOADED", "FAILED", "QUARANTINED"}:
            raise ValueError("upload_status must be UPLOADED, FAILED, or QUARANTINED")
        return normalized


class MediaAttachmentCreate(BaseModel):
    id: Optional[uuid.UUID] = None
    media_asset_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    purpose: str = "GENERAL"
    caption: Optional[str] = None
    display_order: int = 0
    is_primary: bool = False
    metadata: dict = Field(default_factory=dict)

    @field_validator("entity_type")
    @classmethod
    def validate_entity_type(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in ENTITY_TYPES:
            raise ValueError(f"entity_type must be one of {sorted(ENTITY_TYPES)}")
        return normalized

    @field_validator("purpose")
    @classmethod
    def validate_purpose(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in PURPOSES:
            raise ValueError(f"purpose must be one of {sorted(PURPOSES)}")
        return normalized


def _media_admin_can_edit(principal: AuthenticatedPrincipal) -> bool:
    role = str(principal.role or "").upper()
    return (
        role in MEDIA_WEB_ADMIN_ROLES
        and AdminPermission.EDIT in ROLE_PERMISSIONS.get(role, set())
    )


def _media_scope_forbidden(message: str) -> HTTPException:
    return HTTPException(
        status_code=403,
        detail={
            "error": "MEDIA_SCOPE_DENIED",
            "message": message,
        },
    )


def _require_media_creation_scope(
    db: Session,
    *,
    principal: AuthenticatedPrincipal,
    project_id: Optional[uuid.UUID],
    farmer_id: Optional[uuid.UUID],
) -> None:
    project = None
    if project_id:
        project = (
            db.query(Project)
            .filter(
                Project.id == project_id,
                Project.tenant_id == principal.tenant_id,
                Project.is_active == True,
            )
            .first()
        )
        if not project:
            raise HTTPException(404, "Project not found")

    farmer = None
    if farmer_id:
        farmer = (
            db.query(Farmer)
            .filter(
                Farmer.id == farmer_id,
                Farmer.tenant_id == principal.tenant_id,
                Farmer.status != "ARCHIVED",
                Farmer.is_active == True,
            )
            .first()
        )
        if not farmer:
            raise HTTPException(404, "Farmer not found")

    if farmer and project:
        legacy_project_match = farmer.project_id == project.id
        enrollment_match = (
            db.query(FarmerProjectEnrollment.id)
            .filter(
                FarmerProjectEnrollment.tenant_id == principal.tenant_id,
                FarmerProjectEnrollment.farmer_id == farmer.id,
                FarmerProjectEnrollment.project_id == project.id,
                FarmerProjectEnrollment.status == "ACTIVE",
                FarmerProjectEnrollment.is_active == True,
            )
            .first()
            is not None
        )
        if not legacy_project_match and not enrollment_match:
            raise _media_scope_forbidden(
                "Farmer is not enrolled in the requested project."
            )

    if _media_admin_can_edit(principal):
        return

    scope = resolve_human_persona_scope(db, principal)
    if farmer and scope.can_operate_farmer(farmer.id):
        return

    if farmer:
        raise _media_scope_forbidden(
            "Authenticated user cannot upload media for this farmer."
        )
    if project:
        raise _media_scope_forbidden(
            "Project-only media requires an authorised web administrator."
        )
    raise _media_scope_forbidden(
        "Media must be scoped to an authorised farmer or created by an "
        "authorised web administrator."
    )


def _attachment_target_unsupported(entity_type: str) -> HTTPException:
    return HTTPException(
        status_code=403,
        detail={
            "error": "MEDIA_ATTACHMENT_TARGET_UNSUPPORTED",
            "message": (
                f"Generic attachment creation is not authorised for "
                f"{entity_type} targets."
            ),
        },
    )


def _require_media_attachment_scope(
    db: Session,
    *,
    principal: AuthenticatedPrincipal,
    asset: MediaAsset,
    entity_type: str,
    entity_id: uuid.UUID,
) -> None:
    """Authorise both sides of a generic media attachment relationship."""

    _require_media_creation_scope(
        db,
        principal=principal,
        project_id=asset.project_id,
        farmer_id=asset.farmer_id,
    )

    target_project_id = None
    target_farmer_id = None

    if entity_type == "FARMER":
        farmer = (
            db.query(Farmer)
            .filter(
                Farmer.id == entity_id,
                Farmer.tenant_id == principal.tenant_id,
                Farmer.status != "ARCHIVED",
                Farmer.is_active == True,
            )
            .first()
        )
        if not farmer:
            raise HTTPException(404, "Farmer not found")
        target_project_id = farmer.project_id
        target_farmer_id = farmer.id

    elif entity_type == "PARCEL":
        parcel = (
            db.query(Parcel)
            .filter(
                Parcel.id == entity_id,
                Parcel.tenant_id == principal.tenant_id,
                Parcel.is_active == True,
            )
            .first()
        )
        if not parcel:
            raise HTTPException(404, "Parcel not found")
        target_project_id = parcel.project_id
        target_farmer_id = parcel.farmer_id

    elif entity_type == "FIELD_EVENT":
        event = (
            db.query(FieldEventReport)
            .filter(
                FieldEventReport.id == entity_id,
                FieldEventReport.tenant_id == principal.tenant_id,
                FieldEventReport.is_active == True,
            )
            .first()
        )
        if not event:
            raise HTTPException(404, "Field event not found")
        target_project_id = event.project_id
        target_farmer_id = event.farmer_id

    elif entity_type == "ADVISORY":
        if not _media_admin_can_edit(principal):
            raise _media_scope_forbidden(
                "Advisory attachments require an authorised web administrator."
            )

        advisory_row = (
            db.query(BroadcastContent, BroadcastCampaign)
            .join(
                BroadcastCampaign,
                BroadcastCampaign.id == BroadcastContent.campaign_id,
            )
            .filter(
                BroadcastContent.id == entity_id,
                BroadcastContent.tenant_id == principal.tenant_id,
                BroadcastCampaign.tenant_id == principal.tenant_id,
                BroadcastCampaign.is_active == True,
            )
            .first()
        )
        if not advisory_row:
            raise HTTPException(404, "Advisory content not found")

        _, campaign = advisory_row
        target_project_id = campaign.project_id

    else:
        raise _attachment_target_unsupported(entity_type)

    if (
        asset.farmer_id
        and target_farmer_id
        and asset.farmer_id != target_farmer_id
    ):
        raise _media_scope_forbidden(
            "Media asset farmer does not match the attachment target."
        )

    if (
        asset.project_id
        and target_project_id
        and asset.project_id != target_project_id
    ):
        raise _media_scope_forbidden(
            "Media asset project does not match the attachment target."
        )

    if entity_type != "ADVISORY":
        _require_media_creation_scope(
            db,
            principal=principal,
            project_id=target_project_id,
            farmer_id=target_farmer_id,
        )


@router.post("/assets", status_code=201)
def create_media_asset(
    body: MediaAssetCreate,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require_authenticated_human()),
):
    if body.uploaded_by and body.uploaded_by != principal.user_id:
        raise _media_scope_forbidden(
            "uploaded_by must match the authenticated user."
        )

    _require_media_creation_scope(
        db,
        principal=principal,
        project_id=body.project_id,
        farmer_id=body.farmer_id,
    )

    asset = MediaAsset(
        id=body.id or uuid.uuid4(),
        tenant_id=principal.tenant_id,
        project_id=body.project_id,
        farmer_id=body.farmer_id,
        uploaded_by=principal.user_id,
        media_type=body.media_type,
        mime_type=body.mime_type,
        storage_url=body.storage_url,
        storage_key=body.storage_key,
        thumbnail_url=body.thumbnail_url,
        sha256_hash=body.sha256_hash,
        size_bytes=body.size_bytes,
        duration_seconds=body.duration_seconds,
        width=body.width,
        height=body.height,
        capture_lat=body.capture_lat,
        capture_lng=body.capture_lng,
        capture_accuracy_meters=body.capture_accuracy_meters,
        captured_at=body.captured_at,
        upload_status=body.upload_status,
        metadata_=body.metadata or {},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return _asset_payload(asset)


@router.post("/assets/{asset_id}/complete")
def complete_media_asset(
    asset_id: uuid.UUID,
    body: MediaAssetComplete,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require_authenticated_human()),
):
    asset = (
        db.query(MediaAsset)
        .filter(
            MediaAsset.id == asset_id,
            MediaAsset.tenant_id == principal.tenant_id,
        )
        .first()
    )
    if not asset:
        raise HTTPException(404, "Media asset not found")

    if asset.uploaded_by != principal.user_id:
        _require_media_creation_scope(
            db,
            principal=principal,
            project_id=asset.project_id,
            farmer_id=asset.farmer_id,
        )
    if body.storage_url is not None:
        asset.storage_url = body.storage_url
    if body.storage_key is not None:
        asset.storage_key = body.storage_key
    if body.thumbnail_url is not None:
        asset.thumbnail_url = body.thumbnail_url
    if body.sha256_hash is not None:
        asset.sha256_hash = body.sha256_hash
    if body.size_bytes is not None:
        asset.size_bytes = body.size_bytes
    if body.metadata is not None:
        asset.metadata_ = {**(asset.metadata_ or {}), **body.metadata}
    asset.upload_status = body.upload_status
    asset.updated_at = datetime.now(timezone.utc)
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return _asset_payload(asset)


@router.get("/assets/{asset_id}")
def get_media_asset(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id, MediaAsset.tenant_id == x_tenant_id).first()
    if not asset:
        raise HTTPException(404, "Media asset not found")
    return _asset_payload(asset)


@router.post("/attachments", status_code=201)
def create_media_attachment(
    body: MediaAttachmentCreate,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require_authenticated_human()),
):
    asset = (
        db.query(MediaAsset)
        .filter(
            MediaAsset.id == body.media_asset_id,
            MediaAsset.tenant_id == principal.tenant_id,
        )
        .first()
    )
    if not asset:
        raise HTTPException(404, "Media asset not found")

    _require_media_attachment_scope(
        db,
        principal=principal,
        asset=asset,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
    )

    attachment = MediaAttachment(
        id=body.id or uuid.uuid4(),
        tenant_id=principal.tenant_id,
        media_asset_id=asset.id,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        purpose=body.purpose,
        caption=body.caption,
        display_order=body.display_order,
        is_primary=body.is_primary,
        metadata_={
            **(body.metadata or {}),
            "created_by_user_id": str(principal.user_id),
        },
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return _attachment_payload(attachment, asset)


@router.get("/attachments")
def list_media_attachments(
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[uuid.UUID] = Query(None),
    purpose: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    query = db.query(MediaAttachment, MediaAsset).join(MediaAsset, MediaAsset.id == MediaAttachment.media_asset_id).filter(MediaAttachment.tenant_id == x_tenant_id)
    if entity_type:
        normalized_entity_type = entity_type.upper()
        if normalized_entity_type not in ENTITY_TYPES:
            raise HTTPException(400, "Invalid entity_type")
        query = query.filter(MediaAttachment.entity_type == normalized_entity_type)
    if entity_id:
        query = query.filter(MediaAttachment.entity_id == entity_id)
    if purpose:
        normalized_purpose = purpose.upper()
        if normalized_purpose not in PURPOSES:
            raise HTTPException(400, "Invalid purpose")
        query = query.filter(MediaAttachment.purpose == normalized_purpose)

    rows = query.order_by(MediaAttachment.display_order.asc(), MediaAttachment.created_at.desc()).limit(limit).all()
    return {
        "schema_version": "media_attachments.v1",
        "tenant_id": x_tenant_id,
        "filters": {
            "entity_type": entity_type.upper() if entity_type else None,
            "entity_id": str(entity_id) if entity_id else None,
            "purpose": purpose.upper() if purpose else None,
            "limit": limit,
        },
        "count": len(rows),
        "attachments": [_attachment_payload(attachment, asset) for attachment, asset in rows],
    }


FIELD_EVENT_TRANSITIONS = {
    "REPORTED": {"UNDER_REVIEW", "RESOLVED", "DISMISSED"},
    "UNDER_REVIEW": {"ADVISORY_SENT", "RESOLVED", "DISMISSED"},
    "ADVISORY_SENT": {"RESOLVED"},
    "RESOLVED": set(),
    "DISMISSED": set(),
}


def _field_event_scope_forbidden(message: str) -> HTTPException:
    return HTTPException(
        status_code=403,
        detail={
            "error": "FIELD_EVENT_SCOPE_DENIED",
            "message": message,
        },
    )


def _field_event_creation_source(
    db: Session,
    *,
    principal: AuthenticatedPrincipal,
    farmer_id: uuid.UUID,
) -> str:
    if _media_admin_can_edit(principal):
        return "ADMIN_WEB"

    scope = resolve_human_persona_scope(db, principal)
    if scope.owns_farmer(farmer_id):
        return "FARMER_ANDROID"
    if (
        scope.has_agent_persona
        and scope.is_assigned_to_farmer(farmer_id)
    ):
        return "FIELD_AGENT_ANDROID"

    raise _field_event_scope_forbidden(
        "Authenticated user cannot report an event for this farmer."
    )


def _require_field_event_status_scope(
    db: Session,
    *,
    principal: AuthenticatedPrincipal,
    event: FieldEventReport,
    target_status: str,
) -> None:
    allowed = FIELD_EVENT_TRANSITIONS.get(event.status, set())
    if target_status not in allowed:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "FIELD_EVENT_TRANSITION_INVALID",
                "message": (
                    f"Field event cannot transition from "
                    f"{event.status} to {target_status}."
                ),
            },
        )

    if _media_admin_can_edit(principal):
        return

    scope = resolve_human_persona_scope(db, principal)
    if not (
        scope.has_agent_persona
        and scope.is_assigned_to_farmer(event.farmer_id)
    ):
        raise _field_event_scope_forbidden(
            "Field-event status changes require an assigned agent "
            "or authorised web administrator."
        )

    if target_status == "ADVISORY_SENT":
        raise _field_event_scope_forbidden(
            "Only an authorised web administrator can mark an "
            "advisory as sent."
        )


@field_events_router.post("", status_code=201)
def create_field_event_report(
    body: FieldEventCreate,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require_authenticated_human()),
):
    if body.status != "REPORTED":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "FIELD_EVENT_INITIAL_STATUS_INVALID",
                "message": "New field events must start in REPORTED status.",
            },
        )

    farmer = (
        db.query(Farmer)
        .filter(
            Farmer.id == body.farmer_id,
            Farmer.tenant_id == principal.tenant_id,
            Farmer.status != "ARCHIVED",
            Farmer.is_active == True,
        )
        .first()
    )
    if not farmer:
        raise HTTPException(404, "Farmer not found")

    _require_media_creation_scope(
        db,
        principal=principal,
        project_id=body.project_id,
        farmer_id=body.farmer_id,
    )
    source = _field_event_creation_source(
        db,
        principal=principal,
        farmer_id=body.farmer_id,
    )

    if body.parcel_id:
        parcel = (
            db.query(Parcel)
            .filter(
                Parcel.id == body.parcel_id,
                Parcel.tenant_id == principal.tenant_id,
                Parcel.farmer_id == body.farmer_id,
                Parcel.is_active == True,
            )
            .first()
        )
        if not parcel:
            raise HTTPException(404, "Parcel not found")
        if (
            body.project_id
            and parcel.project_id
            and parcel.project_id != body.project_id
        ):
            raise _field_event_scope_forbidden(
                "Parcel project does not match the field event project."
            )

    attachment_assets = []
    for attachment in body.media_attachments:
        asset = (
            db.query(MediaAsset)
            .filter(
                MediaAsset.id == attachment.media_asset_id,
                MediaAsset.tenant_id == principal.tenant_id,
            )
            .first()
        )
        if not asset:
            raise HTTPException(
                404,
                f"Media asset {attachment.media_asset_id} not found",
            )

        _require_media_creation_scope(
            db,
            principal=principal,
            project_id=asset.project_id,
            farmer_id=asset.farmer_id,
        )
        if asset.farmer_id and asset.farmer_id != body.farmer_id:
            raise _field_event_scope_forbidden(
                "Inline media asset farmer does not match the field event."
            )
        if (
            asset.project_id
            and body.project_id
            and asset.project_id != body.project_id
        ):
            raise _field_event_scope_forbidden(
                "Inline media asset project does not match the field event."
            )
        attachment_assets.append((attachment, asset))

    timestamp = datetime.now(timezone.utc)
    event_metadata = {
        **(body.metadata or {}),
        "reported_by_user_id": str(principal.user_id),
        "reported_by_role": principal.role,
    }
    event = FieldEventReport(
        id=body.id or uuid.uuid4(),
        tenant_id=principal.tenant_id,
        project_id=body.project_id,
        farmer_id=body.farmer_id,
        parcel_id=body.parcel_id,
        crop_cycle_id=body.crop_cycle_id,
        stage_code=body.stage_code,
        event_type=body.event_type,
        severity=body.severity,
        event_date=body.event_date or timestamp,
        reported_at=timestamp,
        lat=body.lat,
        lng=body.lng,
        accuracy_meters=body.accuracy_meters,
        description=body.description,
        estimated_area_affected=body.estimated_area_affected,
        estimated_loss_percent=body.estimated_loss_percent,
        source=source,
        external_source=None,
        external_event_id=None,
        status="REPORTED",
        metadata_=event_metadata,
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(event)
    db.flush()

    created_attachments = []
    for attachment_body, asset in attachment_assets:
        attachment = MediaAttachment(
            tenant_id=principal.tenant_id,
            media_asset_id=asset.id,
            entity_type="FIELD_EVENT",
            entity_id=event.id,
            purpose=attachment_body.purpose,
            caption=attachment_body.caption,
            display_order=attachment_body.display_order,
            is_primary=attachment_body.is_primary,
            metadata_={
                **(attachment_body.metadata or {}),
                "created_by_user_id": str(principal.user_id),
            },
            created_at=timestamp,
            updated_at=timestamp,
        )
        db.add(attachment)
        created_attachments.append((attachment, asset))

    db.commit()
    db.refresh(event)
    payload = _field_event_payload(event, len(created_attachments))
    if created_attachments:
        payload["media_attachments"] = [
            _attachment_payload(attachment, asset)
            for attachment, asset in created_attachments
        ]
    return payload


def _field_event_readable_farmer_ids(
    db: Session,
    principal: AuthenticatedPrincipal,
) -> frozenset[uuid.UUID] | None:
    if _media_admin_can_edit(principal):
        return None

    scope = resolve_human_persona_scope(db, principal)
    return frozenset(
        set(scope.own_farmer_ids) | set(scope.assigned_farmer_ids)
    )


@field_events_router.get("")
def list_field_event_reports(
    project_id: Optional[uuid.UUID] = Query(None),
    farmer_id: Optional[uuid.UUID] = Query(None),
    parcel_id: Optional[uuid.UUID] = Query(None),
    event_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require_authenticated_human()),
):
    query = db.query(FieldEventReport).filter(
        FieldEventReport.tenant_id == principal.tenant_id,
        FieldEventReport.is_active == True,
    )

    readable_farmer_ids = _field_event_readable_farmer_ids(db, principal)
    if readable_farmer_ids is not None:
        query = query.filter(
            FieldEventReport.farmer_id.in_(readable_farmer_ids)
        )

    if project_id:
        query = query.filter(FieldEventReport.project_id == project_id)
    if farmer_id:
        query = query.filter(FieldEventReport.farmer_id == farmer_id)
    if parcel_id:
        query = query.filter(FieldEventReport.parcel_id == parcel_id)
    if event_type:
        normalized_event_type = event_type.upper()
        if normalized_event_type not in FIELD_EVENT_TYPES:
            raise HTTPException(400, "Invalid event_type")
        query = query.filter(
            FieldEventReport.event_type == normalized_event_type
        )
    if severity:
        normalized_severity = severity.upper()
        if normalized_severity not in FIELD_EVENT_SEVERITIES:
            raise HTTPException(400, "Invalid severity")
        query = query.filter(
            FieldEventReport.severity == normalized_severity
        )
    if status:
        normalized_status = status.upper()
        if normalized_status not in FIELD_EVENT_STATUSES:
            raise HTTPException(400, "Invalid status")
        query = query.filter(
            FieldEventReport.status == normalized_status
        )

    rows = (
        query.order_by(
            FieldEventReport.reported_at.desc(),
            FieldEventReport.created_at.desc(),
        )
        .limit(limit)
        .all()
    )
    return {
        "schema_version": "field_event_reports.v1",
        "tenant_id": principal.tenant_id,
        "filters": {
            "project_id": str(project_id) if project_id else None,
            "farmer_id": str(farmer_id) if farmer_id else None,
            "parcel_id": str(parcel_id) if parcel_id else None,
            "event_type": event_type.upper() if event_type else None,
            "severity": severity.upper() if severity else None,
            "status": status.upper() if status else None,
            "limit": limit,
        },
        "count": len(rows),
        "events": [
            _field_event_payload(
                row,
                db.query(MediaAttachment)
                .filter(
                    MediaAttachment.tenant_id == principal.tenant_id,
                    MediaAttachment.entity_type == "FIELD_EVENT",
                    MediaAttachment.entity_id == row.id,
                )
                .count(),
            )
            for row in rows
        ],
    }


@field_events_router.get("/{event_id}")
def get_field_event_report(
    event_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require_authenticated_human()),
):
    event = (
        db.query(FieldEventReport)
        .filter(
            FieldEventReport.id == event_id,
            FieldEventReport.tenant_id == principal.tenant_id,
            FieldEventReport.is_active == True,
        )
        .first()
    )
    if not event:
        raise HTTPException(404, "Field event not found")

    readable_farmer_ids = _field_event_readable_farmer_ids(db, principal)
    if (
        readable_farmer_ids is not None
        and event.farmer_id not in readable_farmer_ids
    ):
        raise HTTPException(404, "Field event not found")

    attachment_count = (
        db.query(MediaAttachment)
        .filter(
            MediaAttachment.tenant_id == principal.tenant_id,
            MediaAttachment.entity_type == "FIELD_EVENT",
            MediaAttachment.entity_id == event.id,
        )
        .count()
    )
    payload = _field_event_payload(event, attachment_count)
    attachments = (
        db.query(MediaAttachment, MediaAsset)
        .join(
            MediaAsset,
            MediaAsset.id == MediaAttachment.media_asset_id,
        )
        .filter(
            MediaAttachment.tenant_id == principal.tenant_id,
            MediaAttachment.entity_type == "FIELD_EVENT",
            MediaAttachment.entity_id == event.id,
        )
        .order_by(
            MediaAttachment.display_order.asc(),
            MediaAttachment.created_at.desc(),
        )
        .all()
    )
    payload["media_attachments"] = [
        _attachment_payload(attachment, asset)
        for attachment, asset in attachments
    ]
    return payload


@field_events_router.patch("/{event_id}/status")
def update_field_event_status(
    event_id: uuid.UUID,
    body: FieldEventStatusPatch,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require_authenticated_human()),
):
    event = (
        db.query(FieldEventReport)
        .filter(
            FieldEventReport.id == event_id,
            FieldEventReport.tenant_id == principal.tenant_id,
            FieldEventReport.is_active == True,
        )
        .first()
    )
    if not event:
        raise HTTPException(404, "Field event not found")

    _require_field_event_status_scope(
        db,
        principal=principal,
        event=event,
        target_status=body.status,
    )

    changed_at = datetime.now(timezone.utc)
    metadata = dict(event.metadata_ or {})
    history = list(metadata.get("status_history") or [])
    history.append({
        "from_status": event.status,
        "to_status": body.status,
        "reason": body.reason,
        "at": changed_at.isoformat(),
        "actor_user_id": str(principal.user_id),
        "actor_role": principal.role,
    })
    metadata["status_history"] = history
    event.status = body.status
    event.metadata_ = metadata
    event.updated_at = changed_at
    db.add(event)
    db.commit()
    db.refresh(event)
    return _field_event_payload(
        event,
        db.query(MediaAttachment)
        .filter(
            MediaAttachment.tenant_id == principal.tenant_id,
            MediaAttachment.entity_type == "FIELD_EVENT",
            MediaAttachment.entity_id == event.id,
        )
        .count(),
    )

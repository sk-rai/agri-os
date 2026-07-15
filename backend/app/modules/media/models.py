"""Shared media asset and attachment models.

Metadata-only foundation for photos, audio, documents, and future object storage.
Binary upload/storage can be added behind these stable records without changing
Android entity linkage semantics.
"""
import uuid

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.shared.models import AuditMixin, UUIDPrimaryKey


class MediaAsset(Base, UUIDPrimaryKey, AuditMixin):
    __tablename__ = "media_assets"

    tenant_id = Column(String(50), ForeignKey("tenants.id"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"))
    farmer_id = Column(UUID(as_uuid=True), ForeignKey("farmers.id"))
    uploaded_by = Column(UUID(as_uuid=True))

    media_type = Column(String(20), nullable=False)
    # PHOTO, AUDIO, VIDEO, DOCUMENT
    mime_type = Column(String(120), nullable=False)
    storage_url = Column(Text)
    storage_key = Column(String(500))
    thumbnail_url = Column(Text)
    sha256_hash = Column(String(128))
    size_bytes = Column(Integer)
    duration_seconds = Column(Integer)
    width = Column(Integer)
    height = Column(Integer)

    capture_lat = Column(String(40))
    capture_lng = Column(String(40))
    capture_accuracy_meters = Column(String(40))
    captured_at = Column(DateTime(timezone=True))

    upload_status = Column(String(20), nullable=False, default="PENDING")
    # PENDING, UPLOADED, FAILED, QUARANTINED
    metadata_ = Column("metadata", JSONB, default=dict)

    __table_args__ = (
        Index("idx_media_asset_tenant", "tenant_id"),
        Index("idx_media_asset_project", "project_id"),
        Index("idx_media_asset_farmer", "farmer_id"),
        Index("idx_media_asset_type", "media_type"),
        Index("idx_media_asset_status", "upload_status"),
        Index("idx_media_asset_hash", "sha256_hash"),
        CheckConstraint("media_type IN ('PHOTO', 'AUDIO', 'VIDEO', 'DOCUMENT')", name="ck_media_asset_type"),
        CheckConstraint("upload_status IN ('PENDING', 'UPLOADED', 'FAILED', 'QUARANTINED')", name="ck_media_asset_upload_status"),
    )


class MediaAttachment(Base, UUIDPrimaryKey, AuditMixin):
    __tablename__ = "media_attachments"

    tenant_id = Column(String(50), ForeignKey("tenants.id"), nullable=False)
    media_asset_id = Column(UUID(as_uuid=True), ForeignKey("media_assets.id"), nullable=False)
    entity_type = Column(String(40), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    purpose = Column(String(40), nullable=False)
    caption = Column(Text)
    display_order = Column(Integer, nullable=False, default=0)
    is_primary = Column(Boolean, nullable=False, default=False)
    metadata_ = Column("metadata", JSONB, default=dict)

    __table_args__ = (
        Index("idx_media_attachment_tenant", "tenant_id"),
        Index("idx_media_attachment_asset", "media_asset_id"),
        Index("idx_media_attachment_entity", "tenant_id", "entity_type", "entity_id"),
        Index("idx_media_attachment_purpose", "purpose"),
        CheckConstraint(
            "entity_type IN ('FARMER', 'PARCEL', 'SOIL_PROFILE', 'CROP_CYCLE', 'CROP_STAGE', 'CROP_ACTIVITY', 'FIELD_EVENT', 'ADVISORY', 'QUERY_THREAD', 'QUERY_MESSAGE')",
            name="ck_media_attachment_entity_type",
        ),
        CheckConstraint(
            "purpose IN ('STAGE_EVIDENCE', 'ACTIVITY_EVIDENCE', 'DISEASE_PHOTO', 'SOIL_CARD', 'PARCEL_BOUNDARY', 'QUERY_ATTACHMENT', 'ADVISORY_ATTACHMENT', 'AUDIO_NOTE', 'GENERAL')",
            name="ck_media_attachment_purpose",
        ),
    )


class FieldEventReport(Base, UUIDPrimaryKey, AuditMixin):
    __tablename__ = "field_event_reports"

    tenant_id = Column(String(50), ForeignKey("tenants.id"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"))
    farmer_id = Column(UUID(as_uuid=True), ForeignKey("farmers.id"), nullable=False)
    parcel_id = Column(UUID(as_uuid=True), ForeignKey("parcels.id"))
    crop_cycle_id = Column(UUID(as_uuid=True), ForeignKey("crop_cycles.id"))
    stage_code = Column(String(50))

    event_type = Column(String(40), nullable=False)
    severity = Column(String(20), nullable=False, default="MEDIUM")
    event_date = Column(DateTime(timezone=True), nullable=False)
    reported_at = Column(DateTime(timezone=True), nullable=False)

    lat = Column(String(40))
    lng = Column(String(40))
    accuracy_meters = Column(String(40))
    description = Column(Text)
    estimated_area_affected = Column(String(40))
    estimated_loss_percent = Column(String(40))

    source = Column(String(40), nullable=False, default="FARMER_ANDROID")
    external_source = Column(String(100))
    external_event_id = Column(String(120))
    status = Column(String(30), nullable=False, default="REPORTED")
    metadata_ = Column("metadata", JSONB, default=dict)

    __table_args__ = (
        Index("idx_field_event_tenant", "tenant_id"),
        Index("idx_field_event_project", "project_id"),
        Index("idx_field_event_farmer", "farmer_id"),
        Index("idx_field_event_parcel", "parcel_id"),
        Index("idx_field_event_cycle", "crop_cycle_id"),
        Index("idx_field_event_type", "event_type"),
        Index("idx_field_event_severity", "severity"),
        Index("idx_field_event_status", "status"),
        Index("idx_field_event_reported_at", "reported_at"),
        CheckConstraint("event_type IN ('RAIN', 'PEST', 'DISEASE', 'HAILSTORM', 'LOCUST', 'FLOOD', 'DROUGHT_STRESS', 'THUNDERSTORM_WIND', 'HEAT_STRESS', 'COLD_STRESS', 'IRRIGATION_FAILURE', 'OTHER')", name="ck_field_event_type"),
        CheckConstraint("severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')", name="ck_field_event_severity"),
        CheckConstraint("source IN ('FARMER_ANDROID', 'FIELD_AGENT_ANDROID', 'ADMIN_WEB', 'EXTERNAL_API', 'IOT_DEVICE')", name="ck_field_event_source"),
        CheckConstraint("status IN ('REPORTED', 'UNDER_REVIEW', 'ADVISORY_SENT', 'RESOLVED', 'DISMISSED')", name="ck_field_event_status"),
    )



class QueryThread(Base, UUIDPrimaryKey, AuditMixin):
    __tablename__ = "query_threads"

    tenant_id = Column(String(50), ForeignKey("tenants.id"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"))
    farmer_id = Column(UUID(as_uuid=True), ForeignKey("farmers.id"), nullable=False)
    parcel_id = Column(UUID(as_uuid=True), ForeignKey("parcels.id"))
    crop_cycle_id = Column(UUID(as_uuid=True), ForeignKey("crop_cycles.id"))
    stage_code = Column(String(50))

    subject = Column(String(200), nullable=False)
    category = Column(String(40), nullable=False, default="OTHER")
    priority = Column(String(20), nullable=False, default="MEDIUM")
    status = Column(String(30), nullable=False, default="OPEN")
    assigned_to = Column(UUID(as_uuid=True))
    last_message_at = Column(DateTime(timezone=True))
    metadata_ = Column("metadata", JSONB, default=dict)

    __table_args__ = (
        Index("idx_query_thread_tenant", "tenant_id"),
        Index("idx_query_thread_project", "project_id"),
        Index("idx_query_thread_farmer", "farmer_id"),
        Index("idx_query_thread_parcel", "parcel_id"),
        Index("idx_query_thread_status", "status"),
        Index("idx_query_thread_category", "category"),
        Index("idx_query_thread_last_message", "last_message_at"),
        CheckConstraint("category IN ('CROP_HEALTH', 'INPUT_USAGE', 'IRRIGATION', 'MARKET', 'INSURANCE', 'TECH_SUPPORT', 'OTHER')", name="ck_query_thread_category"),
        CheckConstraint("priority IN ('LOW', 'MEDIUM', 'HIGH', 'URGENT')", name="ck_query_thread_priority"),
        CheckConstraint("status IN ('OPEN', 'ASSIGNED', 'ANSWERED', 'CLOSED')", name="ck_query_thread_status"),
    )


class QueryMessage(Base, UUIDPrimaryKey, AuditMixin):
    __tablename__ = "query_messages"

    tenant_id = Column(String(50), ForeignKey("tenants.id"), nullable=False)
    thread_id = Column(UUID(as_uuid=True), ForeignKey("query_threads.id"), nullable=False)
    sender_type = Column(String(30), nullable=False)
    sender_id = Column(UUID(as_uuid=True))
    message_type = Column(String(20), nullable=False, default="TEXT")
    body_text = Column(Text)
    metadata_ = Column("metadata", JSONB, default=dict)

    __table_args__ = (
        Index("idx_query_message_tenant", "tenant_id"),
        Index("idx_query_message_thread", "thread_id"),
        Index("idx_query_message_sender", "sender_type", "sender_id"),
        CheckConstraint("sender_type IN ('FARMER', 'FIELD_AGENT', 'AGRONOMIST', 'ADMIN', 'SYSTEM')", name="ck_query_message_sender_type"),
        CheckConstraint("message_type IN ('TEXT', 'AUDIO', 'PHOTO', 'DOCUMENT', 'SYSTEM')", name="ck_query_message_type"),
    )


class QueryThreadAudit(Base):
    __tablename__ = "query_thread_audit_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(50), nullable=False, index=True)
    thread_id = Column(UUID(as_uuid=True), ForeignKey("query_threads.id"), nullable=False, index=True)
    action = Column(String(50), nullable=False, index=True)
    actor_type = Column(String(50), nullable=True)
    actor_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    before = Column(JSONB, nullable=True)
    after = Column(JSONB, nullable=True)
    reason = Column(Text, nullable=True)
    metadata_ = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    thread = relationship("QueryThread")

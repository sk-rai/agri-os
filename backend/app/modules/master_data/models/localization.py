"""Localized content and Android land-intelligence summary override models."""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.shared.models import AuditMixin, UUIDPrimaryKey


class LocalizedContentKey(Base, UUIDPrimaryKey, AuditMixin):
    """Stable backend-owned content key that tenant/project admins may override."""

    __tablename__ = "localized_content_keys"

    content_key = Column(String(300), nullable=False, unique=True, index=True)
    source = Column(String(80), nullable=False, index=True)
    content_kind = Column(String(80), nullable=False, index=True)
    default_labels = Column(JSONB, nullable=False, default=dict)
    metadata_ = Column("metadata", JSONB, nullable=False, default=dict)
    review_status = Column(String(40), nullable=False, default="PLATFORM_DEFAULT")

    overrides = relationship("LocalizedContentOverride", back_populates="content_key")

    __table_args__ = (
        Index("idx_localized_content_keys_source", "source", "content_kind"),
        Index("idx_localized_content_keys_active", "is_active", "review_status"),
    )


class LocalizedContentOverride(Base, UUIDPrimaryKey, AuditMixin):
    """Tenant/project/language scoped override for a platform-owned content key."""

    __tablename__ = "localized_content_overrides"

    tenant_id = Column(String(50), ForeignKey("tenants.id"), nullable=False, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True, index=True)
    content_key_id = Column(UUID(as_uuid=True), ForeignKey("localized_content_keys.id"), nullable=False, index=True)
    language_code = Column(String(12), nullable=False, index=True)
    override_text = Column(Text, nullable=False)
    review_status = Column(String(40), nullable=False, default="DRAFT", index=True)
    review_notes = Column(Text)
    created_by = Column(UUID(as_uuid=True))
    updated_by = Column(UUID(as_uuid=True))
    published_at = Column(DateTime(timezone=True))
    metadata_ = Column("metadata", JSONB, nullable=False, default=dict)

    content_key = relationship("LocalizedContentKey", back_populates="overrides")

    __table_args__ = (
        Index(
            "idx_localized_content_override_lookup",
            "tenant_id",
            "project_id",
            "content_key_id",
            "language_code",
            "review_status",
        ),
    )


class LandIntelligenceSummaryOverride(Base, UUIDPrimaryKey, AuditMixin):
    """Project/company editable Android-ready land-intelligence summary payload."""

    __tablename__ = "land_intelligence_summary_overrides"

    tenant_id = Column(String(50), ForeignKey("tenants.id"), nullable=False, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True, index=True)
    scope_type = Column(String(40), nullable=False, index=True)
    scope_code = Column(String(120), nullable=False, index=True)
    language_code = Column(String(12), nullable=False, default="en", index=True)
    summary_payload = Column(JSONB, nullable=False, default=dict)
    review_status = Column(String(40), nullable=False, default="DRAFT", index=True)
    review_notes = Column(Text)
    created_by = Column(UUID(as_uuid=True))
    updated_by = Column(UUID(as_uuid=True))
    published_at = Column(DateTime(timezone=True))
    metadata_ = Column("metadata", JSONB, nullable=False, default=dict)

    __table_args__ = (
        Index(
            "idx_land_intelligence_summary_override_lookup",
            "tenant_id",
            "project_id",
            "scope_type",
            "scope_code",
            "language_code",
            "review_status",
        ),
    )

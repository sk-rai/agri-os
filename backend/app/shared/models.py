import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Boolean, String
from sqlalchemy.dialects.postgresql import UUID


class AuditMixin:
    """Mixin for audit fields on all entities."""
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    version = Column(String(10), default="v1.0", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)


class UUIDPrimaryKey:
    """Mixin for UUID primary key."""
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

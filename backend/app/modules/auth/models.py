"""Auth models: User, Device, OTP."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.shared.models import AuditMixin, UUIDPrimaryKey


class User(Base, UUIDPrimaryKey, AuditMixin):
    """Platform user. Can be farmer, dealer, agent, agronomist, enterprise."""

    __tablename__ = "users"

    mobile_number = Column(String(15), unique=True, nullable=False, index=True)
    role = Column(String(30), nullable=False, default="FARMER")
    display_name = Column(String(100))
    language_preference = Column(String(10), default="hi")  # ISO 639-1
    tenant_id = Column(String(50))  # Assigned after enterprise onboarding
    territory_scope = Column(JSONB, default=dict)  # Geography access scope
    last_login_at = Column(DateTime(timezone=True))
    login_count = Column(Integer, default=0)

    # Relationships
    devices = relationship("UserDevice", back_populates="user")

    __table_args__ = (
        Index("idx_user_tenant", "tenant_id"),
        Index("idx_user_role", "role"),
    )


class UserDevice(Base, UUIDPrimaryKey, AuditMixin):
    """Registered device for a user. Enables SMS-free login after first OTP."""

    __tablename__ = "user_devices"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    device_id = Column(String(200), nullable=False)  # Android device ID
    device_key = Column(String(200), unique=True, nullable=False, index=True)
    device_name = Column(String(100))
    is_active = Column(Boolean, default=True, nullable=False)
    last_used_at = Column(DateTime(timezone=True))

    # Relationships
    user = relationship("User", back_populates="devices")

    __table_args__ = (
        Index("idx_device_user", "user_id"),
        Index("idx_device_key", "device_key"),
    )


class OTPRecord(Base, UUIDPrimaryKey):
    """Temporary OTP record. Expires after 5 minutes."""

    __tablename__ = "otp_records"

    mobile_number = Column(String(15), nullable=False, index=True)
    otp_hash = Column(String(200), nullable=False)  # bcrypt hash
    expires_at = Column(DateTime(timezone=True), nullable=False)
    attempts = Column(Integer, default=0)
    is_used = Column(Boolean, default=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

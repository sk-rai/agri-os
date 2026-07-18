"""Auth models: User, Device, OTP."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey, Index, Text
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


class TenantUserAccessAuditEvent(Base, UUIDPrimaryKey):
    """Immutable audit event for tenant roles and project access."""

    __tablename__ = "tenant_user_access_audit_events"

    tenant_id = Column(String(50), ForeignKey("tenants.id"), nullable=False, index=True)
    target_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    actor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), index=True)
    action = Column(String(50), nullable=False, index=True)
    before_payload = Column(JSONB)
    after_payload = Column(JSONB)
    reason = Column(Text)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_tenant_user_access_audit_tenant_created", "tenant_id", "created_at"),
        Index("idx_tenant_user_access_audit_target_created", "target_user_id", "created_at"),
    )


class AgentProfile(Base, UUIDPrimaryKey, AuditMixin):
    """Operational profile for field agents, agronomists, dealers, and other assisted-capture users.

    A person may simultaneously have:
    - a User account for login/agent capabilities;
    - an AgentProfile for work assignment metadata;
    - a Farmer profile when they farm personally.
    """

    __tablename__ = "agent_profiles"

    tenant_id = Column(String(50), ForeignKey("tenants.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    farmer_id = Column(UUID(as_uuid=True), ForeignKey("farmers.id"), nullable=True, index=True)
    agent_code = Column(String(50), index=True)
    role_type = Column(String(50), nullable=False, default="FIELD_AGENT")
    # FIELD_AGENT, AGRONOMIST, DEALER, MANAGER, ENUMERATOR
    display_name = Column(String(150))
    mobile_number = Column(String(15), index=True)
    status = Column(String(30), nullable=False, default="ACTIVE")
    # ACTIVE, INACTIVE, SUSPENDED
    skills = Column(JSONB, default=list)
    languages = Column(JSONB, default=list)
    territory_scope = Column(JSONB, default=dict)
    availability = Column(JSONB, default=dict)
    certification = Column(JSONB, default=dict)
    metadata_ = Column("metadata", JSONB, default=dict)

    __table_args__ = (
        Index("idx_agent_profiles_tenant_user", "tenant_id", "user_id", unique=True),
        Index("idx_agent_profiles_tenant_role", "tenant_id", "role_type"),
        Index("idx_agent_profiles_tenant_status", "tenant_id", "status"),
    )

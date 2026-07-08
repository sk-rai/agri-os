"""Agricultural input master data: fertilizers, pesticides, seeds.

Source: Public company catalogs, ministry data.
Canonical naming per Semantic Registry v1: input_category, agricultural_input.
"""

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DECIMAL,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.shared.models import AuditMixin, UUIDPrimaryKey


class InputCategory(Base, UUIDPrimaryKey, AuditMixin):
    """Category of agricultural input (FERTILIZER, PESTICIDE, SEED, etc.)."""

    __tablename__ = "input_categories"

    code = Column(String(30), unique=True, nullable=False, index=True)
    canonical_name = Column(String(100), nullable=False)
    description = Column(Text)
    aliases = Column(JSONB, default=list)

    # Relationships
    inputs = relationship("AgriculturalInput", back_populates="category")


class Manufacturer(Base, UUIDPrimaryKey, AuditMixin):
    """Manufacturer/company that produces agricultural inputs."""

    __tablename__ = "manufacturers"

    code = Column(String(50), unique=True, nullable=False, index=True)
    canonical_name = Column(String(200), nullable=False)
    short_name = Column(String(50))
    country = Column(String(50), default="India")
    aliases = Column(JSONB, default=list)


class AgriculturalInput(Base, UUIDPrimaryKey, AuditMixin):
    """Specific agricultural input product (e.g., DAP 50kg, Urea 45kg)."""

    __tablename__ = "agricultural_inputs"

    code = Column(String(50), unique=True, nullable=False, index=True)
    category_id = Column(
        UUID(as_uuid=True),
        ForeignKey("input_categories.id"),
        nullable=False,
    )
    manufacturer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("manufacturers.id"),
    )
    canonical_name = Column(String(200), nullable=False)
    brand_name = Column(String(200))
    composition = Column(String(200))  # e.g., "N:P:K = 18:46:0"
    unit = Column(String(20), nullable=False)  # kg, litre, packet
    standard_weight = Column(DECIMAL(10, 2))  # e.g., 50.00 (kg)
    applicable_crops = Column(ARRAY(String), default=list)
    application_method = Column(Text)
    safety_instructions = Column(Text)
    aliases = Column(JSONB, default=list)

    # Relationships
    category = relationship("InputCategory", back_populates="inputs")
    manufacturer = relationship("Manufacturer")

    __table_args__ = (
        Index("idx_input_category", "category_id"),
        Index("idx_input_manufacturer", "manufacturer_id"),
        Index(
            "idx_input_search",
            "canonical_name",
            postgresql_using="gin",
            postgresql_ops={"canonical_name": "gin_trgm_ops"},
        ),
    )

class ProjectInputAssignment(Base, UUIDPrimaryKey, AuditMixin):
    """Project-level allow/block rule for an agricultural input."""

    __tablename__ = "project_input_assignments"

    tenant_id = Column(String(50), nullable=False, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True)
    input_id = Column(UUID(as_uuid=True), ForeignKey("agricultural_inputs.id"), nullable=False, index=True)
    input_code = Column(String(50), nullable=False, index=True)
    enabled = Column(Boolean, nullable=False, default=True)
    display_order = Column(Integer, nullable=False, default=1000)
    reason = Column(Text)
    effective_from = Column(Date)
    effective_to = Column(Date)
    metadata_ = Column("metadata", JSONB, default=dict)

    input = relationship("AgriculturalInput")

    __table_args__ = (
        UniqueConstraint("tenant_id", "project_id", "input_code", name="uq_project_input_assignment"),
        Index("idx_project_input_assignment_project", "project_id", "enabled"),
    )

class ProjectInputAssignmentAuditEvent(Base, UUIDPrimaryKey, AuditMixin):
    """Audit event for project input assignment changes."""

    __tablename__ = "project_input_assignment_audit_events"

    tenant_id = Column(String(50), nullable=False, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True)
    input_code = Column(String(50), nullable=False, index=True)
    assignment_id = Column(UUID(as_uuid=True), ForeignKey("project_input_assignments.id"))
    actor_id = Column(UUID(as_uuid=True))
    action = Column(String(50), nullable=False)
    before_payload = Column(JSONB)
    after_payload = Column(JSONB)
    reason = Column(Text)
    metadata_ = Column("metadata", JSONB, default=dict)

    __table_args__ = (
        Index("idx_project_input_assignment_audit_project", "project_id", "created_at"),
        Index("idx_project_input_assignment_audit_input", "project_id", "input_code"),
    )

"""Agricultural input master data: fertilizers, pesticides, seeds.

Source: Public company catalogs, ministry data.
Canonical naming per Semantic Registry v1: input_category, agricultural_input.
"""

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
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
    catalog_status = Column(String(20), nullable=False, default="DRAFT", index=True)
    submitted_at = Column(DateTime(timezone=True))
    reviewed_at = Column(DateTime(timezone=True))
    reviewed_by = Column(UUID(as_uuid=True))
    review_reason = Column(Text)

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


class AgriculturalInputAuditEvent(Base, UUIDPrimaryKey, AuditMixin):
    """Audit event for master agricultural input metadata changes."""

    __tablename__ = "agricultural_input_audit_events"

    tenant_id = Column(String(50), nullable=False, index=True)
    input_id = Column(UUID(as_uuid=True), ForeignKey("agricultural_inputs.id"), nullable=False, index=True)
    input_code = Column(String(50), nullable=False, index=True)
    actor_id = Column(UUID(as_uuid=True))
    action = Column(String(50), nullable=False)
    before_payload = Column(JSONB)
    after_payload = Column(JSONB)
    reason = Column(Text)
    metadata_ = Column("metadata", JSONB, default=dict)

    input = relationship("AgriculturalInput")

    __table_args__ = (
        Index("idx_agricultural_input_audit_input", "input_code", "created_at"),
        Index("idx_agricultural_input_audit_tenant", "tenant_id", "created_at"),
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


class AgriculturalProduct(Base, UUIDPrimaryKey, AuditMixin):
    """Manufacturer-specific branded product mapped to a canonical input."""

    __tablename__ = "agricultural_products"

    code = Column(String(80), unique=True, nullable=False, index=True)
    canonical_input_id = Column(UUID(as_uuid=True), ForeignKey("agricultural_inputs.id"), nullable=False, index=True)
    manufacturer_id = Column(UUID(as_uuid=True), ForeignKey("manufacturers.id"), nullable=False, index=True)
    brand_name = Column(String(200), nullable=False)
    composition = Column(String(300))
    registration_number = Column(String(100), index=True)
    registration_authority = Column(String(150))
    registration_expiry_date = Column(Date)
    country = Column(String(50), default="India")
    status = Column(String(20), nullable=False, default="ACTIVE", index=True)
    metadata_ = Column("metadata", JSONB, default=dict)

    canonical_input = relationship("AgriculturalInput")
    manufacturer = relationship("Manufacturer")
    packages = relationship("AgriculturalProductPackage", back_populates="product", cascade="all, delete-orphan")


class AgriculturalProductPackage(Base, UUIDPrimaryKey, AuditMixin):
    """Sellable package/size for an agricultural product."""

    __tablename__ = "agricultural_product_packages"

    product_id = Column(UUID(as_uuid=True), ForeignKey("agricultural_products.id"), nullable=False, index=True)
    sku = Column(String(100), unique=True, nullable=False, index=True)
    quantity = Column(DECIMAL(12, 3), nullable=False)
    unit = Column(String(20), nullable=False)
    pack_label = Column(String(100), nullable=False)
    barcode = Column(String(100), unique=True)
    status = Column(String(20), nullable=False, default="ACTIVE", index=True)

    product = relationship("AgriculturalProduct", back_populates="packages")


class ProjectProductApproval(Base, UUIDPrimaryKey, AuditMixin):
    """Project allow/preference rule for a branded agricultural product."""

    __tablename__ = "project_product_approvals"

    tenant_id = Column(String(50), nullable=False, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey("agricultural_products.id"), nullable=False, index=True)
    enabled = Column(Boolean, nullable=False, default=True)
    preferred = Column(Boolean, nullable=False, default=False)
    display_order = Column(Integer, nullable=False, default=1000)
    reason = Column(Text)

    product = relationship("AgriculturalProduct")

    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "product_id", name="uq_project_product_approval"),)


class ProductCatalogAuditEvent(Base, UUIDPrimaryKey, AuditMixin):
    """Audit event for manufacturer, product, package and approval mutations."""

    __tablename__ = "product_catalog_audit_events"

    tenant_id = Column(String(50), nullable=False, index=True)
    entity_type = Column(String(30), nullable=False, index=True)
    entity_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    entity_code = Column(String(100), nullable=False, index=True)
    actor_id = Column(UUID(as_uuid=True))
    action = Column(String(50), nullable=False)
    before_payload = Column(JSONB)
    after_payload = Column(JSONB)
    reason = Column(Text)
    metadata_ = Column("metadata", JSONB, default=dict)

    __table_args__ = (Index("idx_product_catalog_audit_entity", "entity_type", "entity_code", "created_at"),)


class InputCatalogImportBatch(Base, UUIDPrimaryKey, AuditMixin):
    """Validated CSV import batch awaiting explicit admin application."""

    __tablename__ = "input_catalog_import_batches"

    tenant_id = Column(String(50), nullable=False, index=True)
    actor_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    file_name = Column(String(255))
    status = Column(String(20), nullable=False, default="VALIDATED", index=True)
    normalized_rows = Column(JSONB, nullable=False, default=list)
    validation_report = Column(JSONB, nullable=False, default=dict)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    applied_at = Column(DateTime(timezone=True))

    __table_args__ = (
        Index("idx_input_catalog_import_tenant_created", "tenant_id", "created_at"),
        Index("idx_input_catalog_import_status_expiry", "status", "expires_at"),
    )

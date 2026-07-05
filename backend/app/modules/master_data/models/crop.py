"""Crop master data: categories, crops, varieties, and lifecycle templates.

Source: ICAR, state agriculture universities, public catalogs.
Pilot: Top 10 crops for Uttar Pradesh.
"""

from sqlalchemy import (
    Boolean,
    Column,
    String,
    Integer,
    Text,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.shared.models import AuditMixin, UUIDPrimaryKey


class CropCategory(Base, UUIDPrimaryKey, AuditMixin):
    """Top-level crop classification (Cereals, Pulses, Oilseeds, etc.)."""

    __tablename__ = "crop_categories"

    code = Column(String(30), unique=True, nullable=False, index=True)
    canonical_name = Column(String(100), nullable=False)
    description = Column(Text)
    aliases = Column(JSONB, default=list)

    # Relationships
    crops = relationship("Crop", back_populates="category")


class Crop(Base, UUIDPrimaryKey, AuditMixin):
    """Individual crop (Rice, Wheat, Sugarcane, etc.)."""

    __tablename__ = "crops"

    code = Column(String(30), unique=True, nullable=False, index=True)
    category_id = Column(
        UUID(as_uuid=True),
        ForeignKey("crop_categories.id"),
        nullable=False,
    )
    canonical_name = Column(String(100), nullable=False)
    scientific_name = Column(String(150))
    description = Column(Text)
    typical_duration_days = Column(Integer)
    suitable_seasons = Column(ARRAY(String), default=list)
    suitable_soil_types = Column(ARRAY(String), default=list)
    aliases = Column(JSONB, default=list)

    # Relationships
    category = relationship("CropCategory", back_populates="crops")
    varieties = relationship("CropVariety", back_populates="crop")
    lifecycle_templates = relationship(
        "CropLifecycleTemplate", back_populates="crop"
    )

    __table_args__ = (
        Index("idx_crop_category", "category_id"),
    )


class CropVariety(Base, UUIDPrimaryKey, AuditMixin):
    """Specific variety of a crop (e.g., Pusa Basmati 1121 for Rice)."""

    __tablename__ = "crop_varieties"

    code = Column(String(50), unique=True, nullable=False, index=True)
    crop_id = Column(
        UUID(as_uuid=True),
        ForeignKey("crops.id"),
        nullable=False,
    )
    canonical_name = Column(String(150), nullable=False)
    developer = Column(String(200))  # e.g., "IARI, New Delhi"
    release_year = Column(Integer)
    duration_days = Column(Integer)
    characteristics = Column(JSONB, default=dict)
    recommended_states = Column(ARRAY(String), default=list)
    aliases = Column(JSONB, default=list)

    # Relationships
    crop = relationship("Crop", back_populates="varieties")

    __table_args__ = (
        Index("idx_variety_crop", "crop_id"),
    )


class CropLifecycleTemplate(Base, UUIDPrimaryKey, AuditMixin):
    """Configurable lifecycle template defining stages for a crop+season.

    Tenant-configurable: enterprises can customize stage names and durations.
    """

    __tablename__ = "crop_lifecycle_templates"

    code = Column(String(50), unique=True, nullable=False, index=True)
    crop_id = Column(
        UUID(as_uuid=True),
        ForeignKey("crops.id"),
        nullable=False,
    )
    season_code = Column(String(20), nullable=False)
    canonical_name = Column(String(150), nullable=False)
    description = Column(Text)
    total_duration_days = Column(Integer)
    stages = Column(JSONB, nullable=False, default=list)
    is_default = Column(Boolean, default=False, nullable=False)
    aliases = Column(JSONB, default=list)

    # Relationships
    crop = relationship("Crop", back_populates="lifecycle_templates")

    __table_args__ = (
        Index("idx_lifecycle_crop", "crop_id"),
        Index("idx_lifecycle_season", "season_code"),
    )


class CropTaxonomyNode(Base, UUIDPrimaryKey, AuditMixin):
    """Flexible crop taxonomy node.

    Supports agronomic, economic, botanical, and client-facing groupings
    without forcing a crop into a single category.
    """

    __tablename__ = "crop_taxonomy_nodes"

    code = Column(String(50), unique=True, nullable=False, index=True)
    canonical_name = Column(String(150), nullable=False)
    description = Column(Text)
    node_type = Column(String(30), nullable=False, default="AGRONOMIC")
    # ROOT, AGRONOMIC, ECONOMIC, BOTANICAL, GROWTH_HABIT, SEASONAL, PROPAGATION
    level = Column(Integer, nullable=False, default=0)
    display_order = Column(Integer, nullable=False, default=0)
    aliases = Column(JSONB, default=list)
    metadata_ = Column("metadata", JSONB, default=dict)

    __table_args__ = (
        Index("idx_crop_taxonomy_node_type", "node_type"),
        Index("idx_crop_taxonomy_display", "level", "display_order"),
    )


class CropTaxonomyEdge(Base, UUIDPrimaryKey, AuditMixin):
    """Parent-child relationship between taxonomy nodes.

    This allows a tree or DAG, so intermediate/higher/lower taxonomy levels can
    be added later without reshaping crops.
    """

    __tablename__ = "crop_taxonomy_edges"

    parent_node_id = Column(UUID(as_uuid=True), ForeignKey("crop_taxonomy_nodes.id"), nullable=False)
    child_node_id = Column(UUID(as_uuid=True), ForeignKey("crop_taxonomy_nodes.id"), nullable=False)
    relationship_type = Column(String(30), nullable=False, default="IS_A")
    display_order = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("parent_node_id", "child_node_id", name="uq_crop_taxonomy_edge"),
        Index("idx_crop_taxonomy_edge_parent", "parent_node_id"),
        Index("idx_crop_taxonomy_edge_child", "child_node_id"),
    )


class CropTaxonomyAssignment(Base, UUIDPrimaryKey, AuditMixin):
    """Many-to-many assignment of crops to taxonomy nodes."""

    __tablename__ = "crop_taxonomy_assignments"

    crop_id = Column(UUID(as_uuid=True), ForeignKey("crops.id"), nullable=False)
    taxonomy_node_id = Column(UUID(as_uuid=True), ForeignKey("crop_taxonomy_nodes.id"), nullable=False)
    assignment_type = Column(String(30), nullable=False, default="PRIMARY")
    # PRIMARY, SECONDARY, ECONOMIC_USE, BOTANICAL, CLIENT_TAG
    is_primary = Column(Boolean, nullable=False, default=False)
    source = Column(String(50), nullable=False, default="SYSTEM")

    __table_args__ = (
        UniqueConstraint("crop_id", "taxonomy_node_id", name="uq_crop_taxonomy_assignment"),
        Index("idx_crop_taxonomy_assignment_crop", "crop_id"),
        Index("idx_crop_taxonomy_assignment_node", "taxonomy_node_id"),
    )


class CropPropagationType(Base, UUIDPrimaryKey, AuditMixin):
    """Canonical crop establishment / propagation type."""

    __tablename__ = "crop_propagation_types"

    code = Column(String(50), unique=True, nullable=False, index=True)
    canonical_name = Column(String(150), nullable=False)
    description = Column(Text)
    establishment_type = Column(String(30), nullable=False, default="SEED")
    # SEED, TRANSPLANT, VEGETATIVE, PERENNIAL_PLANTING
    aliases = Column(JSONB, default=list)
    metadata_ = Column("metadata", JSONB, default=dict)

    __table_args__ = (
        Index("idx_crop_propagation_establishment", "establishment_type"),
    )


class CropPropagationOption(Base, UUIDPrimaryKey, AuditMixin):
    """Allowed propagation options for a crop, optionally season-specific."""

    __tablename__ = "crop_propagation_options"

    crop_id = Column(UUID(as_uuid=True), ForeignKey("crops.id"), nullable=False)
    propagation_type_id = Column(UUID(as_uuid=True), ForeignKey("crop_propagation_types.id"), nullable=False)
    season_code = Column(String(20))
    is_default = Column(Boolean, nullable=False, default=False)
    notes = Column(Text)
    metadata_ = Column("metadata", JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint("crop_id", "propagation_type_id", "season_code", name="uq_crop_propagation_option"),
        Index("idx_crop_propagation_option_crop", "crop_id"),
        Index("idx_crop_propagation_option_type", "propagation_type_id"),
        Index("idx_crop_propagation_option_season", "season_code"),
    )


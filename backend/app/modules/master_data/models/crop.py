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

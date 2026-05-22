"""Geography hierarchy models: State → District → Block → Village.

Canonical naming per Semantic Registry v1.
Data source: Local Government Directory (LGD) India.
Pilot state: Uttar Pradesh.
"""

from sqlalchemy import Column, String, ForeignKey, Index, DECIMAL
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.shared.models import AuditMixin, UUIDPrimaryKey


class GeographyState(Base, UUIDPrimaryKey, AuditMixin):
    """Indian state - top of geography hierarchy."""

    __tablename__ = "geography_states"

    lgd_code = Column(String(20), unique=True, nullable=False, index=True)
    canonical_name = Column(String(100), nullable=False)
    census_name = Column(String(100))
    aliases = Column(JSONB, default=list)

    # Relationships
    districts = relationship("GeographyDistrict", back_populates="state")


class GeographyDistrict(Base, UUIDPrimaryKey, AuditMixin):
    """District within a state."""

    __tablename__ = "geography_districts"

    lgd_code = Column(String(20), unique=True, nullable=False, index=True)
    state_id = Column(
        UUID(as_uuid=True),
        ForeignKey("geography_states.id"),
        nullable=False,
    )
    canonical_name = Column(String(100), nullable=False)
    census_name = Column(String(100))
    aliases = Column(JSONB, default=list)

    # Relationships
    state = relationship("GeographyState", back_populates="districts")
    blocks = relationship("GeographyBlock", back_populates="district")

    __table_args__ = (
        Index("idx_district_state", "state_id"),
    )


class GeographyBlock(Base, UUIDPrimaryKey, AuditMixin):
    """Block/Tehsil/Taluka within a district."""

    __tablename__ = "geography_blocks"

    lgd_code = Column(String(20), unique=True, nullable=False, index=True)
    district_id = Column(
        UUID(as_uuid=True),
        ForeignKey("geography_districts.id"),
        nullable=False,
    )
    canonical_name = Column(String(100), nullable=False)
    aliases = Column(JSONB, default=list)

    # Relationships
    district = relationship("GeographyDistrict", back_populates="blocks")
    villages = relationship("GeographyVillage", back_populates="block")

    __table_args__ = (
        Index("idx_block_district", "district_id"),
    )


class GeographyVillage(Base, UUIDPrimaryKey, AuditMixin):
    """Village - lowest geography unit. Farmers and parcels belong here."""

    __tablename__ = "geography_villages"

    lgd_code = Column(String(30), unique=True, nullable=False, index=True)
    block_id = Column(
        UUID(as_uuid=True),
        ForeignKey("geography_blocks.id"),
        nullable=False,
    )
    district_id = Column(
        UUID(as_uuid=True),
        ForeignKey("geography_districts.id"),
        nullable=False,
    )
    canonical_name = Column(String(150), nullable=False)
    census_name = Column(String(150))
    census_village_code = Column(String(20))
    pin_codes = Column(ARRAY(String), default=list)
    latitude = Column(DECIMAL(10, 8))
    longitude = Column(DECIMAL(11, 8))
    aliases = Column(JSONB, default=list)

    # Relationships
    block = relationship("GeographyBlock", back_populates="villages")

    __table_args__ = (
        Index("idx_village_block", "block_id"),
        Index("idx_village_district", "district_id"),
        Index("idx_village_pin", "pin_codes", postgresql_using="gin"),
        Index(
            "idx_village_search",
            "canonical_name",
            postgresql_using="gin",
            postgresql_ops={"canonical_name": "gin_trgm_ops"},
        ),
    )

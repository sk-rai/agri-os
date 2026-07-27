"""Geography hierarchy models: State → District → Block → Village.

Canonical naming per Semantic Registry v1.
Data source: Local Government Directory (LGD) India.
Pilot state: Uttar Pradesh.
"""

from sqlalchemy import Column, String, ForeignKey, Index, DECIMAL, DateTime, Text, CheckConstraint, UniqueConstraint
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

    lgd_code = Column(String(20), nullable=False, index=True)
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
        UniqueConstraint("district_id", "lgd_code", name="uq_geography_blocks_district_lgd"),
    )


class GeographyVillage(Base, UUIDPrimaryKey, AuditMixin):
    """Village - lowest geography unit. Farmers and parcels belong here."""

    __tablename__ = "geography_villages"

    lgd_code = Column(String(30), nullable=False, index=True)
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
        UniqueConstraint("block_id", "lgd_code", name="uq_geography_villages_block_lgd"),
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


class GeographyImportBatch(Base, UUIDPrimaryKey, AuditMixin):
    """Source snapshot/import provenance for LGD, postal, and future Census geography feeds."""

    __tablename__ = "geography_import_batches"

    source_system = Column(String(80), nullable=False, index=True)
    source_resource_id = Column(String(120))
    source_label = Column(String(255))
    source_url = Column(Text)
    license = Column(String(255))
    raw_manifest_path = Column(Text)
    validation_report_path = Column(Text)
    refresh_mode = Column(String(40), default="INITIAL_FULL_LOAD", nullable=False)
    status = Column(String(40), default="DRAFT", nullable=False, index=True)
    snapshot_status = Column(String(60))
    retrieved_at = Column(DateTime(timezone=True))
    validated_at = Column(DateTime(timezone=True))
    applied_at = Column(DateTime(timezone=True))
    actor_id = Column(String(80))
    reason = Column(Text)
    row_counts = Column(JSONB, default=dict, nullable=False)
    checksums = Column(JSONB, default=dict, nullable=False)
    validation_summary = Column(JSONB, default=dict, nullable=False)
    diff_summary = Column(JSONB, default=dict, nullable=False)


class GeographyPostalReference(Base, UUIDPrimaryKey, AuditMixin):
    """India Post/OGD postal reference row keyed by PIN and post office context."""

    __tablename__ = "geography_postal_references"

    import_batch_id = Column(UUID(as_uuid=True), ForeignKey("geography_import_batches.id"))
    pin_code = Column(String(6), nullable=False, index=True)
    office_name = Column(String(180), nullable=False)
    office_type = Column(String(40))
    delivery_status = Column(String(40))
    circle_name = Column(String(120))
    region_name = Column(String(120))
    division_name = Column(String(120))
    postal_district_name = Column(String(120))
    postal_state_name = Column(String(120), index=True)
    latitude = Column(DECIMAL(10, 8))
    longitude = Column(DECIMAL(11, 8))
    source_system = Column(String(80), default="OGD_ALL_INDIA_PINCODE_DIRECTORY", nullable=False)
    source_row_hash = Column(String(64))
    first_seen_at = Column(DateTime(timezone=True))
    last_seen_at = Column(DateTime(timezone=True))
    expired_at = Column(DateTime(timezone=True))
    metadata_ = Column("metadata", JSONB, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("pin_code ~ '^[1-9][0-9]{5}$'", name="ck_geography_postal_references_pin"),
        UniqueConstraint("pin_code", "office_name", "office_type", "postal_state_name", "postal_district_name", name="uq_geography_postal_references_pin_office"),
    )


class GeographyVillagePinLink(Base, UUIDPrimaryKey, AuditMixin):
    """Many-to-many LGD village to PIN link from OGD LGD villages-with-PIN resource."""

    __tablename__ = "geography_village_pin_links"

    import_batch_id = Column(UUID(as_uuid=True), ForeignKey("geography_import_batches.id"))
    geography_village_id = Column(UUID(as_uuid=True), ForeignKey("geography_villages.id"), index=True)
    pin_code = Column(String(6), nullable=False, index=True)
    state_lgd_code = Column(String(20), nullable=False)
    state_name = Column(String(120))
    district_lgd_code = Column(String(20), nullable=False)
    district_name = Column(String(120))
    subdistrict_lgd_code = Column(String(20), nullable=False)
    subdistrict_name = Column(String(120))
    village_lgd_code = Column(String(30), nullable=False)
    village_name = Column(String(180))
    source_system = Column(String(80), default="OGD_LGD_VILLAGES_PIN_CODES", nullable=False)
    source_row_hash = Column(String(64))
    match_status = Column(String(40), default="UNMATCHED", nullable=False)
    first_seen_at = Column(DateTime(timezone=True))
    last_seen_at = Column(DateTime(timezone=True))
    expired_at = Column(DateTime(timezone=True))
    metadata_ = Column("metadata", JSONB, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("pin_code ~ '^[1-9][0-9]{5}$'", name="ck_geography_village_pin_links_pin"),
        UniqueConstraint("state_lgd_code", "district_lgd_code", "subdistrict_lgd_code", "village_lgd_code", "pin_code", name="uq_geography_village_pin_links_context_pin"),
        Index("idx_geography_village_pin_links_lgd_context", "state_lgd_code", "district_lgd_code", "subdistrict_lgd_code", "village_lgd_code"),
    )

class GeographyClimateRegion(Base, UUIDPrimaryKey, AuditMixin):
    """Agro-climatic/agro-ecological reference region for suitability metadata."""

    __tablename__ = "geography_climate_regions"

    region_code = Column(String(80), unique=True, nullable=False, index=True)
    region_name = Column(String(180), nullable=False)
    region_system = Column(String(60), nullable=False, index=True)
    parent_region_code = Column(String(80), index=True)
    country_code = Column(String(3), default="IND", nullable=False, index=True)
    rainfall_band_mm = Column(JSONB, default=dict, nullable=False)
    temperature_band_c = Column(JSONB, default=dict, nullable=False)
    length_of_growing_period_days = Column(JSONB, default=dict, nullable=False)
    dominant_soil_groups = Column(JSONB, default=list, nullable=False)
    irrigation_context = Column(JSONB, default=dict, nullable=False)
    source_references = Column(JSONB, default=list, nullable=False)
    confidence = Column(String(50), nullable=False, default="LOCAL_DEMO_SEED")
    review_status = Column(String(40), nullable=False, default="MANUAL_REVIEW", index=True)
    metadata_ = Column("metadata", JSONB, default=dict, nullable=False)

    __table_args__ = (
        Index("idx_geography_climate_region_system", "region_system", "review_status"),
    )


class GeographyClimateRegionMapping(Base, UUIDPrimaryKey, AuditMixin):
    """Maps climate/agro-ecological regions to LGD geography scopes."""

    __tablename__ = "geography_climate_region_mappings"

    region_id = Column(UUID(as_uuid=True), ForeignKey("geography_climate_regions.id"), nullable=False, index=True)
    region_code = Column(String(80), nullable=False, index=True)
    scope_level = Column(String(30), nullable=False, index=True)
    state_lgd_code = Column(String(20), index=True)
    district_lgd_code = Column(String(20), index=True)
    block_lgd_code = Column(String(20), index=True)
    village_lgd_code = Column(String(30), index=True)
    pin_code = Column(String(6), index=True)
    source_references = Column(JSONB, default=list, nullable=False)
    confidence = Column(String(50), nullable=False, default="LOCAL_DEMO_SEED")
    review_status = Column(String(40), nullable=False, default="MANUAL_REVIEW", index=True)
    metadata_ = Column("metadata", JSONB, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "region_code",
            "scope_level",
            "state_lgd_code",
            "district_lgd_code",
            "block_lgd_code",
            "village_lgd_code",
            "pin_code",
            name="uq_geography_climate_region_mapping_scope",
        ),
        Index("idx_geography_climate_region_mapping_lookup", "scope_level", "state_lgd_code", "district_lgd_code", "pin_code"),
    )


"""Farmer and Parcel operational models.

Per ADR-005 (MVP Vertical Slice):
- Farmer: progressive enrollment (mobile + village + crop is enough to start)
- Parcel: GPS polygon is OPTIONAL. Reported area + village is minimum.

Per Farmer Value Ladder:
- Level 1: Registration (weather/advisory)
- Level 2: Parcel mapping (localized alerts)
- Level 3: Crop tracking (stage reminders)

Geometry progression:
- NONE: farmer-reported area only (enrollment day)
- PIN_DROP: single GPS point (dealer visit)
- GPS_WALK: full polygon boundary (motivated farmer)
- SATELLITE: remote sensing boundary (future)
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Integer, Text, DECIMAL, Date,
    ForeignKey, Index, Boolean, DateTime, CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from geoalchemy2 import Geometry
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.shared.models import AuditMixin, UUIDPrimaryKey


class Tenant(Base, AuditMixin):
    """Enterprise tenant (fertilizer company, FPO, insurer, etc.)."""

    __tablename__ = "tenants"

    id = Column(String(50), primary_key=True)
    name = Column(String(200), nullable=False)
    type = Column(String(30), nullable=False, default="ENTERPRISE")
    # ENTERPRISE, FPO, INSURER, GOVERNMENT
    contact_email = Column(String(200))
    contact_phone = Column(String(15))
    config = Column(JSONB, default=dict)  # Tenant-specific configuration

    # Relationships
    projects = relationship("Project", back_populates="tenant")


class Project(Base, UUIDPrimaryKey, AuditMixin):
    """A time-bound operational project within a tenant.

    Examples:
    - "Kharif 2026 UP Wheat Program"
    - "Rabi 2026 Sugarcane Monitoring - Gorakhpur"

    Projects scope: geography, crops, duration, enrolled users.
    """

    __tablename__ = "projects"

    tenant_id = Column(String(50), ForeignKey("tenants.id"), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(String(20), nullable=False, default="PLANNED")
    # PLANNED, ACTIVE, COMPLETED, ARCHIVED
    geography_scope = Column(JSONB, default=dict)
    # {"state_ids": [], "district_ids": [], "block_ids": []}
    crop_scope = Column(JSONB, default=list)
    # ["RICE", "WHEAT", "SUGARCANE"]
    config = Column(JSONB, default=dict)
    # Project-specific overrides (lifecycle templates, KPI targets, etc.)

    # Relationships
    tenant = relationship("Tenant", back_populates="projects")
    roles = relationship("ProjectRole", back_populates="project")

    __table_args__ = (
        Index("idx_project_tenant", "tenant_id"),
        Index("idx_project_status", "status"),
        CheckConstraint(
            "status IN ('PLANNED', 'ACTIVE', 'COMPLETED', 'ARCHIVED')",
            name="ck_project_status",
        ),
    )


class ProjectRole(Base, UUIDPrimaryKey, AuditMixin):
    """User assigned to a project with a specific role and territory scope.

    A dealer might be assigned to 5 villages within a project.
    A field agent might cover an entire block.
    """

    __tablename__ = "project_roles"

    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=False)  # No FK — user may not exist yet
    role = Column(String(30), nullable=False)
    # DEALER, FIELD_AGENT, AGRONOMIST, MANAGER, ENTERPRISE_ADMIN
    territory_scope = Column(JSONB, default=dict)
    # {"village_ids": [], "block_ids": [], "district_ids": []}

    # Relationships
    project = relationship("Project", back_populates="roles")

    __table_args__ = (
        Index("idx_project_role_project", "project_id"),
        Index("idx_project_role_user", "user_id"),
        Index("idx_project_role_unique", "project_id", "user_id", unique=True),
    )


class Farmer(Base, UUIDPrimaryKey, AuditMixin):
    """Farmer profile — progressive enrollment.

    Minimum for enrollment: mobile_number + village_id + primary_crop
    Everything else is collected progressively over time.

    Per Farmer Value Ladder: farmer gets value (weather/advisory)
    immediately after minimal registration.
    """

    __tablename__ = "farmers"

    tenant_id = Column(String(50), ForeignKey("tenants.id"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))

    # Minimum required (enrollment day)
    mobile_number = Column(String(15), nullable=False)
    village_id = Column(UUID(as_uuid=True), ForeignKey("geography_villages.id"))  # Nullable for manual villages
    village_name_manual = Column(String(200))  # If village not in LGD DB
    primary_crop_code = Column(String(30))  # From canonical crop codes
    crops_by_season = Column(JSONB, default=dict)  # {"KHARIF": ["RICE"], "RABI": ["WHEAT"]}

    # Progressive (collected over time)
    display_name = Column(String(100))
    father_name = Column(String(100))
    age = Column(Integer)
    gender = Column(String(10))  # MALE, FEMALE, OTHER
    education_level = Column(String(30))
    total_land_area = Column(DECIMAL(10, 2))  # Farmer-reported total
    total_land_unit = Column(String(20), default="BIGHA")
    # BIGHA, BISWA, HECTARE, ACRE, KATHA
    government_id_type = Column(String(30))  # AADHAAR, VOTER_ID, etc.
    government_id_hash = Column(String(64))  # SHA256 hash (never store plaintext)
    aadhaar_number = Column(String(12))  # 12-digit Aadhaar (plaintext for pilot, encrypt in prod)
    bank_account_linked = Column(Boolean, default=False)
    language_preference = Column(String(10), default="hi")

    # Enrollment metadata
    enrolled_by = Column(UUID(as_uuid=True))  # Dealer/agent who enrolled
    enrollment_method = Column(String(20), default="ASSISTED")
    # ASSISTED (dealer did it), SELF (farmer did it), BULK (CSV import)
    enrollment_gps_lat = Column(DECIMAL(10, 8))
    enrollment_gps_lng = Column(DECIMAL(11, 8))

    # Status
    status = Column(String(20), default="ACTIVE", nullable=False)
    # PENDING, ACTIVE, INACTIVE, SUSPENDED

    __table_args__ = (
        Index("idx_farmer_tenant", "tenant_id"),
        Index("idx_farmer_project", "project_id"),
        Index("idx_farmer_village", "village_id"),
        Index("idx_farmer_mobile", "mobile_number"),
        Index("idx_farmer_status", "status"),
    )


class Parcel(Base, UUIDPrimaryKey, AuditMixin):
    """A piece of agricultural land belonging to a farmer.

    PROGRESSIVE GEOMETRY MODEL:
    - Level 1 (NONE): farmer-reported area only. No GPS. Enrollment day.
    - Level 2 (PIN_DROP): single GPS point (centroid). Dealer visit.
    - Level 3 (GPS_WALK): full polygon boundary. Motivated farmer.
    - Level 4 (SATELLITE): remote sensing boundary. Future.

    GPS polygon is NEVER mandatory. Farmer-reported area is always accepted.
    Computed area (from geometry) supplements but doesn't replace reported area.
    """

    __tablename__ = "parcels"

    tenant_id = Column(String(50), ForeignKey("tenants.id"), nullable=False)
    farmer_id = Column(UUID(as_uuid=True), ForeignKey("farmers.id"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"))

    # Always required (enrollment day)
    village_id = Column(UUID(as_uuid=True), ForeignKey("geography_villages.id"))  # Nullable for manual
    village_name_manual = Column(String(200))  # If village not in LGD DB
    reported_area = Column(DECIMAL(10, 2), nullable=False)  # Farmer says "3 bigha"
    reported_area_unit = Column(String(20), nullable=False, default="BIGHA")
    # BIGHA, BISWA, HECTARE, ACRE, KATHA, GUNTHA
    soil_type_code = Column(String(30))  # From soil_types.code
    current_crop_code = Column(String(30))  # What's growing now

    # Progressive geometry (optional, encouraged)
    geometry_source = Column(String(20), nullable=False, default="NONE")
    # NONE, PIN_DROP, GPS_WALK, SATELLITE
    centroid_lat = Column(DECIMAL(10, 8))  # Single pin drop
    centroid_lng = Column(DECIMAL(11, 8))
    geometry = Column(Geometry("POLYGON", srid=4326))  # Full polygon (nullable)
    computed_area_hectares = Column(DECIMAL(10, 4))  # From ST_Area(geometry)
    geometry_accuracy_meters = Column(DECIMAL(6, 1))  # GPS accuracy at capture
    geometry_captured_at = Column(DateTime(timezone=True))
    geometry_captured_by = Column(UUID(as_uuid=True))  # Who did the GPS walk

    # Parcel identification
    local_name = Column(String(100))  # Farmer's name for this land
    survey_number = Column(String(100))  # Government survey/khasra number
    ownership_type = Column(String(30), default="OWNED")
    # OWNED, LEASED, SHARED, SHARECROP, FAMILY
    annual_rent = Column(DECIMAL(12, 2))  # Only for LEASED parcels
    annual_rent_currency = Column(String(3), default="INR")
    irrigation_source = Column(String(50))
    # TUBEWELL_DIESEL, TUBEWELL_ELECTRIC, CANAL, PURCHASED_WATER, RAIN_FED, POND_TANK, RIVER_STREAM
    share_percentage = Column(Integer)  # For SHARED ownership (1-100)
    sharecrop_percentage = Column(Integer)  # For SHARECROP (harvest share %)

    # Status
    status = Column(String(20), default="ACTIVE", nullable=False)
    # DRAFT, ACTIVE, INACTIVE, DISPUTED

    __table_args__ = (
        Index("idx_parcel_tenant", "tenant_id"),
        Index("idx_parcel_farmer", "farmer_id"),
        Index("idx_parcel_village", "village_id"),
        Index("idx_parcel_project", "project_id"),
        Index("idx_parcel_geometry", "geometry", postgresql_using="gist"),
    )

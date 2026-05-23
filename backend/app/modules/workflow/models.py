"""Crop cycle and activity models — the main operational workflow.

A crop cycle represents one growing season on one parcel:
  Farmer → Parcel → Crop Cycle → Stages → Activities

Per architecture spec:
- crop_cycle states: PLANNED, ACTIVE, PARTIALLY_TRACKED, COMPLETED, ABANDONED, ARCHIVED
- crop_stage states: PENDING, ACTIVE, COMPLETED, SKIPPED, PARTIALLY_COMPLETED, FAILED
- Transition rule: EXPLICIT ONLY (never auto-advance)
- Configuration-driven: stages loaded from crop_lifecycle_templates (never hardcoded)
- Activities are stage-aware (linked to the current stage)

Per ADR-003 (Workflow Ownership):
- Workflow Engine: validates state transitions
- Rules Engine: decides (triggers, escalations)
- Notification Engine: delivers messages
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Integer, Text, DECIMAL, Date, DateTime,
    ForeignKey, Index, Boolean, CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.shared.models import AuditMixin, UUIDPrimaryKey


class CropCycle(Base, UUIDPrimaryKey, AuditMixin):
    """One growing season of one crop on one parcel.

    Lifecycle: PLANNED → ACTIVE → COMPLETED (or ABANDONED)
    Stages are loaded from crop_lifecycle_templates — never hardcoded.
    """

    __tablename__ = "crop_cycles"

    tenant_id = Column(String(50), ForeignKey("tenants.id"), nullable=False)
    farmer_id = Column(UUID(as_uuid=True), ForeignKey("farmers.id"), nullable=False)
    parcel_id = Column(UUID(as_uuid=True), ForeignKey("parcels.id"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"))

    # Crop + template (configuration-driven)
    crop_code = Column(String(30), nullable=False)
    variety_code = Column(String(50))
    season_code = Column(String(20), nullable=False)  # KHARIF, RABI, ZAID
    lifecycle_template_id = Column(
        UUID(as_uuid=True),
        ForeignKey("crop_lifecycle_templates.id"),
        nullable=False,
    )

    # Dates
    planned_sowing_date = Column(Date)
    actual_sowing_date = Column(Date)
    expected_harvest_date = Column(Date)
    actual_harvest_date = Column(Date)

    # Status
    status = Column(String(30), nullable=False, default="PLANNED")
    # PLANNED, ACTIVE, PARTIALLY_TRACKED, COMPLETED, ABANDONED, ARCHIVED

    # Yield (filled at harvest)
    reported_yield_kg = Column(DECIMAL(10, 2))
    reported_yield_unit = Column(String(20))  # KG, QUINTAL, TON

    # Economics summary (computed from activities)
    total_input_cost = Column(DECIMAL(12, 2))
    total_revenue = Column(DECIMAL(12, 2))

    # Metadata
    notes = Column(Text)

    __table_args__ = (
        Index("idx_crop_cycle_tenant", "tenant_id"),
        Index("idx_crop_cycle_farmer", "farmer_id"),
        Index("idx_crop_cycle_parcel", "parcel_id"),
        Index("idx_crop_cycle_status", "status"),
        Index("idx_crop_cycle_season", "season_code"),
        CheckConstraint(
            "status IN ('PLANNED', 'ACTIVE', 'PARTIALLY_TRACKED', 'COMPLETED', 'ABANDONED', 'ARCHIVED')",
            name="ck_crop_cycle_status",
        ),
    )


class CropStageInstance(Base, UUIDPrimaryKey, AuditMixin):
    """A specific stage within a crop cycle.

    Created when crop cycle starts — one instance per stage in the template.
    Transitions: PENDING → ACTIVE → COMPLETED (or SKIPPED/FAILED)
    Transition is EXPLICIT ONLY — never auto-advances.
    """

    __tablename__ = "crop_stage_instances"

    crop_cycle_id = Column(UUID(as_uuid=True), ForeignKey("crop_cycles.id"), nullable=False)
    tenant_id = Column(String(50), nullable=False)

    # Stage identity (from lifecycle template — never hardcoded)
    stage_code = Column(String(50), nullable=False)  # e.g., NURSERY, TRANSPLANTING
    stage_name = Column(String(100), nullable=False)  # Display name from template
    stage_order = Column(Integer, nullable=False)
    expected_duration_days = Column(Integer)

    # BBCH mapping (optional — for scientific interoperability)
    bbch_range_start = Column(Integer)  # e.g., 0 (germination start)
    bbch_range_end = Column(Integer)    # e.g., 9 (germination end)

    # Dates
    planned_start_date = Column(Date)
    actual_start_date = Column(Date)
    actual_end_date = Column(Date)

    # Status
    status = Column(String(30), nullable=False, default="PENDING")
    # PENDING, ACTIVE, COMPLETED, SKIPPED, PARTIALLY_COMPLETED, FAILED

    # Transition metadata
    started_by = Column(UUID(as_uuid=True))  # Actor who started this stage
    completed_by = Column(UUID(as_uuid=True))  # Actor who completed
    skip_reason = Column(Text)  # If SKIPPED, why

    __table_args__ = (
        Index("idx_stage_instance_cycle", "crop_cycle_id"),
        Index("idx_stage_instance_status", "status"),
        Index("idx_stage_instance_order", "crop_cycle_id", "stage_order"),
        CheckConstraint(
            "status IN ('PENDING', 'ACTIVE', 'COMPLETED', 'SKIPPED', 'PARTIALLY_COMPLETED', 'FAILED')",
            name="ck_stage_instance_status",
        ),
    )


class CropActivity(Base, UUIDPrimaryKey, AuditMixin):
    """An operational activity logged during a crop cycle.

    Types: FERTILIZER, PESTICIDE, IRRIGATION, LABOR, MACHINERY, OTHER
    Activities are STAGE-AWARE — linked to the current active stage.
    Append-only for conflict resolution (per sync conflict registry).
    """

    __tablename__ = "crop_activities"

    crop_cycle_id = Column(UUID(as_uuid=True), ForeignKey("crop_cycles.id"), nullable=False)
    stage_instance_id = Column(UUID(as_uuid=True), ForeignKey("crop_stage_instances.id"))
    tenant_id = Column(String(50), nullable=False)
    farmer_id = Column(UUID(as_uuid=True), ForeignKey("farmers.id"), nullable=False)

    # Activity type
    activity_type = Column(String(30), nullable=False)
    # FERTILIZER, PESTICIDE, IRRIGATION, LABOR, MACHINERY, HARVEST, OTHER

    # What was used/done
    input_code = Column(String(50))  # From agricultural_inputs.code
    input_name = Column(String(200))  # Display name (for offline)
    quantity = Column(DECIMAL(10, 2))
    quantity_unit = Column(String(20))  # KG, LITRE, HOURS, etc.
    area_applied = Column(DECIMAL(10, 2))  # Area this was applied to
    area_unit = Column(String(20))

    # Cost
    cost_amount = Column(DECIMAL(12, 2))
    cost_currency = Column(String(5), default="INR")

    # When & where
    activity_date = Column(Date, nullable=False)
    gps_lat = Column(DECIMAL(10, 8))
    gps_lng = Column(DECIMAL(11, 8))

    # Who logged it
    logged_by = Column(UUID(as_uuid=True), nullable=False)
    logging_method = Column(String(20), default="MANUAL")
    # MANUAL, OCR, VOICE, BULK

    notes = Column(Text)

    __table_args__ = (
        Index("idx_activity_cycle", "crop_cycle_id"),
        Index("idx_activity_stage", "stage_instance_id"),
        Index("idx_activity_type", "activity_type"),
        Index("idx_activity_date", "activity_date"),
        Index("idx_activity_tenant", "tenant_id"),
    )

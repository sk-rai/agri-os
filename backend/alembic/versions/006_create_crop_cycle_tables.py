"""Create crop cycle, stage instance, and activity tables

Revision ID: 006
Revises: 005
Create Date: 2026-05-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- bbch_principal_stages (universal reference) ---
    op.create_table(
        "bbch_principal_stages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.Integer, unique=True, nullable=False),
        sa.Column("code_range_start", sa.Integer, nullable=False),
        sa.Column("code_range_end", sa.Integer, nullable=False),
        sa.Column("canonical_name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("aliases", JSONB, server_default="[]"),
        sa.Column("applicable_crop_types", JSONB, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(10), server_default="v1.0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
    )

    # --- crop_cycles ---
    op.create_table(
        "crop_cycles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(50), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("farmer_id", UUID(as_uuid=True), sa.ForeignKey("farmers.id"), nullable=False),
        sa.Column("parcel_id", UUID(as_uuid=True), sa.ForeignKey("parcels.id"), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id")),
        sa.Column("crop_code", sa.String(30), nullable=False),
        sa.Column("variety_code", sa.String(50)),
        sa.Column("season_code", sa.String(20), nullable=False),
        sa.Column("lifecycle_template_id", UUID(as_uuid=True), sa.ForeignKey("crop_lifecycle_templates.id"), nullable=False),
        sa.Column("planned_sowing_date", sa.Date),
        sa.Column("actual_sowing_date", sa.Date),
        sa.Column("expected_harvest_date", sa.Date),
        sa.Column("actual_harvest_date", sa.Date),
        sa.Column("status", sa.String(30), nullable=False, server_default="PLANNED"),
        sa.Column("reported_yield_kg", sa.DECIMAL(10, 2)),
        sa.Column("reported_yield_unit", sa.String(20)),
        sa.Column("total_input_cost", sa.DECIMAL(12, 2)),
        sa.Column("total_revenue", sa.DECIMAL(12, 2)),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(10), server_default="v1.0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
    )
    op.create_index("idx_crop_cycle_tenant", "crop_cycles", ["tenant_id"])
    op.create_index("idx_crop_cycle_farmer", "crop_cycles", ["farmer_id"])
    op.create_index("idx_crop_cycle_parcel", "crop_cycles", ["parcel_id"])
    op.create_index("idx_crop_cycle_status", "crop_cycles", ["status"])
    op.create_index("idx_crop_cycle_season", "crop_cycles", ["season_code"])

    # --- crop_stage_instances ---
    op.create_table(
        "crop_stage_instances",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("crop_cycle_id", UUID(as_uuid=True), sa.ForeignKey("crop_cycles.id"), nullable=False),
        sa.Column("tenant_id", sa.String(50), nullable=False),
        sa.Column("stage_code", sa.String(50), nullable=False),
        sa.Column("stage_name", sa.String(100), nullable=False),
        sa.Column("stage_order", sa.Integer, nullable=False),
        sa.Column("expected_duration_days", sa.Integer),
        sa.Column("bbch_range_start", sa.Integer),
        sa.Column("bbch_range_end", sa.Integer),
        sa.Column("planned_start_date", sa.Date),
        sa.Column("actual_start_date", sa.Date),
        sa.Column("actual_end_date", sa.Date),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING"),
        sa.Column("started_by", UUID(as_uuid=True)),
        sa.Column("completed_by", UUID(as_uuid=True)),
        sa.Column("skip_reason", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(10), server_default="v1.0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
    )
    op.create_index("idx_stage_instance_cycle", "crop_stage_instances", ["crop_cycle_id"])
    op.create_index("idx_stage_instance_status", "crop_stage_instances", ["status"])
    op.create_index("idx_stage_instance_order", "crop_stage_instances", ["crop_cycle_id", "stage_order"])

    # --- crop_activities ---
    op.create_table(
        "crop_activities",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("crop_cycle_id", UUID(as_uuid=True), sa.ForeignKey("crop_cycles.id"), nullable=False),
        sa.Column("stage_instance_id", UUID(as_uuid=True), sa.ForeignKey("crop_stage_instances.id")),
        sa.Column("tenant_id", sa.String(50), nullable=False),
        sa.Column("farmer_id", UUID(as_uuid=True), sa.ForeignKey("farmers.id"), nullable=False),
        sa.Column("activity_type", sa.String(30), nullable=False),
        sa.Column("input_code", sa.String(50)),
        sa.Column("input_name", sa.String(200)),
        sa.Column("quantity", sa.DECIMAL(10, 2)),
        sa.Column("quantity_unit", sa.String(20)),
        sa.Column("area_applied", sa.DECIMAL(10, 2)),
        sa.Column("area_unit", sa.String(20)),
        sa.Column("cost_amount", sa.DECIMAL(12, 2)),
        sa.Column("cost_currency", sa.String(5), server_default="INR"),
        sa.Column("activity_date", sa.Date, nullable=False),
        sa.Column("gps_lat", sa.DECIMAL(10, 8)),
        sa.Column("gps_lng", sa.DECIMAL(11, 8)),
        sa.Column("logged_by", UUID(as_uuid=True), nullable=False),
        sa.Column("logging_method", sa.String(20), server_default="MANUAL"),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(10), server_default="v1.0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
    )
    op.create_index("idx_activity_cycle", "crop_activities", ["crop_cycle_id"])
    op.create_index("idx_activity_stage", "crop_activities", ["stage_instance_id"])
    op.create_index("idx_activity_type", "crop_activities", ["activity_type"])
    op.create_index("idx_activity_date", "crop_activities", ["activity_date"])
    op.create_index("idx_activity_tenant", "crop_activities", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("crop_activities")
    op.drop_table("crop_stage_instances")
    op.drop_table("crop_cycles")
    op.drop_table("bbch_principal_stages")

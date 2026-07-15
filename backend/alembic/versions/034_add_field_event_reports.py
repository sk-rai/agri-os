"""add field event reports

Revision ID: 034
Revises: 033
Create Date: 2026-07-15 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "034"
down_revision: Union[str, None] = "033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "field_event_reports",
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("farmer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parcel_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("crop_cycle_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("stage_code", sa.String(length=50), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="MEDIUM"),
        sa.Column("event_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lat", sa.String(length=40), nullable=True),
        sa.Column("lng", sa.String(length=40), nullable=True),
        sa.Column("accuracy_meters", sa.String(length=40), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("estimated_area_affected", sa.String(length=40), nullable=True),
        sa.Column("estimated_loss_percent", sa.String(length=40), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=False, server_default="FARMER_ANDROID"),
        sa.Column("external_source", sa.String(length=100), nullable=True),
        sa.Column("external_event_id", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="REPORTED"),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(length=10), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("event_type IN ('RAIN', 'PEST', 'DISEASE', 'HAILSTORM', 'LOCUST', 'FLOOD', 'DROUGHT_STRESS', 'THUNDERSTORM_WIND', 'HEAT_STRESS', 'COLD_STRESS', 'IRRIGATION_FAILURE', 'OTHER')", name="ck_field_event_type"),
        sa.CheckConstraint("severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')", name="ck_field_event_severity"),
        sa.CheckConstraint("source IN ('FARMER_ANDROID', 'FIELD_AGENT_ANDROID', 'ADMIN_WEB', 'EXTERNAL_API', 'IOT_DEVICE')", name="ck_field_event_source"),
        sa.CheckConstraint("status IN ('REPORTED', 'UNDER_REVIEW', 'ADVISORY_SENT', 'RESOLVED', 'DISMISSED')", name="ck_field_event_status"),
        sa.ForeignKeyConstraint(["crop_cycle_id"], ["crop_cycles.id"]),
        sa.ForeignKeyConstraint(["farmer_id"], ["farmers.id"]),
        sa.ForeignKeyConstraint(["parcel_id"], ["parcels.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_field_event_tenant", "field_event_reports", ["tenant_id"], unique=False)
    op.create_index("idx_field_event_project", "field_event_reports", ["project_id"], unique=False)
    op.create_index("idx_field_event_farmer", "field_event_reports", ["farmer_id"], unique=False)
    op.create_index("idx_field_event_parcel", "field_event_reports", ["parcel_id"], unique=False)
    op.create_index("idx_field_event_cycle", "field_event_reports", ["crop_cycle_id"], unique=False)
    op.create_index("idx_field_event_type", "field_event_reports", ["event_type"], unique=False)
    op.create_index("idx_field_event_severity", "field_event_reports", ["severity"], unique=False)
    op.create_index("idx_field_event_status", "field_event_reports", ["status"], unique=False)
    op.create_index("idx_field_event_reported_at", "field_event_reports", ["reported_at"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_field_event_reported_at", table_name="field_event_reports")
    op.drop_index("idx_field_event_status", table_name="field_event_reports")
    op.drop_index("idx_field_event_severity", table_name="field_event_reports")
    op.drop_index("idx_field_event_type", table_name="field_event_reports")
    op.drop_index("idx_field_event_cycle", table_name="field_event_reports")
    op.drop_index("idx_field_event_parcel", table_name="field_event_reports")
    op.drop_index("idx_field_event_farmer", table_name="field_event_reports")
    op.drop_index("idx_field_event_project", table_name="field_event_reports")
    op.drop_index("idx_field_event_tenant", table_name="field_event_reports")
    op.drop_table("field_event_reports")

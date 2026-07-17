"""add weather snapshot foundation

Revision ID: 039
Revises: 038
Create Date: 2026-07-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "weather_provider_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("provider_code", sa.String(length=80), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("provider_type", sa.String(length=40), nullable=False, server_default="EXTERNAL_API"),
        sa.Column("refresh_interval_hours", sa.Integer(), nullable=False, server_default="6"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_refresh_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_refresh_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("provider_type IN ('EXTERNAL_API', 'MANUAL', 'INTERNAL_MODEL', 'SATELLITE', 'IOT_STATION')", name="ck_weather_provider_type"),
        sa.CheckConstraint("refresh_interval_hours >= 1 AND refresh_interval_hours <= 168", name="ck_weather_provider_refresh_interval"),
    )
    op.create_index("idx_weather_provider_tenant_code", "weather_provider_configs", ["tenant_id", "provider_code"], unique=True)
    op.create_index("idx_weather_provider_enabled", "weather_provider_configs", ["tenant_id", "is_enabled"])

    op.create_table(
        "weather_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("weather_provider_configs.id"), nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("farmer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("parcel_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("location_scope", sa.String(length=40), nullable=False, server_default="GEOPOINT"),
        sa.Column("location_key", sa.String(length=160), nullable=True),
        sa.Column("lat", sa.String(length=40), nullable=True),
        sa.Column("lng", sa.String(length=40), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("forecast_valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("forecast_valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary", sa.String(length=200), nullable=True),
        sa.Column("condition_code", sa.String(length=80), nullable=True),
        sa.Column("rainfall_probability_percent", sa.Integer(), nullable=True),
        sa.Column("rainfall_mm", sa.String(length=40), nullable=True),
        sa.Column("temperature_min_c", sa.String(length=40), nullable=True),
        sa.Column("temperature_max_c", sa.String(length=40), nullable=True),
        sa.Column("humidity_percent", sa.Integer(), nullable=True),
        sa.Column("wind_speed_kmph", sa.String(length=40), nullable=True),
        sa.Column("risk_flags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("location_scope IN ('TENANT', 'PROJECT', 'FARMER', 'PARCEL', 'GEOPOINT', 'PINCODE', 'VILLAGE', 'DISTRICT', 'STATE', 'WEATHER_GRID')", name="ck_weather_snapshot_location_scope"),
    )
    op.create_index("ix_weather_snapshots_tenant_id", "weather_snapshots", ["tenant_id"])
    op.create_index("ix_weather_snapshots_provider_id", "weather_snapshots", ["provider_id"])
    op.create_index("ix_weather_snapshots_project_id", "weather_snapshots", ["project_id"])
    op.create_index("ix_weather_snapshots_farmer_id", "weather_snapshots", ["farmer_id"])
    op.create_index("ix_weather_snapshots_parcel_id", "weather_snapshots", ["parcel_id"])
    op.create_index("ix_weather_snapshots_location_key", "weather_snapshots", ["location_key"])
    op.create_index("ix_weather_snapshots_expires_at", "weather_snapshots", ["expires_at"])
    op.create_index("ix_weather_snapshots_condition_code", "weather_snapshots", ["condition_code"])
    op.create_index("idx_weather_snapshot_tenant_scope", "weather_snapshots", ["tenant_id", "location_scope", "location_key"])
    op.create_index("idx_weather_snapshot_validity", "weather_snapshots", ["tenant_id", "forecast_valid_from", "forecast_valid_to"])
    op.create_index("idx_weather_snapshot_fetched", "weather_snapshots", ["tenant_id", "fetched_at"])


def downgrade():
    op.drop_index("idx_weather_snapshot_fetched", table_name="weather_snapshots")
    op.drop_index("idx_weather_snapshot_validity", table_name="weather_snapshots")
    op.drop_index("idx_weather_snapshot_tenant_scope", table_name="weather_snapshots")
    op.drop_index("ix_weather_snapshots_condition_code", table_name="weather_snapshots")
    op.drop_index("ix_weather_snapshots_expires_at", table_name="weather_snapshots")
    op.drop_index("ix_weather_snapshots_location_key", table_name="weather_snapshots")
    op.drop_index("ix_weather_snapshots_parcel_id", table_name="weather_snapshots")
    op.drop_index("ix_weather_snapshots_farmer_id", table_name="weather_snapshots")
    op.drop_index("ix_weather_snapshots_project_id", table_name="weather_snapshots")
    op.drop_index("ix_weather_snapshots_provider_id", table_name="weather_snapshots")
    op.drop_index("ix_weather_snapshots_tenant_id", table_name="weather_snapshots")
    op.drop_table("weather_snapshots")
    op.drop_index("idx_weather_provider_enabled", table_name="weather_provider_configs")
    op.drop_index("idx_weather_provider_tenant_code", table_name="weather_provider_configs")
    op.drop_table("weather_provider_configs")

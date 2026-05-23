"""Create tenant, project, farmer, parcel tables

Revision ID: 005
Revises: 004
Create Date: 2026-05-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from geoalchemy2 import Geometry

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- tenants ---
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("type", sa.String(30), nullable=False, server_default="ENTERPRISE"),
        sa.Column("contact_email", sa.String(200)),
        sa.Column("contact_phone", sa.String(15)),
        sa.Column("config", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(10), server_default="v1.0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
    )

    # --- projects ---
    op.create_table(
        "projects",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(50), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PLANNED"),
        sa.Column("geography_scope", JSONB, server_default="{}"),
        sa.Column("crop_scope", JSONB, server_default="[]"),
        sa.Column("config", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(10), server_default="v1.0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
    )
    op.create_index("idx_project_tenant", "projects", ["tenant_id"])
    op.create_index("idx_project_status", "projects", ["status"])

    # --- project_roles ---
    op.create_table(
        "project_roles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("territory_scope", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(10), server_default="v1.0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
    )
    op.create_index("idx_project_role_project", "project_roles", ["project_id"])
    op.create_index("idx_project_role_user", "project_roles", ["user_id"])
    op.create_index("idx_project_role_unique", "project_roles", ["project_id", "user_id"], unique=True)

    # --- farmers ---
    op.create_table(
        "farmers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(50), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("mobile_number", sa.String(15), nullable=False),
        sa.Column("village_id", UUID(as_uuid=True), sa.ForeignKey("geography_villages.id"), nullable=False),
        sa.Column("primary_crop_code", sa.String(30)),
        sa.Column("display_name", sa.String(100)),
        sa.Column("father_name", sa.String(100)),
        sa.Column("age", sa.Integer),
        sa.Column("gender", sa.String(10)),
        sa.Column("education_level", sa.String(30)),
        sa.Column("total_land_area", sa.DECIMAL(10, 2)),
        sa.Column("total_land_unit", sa.String(20), server_default="BIGHA"),
        sa.Column("government_id_type", sa.String(30)),
        sa.Column("government_id_hash", sa.String(64)),
        sa.Column("bank_account_linked", sa.Boolean, server_default="false"),
        sa.Column("language_preference", sa.String(10), server_default="hi"),
        sa.Column("enrolled_by", UUID(as_uuid=True)),
        sa.Column("enrollment_method", sa.String(20), server_default="ASSISTED"),
        sa.Column("enrollment_gps_lat", sa.DECIMAL(10, 8)),
        sa.Column("enrollment_gps_lng", sa.DECIMAL(11, 8)),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(10), server_default="v1.0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
    )
    op.create_index("idx_farmer_tenant", "farmers", ["tenant_id"])
    op.create_index("idx_farmer_project", "farmers", ["project_id"])
    op.create_index("idx_farmer_village", "farmers", ["village_id"])
    op.create_index("idx_farmer_mobile", "farmers", ["mobile_number"])
    op.create_index("idx_farmer_status", "farmers", ["status"])

    # --- parcels ---
    op.create_table(
        "parcels",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(50), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("farmer_id", UUID(as_uuid=True), sa.ForeignKey("farmers.id"), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id")),
        sa.Column("village_id", UUID(as_uuid=True), sa.ForeignKey("geography_villages.id"), nullable=False),
        sa.Column("reported_area", sa.DECIMAL(10, 2), nullable=False),
        sa.Column("reported_area_unit", sa.String(20), nullable=False, server_default="BIGHA"),
        sa.Column("soil_type_code", sa.String(30)),
        sa.Column("current_crop_code", sa.String(30)),
        sa.Column("geometry_source", sa.String(20), nullable=False, server_default="NONE"),
        sa.Column("centroid_lat", sa.DECIMAL(10, 8)),
        sa.Column("centroid_lng", sa.DECIMAL(11, 8)),
        sa.Column("geometry", Geometry("POLYGON", srid=4326)),
        sa.Column("computed_area_hectares", sa.DECIMAL(10, 4)),
        sa.Column("geometry_accuracy_meters", sa.DECIMAL(6, 1)),
        sa.Column("geometry_captured_at", sa.DateTime(timezone=True)),
        sa.Column("geometry_captured_by", UUID(as_uuid=True)),
        sa.Column("local_name", sa.String(100)),
        sa.Column("survey_number", sa.String(50)),
        sa.Column("ownership_type", sa.String(30), server_default="OWNED"),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(10), server_default="v1.0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
    )
    op.create_index("idx_parcel_tenant", "parcels", ["tenant_id"])
    op.create_index("idx_parcel_farmer", "parcels", ["farmer_id"])
    op.create_index("idx_parcel_village", "parcels", ["village_id"])
    op.create_index("idx_parcel_project", "parcels", ["project_id"])
    op.create_index("idx_parcel_geometry", "parcels", ["geometry"], postgresql_using="gist")


def downgrade() -> None:
    op.drop_table("parcels")
    op.drop_table("farmers")
    op.drop_table("project_roles")
    op.drop_table("projects")
    op.drop_table("tenants")

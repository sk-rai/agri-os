"""Create soil_profiles table

Revision ID: 009
Revises: 008
Create Date: 2026-05-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "soil_profiles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(50), nullable=False),
        sa.Column("parcel_id", UUID(as_uuid=True), sa.ForeignKey("parcels.id"), nullable=False),
        sa.Column("farmer_id", UUID(as_uuid=True), sa.ForeignKey("farmers.id"), nullable=False),
        sa.Column("test_date", sa.Date, nullable=False),
        sa.Column("lab_name", sa.String(200)),
        sa.Column("sample_id", sa.String(100)),
        sa.Column("shc_card_number", sa.String(100)),
        # Macro nutrients
        sa.Column("nitrogen_n", sa.DECIMAL(8, 2)),
        sa.Column("phosphorus_p", sa.DECIMAL(8, 2)),
        sa.Column("potassium_k", sa.DECIMAL(8, 2)),
        sa.Column("sulphur_s", sa.DECIMAL(8, 2)),
        # Micro nutrients
        sa.Column("zinc_zn", sa.DECIMAL(8, 3)),
        sa.Column("iron_fe", sa.DECIMAL(8, 3)),
        sa.Column("copper_cu", sa.DECIMAL(8, 3)),
        sa.Column("manganese_mn", sa.DECIMAL(8, 3)),
        sa.Column("boron_bo", sa.DECIMAL(8, 3)),
        # Physical
        sa.Column("ph", sa.DECIMAL(4, 2)),
        sa.Column("ec", sa.DECIMAL(6, 3)),
        sa.Column("organic_carbon_oc", sa.DECIMAL(5, 2)),
        # Classification
        sa.Column("soil_type_code", sa.String(30)),
        sa.Column("soil_texture", sa.String(50)),
        sa.Column("soil_color", sa.String(50)),
        # Ratings and recommendations
        sa.Column("ratings", JSONB, server_default="{}"),
        sa.Column("recommendations", JSONB, server_default="{}"),
        # Meta
        sa.Column("data_source", sa.String(30), server_default="MANUAL"),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(10), server_default="v1.0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
    )
    op.create_index("idx_soil_profile_tenant", "soil_profiles", ["tenant_id"])
    op.create_index("idx_soil_profile_parcel", "soil_profiles", ["parcel_id"])
    op.create_index("idx_soil_profile_farmer", "soil_profiles", ["farmer_id"])
    op.create_index("idx_soil_profile_date", "soil_profiles", ["test_date"])


def downgrade() -> None:
    op.drop_table("soil_profiles")

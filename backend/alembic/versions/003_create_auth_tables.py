"""Create auth tables: users, user_devices, otp_records

Revision ID: 003
Revises: 002
Create Date: 2026-05-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("mobile_number", sa.String(15), unique=True, nullable=False),
        sa.Column("role", sa.String(30), nullable=False, server_default="FARMER"),
        sa.Column("display_name", sa.String(100)),
        sa.Column("language_preference", sa.String(10), server_default="hi"),
        sa.Column("tenant_id", sa.String(50)),
        sa.Column("territory_scope", JSONB, server_default="{}"),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("login_count", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(10), server_default="v1.0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
    )
    op.create_index("ix_users_mobile", "users", ["mobile_number"])
    op.create_index("idx_user_tenant", "users", ["tenant_id"])
    op.create_index("idx_user_role", "users", ["role"])

    # --- user_devices ---
    op.create_table(
        "user_devices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("device_id", sa.String(200), nullable=False),
        sa.Column("device_key", sa.String(200), unique=True, nullable=False),
        sa.Column("device_name", sa.String(100)),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(10), server_default="v1.0", nullable=False),
    )
    op.create_index("idx_device_user", "user_devices", ["user_id"])
    op.create_index("idx_device_key", "user_devices", ["device_key"])

    # --- otp_records ---
    op.create_table(
        "otp_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("mobile_number", sa.String(15), nullable=False),
        sa.Column("otp_hash", sa.String(200), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer, server_default="0"),
        sa.Column("is_used", sa.Boolean(), server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_otp_mobile", "otp_records", ["mobile_number"])


def downgrade() -> None:
    op.drop_table("otp_records")
    op.drop_table("user_devices")
    op.drop_table("users")

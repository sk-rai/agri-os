"""add farmer project enrollments

Revision ID: 030
Revises: 029
Create Date: 2026-07-14 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "030"
down_revision: Union[str, None] = "029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "farmer_project_enrollments",
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("farmer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("enrollment_method", sa.String(length=30), nullable=False, server_default="ASSISTED"),
        sa.Column("enrollment_source", sa.String(length=50), nullable=True),
        sa.Column("enrollment_batch_id", sa.String(length=100), nullable=True),
        sa.Column("enrolled_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.Column("parcel_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default=sa.text("'[]'::jsonb")),
        sa.Column("assigned_user_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default=sa.text("'[]'::jsonb")),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default=sa.text("'{}'::jsonb")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(10), nullable=False, server_default="v1.0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.CheckConstraint(
            "status IN ('PENDING', 'ACTIVE', 'COMPLETED', 'ARCHIVED', 'CANCELLED')",
            name="ck_farmer_project_enrollment_status",
        ),
        sa.ForeignKeyConstraint(["farmer_id"], ["farmers.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_farmer_project_enrollment_tenant", "farmer_project_enrollments", ["tenant_id"], unique=False)
    op.create_index("idx_farmer_project_enrollment_farmer", "farmer_project_enrollments", ["farmer_id"], unique=False)
    op.create_index("idx_farmer_project_enrollment_project", "farmer_project_enrollments", ["project_id"], unique=False)
    op.create_index("idx_farmer_project_enrollment_status", "farmer_project_enrollments", ["status"], unique=False)
    op.create_index(
        "idx_farmer_project_enrollment_unique",
        "farmer_project_enrollments",
        ["tenant_id", "farmer_id", "project_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("idx_farmer_project_enrollment_unique", table_name="farmer_project_enrollments")
    op.drop_index("idx_farmer_project_enrollment_status", table_name="farmer_project_enrollments")
    op.drop_index("idx_farmer_project_enrollment_project", table_name="farmer_project_enrollments")
    op.drop_index("idx_farmer_project_enrollment_farmer", table_name="farmer_project_enrollments")
    op.drop_index("idx_farmer_project_enrollment_tenant", table_name="farmer_project_enrollments")
    op.drop_table("farmer_project_enrollments")

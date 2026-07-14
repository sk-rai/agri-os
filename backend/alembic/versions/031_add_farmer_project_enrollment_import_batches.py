"""add farmer project enrollment import batches

Revision ID: 031
Revises: 030
Create Date: 2026-07-14 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "031"
down_revision: Union[str, None] = "030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "farmer_project_enrollment_import_batches",
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="VALIDATED"),
        sa.Column("normalized_rows", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("validation_report", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(10), nullable=False, server_default="v1.0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_farmer_project_enrollment_import_tenant", "farmer_project_enrollment_import_batches", ["tenant_id"], unique=False)
    op.create_index("idx_farmer_project_enrollment_import_project", "farmer_project_enrollment_import_batches", ["project_id"], unique=False)
    op.create_index("idx_farmer_project_enrollment_import_actor", "farmer_project_enrollment_import_batches", ["actor_id"], unique=False)
    op.create_index("idx_farmer_project_enrollment_import_status", "farmer_project_enrollment_import_batches", ["status"], unique=False)
    op.create_index("idx_farmer_project_enrollment_import_tenant_created", "farmer_project_enrollment_import_batches", ["tenant_id", "created_at"], unique=False)
    op.create_index("idx_farmer_project_enrollment_import_project_status", "farmer_project_enrollment_import_batches", ["project_id", "status"], unique=False)
    op.create_index("idx_farmer_project_enrollment_import_status_expiry", "farmer_project_enrollment_import_batches", ["status", "expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_farmer_project_enrollment_import_status_expiry", table_name="farmer_project_enrollment_import_batches")
    op.drop_index("idx_farmer_project_enrollment_import_project_status", table_name="farmer_project_enrollment_import_batches")
    op.drop_index("idx_farmer_project_enrollment_import_tenant_created", table_name="farmer_project_enrollment_import_batches")
    op.drop_index("idx_farmer_project_enrollment_import_status", table_name="farmer_project_enrollment_import_batches")
    op.drop_index("idx_farmer_project_enrollment_import_actor", table_name="farmer_project_enrollment_import_batches")
    op.drop_index("idx_farmer_project_enrollment_import_project", table_name="farmer_project_enrollment_import_batches")
    op.drop_index("idx_farmer_project_enrollment_import_tenant", table_name="farmer_project_enrollment_import_batches")
    op.drop_table("farmer_project_enrollment_import_batches")

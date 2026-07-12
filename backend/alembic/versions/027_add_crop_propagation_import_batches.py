"""Add persisted crop propagation CSV import batches.

Revision ID: 027
Revises: 026
Create Date: 2026-07-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "027"
down_revision: Union[str, None] = "026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "crop_propagation_import_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(50), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_name", sa.String(255)),
        sa.Column("status", sa.String(20), nullable=False, server_default="VALIDATED"),
        sa.Column("normalized_rows", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("validation_report", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(10), nullable=False, server_default="v1.0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_crop_propagation_import_batches_tenant_id", "crop_propagation_import_batches", ["tenant_id"])
    op.create_index("ix_crop_propagation_import_batches_actor_id", "crop_propagation_import_batches", ["actor_id"])
    op.create_index("ix_crop_propagation_import_batches_status", "crop_propagation_import_batches", ["status"])
    op.create_index("idx_crop_propagation_import_tenant_created", "crop_propagation_import_batches", ["tenant_id", "created_at"])
    op.create_index("idx_crop_propagation_import_status_expiry", "crop_propagation_import_batches", ["status", "expires_at"])


def downgrade() -> None:
    op.drop_table("crop_propagation_import_batches")

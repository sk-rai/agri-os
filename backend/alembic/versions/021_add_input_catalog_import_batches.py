"""Add persisted input catalog CSV import batches.

Revision ID: 021
Revises: 020
Create Date: 2026-07-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "input_catalog_import_batches",
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
    op.create_index("ix_input_catalog_import_batches_tenant_id", "input_catalog_import_batches", ["tenant_id"])
    op.create_index("ix_input_catalog_import_batches_actor_id", "input_catalog_import_batches", ["actor_id"])
    op.create_index("ix_input_catalog_import_batches_status", "input_catalog_import_batches", ["status"])
    op.create_index(
        "idx_input_catalog_import_tenant_created",
        "input_catalog_import_batches",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "idx_input_catalog_import_status_expiry",
        "input_catalog_import_batches",
        ["status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_table("input_catalog_import_batches")

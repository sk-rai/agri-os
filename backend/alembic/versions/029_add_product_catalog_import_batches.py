"""add product catalog import batches

Revision ID: 029
Revises: 028
Create Date: 2026-07-13 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "029"
down_revision: Union[str, None] = "028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "product_catalog_import_batches",
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("normalized_rows", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("validation_report", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.String(10), nullable=False, server_default="v1.0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_product_catalog_import_batches_actor_id"), "product_catalog_import_batches", ["actor_id"], unique=False)
    op.create_index(op.f("ix_product_catalog_import_batches_status"), "product_catalog_import_batches", ["status"], unique=False)
    op.create_index(op.f("ix_product_catalog_import_batches_tenant_id"), "product_catalog_import_batches", ["tenant_id"], unique=False)
    op.create_index("idx_product_catalog_import_status_expiry", "product_catalog_import_batches", ["status", "expires_at"], unique=False)
    op.create_index("idx_product_catalog_import_tenant_created", "product_catalog_import_batches", ["tenant_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_product_catalog_import_tenant_created", table_name="product_catalog_import_batches")
    op.drop_index("idx_product_catalog_import_status_expiry", table_name="product_catalog_import_batches")
    op.drop_index(op.f("ix_product_catalog_import_batches_tenant_id"), table_name="product_catalog_import_batches")
    op.drop_index(op.f("ix_product_catalog_import_batches_status"), table_name="product_catalog_import_batches")
    op.drop_index(op.f("ix_product_catalog_import_batches_actor_id"), table_name="product_catalog_import_batches")
    op.drop_table("product_catalog_import_batches")

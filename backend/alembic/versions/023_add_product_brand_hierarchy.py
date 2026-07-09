"""Add agricultural product, package and project approval hierarchy.

Revision ID: 023
Revises: 022
Create Date: 2026-07-09
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "023"
down_revision: Union[str, None] = "022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def audit_columns():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(10), nullable=False, server_default="v1.0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    ]


def upgrade() -> None:
    op.create_table("agricultural_products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(80), nullable=False, unique=True),
        sa.Column("canonical_input_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agricultural_inputs.id"), nullable=False),
        sa.Column("manufacturer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("manufacturers.id"), nullable=False),
        sa.Column("brand_name", sa.String(200), nullable=False), sa.Column("composition", sa.String(300)),
        sa.Column("registration_number", sa.String(100)), sa.Column("registration_authority", sa.String(150)),
        sa.Column("registration_expiry_date", sa.Date()), sa.Column("country", sa.String(50), server_default="India"),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}"), *audit_columns())
    for name, cols in [("ix_agricultural_products_code", ["code"]), ("ix_agricultural_products_canonical_input_id", ["canonical_input_id"]), ("ix_agricultural_products_manufacturer_id", ["manufacturer_id"]), ("ix_agricultural_products_registration_number", ["registration_number"]), ("ix_agricultural_products_status", ["status"])]: op.create_index(name, "agricultural_products", cols)
    op.create_table("agricultural_product_packages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agricultural_products.id"), nullable=False),
        sa.Column("sku", sa.String(100), nullable=False, unique=True), sa.Column("quantity", sa.Numeric(12,3), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False), sa.Column("pack_label", sa.String(100), nullable=False),
        sa.Column("barcode", sa.String(100), unique=True), sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"), *audit_columns())
    for name, cols in [("ix_agricultural_product_packages_product_id", ["product_id"]), ("ix_agricultural_product_packages_sku", ["sku"]), ("ix_agricultural_product_packages_status", ["status"])]: op.create_index(name, "agricultural_product_packages", cols)
    op.create_table("project_product_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("tenant_id", sa.String(50), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agricultural_products.id"), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("preferred", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="1000"), sa.Column("reason", sa.Text()), *audit_columns(),
        sa.UniqueConstraint("tenant_id", "project_id", "product_id", name="uq_project_product_approval"))
    for col in ["tenant_id", "project_id", "product_id"]: op.create_index(f"ix_project_product_approvals_{col}", "project_product_approvals", [col])
    op.create_table("product_catalog_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("tenant_id", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(30), nullable=False), sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_code", sa.String(100), nullable=False), sa.Column("actor_id", postgresql.UUID(as_uuid=True)),
        sa.Column("action", sa.String(50), nullable=False), sa.Column("before_payload", postgresql.JSONB()), sa.Column("after_payload", postgresql.JSONB()),
        sa.Column("reason", sa.Text()), sa.Column("metadata", postgresql.JSONB(), server_default="{}"), *audit_columns())
    for col in ["tenant_id", "entity_type", "entity_id", "entity_code"]: op.create_index(f"ix_product_catalog_audit_events_{col}", "product_catalog_audit_events", [col])
    op.create_index("idx_product_catalog_audit_entity", "product_catalog_audit_events", ["entity_type", "entity_code", "created_at"])


def downgrade() -> None:
    op.drop_table("product_catalog_audit_events")
    op.drop_table("project_product_approvals")
    op.drop_table("agricultural_product_packages")
    op.drop_table("agricultural_products")
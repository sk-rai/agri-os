"""Add product/package traceability to crop activities.

Revision ID: 025
Revises: 024
Create Date: 2026-07-09
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "025"
down_revision: Union[str, None] = "024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("crop_activities", sa.Column("input_rule_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("crop_stage_input_rules.id")))
    op.add_column("crop_activities", sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agricultural_products.id")))
    op.add_column("crop_activities", sa.Column("product_code", sa.String(80)))
    op.add_column("crop_activities", sa.Column("package_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agricultural_product_packages.id")))
    op.add_column("crop_activities", sa.Column("package_sku", sa.String(100)))
    op.add_column("crop_activities", sa.Column("recommended_quantity", sa.Numeric(12, 3)))
    op.add_column("crop_activities", sa.Column("recommended_quantity_unit", sa.String(20)))
    op.add_column("crop_activities", sa.Column("actual_quantity", sa.Numeric(12, 3)))
    op.add_column("crop_activities", sa.Column("actual_quantity_unit", sa.String(20)))
    op.add_column("crop_activities", sa.Column("dosage_variance_reason", sa.Text()))
    op.create_index("idx_activity_input_rule", "crop_activities", ["input_rule_id"])
    op.create_index("idx_activity_product", "crop_activities", ["product_code"])
    op.create_index("idx_activity_package", "crop_activities", ["package_sku"])


def downgrade() -> None:
    op.drop_index("idx_activity_package", table_name="crop_activities")
    op.drop_index("idx_activity_product", table_name="crop_activities")
    op.drop_index("idx_activity_input_rule", table_name="crop_activities")
    for column in ["dosage_variance_reason", "actual_quantity_unit", "actual_quantity", "recommended_quantity_unit", "recommended_quantity", "package_sku", "package_id", "product_code", "product_id", "input_rule_id"]:
        op.drop_column("crop_activities", column)
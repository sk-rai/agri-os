"""Add crop taxonomy and propagation catalog tables.

Revision ID: 014
Revises: 013
Create Date: 2026-07-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def audit_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(), server_default="v1.0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "crop_taxonomy_nodes",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("canonical_name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("node_type", sa.String(length=30), server_default="AGRONOMIC", nullable=False),
        sa.Column("level", sa.Integer(), server_default="0", nullable=False),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("aliases", JSONB(), server_default="[]", nullable=True),
        sa.Column("metadata", JSONB(), server_default="{}", nullable=True),
        *audit_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_crop_taxonomy_nodes_code", "crop_taxonomy_nodes", ["code"])
    op.create_index("idx_crop_taxonomy_node_type", "crop_taxonomy_nodes", ["node_type"])
    op.create_index("idx_crop_taxonomy_display", "crop_taxonomy_nodes", ["level", "display_order"])

    op.create_table(
        "crop_taxonomy_edges",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("parent_node_id", UUID(as_uuid=True), nullable=False),
        sa.Column("child_node_id", UUID(as_uuid=True), nullable=False),
        sa.Column("relationship_type", sa.String(length=30), server_default="IS_A", nullable=False),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        *audit_columns(),
        sa.ForeignKeyConstraint(["parent_node_id"], ["crop_taxonomy_nodes.id"]),
        sa.ForeignKeyConstraint(["child_node_id"], ["crop_taxonomy_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("parent_node_id", "child_node_id", name="uq_crop_taxonomy_edge"),
    )
    op.create_index("idx_crop_taxonomy_edge_parent", "crop_taxonomy_edges", ["parent_node_id"])
    op.create_index("idx_crop_taxonomy_edge_child", "crop_taxonomy_edges", ["child_node_id"])

    op.create_table(
        "crop_taxonomy_assignments",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("crop_id", UUID(as_uuid=True), nullable=False),
        sa.Column("taxonomy_node_id", UUID(as_uuid=True), nullable=False),
        sa.Column("assignment_type", sa.String(length=30), server_default="PRIMARY", nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("source", sa.String(length=50), server_default="SYSTEM", nullable=False),
        *audit_columns(),
        sa.ForeignKeyConstraint(["crop_id"], ["crops.id"]),
        sa.ForeignKeyConstraint(["taxonomy_node_id"], ["crop_taxonomy_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("crop_id", "taxonomy_node_id", name="uq_crop_taxonomy_assignment"),
    )
    op.create_index("idx_crop_taxonomy_assignment_crop", "crop_taxonomy_assignments", ["crop_id"])
    op.create_index("idx_crop_taxonomy_assignment_node", "crop_taxonomy_assignments", ["taxonomy_node_id"])

    op.create_table(
        "crop_propagation_types",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("canonical_name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("establishment_type", sa.String(length=30), server_default="SEED", nullable=False),
        sa.Column("aliases", JSONB(), server_default="[]", nullable=True),
        sa.Column("metadata", JSONB(), server_default="{}", nullable=True),
        *audit_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_crop_propagation_types_code", "crop_propagation_types", ["code"])
    op.create_index("idx_crop_propagation_establishment", "crop_propagation_types", ["establishment_type"])

    op.create_table(
        "crop_propagation_options",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("crop_id", UUID(as_uuid=True), nullable=False),
        sa.Column("propagation_type_id", UUID(as_uuid=True), nullable=False),
        sa.Column("season_code", sa.String(length=20), nullable=True),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata", JSONB(), server_default="{}", nullable=True),
        *audit_columns(),
        sa.ForeignKeyConstraint(["crop_id"], ["crops.id"]),
        sa.ForeignKeyConstraint(["propagation_type_id"], ["crop_propagation_types.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("crop_id", "propagation_type_id", "season_code", name="uq_crop_propagation_option"),
    )
    op.create_index("idx_crop_propagation_option_crop", "crop_propagation_options", ["crop_id"])
    op.create_index("idx_crop_propagation_option_type", "crop_propagation_options", ["propagation_type_id"])
    op.create_index("idx_crop_propagation_option_season", "crop_propagation_options", ["season_code"])


def downgrade() -> None:
    op.drop_table("crop_propagation_options")
    op.drop_table("crop_propagation_types")
    op.drop_table("crop_taxonomy_assignments")
    op.drop_table("crop_taxonomy_edges")
    op.drop_table("crop_taxonomy_nodes")

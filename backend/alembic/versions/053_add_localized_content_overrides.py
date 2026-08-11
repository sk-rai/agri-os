"""Add localized content override tables.

Revision ID: 053
Revises: 052
Create Date: 2026-08-11
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "053"
down_revision = "052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "localized_content_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("content_key", sa.String(length=300), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("content_kind", sa.String(length=80), nullable=False),
        sa.Column("default_labels", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("review_status", sa.String(length=40), nullable=False, server_default="PLATFORM_DEFAULT"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("version", sa.String(length=10), nullable=False, server_default="v1.0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint("content_key", name="uq_localized_content_keys_content_key"),
    )
    op.create_index("idx_localized_content_keys_source", "localized_content_keys", ["source", "content_kind"])
    op.create_index("idx_localized_content_keys_active", "localized_content_keys", ["is_active", "review_status"])

    op.create_table(
        "localized_content_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(length=50), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("content_key_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("localized_content_keys.id"), nullable=False),
        sa.Column("language_code", sa.String(length=12), nullable=False),
        sa.Column("override_text", sa.Text(), nullable=False),
        sa.Column("review_status", sa.String(length=40), nullable=False, server_default="DRAFT"),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("version", sa.String(length=10), nullable=False, server_default="v1.0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_index(
        "idx_localized_content_override_lookup",
        "localized_content_overrides",
        ["tenant_id", "project_id", "content_key_id", "language_code", "review_status"],
    )
    op.execute(
        """
        create unique index uq_localized_content_override_scope
        on localized_content_overrides (
            tenant_id,
            coalesce(project_id::text, 'TENANT_DEFAULT'),
            content_key_id,
            language_code
        )
        where is_active = true
        """
    )

    op.create_table(
        "land_intelligence_summary_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(length=50), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("scope_type", sa.String(length=40), nullable=False),
        sa.Column("scope_code", sa.String(length=120), nullable=False),
        sa.Column("language_code", sa.String(length=12), nullable=False, server_default="en"),
        sa.Column("summary_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("review_status", sa.String(length=40), nullable=False, server_default="DRAFT"),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("version", sa.String(length=10), nullable=False, server_default="v1.0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_index(
        "idx_land_intelligence_summary_override_lookup",
        "land_intelligence_summary_overrides",
        ["tenant_id", "project_id", "scope_type", "scope_code", "language_code", "review_status"],
    )
    op.execute(
        """
        create unique index uq_land_intelligence_summary_override_scope
        on land_intelligence_summary_overrides (
            tenant_id,
            coalesce(project_id::text, 'TENANT_DEFAULT'),
            scope_type,
            scope_code,
            language_code
        )
        where is_active = true
        """
    )


def downgrade() -> None:
    op.execute("drop index if exists uq_land_intelligence_summary_override_scope")
    op.drop_index("idx_land_intelligence_summary_override_lookup", table_name="land_intelligence_summary_overrides")
    op.drop_table("land_intelligence_summary_overrides")

    op.execute("drop index if exists uq_localized_content_override_scope")
    op.drop_index("idx_localized_content_override_lookup", table_name="localized_content_overrides")
    op.drop_table("localized_content_overrides")

    op.drop_index("idx_localized_content_keys_active", table_name="localized_content_keys")
    op.drop_index("idx_localized_content_keys_source", table_name="localized_content_keys")
    op.drop_table("localized_content_keys")

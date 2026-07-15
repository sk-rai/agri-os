"""add media assets and attachments

Revision ID: 033
Revises: 032
Create Date: 2026-07-15 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "033"
down_revision: Union[str, None] = "032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "media_assets",
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("farmer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("media_type", sa.String(length=20), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("storage_url", sa.Text(), nullable=True),
        sa.Column("storage_key", sa.String(length=500), nullable=True),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        sa.Column("sha256_hash", sa.String(length=128), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("capture_lat", sa.String(length=40), nullable=True),
        sa.Column("capture_lng", sa.String(length=40), nullable=True),
        sa.Column("capture_accuracy_meters", sa.String(length=40), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("upload_status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(length=10), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("media_type IN ('PHOTO', 'AUDIO', 'VIDEO', 'DOCUMENT')", name="ck_media_asset_type"),
        sa.CheckConstraint("upload_status IN ('PENDING', 'UPLOADED', 'FAILED', 'QUARANTINED')", name="ck_media_asset_upload_status"),
        sa.ForeignKeyConstraint(["farmer_id"], ["farmers.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_media_asset_tenant", "media_assets", ["tenant_id"], unique=False)
    op.create_index("idx_media_asset_project", "media_assets", ["project_id"], unique=False)
    op.create_index("idx_media_asset_farmer", "media_assets", ["farmer_id"], unique=False)
    op.create_index("idx_media_asset_type", "media_assets", ["media_type"], unique=False)
    op.create_index("idx_media_asset_status", "media_assets", ["upload_status"], unique=False)
    op.create_index("idx_media_asset_hash", "media_assets", ["sha256_hash"], unique=False)

    op.create_table(
        "media_attachments",
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("media_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purpose", sa.String(length=40), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(length=10), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("entity_type IN ('FARMER', 'PARCEL', 'SOIL_PROFILE', 'CROP_CYCLE', 'CROP_STAGE', 'CROP_ACTIVITY', 'FIELD_EVENT', 'ADVISORY', 'QUERY_THREAD', 'QUERY_MESSAGE')", name="ck_media_attachment_entity_type"),
        sa.CheckConstraint("purpose IN ('STAGE_EVIDENCE', 'ACTIVITY_EVIDENCE', 'DISEASE_PHOTO', 'SOIL_CARD', 'PARCEL_BOUNDARY', 'QUERY_ATTACHMENT', 'ADVISORY_ATTACHMENT', 'AUDIO_NOTE', 'GENERAL')", name="ck_media_attachment_purpose"),
        sa.ForeignKeyConstraint(["media_asset_id"], ["media_assets.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_media_attachment_tenant", "media_attachments", ["tenant_id"], unique=False)
    op.create_index("idx_media_attachment_asset", "media_attachments", ["media_asset_id"], unique=False)
    op.create_index("idx_media_attachment_entity", "media_attachments", ["tenant_id", "entity_type", "entity_id"], unique=False)
    op.create_index("idx_media_attachment_purpose", "media_attachments", ["purpose"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_media_attachment_purpose", table_name="media_attachments")
    op.drop_index("idx_media_attachment_entity", table_name="media_attachments")
    op.drop_index("idx_media_attachment_asset", table_name="media_attachments")
    op.drop_index("idx_media_attachment_tenant", table_name="media_attachments")
    op.drop_table("media_attachments")
    op.drop_index("idx_media_asset_hash", table_name="media_assets")
    op.drop_index("idx_media_asset_status", table_name="media_assets")
    op.drop_index("idx_media_asset_type", table_name="media_assets")
    op.drop_index("idx_media_asset_farmer", table_name="media_assets")
    op.drop_index("idx_media_asset_project", table_name="media_assets")
    op.drop_index("idx_media_asset_tenant", table_name="media_assets")
    op.drop_table("media_assets")

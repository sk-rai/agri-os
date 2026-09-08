"""Add boundary validation metadata apply events.

Revision ID: 058
Revises: 057
Create Date: 2026-09-08
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "058"
down_revision = "057"
branch_labels = None
depends_on = None

TABLE = "geography_boundary_validation_metadata_events"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "source_feature_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("geography_boundary_source_features.id"),
            nullable=False,
        ),
        sa.Column(
            "import_batch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("geography_boundary_import_batches.id"),
            nullable=False,
        ),
        sa.Column(
            "source_system",
            sa.String(length=80),
            nullable=False,
        ),
        sa.Column(
            "state_or_ut",
            sa.String(length=160),
            nullable=False,
        ),
        sa.Column(
            "source_feature_index",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "source_sha256",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "plan_checksum",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "geometry_hash_algorithm",
            sa.String(length=80),
            nullable=False,
        ),
        sa.Column(
            "rollback_token",
            sa.String(length=120),
            nullable=False,
        ),
        sa.Column(
            "apply_status",
            sa.String(length=40),
            nullable=False,
            server_default="PLANNED",
        ),
        sa.Column(
            "before_values",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "planned_values",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "after_values",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "apply_report",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "rollback_report",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "applied_by",
            sa.String(length=120),
            nullable=True,
        ),
        sa.Column(
            "applied_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "rolled_back_by",
            sa.String(length=120),
            nullable=True,
        ),
        sa.Column(
            "rolled_back_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "version",
            sa.String(length=10),
            nullable=False,
            server_default="v1.0",
        ),
        sa.CheckConstraint(
            "apply_status in "
            "('PLANNED', 'APPLIED', 'ROLLED_BACK', 'FAILED')",
            name="ck_gb_validation_events_status",
        ),
        sa.CheckConstraint(
            "is_active = false or apply_status = 'APPLIED'",
            name="ck_gb_validation_events_active_status",
        ),
        sa.CheckConstraint(
            "char_length(source_sha256) = 64",
            name="ck_gb_validation_events_source_sha256",
        ),
        sa.CheckConstraint(
            "char_length(plan_checksum) = 64",
            name="ck_gb_validation_events_plan_checksum",
        ),
    )

    op.create_index(
        "idx_gb_validation_events_source",
        TABLE,
        ["source_feature_id", "created_at"],
    )
    op.create_index(
        "idx_gb_validation_events_batch",
        TABLE,
        ["import_batch_id", "apply_status"],
    )
    op.create_index(
        "idx_gb_validation_events_state",
        TABLE,
        ["state_or_ut", "source_feature_index"],
    )
    op.create_index(
        "idx_gb_validation_events_rollback",
        TABLE,
        ["rollback_token", "apply_status"],
    )
    op.create_index(
        "uq_gb_validation_events_identity",
        TABLE,
        [
            "source_feature_id",
            "source_sha256",
            "plan_checksum",
            "rollback_token",
        ],
        unique=True,
    )
    op.create_index(
        "uq_gb_validation_events_active_source",
        TABLE,
        ["source_feature_id"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_gb_validation_events_active_source",
        table_name=TABLE,
    )
    op.drop_index(
        "uq_gb_validation_events_identity",
        table_name=TABLE,
    )
    op.drop_index(
        "idx_gb_validation_events_rollback",
        table_name=TABLE,
    )
    op.drop_index(
        "idx_gb_validation_events_state",
        table_name=TABLE,
    )
    op.drop_index(
        "idx_gb_validation_events_batch",
        table_name=TABLE,
    )
    op.drop_index(
        "idx_gb_validation_events_source",
        table_name=TABLE,
    )
    op.drop_table(TABLE)

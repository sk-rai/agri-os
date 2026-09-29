"""Add precomputed district geography-layer readiness snapshots.

Revision ID: 061
Revises: 060
Create Date: 2026-09-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "061"
down_revision = "060"
branch_labels = None
depends_on = None


def _audit_columns() -> list[sa.Column]:
    return [
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
            "version",
            sa.String(length=10),
            nullable=False,
            server_default="v1.0",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "geography_layer_readiness_snapshots",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "state_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("geography_states.id"),
            nullable=False,
        ),
        sa.Column(
            "district_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("geography_districts.id"),
            nullable=False,
        ),
        sa.Column(
            "state_lgd_code",
            sa.String(length=20),
            nullable=False,
        ),
        sa.Column(
            "district_lgd_code",
            sa.String(length=20),
            nullable=False,
        ),
        sa.Column(
            "state_or_ut",
            sa.String(length=160),
            nullable=False,
        ),
        sa.Column(
            "district",
            sa.String(length=160),
            nullable=False,
        ),
        sa.Column(
            "snapshot_schema_version",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "calculation_status",
            sa.String(length=30),
            nullable=False,
            server_default="READY",
        ),
        sa.Column(
            "readiness_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "source_versions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "evidence_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "refresh_run_id",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "failure_reason",
            sa.Text(),
            nullable=True,
        ),
        *_audit_columns(),
        sa.CheckConstraint(
            "calculation_status in ('READY', 'STALE', 'FAILED')",
            name="ck_geography_layer_readiness_snapshot_status",
        ),
        sa.CheckConstraint(
            "is_active = false or calculation_status = 'READY'",
            name="ck_geography_layer_readiness_snapshot_active_status",
        ),
    )

    op.create_index(
        "idx_geography_layer_readiness_snapshot_district",
        "geography_layer_readiness_snapshots",
        ["state_lgd_code", "district_lgd_code", "is_active"],
    )
    op.create_index(
        "idx_geography_layer_readiness_snapshot_freshness",
        "geography_layer_readiness_snapshots",
        ["calculation_status", "computed_at"],
    )
    op.create_index(
        "idx_geography_layer_readiness_snapshot_refresh",
        "geography_layer_readiness_snapshots",
        ["refresh_run_id"],
    )
    op.create_index(
        "uq_geography_layer_readiness_snapshot_one_active",
        "geography_layer_readiness_snapshots",
        ["state_id", "district_id"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_geography_layer_readiness_snapshot_one_active",
        table_name="geography_layer_readiness_snapshots",
    )
    op.drop_index(
        "idx_geography_layer_readiness_snapshot_refresh",
        table_name="geography_layer_readiness_snapshots",
    )
    op.drop_index(
        "idx_geography_layer_readiness_snapshot_freshness",
        table_name="geography_layer_readiness_snapshots",
    )
    op.drop_index(
        "idx_geography_layer_readiness_snapshot_district",
        table_name="geography_layer_readiness_snapshots",
    )
    op.drop_table("geography_layer_readiness_snapshots")

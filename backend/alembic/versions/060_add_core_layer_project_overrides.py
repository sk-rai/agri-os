"""Add project-scoped Core geography layer overrides.

Revision ID: 060
Revises: 059
Create Date: 2026-09-28
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "060"
down_revision = "059"
branch_labels = None
depends_on = None


TABLE = "geography_core_layer_project_overrides"


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
        TABLE,
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "tenant_id",
            sa.String(length=50),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id"),
            nullable=False,
        ),
        sa.Column(
            "village_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("geography_villages.id"),
            nullable=False,
        ),
        sa.Column(
            "region_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("geography_climate_regions.id"),
            nullable=False,
        ),
        sa.Column(
            "region_system",
            sa.String(length=60),
            nullable=False,
        ),
        sa.Column(
            "assignment_source",
            sa.String(length=60),
            nullable=False,
            server_default="ADMIN_PROJECT_OVERRIDE",
        ),
        sa.Column(
            "assignment_status",
            sa.String(length=40),
            nullable=False,
            server_default="PLANNED",
        ),
        sa.Column(
            "evidence_basis",
            sa.String(length=80),
            nullable=True,
        ),
        sa.Column(
            "reviewer",
            sa.String(length=120),
            nullable=True,
        ),
        sa.Column(
            "review_notes",
            sa.Text(),
            nullable=True,
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
            "rollback_token",
            sa.String(length=80),
            nullable=False,
        ),
        sa.Column(
            "dry_run_report",
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
        *_audit_columns(),
        sa.CheckConstraint(
            "assignment_status in "
            "('PLANNED', 'APPLIED', 'ROLLED_BACK', 'FAILED')",
            name=(
                "ck_geography_core_layer_project_overrides_status"
            ),
        ),
        sa.CheckConstraint(
            "is_active = false "
            "or assignment_status = 'APPLIED'",
            name=(
                "ck_geography_core_layer_project_overrides_"
                "active_status"
            ),
        ),
    )

    op.create_index(
        "idx_geography_core_layer_project_overrides_project",
        TABLE,
        ["tenant_id", "project_id", "is_active"],
    )
    op.create_index(
        "idx_geography_core_layer_project_overrides_village",
        TABLE,
        ["village_id", "region_system", "is_active"],
    )
    op.create_index(
        "idx_geography_core_layer_project_overrides_region",
        TABLE,
        ["region_id"],
    )
    op.create_index(
        "idx_geography_core_layer_project_overrides_rollback",
        TABLE,
        ["rollback_token", "assignment_status"],
    )
    op.create_index(
        "uq_geography_core_layer_project_overrides_one_active",
        TABLE,
        [
            "tenant_id",
            "project_id",
            "village_id",
            "region_system",
        ],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_geography_core_layer_project_overrides_one_active",
        table_name=TABLE,
    )
    op.drop_index(
        "idx_geography_core_layer_project_overrides_rollback",
        table_name=TABLE,
    )
    op.drop_index(
        "idx_geography_core_layer_project_overrides_region",
        table_name=TABLE,
    )
    op.drop_index(
        "idx_geography_core_layer_project_overrides_village",
        table_name=TABLE,
    )
    op.drop_index(
        "idx_geography_core_layer_project_overrides_project",
        table_name=TABLE,
    )
    op.drop_table(TABLE)

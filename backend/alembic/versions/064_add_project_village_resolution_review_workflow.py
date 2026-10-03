"""Add project village resolution proposal and approval workflow.

Revision ID: 064
Revises: 063
Create Date: 2026-10-03
"""
from alembic import op
import sqlalchemy as sa

revision = "064"
down_revision = "063"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint(
        "ck_project_village_resolution_event_action",
        "geography_project_village_resolution_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_project_village_resolution_event_action",
        "geography_project_village_resolution_events",
        "action in ('PROPOSED','APPROVED','APPLIED','ROLLED_BACK')",
    )
    op.drop_index(
        "uq_project_village_resolution_active_canonical",
        table_name="geography_project_village_resolutions",
    )
    op.create_index(
        "uq_project_village_resolution_open_canonical",
        "geography_project_village_resolutions",
        ["tenant_id", "project_id", "canonical_village_id"],
        unique=True,
        postgresql_where=sa.text(
            "resolution_status in ('DRAFT','APPROVED','ACTIVE') "
            "and canonical_village_id is not null"
        ),
    )


def downgrade():
    op.drop_index(
        "uq_project_village_resolution_open_canonical",
        table_name="geography_project_village_resolutions",
    )
    op.create_index(
        "uq_project_village_resolution_active_canonical",
        "geography_project_village_resolutions",
        ["tenant_id", "project_id", "canonical_village_id"],
        unique=True,
        postgresql_where=sa.text(
            "is_active=true and canonical_village_id is not null"
        ),
    )
    op.drop_constraint(
        "ck_project_village_resolution_event_action",
        "geography_project_village_resolution_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_project_village_resolution_event_action",
        "geography_project_village_resolution_events",
        "action in ('APPLIED','ROLLED_BACK')",
    )

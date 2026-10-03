"""Add project village resolution rejection and cancellation events.

Revision ID: 065
Revises: 064
Create Date: 2026-10-03
"""
from alembic import op

revision = "065"
down_revision = "064"
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
        "action in ('PROPOSED','APPROVED','REJECTED','CANCELLED','APPLIED','ROLLED_BACK')",
    )


def downgrade():
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

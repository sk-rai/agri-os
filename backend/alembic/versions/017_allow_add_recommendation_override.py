"""Allow ADD_RECOMMENDATION workflow override operation.

Revision ID: 017
Revises: 016
Create Date: 2026-07-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_OPERATION_CHECK = "operation IN ('HIDE', 'RENAME', 'CHANGE_DURATION', 'CHANGE_OFFSET', 'CHANGE_QUANTITY', 'ADD_RECOMMENDATION')"
OLD_OPERATION_CHECK = "operation IN ('HIDE', 'RENAME', 'CHANGE_DURATION', 'CHANGE_OFFSET', 'CHANGE_QUANTITY')"


def upgrade() -> None:
    op.drop_constraint("ck_workflow_template_override_operation", "workflow_template_overrides", type_="check")
    op.create_check_constraint(
        "ck_workflow_template_override_operation",
        "workflow_template_overrides",
        sa.text(NEW_OPERATION_CHECK),
    )


def downgrade() -> None:
    op.drop_constraint("ck_workflow_template_override_operation", "workflow_template_overrides", type_="check")
    op.create_check_constraint(
        "ck_workflow_template_override_operation",
        "workflow_template_overrides",
        sa.text(OLD_OPERATION_CHECK),
    )

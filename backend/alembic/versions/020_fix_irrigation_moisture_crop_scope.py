"""Include Rice in moisture irrigation input crop scope.

Revision ID: 020
Revises: 019
Create Date: 2026-07-09
"""

from typing import Sequence, Union

from alembic import op


revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE agricultural_inputs
        SET applicable_crops = array_append(COALESCE(applicable_crops, ARRAY[]::varchar[]), 'RICE')
        WHERE code = 'IRRIGATION_MOISTURE'
          AND NOT ('RICE' = ANY(COALESCE(applicable_crops, ARRAY[]::varchar[])))
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE agricultural_inputs
        SET applicable_crops = array_remove(applicable_crops, 'RICE')
        WHERE code = 'IRRIGATION_MOISTURE'
    """)

"""Add agricultural input review and publish lifecycle.

Revision ID: 022
Revises: 021
Create Date: 2026-07-09
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agricultural_inputs", sa.Column("catalog_status", sa.String(20), nullable=False, server_default="PUBLISHED"))
    op.add_column("agricultural_inputs", sa.Column("submitted_at", sa.DateTime(timezone=True)))
    op.add_column("agricultural_inputs", sa.Column("reviewed_at", sa.DateTime(timezone=True)))
    op.add_column("agricultural_inputs", sa.Column("reviewed_by", postgresql.UUID(as_uuid=True)))
    op.add_column("agricultural_inputs", sa.Column("review_reason", sa.Text()))
    op.create_index("ix_agricultural_inputs_catalog_status", "agricultural_inputs", ["catalog_status"])


def downgrade() -> None:
    op.drop_index("ix_agricultural_inputs_catalog_status", table_name="agricultural_inputs")
    op.drop_column("agricultural_inputs", "review_reason")
    op.drop_column("agricultural_inputs", "reviewed_by")
    op.drop_column("agricultural_inputs", "reviewed_at")
    op.drop_column("agricultural_inputs", "submitted_at")
    op.drop_column("agricultural_inputs", "catalog_status")
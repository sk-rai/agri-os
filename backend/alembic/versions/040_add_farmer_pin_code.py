"""add farmer pin code

Revision ID: 040
Revises: 039
Create Date: 2026-07-18
"""

from alembic import op
import sqlalchemy as sa

revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("farmers", sa.Column("pin_code", sa.String(length=10), nullable=True))


def downgrade():
    op.drop_column("farmers", "pin_code")

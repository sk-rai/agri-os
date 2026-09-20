"""Add native PostGIS geometry for runtime lookup.

Revision ID: 059
Revises: 058
Create Date: 2026-09-20

Schema-only migration. It does not backfill geometry, enable lookup,
activate runtime rows, or change Android behavior.
"""

from __future__ import annotations

from alembic import op
from geoalchemy2 import Geometry
import sqlalchemy as sa


revision = "059"
down_revision = "058"
branch_labels = None
depends_on = None

TABLE = "geography_boundary_runtime_features"
COLUMN = "geometry_wgs84_geom"
INDEX = "idx_boundary_runtime_features_geom_active"

SRID_CONSTRAINT = "ck_boundary_runtime_features_geom_srid"
TYPE_CONSTRAINT = "ck_boundary_runtime_features_geom_type"
VALID_CONSTRAINT = "ck_boundary_runtime_features_geom_valid"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column(
            COLUMN,
            Geometry(
                geometry_type="GEOMETRY",
                srid=4326,
                spatial_index=False,
            ),
            nullable=True,
            comment=(
                "Native WGS84 lookup geometry. Populated only by "
                "a separately authorized and reconciled backfill."
            ),
        ),
    )

    op.create_check_constraint(
        SRID_CONSTRAINT,
        TABLE,
        (
            f"{COLUMN} is null "
            f"or ST_SRID({COLUMN}) = 4326"
        ),
    )
    op.create_check_constraint(
        TYPE_CONSTRAINT,
        TABLE,
        (
            f"{COLUMN} is null "
            f"or ST_GeometryType({COLUMN}) "
            "in ('ST_Polygon', 'ST_MultiPolygon')"
        ),
    )
    op.create_check_constraint(
        VALID_CONSTRAINT,
        TABLE,
        (
            f"{COLUMN} is null "
            f"or (ST_IsValid({COLUMN}) "
            f"and not ST_IsEmpty({COLUMN}))"
        ),
    )

    # A concurrent index avoids holding a long write-blocking lock
    # when the table grows beyond the current pilot. PostgreSQL
    # requires CREATE INDEX CONCURRENTLY outside a transaction.
    with op.get_context().autocommit_block():
        op.execute(
            f"""
            create index concurrently {INDEX}
            on {TABLE}
            using gist ({COLUMN})
            where is_active = true
              and {COLUMN} is not null
            """
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            f"drop index concurrently if exists {INDEX}"
        )

    op.drop_constraint(
        VALID_CONSTRAINT,
        TABLE,
        type_="check",
    )
    op.drop_constraint(
        TYPE_CONSTRAINT,
        TABLE,
        type_="check",
    )
    op.drop_constraint(
        SRID_CONSTRAINT,
        TABLE,
        type_="check",
    )
    op.drop_column(TABLE, COLUMN)

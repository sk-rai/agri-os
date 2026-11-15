"""Drop offline-first-blocking FK constraints on crop_cycles and crop_activities.

Offline-first clients create crop cycles and log activities on-device and sync
later. Hard foreign keys on farmer_id / parcel_id / crop_cycle_id /
stage_instance_id reject rows whose parents have not synced yet, producing
500s (ForeignKeyViolation) during legitimate offline capture.

These constraints were already removed from the live development database by
hand. This migration codifies that change so a rebuild from migrations
reproduces the working state. Guards use IF EXISTS so the migration is
idempotent regardless of whether the manual drop already happened.

Traceability FKs on crop_activities (input_rule_id, product_id, package_id)
are intentionally left in place — they are nullable and do not block capture.
crop_stage_instances.crop_cycle_id is also left in place to match live state.

Downgrade prerequisite: every non-null child reference covered by the five
constraints below must resolve to an existing parent row before downgrade.
PostgreSQL validates each restored constraint immediately, so downgrade fails
closed if offline-first operation admitted an orphan while the constraints were
absent. Operators must inspect and resolve such rows under a separately approved
data policy before attempting downgrade; this migration does not delete, repair,
or reinterpret them.

Revision ID: 070
Revises: 069
Create Date: 2026-10-14
"""

from typing import Sequence, Union

from alembic import op


revision: str = "070"
down_revision: Union[str, None] = "069"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (constraint_name, table_name, referenced_table, local_col, referenced_col)
_DROPPED_FKS = [
    ("crop_cycles_farmer_id_fkey", "crop_cycles", "farmers", "farmer_id", "id"),
    ("crop_cycles_parcel_id_fkey", "crop_cycles", "parcels", "parcel_id", "id"),
    ("crop_activities_farmer_id_fkey", "crop_activities", "farmers", "farmer_id", "id"),
    ("crop_activities_crop_cycle_id_fkey", "crop_activities", "crop_cycles", "crop_cycle_id", "id"),
    ("crop_activities_stage_instance_id_fkey", "crop_activities", "crop_stage_instances", "stage_instance_id", "id"),
]


def upgrade() -> None:
    for conname, table, _ref, _lcol, _rcol in _DROPPED_FKS:
        op.execute(f'ALTER TABLE {table} DROP CONSTRAINT IF EXISTS "{conname}"')


def downgrade() -> None:
    """Restore validated FKs; fails if any covered child reference is orphaned."""

    for conname, table, ref, lcol, rcol in _DROPPED_FKS:
        op.execute(
            f'ALTER TABLE {table} '
            f'ADD CONSTRAINT "{conname}" FOREIGN KEY ({lcol}) '
            f'REFERENCES {ref} ({rcol})'
        )

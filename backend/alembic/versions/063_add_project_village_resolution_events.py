"""Add immutable project village resolution audit events.

Revision ID: 063
Revises: 062
Create Date: 2026-10-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision='063';down_revision='062';branch_labels=None;depends_on=None
TABLE='geography_project_village_resolution_events'
def upgrade():
 op.create_table(TABLE,
  sa.Column('id',postgresql.UUID(as_uuid=True),primary_key=True),
  sa.Column('tenant_id',sa.String(50),sa.ForeignKey('tenants.id'),nullable=False),
  sa.Column('project_id',postgresql.UUID(as_uuid=True),sa.ForeignKey('projects.id'),nullable=False),
  sa.Column('resolution_id',postgresql.UUID(as_uuid=True),sa.ForeignKey('geography_project_village_resolutions.id'),nullable=False),
  sa.Column('action',sa.String(40),nullable=False),
  sa.Column('actor_id',postgresql.UUID(as_uuid=True),sa.ForeignKey('users.id'),nullable=False),
  sa.Column('approver_id',postgresql.UUID(as_uuid=True),sa.ForeignKey('users.id'),nullable=True),
  sa.Column('evidence',postgresql.JSONB(),nullable=False,server_default=sa.text("'{}'::jsonb")),
  sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.text('now()')),
  sa.CheckConstraint("action in ('APPLIED','ROLLED_BACK')",name='ck_project_village_resolution_event_action'))
 op.create_index('idx_project_village_resolution_event_resolution',TABLE,['resolution_id','created_at'])
 op.create_index('idx_project_village_resolution_event_project',TABLE,['tenant_id','project_id','created_at'])
 op.create_index('uq_project_village_resolution_active_canonical','geography_project_village_resolutions',['tenant_id','project_id','canonical_village_id'],unique=True,postgresql_where=sa.text('is_active=true and canonical_village_id is not null'))
def downgrade():
 op.execute('drop index if exists uq_project_village_resolution_active_canonical')
 op.drop_table(TABLE)
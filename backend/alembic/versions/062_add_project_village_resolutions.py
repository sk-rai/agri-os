"""Add project-scoped village resolution records.

Revision ID: 062
Revises: 061
Create Date: 2026-10-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision='062';down_revision='061';branch_labels=None;depends_on=None
TABLE='geography_project_village_resolutions'
def upgrade():
 op.create_table(TABLE,
  sa.Column('id',postgresql.UUID(as_uuid=True),primary_key=True),
  sa.Column('tenant_id',sa.String(50),sa.ForeignKey('tenants.id'),nullable=False),
  sa.Column('project_id',postgresql.UUID(as_uuid=True),sa.ForeignKey('projects.id'),nullable=False),
  sa.Column('resolution_mode',sa.String(40),nullable=False),
  sa.Column('canonical_village_id',postgresql.UUID(as_uuid=True),sa.ForeignKey('geography_villages.id'),nullable=True),
  sa.Column('nwdp_source_feature_id',postgresql.UUID(as_uuid=True),sa.ForeignKey('geography_boundary_source_features.id'),nullable=True),
  sa.Column('project_village_code',sa.String(80),nullable=False),
  sa.Column('display_name',sa.String(180),nullable=False),
  sa.Column('hierarchy_labels',postgresql.JSONB(),nullable=False,server_default=sa.text("'{}'::jsonb")),
  sa.Column('pin_codes',postgresql.ARRAY(sa.String()),nullable=False,server_default=sa.text("'{}'::text[]")),
  sa.Column('pin_evidence',postgresql.JSONB(),nullable=False,server_default=sa.text("'{}'::jsonb")),
  sa.Column('resolution_status',sa.String(40),nullable=False,server_default='DRAFT'),
  sa.Column('evidence_basis',sa.String(120),nullable=False),
  sa.Column('reviewer',sa.String(120),nullable=True),sa.Column('review_notes',sa.Text(),nullable=True),
  sa.Column('rollback_token',sa.String(80),nullable=False),
  sa.Column('metadata',postgresql.JSONB(),nullable=False,server_default=sa.text("'{}'::jsonb")),
  sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.text('now()')),
  sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.text('now()')),
  sa.Column('version',sa.String(10),nullable=False,server_default='v1.0'),
  sa.Column('is_active',sa.Boolean(),nullable=False,server_default=sa.text('false')),
  sa.CheckConstraint("resolution_mode in ('CANONICAL_ENRICHMENT','PROJECT_LOCAL_ADDITION')",name='ck_project_village_resolution_mode'),
  sa.CheckConstraint("resolution_status in ('DRAFT','APPROVED','ACTIVE','RETIRED','REJECTED')",name='ck_project_village_resolution_status'),
  sa.CheckConstraint("(resolution_mode='CANONICAL_ENRICHMENT' and canonical_village_id is not null) or (resolution_mode='PROJECT_LOCAL_ADDITION' and nwdp_source_feature_id is not null)",name='ck_project_village_resolution_identity'),
  sa.CheckConstraint("is_active=false or resolution_status='ACTIVE'",name='ck_project_village_resolution_active_status'),
  sa.UniqueConstraint('tenant_id','project_id','project_village_code',name='uq_project_village_resolution_code'))
 op.create_index('idx_project_village_resolution_project',TABLE,['tenant_id','project_id','resolution_status'])
 op.create_index('idx_project_village_resolution_canonical',TABLE,['canonical_village_id'])
 op.create_index('idx_project_village_resolution_nwdp',TABLE,['nwdp_source_feature_id'])
 op.create_index('uq_project_village_resolution_active_source',TABLE,['tenant_id','project_id','nwdp_source_feature_id'],unique=True,postgresql_where=sa.text('is_active=true and nwdp_source_feature_id is not null'))
def downgrade():op.drop_table(TABLE)

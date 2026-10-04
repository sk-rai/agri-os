"""Add reusable canonical village local-evidence snapshots.

Revision ID: 066
Revises: 065
Create Date: 2026-10-04
"""
from alembic import op

revision = "066"
down_revision = "065"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
      create table geography_village_resolution_evidence_snapshots (
        id uuid primary key,
        schema_version text not null,
        source_manifest_sha256 text not null,
        source_candidate_pairs_sha256 text not null,
        canonical_unresolved_count integer not null,
        item_count integer not null,
        is_active boolean not null default false,
        created_at timestamptz not null default now(),
        activated_at timestamptz null,
        metadata jsonb not null default '{}'::jsonb,
        constraint ck_village_resolution_evidence_snapshot_counts
          check (canonical_unresolved_count >= 0 and item_count >= 0)
      )
    """)
    op.execute("""
      create unique index uq_village_resolution_evidence_snapshot_active
      on geography_village_resolution_evidence_snapshots ((is_active))
      where is_active
    """)
    op.execute("""
      create table geography_village_resolution_evidence_items (
        id uuid primary key,
        snapshot_id uuid not null references
          geography_village_resolution_evidence_snapshots(id) on delete cascade,
        village_id uuid not null references geography_villages(id),
        disposition text not null,
        candidate_count integer not null,
        best_match_rank integer null,
        best_match_basis text null,
        source_feature_id uuid null references geography_boundary_source_features(id),
        source_candidate_village_count integer not null default 0,
        source_collision boolean not null default false,
        review_eligibility text not null,
        prior_candidate_evidence text null,
        automatic_resolution_authorized boolean not null default false,
        created_at timestamptz not null default now(),
        constraint uq_village_resolution_evidence_item unique (snapshot_id, village_id),
        constraint ck_village_resolution_evidence_disposition check (
          disposition in (
            'DETERMINISTIC_SINGLE_REVIEW',
            'HIGH_CONFIDENCE_SINGLE_REVIEW',
            'AMBIGUOUS_MULTIPLE_CANDIDATES',
            'NO_LOCAL_CANDIDATE'
          )
        ),
        constraint ck_village_resolution_evidence_eligibility check (
          review_eligibility in (
            'TWO_SESSION_REVIEW_ELIGIBLE',
            'CONFLICT_REVIEW_REQUIRED',
            'AMBIGUOUS_REVIEW_REQUIRED',
            'AUTHORITATIVE_EVIDENCE_REQUIRED'
          )
        ),
        constraint ck_village_resolution_evidence_candidate_count
          check (candidate_count >= 0),
        constraint ck_village_resolution_evidence_no_automatic_resolution
          check (automatic_resolution_authorized = false)
      )
    """)
    op.execute("""
      create index ix_village_resolution_evidence_items_snapshot_disposition
      on geography_village_resolution_evidence_items
        (snapshot_id, disposition, review_eligibility, source_collision)
    """)
    op.execute("""
      create index ix_village_resolution_evidence_items_village
      on geography_village_resolution_evidence_items (village_id)
    """)


def downgrade():
    op.drop_table("geography_village_resolution_evidence_items")
    op.drop_table("geography_village_resolution_evidence_snapshots")

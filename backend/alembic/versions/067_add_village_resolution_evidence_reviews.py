"""Add reusable two-session village evidence reviews.

Revision ID: 067
Revises: 066
Create Date: 2026-10-04
"""
from alembic import op

revision = "067"
down_revision = "066"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
      create table geography_village_resolution_evidence_reviews (
        id uuid primary key,
        snapshot_id uuid not null references
          geography_village_resolution_evidence_snapshots(id) on delete restrict,
        evidence_item_id uuid not null references
          geography_village_resolution_evidence_items(id) on delete restrict,
        village_id uuid not null references geography_villages(id) on delete restrict,
        source_feature_id uuid not null references
          geography_boundary_source_features(id) on delete restrict,
        status text not null,
        primary_decision text not null,
        primary_reviewer_id uuid not null references users(id) on delete restrict,
        primary_notes text not null,
        second_decision text null,
        second_reviewer_id uuid null references users(id) on delete restrict,
        second_notes text null,
        created_at timestamptz not null default now(),
        updated_at timestamptz not null default now(),
        constraint ck_village_evidence_review_status check (
          status in ('PENDING_SECOND_REVIEW','APPROVED','REJECTED','HELD')
        ),
        constraint ck_village_evidence_primary_decision check (
          primary_decision in ('ACCEPT_FOR_SECOND_REVIEW','REJECT','HOLD')
        ),
        constraint ck_village_evidence_second_decision check (
          second_decision is null or second_decision in ('APPROVE','REJECT','HOLD')
        ),
        constraint ck_village_evidence_distinct_reviewers check (
          second_reviewer_id is null or second_reviewer_id <> primary_reviewer_id
        ),
        constraint uq_village_evidence_review_item unique (snapshot_id, evidence_item_id)
      )
    """)
    op.execute("""
      create index ix_village_evidence_reviews_queue
      on geography_village_resolution_evidence_reviews
        (snapshot_id, status, created_at)
    """)
    op.execute("""
      create table geography_village_resolution_evidence_review_events (
        id uuid primary key,
        review_id uuid not null references
          geography_village_resolution_evidence_reviews(id) on delete cascade,
        action text not null,
        actor_id uuid not null references users(id) on delete restrict,
        notes text not null,
        evidence jsonb not null default '{}'::jsonb,
        created_at timestamptz not null default now(),
        constraint ck_village_evidence_review_event_action check (
          action in ('PRIMARY_ACCEPTED','PRIMARY_REJECTED','PRIMARY_HELD',
                     'SECOND_APPROVED','SECOND_REJECTED','SECOND_HELD')
        )
      )
    """)
    op.execute("""
      create index ix_village_evidence_review_events_review
      on geography_village_resolution_evidence_review_events
        (review_id, created_at)
    """)


def downgrade():
    op.drop_table("geography_village_resolution_evidence_review_events")
    op.drop_table("geography_village_resolution_evidence_reviews")

# NWDP Boundary API and Android Consumption Plan

Status date: 2026-08-23

## Purpose

This document plans how reviewed NWDP/GSI boundary data can eventually be consumed by backend APIs and Android.

This is a planning document only. It does not enable runtime point-in-polygon matching, Android lookup, or automatic geography overwrite.

## Current source of truth

Current NWDP boundary data is staged in inactive review tables:

- geography_boundary_import_batches
- geography_boundary_source_features
- geography_boundary_crosswalk_candidates

Current Karnataka staging state:

- source features: 29,789
- crosswalk candidates: 29,789
- active candidates: 0
- promoted candidates: 0
- runtime spatial matching: disabled
- Android behavior: unchanged

## Consumption boundary

Backend APIs and Android must not consume staging candidates directly for production lookup.

The intended consumption chain is:

1. inactive staging import;
2. admin review and metadata decisions;
3. promotion eligibility dry-run;
4. reviewed runtime promotion into separate runtime tables;
5. read-only runtime API exposure;
6. feature-flagged Android consumption.

## Backend API stages

### Stage 0: Admin review only

Already implemented.

Surfaces:

- batch list/detail;
- candidate list/detail;
- guarded review metadata save;
- filtered CSV export.

Guarantees:

- no candidate activation;
- no promotion;
- no runtime lookup;
- no Android behavior change.

### Stage 1: Promotion dry-run API

Next backend milestone.

A dry-run endpoint should report what could be promoted without writing runtime rows.

Suggested endpoint:

    GET /api/v1/master-data/geography/boundary-runtime-promotion/dry-run

Suggested filters:

- state_or_ut
- source_system
- import_batch_id
- candidate_bucket
- review_status
- proposed_scope
- limit

Dry-run response should include:

- schema version;
- candidate counts by eligibility state;
- excluded counts by reason;
- promotable candidate sample;
- ineligible candidate sample;
- guardrail flags proving no DB writes;
- Android/runtime flags still disabled.

### Stage 2: Runtime table migration

Only after dry-run is reviewed.

Runtime data should live in separate tables from staging:

- geography_boundary_runtime_sets
- geography_boundary_runtime_features
- geography_boundary_runtime_crosswalks
- geography_boundary_runtime_promotion_events

Runtime tables must include active/superseded state and audit metadata.

### Stage 3: Read-only runtime APIs

Only active runtime sets should be exposed.

Initial backend APIs:

- GET /api/v1/master-data/geography/boundary-runtime-sets
- GET /api/v1/master-data/geography/boundary-runtime-sets/{set_id}
- GET /api/v1/master-data/geography/boundary-runtime-features
- GET /api/v1/master-data/geography/boundary-runtime-features/{feature_id}

These APIs should be read-only and should not expose inactive staging rows.

### Stage 4: Spatial lookup API

Only after runtime features exist and feature flags are enabled.

Candidate endpoint:

    POST /api/v1/master-data/geography/boundary-runtime/lookup

Suggested request:

- latitude
- longitude
- state_or_ut
- desired_scope
- project_id or tenant context
- client_source

Suggested response:

- matched runtime feature;
- matched LGD geography;
- confidence;
- source system;
- runtime set id;
- geometry version/hash;
- requires_user_confirmation;
- no_auto_overwrite flag.

## Android consumption stages

### Android Stage A: No runtime consumption

Current state.

Android does not use NWDP boundaries.

### Android Stage B: Read-only suggestion

First allowed Android behavior after runtime APIs are available.

Android may show suggested administrative context, but must not silently overwrite farmer, parcel, or enrollment geography.

Required UI behavior:

- show suggested village/district context;
- show source label such as NWDP/GSI reviewed boundary;
- ask agent/user to confirm;
- store confirmation provenance;
- preserve previous geography values.

### Android Stage C: Assisted validation

Future behavior.

Android may compare GPS point, current selected geography, and runtime boundary suggestion.

Still blocked:

- automatic overwrite;
- background mutation;
- use of unreviewed staging candidates.

## Feature flags

Suggested backend flags:

- boundary_runtime_lookup_enabled
- boundary_runtime_state_ka_enabled
- boundary_runtime_android_enabled
- boundary_runtime_android_cache_enabled
- boundary_runtime_auto_overwrite_enabled

Initial expected values:

- lookup enabled: false
- Karnataka enabled: false
- Android enabled: false
- Android cache enabled: false
- auto overwrite enabled: false

## Required guardrails

Before any Android consumption:

- runtime table migration exists;
- promotion dry-run passes;
- reviewed runtime promotion creates inactive-to-runtime audit events;
- active runtime set exists;
- lookup API reads active runtime tables only;
- Android feature flag remains off until QA;
- Android UI clearly marks suggestions as suggestions;
- no staging table is queried by Android-facing APIs.

## Recommended next implementation

Implement the Stage 1 promotion dry-run API and regression first.

It should calculate promotable candidates from current staging rows but keep:

- db_writes_attempted = false;
- ready_for_runtime_spatial_matching = false;
- android_behavior_changed = false;
- runtime_tables_required = true.

## Stage 1 dry-run API checkpoint

Status date: 2026-08-23

Implemented endpoint:

    GET /api/v1/master-data/geography/boundary-runtime-promotion/dry-run

Current observed Karnataka result:

- candidate_count: 29,789;
- promotable_candidate_count: 0;
- excluded_candidate_count: 29,789;
- eligibility_counts: NOT_REVIEW_APPROVED = 29,789;
- db_writes_attempted: false;
- runtime_tables_written: false;
- ready_for_runtime_spatial_matching: false;
- android_behavior_changed: false;
- runtime_tables_required: true.

Regression coverage:

- `backend/scripts/test_nwdp_boundary_runtime_promotion_dry_run.py`;
- included in `backend/scripts/run_nwdp_boundary_regressions.py`.

Current decision:

- the dry-run can calculate eligibility from inactive staging rows;
- it does not create runtime rows;
- it does not activate or promote candidates;
- it does not enable Android or runtime spatial lookup;
- next runtime work should design and migrate separate runtime tables before any lookup API is enabled.

## Runtime table schema checkpoint

Status date: 2026-08-23

Migration added:

- `backend/alembic/versions/055_add_nwdp_boundary_runtime_tables.py`

Runtime table family:

- geography_boundary_runtime_sets
- geography_boundary_runtime_features
- geography_boundary_runtime_crosswalks
- geography_boundary_runtime_promotion_events

Schema guard:

- `backend/scripts/test_nwdp_boundary_runtime_schema_guard.py`
- included in `backend/scripts/run_nwdp_boundary_regressions.py`

Latest observed guard result:

- healthy: true;
- migration_applied: false;
- db_writes_attempted: false;
- ready_for_runtime_spatial_matching: false;
- android_behavior_changed: false.

Current decision:

- runtime tables are schema-only at this checkpoint;
- no runtime rows are loaded;
- no staging candidate is activated or promoted;
- no lookup API is enabled;
- Android behavior remains unchanged.

## Local runtime migration checkpoint

Status date: 2026-08-23

Local command completed:

    cd ~/projects/farmint/backend
    ../venv/bin/alembic upgrade 055

Observed local verification:

- geography_boundary_runtime_sets exists: true, count: 0;
- geography_boundary_runtime_features exists: true, count: 0;
- geography_boundary_runtime_crosswalks exists: true, count: 0;
- geography_boundary_runtime_promotion_events exists: true, count: 0.

Readiness:

- migration_applied: true;
- runtime_rows_loaded: false;
- ready_for_runtime_spatial_matching: false;
- android_behavior_changed: false.

Current decision:

- runtime schema is now available locally;
- tables are intentionally empty;
- the next implementation should be a guarded runtime promotion importer with dry-run-first behavior;
- no runtime lookup API should be added until runtime promotion has a passing dry-run and explicit apply checkpoint.

## Runtime promotion importer dry-run checkpoint

Status date: 2026-08-24

Importer added:

- `backend/scripts/promote_nwdp_boundary_runtime.py`

Regression added:

- `backend/scripts/test_nwdp_boundary_runtime_promotion_importer.py`
- included in `backend/scripts/run_nwdp_boundary_regressions.py`

Latest observed dry-run result:

- schema_version: nwdp_boundary_runtime_promotion_importer.v1;
- healthy: true;
- apply_mode: false;
- db_writes_attempted: false;
- runtime_tables_written: false;
- runtime_rows_effective: 0;
- runtime tables available: true;
- runtime table counts: 0 for sets, features, crosswalks, and promotion events;
- candidate_count: 29,789;
- promotable_candidate_count: 0;
- excluded_candidate_count: 29,789;
- eligibility_counts: NOT_REVIEW_APPROVED = 29,789;
- ready_for_runtime_table_write: false;
- ready_for_runtime_spatial_matching: false;
- android_behavior_changed: false.

Latest observed blocked apply result:

- `--apply` exits non-zero;
- apply_blocked: true;
- error: APPLY_BLOCKED_PENDING_REVIEWED_RUNTIME_PROMOTION_POLICY;
- db_writes_attempted: false;
- runtime_tables_written: false;
- runtime_rows_effective: 0;
- runtime table counts remain 0.

Current decision:

- the importer is dry-run-first and apply-blocked;
- it can report candidate eligibility against the local runtime schema;
- it cannot write runtime rows yet;
- runtime lookup and Android consumption remain disabled.

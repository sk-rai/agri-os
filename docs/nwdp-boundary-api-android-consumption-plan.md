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

# NWDP Boundary Runtime Promotion Design

Status date: 2026-08-23

## Purpose

This document designs the path from inactive NWDP/GSI boundary review staging to a future runtime boundary dataset consumable by backend APIs and Android.

It is a design document only. It does not authorize immediate runtime spatial matching, Android use, or candidate promotion.

## Current state

- Karnataka NWDP/GSI SHP source has been audited.
- Source CRS is EPSG:7755, WGS 84 / India NSF LCC.
- Geometry plausibility after WGS84 transform is strong.
- 29,789 source features were staged inactive.
- 29,789 crosswalk candidates were staged inactive.
- Active candidates remain 0.
- Promoted candidates remain 0.
- Runtime spatial matching remains disabled.
- Android behavior remains unchanged.

## Existing staging tables

- geography_boundary_import_batches
- geography_boundary_source_features
- geography_boundary_crosswalk_candidates

These tables are review/staging tables. They are not runtime lookup tables.

## Promotion principles

A boundary candidate may be promoted only through a separate reviewed workflow. Promotion must not be a side effect of import, smoke tests, admin browsing, or metadata review.

Promotion must require:

- inactive staging source feature exists;
- candidate is inactive before promotion;
- candidate has promotion_status = NOT_PROMOTED before promotion;
- candidate has review_status = APPROVED_FOR_PROMOTION;
- candidate has a reviewer decision compatible with promotion;
- candidate has reviewer notes and review history;
- candidate bucket is eligible for promotion;
- source geometry was transformed to EPSG:4326 or a reviewed runtime CRS;
- geometry validation passed;
- crosswalk target is explicit enough for the target runtime scope.

## Promotion-ineligible buckets

These buckets must not be promoted directly:

- SPECIAL_REFERENCE_FEATURE
- DISTRICT_SCOPED_AMBIGUOUS
- PARENT_SCOPED_NAME_AMBIGUOUS
- PARENT_MATCH_VILLAGE_UNRESOLVED

They may be retained as review/reference data, but not used for farmer parcel point-in-polygon or Android location lookup.

## Candidate buckets requiring review before promotion

- DIRECT_VLCODE_PARENT_MISMATCH
- PARENT_SCOPED_NAME_MATCH

These can become promotable only after reviewer confirmation and evidence capture.

## Candidate buckets that may be auto-proposed but not auto-promoted

- DIRECT_VLCODE_MATCH

Even direct vlcode matches should remain inactive until a reviewed promotion operation creates runtime rows.

## Proposed runtime tables

Future table family:

- geography_boundary_runtime_sets
- geography_boundary_runtime_features
- geography_boundary_runtime_crosswalks
- geography_boundary_runtime_promotion_events

The runtime tables should be separate from staging tables.

## Runtime set

A runtime set represents one reviewed release of boundary data for a state/source/version.

Suggested fields:

- id
- source_system
- state_or_ut
- source_format
- source_file_sha256
- source_crs
- source_epsg
- runtime_crs
- status
- is_active
- activated_at
- superseded_at
- created_by
- review_summary
- guardrail_metadata

Only one active runtime set per source/state/scope should be allowed unless a future multi-version serving policy is designed.

## Runtime feature

A runtime feature stores transformed, validated geometry for lookup.

Suggested fields:

- id
- runtime_set_id
- source_feature_id
- source_feature_index
- source_codes
- source_names
- feature_category
- geometry_wgs84
- centroid_wgs84
- bbox_wgs84
- geometry_hash
- geometry_validation_status
- is_active

Runtime feature geometry should be stored only after reviewed transform and validation.

## Runtime crosswalk

A runtime crosswalk links a runtime feature to backend geography.

Suggested scopes:

- village
- village_review
- district_subdistrict
- district_review
- reference_only

Only village-level reviewed rows should be eligible for Android village-boundary matching in the first release.

District/subdistrict-scoped rows may support admin review context, but should not drive farmer parcel assignment unless explicitly designed later.

## API consumption design

Backend APIs should expose runtime boundaries only from active runtime sets.

Initial internal APIs may include:

- GET /api/v1/master-data/geography/boundary-runtime-sets
- GET /api/v1/master-data/geography/boundary-runtime-sets/{set_id}
- GET /api/v1/master-data/geography/boundary-runtime-features
- GET /api/v1/master-data/geography/boundary-runtime-features/{feature_id}

Android-facing APIs should not directly query staging candidates.

Android should consume only reviewed runtime APIs, and only after feature flags are enabled.

## Android consumption guardrails

Android use must be feature-flagged.

Suggested flags:

- boundary_runtime_lookup_enabled
- boundary_runtime_state_ka_enabled
- boundary_runtime_android_cache_enabled

Initial Android behavior should be read-only assistive context, not automatic overwrite of farmer geography.

Suggested first Android mode:

- show suggested village/administrative context;
- require user/agent confirmation;
- record source and confidence;
- never silently overwrite existing farmer/parcel geography.

## Promotion operation

Promotion should be a guarded backend command or admin action, not a generic table update.

Promotion should:

- validate candidate eligibility;
- transform geometry to WGS84 if not already transformed;
- validate geometry;
- insert runtime set if needed;
- insert runtime features;
- insert runtime crosswalks;
- write promotion event;
- leave source staging rows immutable except promotion_status metadata;
- keep all actions auditable.

## Rollback and supersession

Runtime activation must support rollback/supersession.

A new runtime set should not delete prior runtime data. Instead:

- create new runtime set;
- activate new set;
- mark previous set superseded;
- keep historical lookup traceability.

## Non-goals for first runtime release

- all-India rollout;
- automatic promotion of all direct matches;
- special/reference feature runtime matching;
- automatic Android geography overwrite;
- parcel-boundary overlap without reviewed geometry policy;
- resolving every unmatched vlcode before first reviewed pilot runtime set.

## First implementation recommendation

Before writing runtime geometry, implement a read-only runtime promotion dry-run that reports:

- promotable candidate count;
- excluded candidate count by reason;
- geometry availability/validation readiness;
- proposed runtime set summary;
- proposed village/district/subdistrict scope counts;
- Android eligibility count;
- unsafe candidates blocked.

Only after dry-run review should a guarded apply path be considered.


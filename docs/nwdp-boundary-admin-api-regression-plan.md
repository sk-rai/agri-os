# NWDP Boundary Admin API Regression Plan

Status date: 2026-08-22

This plan defines the regression target for future NWDP boundary admin review endpoints.

It intentionally mirrors the CoRE/LGD admin review regression style in:

    backend/scripts/test_core_lgd_admin_review_endpoint.py

## Scope

Future regression script:

    backend/scripts/test_nwdp_boundary_admin_review_endpoint.py

The script should validate the admin API contract in:

    docs/nwdp-boundary-admin-api-contract.md

## Preconditions

Run only after:

- staging migration `054_add_nwdp_boundary_review_staging.py` is intentionally applied in a local/dev database;
- a guarded importer has staged candidate rows as inactive;
- no runtime boundary lookup or promotion endpoint is enabled.

## Required test setup

The regression should identify or seed one local test batch containing:

- at least one `DIRECT_VLCODE_MATCH`;
- at least one `DIRECT_VLCODE_PARENT_MISMATCH`;
- at least one `PARENT_MATCH_VILLAGE_UNRESOLVED`;
- at least one `DISTRICT_SCOPED_AMBIGUOUS`;
- at least one `SPECIAL_REFERENCE_FEATURE`.

The fixture must preserve:

- `is_active=false`;
- `promotion_status=NOT_PROMOTED`;
- runtime spatial matching disabled.

## Test 1: unauthenticated access denied

Requests without admin headers must return `401` or `403`:

- `GET /api/v1/admin/geography/boundary-batches`
- `GET /api/v1/admin/geography/boundary-batches/{batch_id}/candidates`
- `GET /api/v1/admin/geography/boundary-candidates/{candidate_id}`

## Test 2: admin viewer can read

`ADMIN_VIEWER` should be able to read:

- batch list;
- batch detail;
- candidate list;
- candidate detail.

Expected response governance:

- `read_only_runtime=true`;
- `promotion_supported=false`;
- `runtime_spatial_matching_changed=false`;
- `android_behavior_changed=false`.

## Test 3: read filters work

Candidate list filters must work for:

- `candidate_bucket`;
- `review_status`;
- `promotion_status`;
- `proposed_scope`;
- `district`;
- `vlcode`;
- `parent_mismatch_only`;
- `unresolved_only`;
- `special_reference_only`.

## Test 4: admin editor can update review metadata

`ADMIN_EDITOR` should be able to patch:

    PATCH /api/v1/admin/geography/boundary-candidates/{candidate_id}/review

Expected behavior:

- review status changes;
- reviewer decision changes;
- reviewer note is recorded;
- `is_active` remains false;
- `promotion_status` remains `NOT_PROMOTED`;
- runtime spatial matching remains unchanged;
- Android behavior remains unchanged.

## Test 5: candidate review validation

The endpoint must reject:

- non-pending decisions without reviewer notes;
- `SPECIAL_REFERENCE_FEATURE` with `APPROVED_FOR_PROMOTION`;
- `MARK_REFERENCE_ONLY` without `review_status=REFERENCE_ONLY`;
- `REJECT_SPECIAL_FEATURE` without `review_status=REJECTED`;
- any attempt to set `is_active=true`;
- any attempt to set `promotion_status=PROMOTED`.

## Test 6: batch review metadata only

`ADMIN_EDITOR` should be able to patch:

    PATCH /api/v1/admin/geography/boundary-batches/{batch_id}/review

Expected behavior:

- batch review status changes;
- batch reviewer note is recorded;
- candidate rows remain inactive;
- no candidate is promoted;
- runtime spatial matching remains disabled.

## Test 7: repeatability reset

The regression should reset any changed test candidate and batch review status at the end, similar to the CoRE/LGD regression.

## Pass criteria

The regression passes only if:

- auth gates behave correctly;
- read endpoints expose governance metadata;
- review endpoints update metadata only;
- zero candidate rows become active;
- zero candidates become promoted;
- zero runtime lookup rows are created;
- Android behavior is unchanged;
- blocked/reference-only safety rules are enforced.

## Read-only endpoint regression checkpoint

Status date: 2026-08-22

Implemented regression:

    backend/scripts/test_nwdp_boundary_admin_read_endpoints.py

The regression passed and confirmed read-only access does not activate or promote NWDP boundary candidates.

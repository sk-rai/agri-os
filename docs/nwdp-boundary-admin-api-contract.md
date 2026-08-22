# NWDP Boundary Admin API Contract

Status date: 2026-08-22

This contract defines the backend admin API shape for reviewing NWDP/GSI village-boundary crosswalk candidates.

It follows the CoRE/LGD admin review pattern:

- staged candidates are inactive;
- admin review may update review metadata;
- review does not activate runtime behavior;
- promotion is a separate future workflow;
- Android, parcel assignment, claim/subsidy/insurance, and point-in-polygon behavior remain unchanged.

## Governance mode

All first-pass endpoints must return governance metadata:

| Field | Required value |
| --- | --- |
| `mode` | `READ_ONLY_ADMIN_REVIEW` or `MANUAL_REVIEW_ONLY` |
| `read_only_runtime` | `true` |
| `promotion_supported` | `false` |
| `runtime_spatial_matching_changed` | `false` |
| `android_behavior_changed` | `false` |
| `db_write_scope` | `REVIEW_METADATA_ONLY` for review endpoints; `NONE` for read endpoints |

## Permissions

Use existing admin auth conventions.

Suggested permission gates:

| Action | Minimum role |
| --- | --- |
| List/read batches | `ADMIN_VIEWER` |
| List/read candidates | `ADMIN_VIEWER` |
| Submit candidate review | `ADMIN_EDITOR` |
| Submit batch review | `ADMIN_EDITOR` |
| Promotion | not implemented |

Non-admin or unauthenticated requests must return `401` or `403`.

## Endpoint summary

Read endpoints:

- `GET /api/v1/admin/geography/boundary-batches`
- `GET /api/v1/admin/geography/boundary-batches/{batch_id}`
- `GET /api/v1/admin/geography/boundary-batches/{batch_id}/candidates`
- `GET /api/v1/admin/geography/boundary-candidates/{candidate_id}`

Review endpoints:

- `PATCH /api/v1/admin/geography/boundary-candidates/{candidate_id}/review`
- `PATCH /api/v1/admin/geography/boundary-batches/{batch_id}/review`

Future endpoints, explicitly not in first implementation:

- `POST /api/v1/admin/geography/boundary-candidates/{candidate_id}/promote`
- `POST /api/v1/admin/geography/boundary-batches/{batch_id}/promote-reviewed-direct-matches`

## `GET /boundary-batches`

Purpose: list NWDP/GSI boundary import batches.

Query params:

| Param | Type | Notes |
| --- | --- | --- |
| `state_or_ut` | string | Optional, e.g. `Karnataka`. |
| `source_system` | string | Optional, e.g. `NWDP_GSI_VILLAGE_BOUNDARY`. |
| `status` | string | Optional batch status filter. |
| `review_status` | string | Optional review status filter. |
| `limit` | int | Default 50, max 200. |
| `offset` | int | Default 0. |

Response shape:

    {
      "schema_version": "nwdp_boundary_admin_batches.v1",
      "mode": "READ_ONLY_ADMIN_REVIEW",
      "governance": {},
      "summary": {
        "total_batches": 0,
        "runtime_spatial_matching_changed": false,
        "android_behavior_changed": false
      },
      "items": []
    }

Batch item fields:

- `batch_id`;
- `source_system`;
- `source_dataset`;
- `source_producer_agency`;
- `state_or_ut`;
- `source_format`;
- `source_crs`;
- `source_epsg`;
- `target_crs`;
- `source_file_sha256`;
- `status`;
- `review_status`;
- `feature_count`;
- `candidate_count`;
- `auto_candidate_count`;
- `manual_review_count`;
- `blocked_count`;
- `created_at`;
- `reviewed_at`.

## `GET /boundary-batches/{batch_id}`

Purpose: show one batch with audit evidence.

Response shape:

    {
      "schema_version": "nwdp_boundary_admin_batch_detail.v1",
      "mode": "READ_ONLY_ADMIN_REVIEW",
      "governance": {},
      "batch": {},
      "audit_evidence": {
        "manifest_audit": {},
        "crs_audit": {},
        "geometry_audit": {},
        "crosswalk_audit": {},
        "dry_run_import_audit": {}
      },
      "candidate_summary": {}
    }

The endpoint must not expose runtime lookup activation actions.

## `GET /boundary-batches/{batch_id}/candidates`

Purpose: list candidate review queue for a batch.

Query params:

| Param | Type | Notes |
| --- | --- | --- |
| `candidate_bucket` | string | Optional. |
| `review_status` | string | Optional; default may emphasize `MANUAL_REVIEW,BLOCKED`. |
| `promotion_status` | string | Optional. |
| `proposed_scope` | string | Optional. |
| `district` | string | Optional text filter. |
| `subdistrict` | string | Optional text filter. |
| `block` | string | Optional text filter. |
| `vlcode` | string | Optional source `vlcode`. |
| `backend_village_lgd_code` | string | Optional proposed backend village code. |
| `parent_mismatch_only` | bool | Optional. |
| `unresolved_only` | bool | Optional. |
| `special_reference_only` | bool | Optional. |
| `limit` | int | Default 50, max 200. |
| `offset` | int | Default 0. |

Response shape:

    {
      "schema_version": "nwdp_boundary_admin_candidates.v1",
      "mode": "READ_ONLY_ADMIN_REVIEW",
      "governance": {},
      "filters": {},
      "summary": {
        "total": 0,
        "auto_candidate_count": 0,
        "manual_review_count": 0,
        "blocked_count": 0,
        "runtime_spatial_matching_changed": false
      },
      "items": []
    }

Candidate list item fields:

- `candidate_id`;
- `source_feature_id`;
- `source_feature_index`;
- `candidate_bucket`;
- `confidence`;
- `review_status`;
- `promotion_status`;
- `proposed_scope`;
- `source_codes`;
- `source_names`;
- `proposed_lgd_codes`;
- `proposed_backend_ids`;
- `reason`;
- `updated_at`.

## `GET /boundary-candidates/{candidate_id}`

Purpose: detail view for one candidate.

Response shape:

    {
      "schema_version": "nwdp_boundary_admin_candidate_detail.v1",
      "mode": "READ_ONLY_ADMIN_REVIEW",
      "governance": {},
      "candidate": {},
      "source_feature": {},
      "proposed_match": {},
      "audit_evidence": {},
      "review_history": [],
      "allowed_review_decisions": []
    }

Required sections:

### Candidate

- `candidate_id`;
- `candidate_bucket`;
- `confidence`;
- `review_status`;
- `promotion_status`;
- `proposed_scope`;
- `reviewer_decision`;
- `reviewer_notes`;
- `reviewed_at`.

### Source feature

- `source_feature_index`;
- `source_stcode`;
- `source_dtcode`;
- `source_sdcode`;
- `source_bkcode`;
- `source_vlcode`;
- `source_state_name`;
- `source_district_name`;
- `source_subdistrict_name`;
- `source_block_name`;
- `source_village_name`;
- `source_agency`;
- `feature_category`;
- `source_properties`;
- `source_geometry_hash`;
- `source_bbox`;
- `transformed_bbox`;
- `transformed_centroid`;
- `geometry_validation_status`.

### Proposed match

- `proposed_state_id`;
- `proposed_district_id`;
- `proposed_block_id`;
- `proposed_village_id`;
- `proposed_state_lgd_code`;
- `proposed_district_lgd_code`;
- `proposed_block_lgd_code`;
- `proposed_village_lgd_code`;
- `match_evidence`.

## `PATCH /boundary-candidates/{candidate_id}/review`

Purpose: update review metadata only.

Request body:

    {
      "reviewer_decision": "KEEP_PENDING",
      "review_status": "MANUAL_REVIEW",
      "reviewer_notes": "Explain evidence and decision.",
      "evidence_summary": {}
    }

Allowed `reviewer_decision` values:

- `KEEP_PENDING`;
- `ACCEPT_DIRECT_CODE_MATCH`;
- `ACCEPT_REVIEWED_NAME_MATCH`;
- `MARK_REFERENCE_ONLY`;
- `REJECT_SOURCE_MISMATCH`;
- `REJECT_SPECIAL_FEATURE`;
- `BLOCK_PENDING_SOURCE_REVIEW`.

Allowed `review_status` values:

- `MANUAL_REVIEW`;
- `APPROVED_FOR_PROMOTION`;
- `REFERENCE_ONLY`;
- `REJECTED`;
- `BLOCKED`.

Validation rules:

- non-`KEEP_PENDING` decisions require non-empty `reviewer_notes`;
- `SPECIAL_REFERENCE_FEATURE` cannot become `APPROVED_FOR_PROMOTION`;
- `MARK_REFERENCE_ONLY` must set `review_status=REFERENCE_ONLY`;
- `REJECT_SPECIAL_FEATURE` must set `review_status=REJECTED`;
- endpoint must not set `is_active=true`;
- endpoint must not change `promotion_status` to promoted;
- endpoint must not write runtime lookup rows.

Response shape:

    {
      "schema_version": "nwdp_boundary_admin_candidate_review.v1",
      "candidate_id": "...",
      "review_status": "MANUAL_REVIEW",
      "reviewer_decision": "KEEP_PENDING",
      "is_active": false,
      "promotion_status": "NOT_PROMOTED",
      "runtime_spatial_matching_changed": false,
      "android_behavior_changed": false
    }

## `PATCH /boundary-batches/{batch_id}/review`

Purpose: update batch-level review metadata only.

Request body:

    {
      "review_status": "MANUAL_REVIEW",
      "reviewer_notes": "Batch-level note."
    }

Allowed batch review statuses:

- `MANUAL_REVIEW`;
- `SOURCE_REVIEWED`;
- `BLOCKED`;
- `READY_FOR_CANDIDATE_IMPORT_REVIEW`;
- `READY_FOR_PROMOTION_REVIEW`.

Validation rules:

- `READY_FOR_PROMOTION_REVIEW` is allowed only if schema guard and dry-run verifier summaries are green;
- batch review must not activate candidate rows;
- batch review must not promote direct matches;
- batch review must not enable runtime spatial matching.

## Regression expectations

First backend regression should mirror `backend/scripts/test_core_lgd_admin_review_endpoint.py`.

It should verify:

- unauthenticated/non-admin request is denied;
- admin viewer can read batches and candidates;
- admin editor can update review metadata;
- review update does not activate candidates;
- review update does not change promotion status to promoted;
- runtime spatial matching behavior remains false;
- Android behavior remains false;
- blocked/reference-only rows cannot be promoted by review endpoint;
- filter by bucket/review status works.

## Claim boundary

These endpoints are admin review tools only.

They do not:

- establish cadastral truth;
- establish ownership;
- auto-assign parcels to villages;
- approve/reject claims;
- approve/reject subsidy or insurance decisions;
- enable Android local boundary matching;
- enable runtime point-in-polygon.

## Current decision

Implement read and review endpoints only after the staging migration is reviewed and intentionally applied locally.

Do not implement promotion endpoints in the first API pass.

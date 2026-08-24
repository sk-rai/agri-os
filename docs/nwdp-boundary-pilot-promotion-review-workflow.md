# NWDP Boundary Pilot Promotion Review Workflow

Status date: 2026-08-24

## Purpose

This document defines a guarded review workflow for moving a small pilot subset of NWDP/GSI boundary candidates toward runtime promotion eligibility.

It does not authorize bulk promotion, runtime lookup, Android consumption, or automatic point-in-polygon matching.

## Current state

- Runtime tables exist locally.
- Runtime tables are empty.
- Runtime promotion importer dry-run is implemented.
- Runtime promotion importer `--apply` is blocked.
- Current promotable candidates: 0.
- Current excluded candidates: 29,789.
- Current exclusion reason: NOT_REVIEW_APPROVED.
- Runtime lookup remains disabled.
- Android behavior remains unchanged.

## Pilot principle

Promotion eligibility should begin with a tiny, auditable pilot subset rather than all direct-code candidates.

Recommended first pilot size:

- 10 to 25 candidates.

Recommended first pilot bucket:

- DIRECT_VLCODE_MATCH.

Reason:

- it has explicit source vlcode and backend village linkage;
- it is easiest to review;
- it still requires human approval and geometry validation before runtime write.

## Candidate selection constraints

A candidate may enter the pilot queue only if:

- candidate_bucket = DIRECT_VLCODE_MATCH;
- review_status = AUTO_CANDIDATE or MANUAL_REVIEW before pilot review;
- promotion_status = NOT_PROMOTED;
- is_active = false;
- proposed_scope = village or village_review;
- proposed_village_id is present;
- proposed_village_lgd_code equals source_vlcode or reviewer documents why mismatch is acceptable;
- source feature is not a special/reference feature;
- source geometry hash is present;
- transformed centroid/bbox are present;
- geometry_validation_status has passed or is explicitly marked for validation.

## Required reviewer decision

For the first pilot, only these decisions should be promotion-compatible:

- ACCEPT_DIRECT_CODE_MATCH
- ACCEPT_REVIEWED_NAME_MATCH

Other decisions should remain non-promotable:

- KEEP_PENDING
- MARK_REFERENCE_ONLY
- REJECT_SOURCE_MISMATCH
- REJECT_SPECIAL_FEATURE
- BLOCK_PENDING_SOURCE_REVIEW

## Required review status

Promotion-compatible candidates must have:

- review_status = APPROVED_FOR_PROMOTION

The review endpoint may set this metadata, but it must not itself write runtime rows.

## Required evidence

Reviewer notes must include:

- why the source village boundary is acceptable;
- whether source vlcode and backend village lgd code match;
- any parent/district/subdistrict check performed;
- whether geometry bbox/centroid looked plausible;
- whether this is part of the bounded pilot.

Evidence summary should include structured keys:

- pilot_id
- reviewer_checklist_version
- source_vlcode_matches_backend
- parent_scope_checked
- geometry_bbox_checked
- geometry_centroid_checked
- source_geometry_hash_present
- runtime_promotion_candidate

## Geometry validation gate

Before runtime write is allowed, geometry_validation_status must be one of:

- VALID
- VALIDATED

Current staged source features are NOT_VALIDATED, so the first pilot cannot write runtime rows until a separate geometry validation checkpoint exists.

## Promotion dry-run expectation after pilot review

After a small pilot subset is review-approved but before geometry validation, the dry-run should shift those rows away from NOT_REVIEW_APPROVED into the next blocking reason:

- GEOMETRY_NOT_VALIDATED

That is expected and safe.

Only after geometry validation is completed should any pilot candidate become PROMOTABLE.

## UI workflow recommendation

Add a pilot helper to the NWDP boundary review UI:

- filter direct-code candidates;
- choose a small pilot district or sample;
- expose source vlcode, proposed village lgd code, source names, proposed match, bbox/centroid evidence;
- provide an approve-for-pilot shortcut;
- require reviewer notes;
- label the action clearly as metadata-only;
- show that promotion importer still requires separate dry-run/apply review.

## Backend workflow recommendation

Add a guarded endpoint or script for pilot approval metadata only.

It should:

- accept candidate ids;
- require admin EDIT;
- require reviewer notes;
- set reviewer_decision and review_status only;
- append review_history;
- keep is_active=false;
- keep promotion_status=NOT_PROMOTED;
- return runtime_spatial_matching_changed=false;
- return android_behavior_changed=false.

## Non-goals

- approving all direct-code candidates;
- marking geometry as validated without geometry checks;
- writing runtime features;
- activating runtime sets;
- enabling Android lookup;
- automatic farmer geography overwrite.

## Recommended next implementation

Implement a pilot selection dry-run report first.

The report should list 10 to 25 candidate ids from DIRECT_VLCODE_MATCH with:

- candidate id;
- source feature index;
- district/subdistrict/village;
- source vlcode;
- proposed village lgd code;
- proposed village id;
- geometry hash;
- transformed bbox/centroid;
- current review status;
- current geometry validation status;
- required next action.

It should remain read-only and should not update review metadata.

## Pilot planner checkpoint

Status date: 2026-08-24

Planner added:

- `backend/scripts/plan_nwdp_boundary_pilot_promotion_review.py`

Regression added:

- `backend/scripts/test_nwdp_boundary_pilot_promotion_review_plan.py`
- included in `backend/scripts/run_nwdp_boundary_regressions.py`

Latest observed planner result:

- schema_version: nwdp_boundary_pilot_promotion_review_plan.v1;
- mode: READ_ONLY_PILOT_SELECTION;
- selected_candidate_count: 10;
- candidate_bucket: DIRECT_VLCODE_MATCH;
- db_writes_attempted: false;
- runtime_tables_written: false;
- runtime_spatial_matching_changed: false;
- android_behavior_changed: false;
- runtime_write_allowed_now: false;
- requires_reviewer_metadata: true;
- requires_geometry_validation: true.

Important finding:

The selected direct-code pilot candidates preserve source vlcode/proposed LGD matches, but their current staged geometry fields are not promotion-ready:

- geometry_validation_status: NOT_VALIDATED;
- source_geometry_hash: null;
- transformed_bbox: empty;
- transformed_centroid: empty.

Current decision:

- reviewer approval alone is not enough for runtime promotion;
- geometry/hash materialization and validation must happen before the runtime importer can write rows;
- the runtime importer remains dry-run-first and apply-blocked.

## Pilot geometry materialization checkpoint

Status date: 2026-08-24

Planner added:

- `backend/scripts/plan_nwdp_boundary_pilot_geometry_materialization.py`

Regression added:

- `backend/scripts/test_nwdp_boundary_pilot_geometry_materialization_plan.py`
- included in `backend/scripts/run_nwdp_boundary_regressions.py`

Latest observed planner result:

- schema_version: nwdp_boundary_pilot_geometry_materialization_plan.v1;
- mode: READ_ONLY_GEOMETRY_MATERIALIZATION_PLAN;
- selected_candidate_count: 10;
- geometry_payload_available_count: 10;
- transformed bbox health: true for sampled rows;
- db_writes_attempted: false;
- staging_rows_to_update_now: 0;
- runtime_tables_written: false;
- runtime_rows_to_write_now: 0;
- runtime_spatial_matching_changed: false;
- android_behavior_changed: false.

Important finding:

The original NWDP/GSI SHP zip is locally available and can provide geometry payloads for the selected pilot rows. The planner can derive materialized source geometry hashes and transformed bboxes, while current staging rows still have:

- source_geometry_hash: null;
- transformed_bbox: empty;
- transformed_centroid: empty;
- geometry_validation_status: NOT_VALIDATED.

Current decision:

- geometry materialization is feasible for the pilot subset;
- materialization remains read-only at this checkpoint;
- the next step should be a guarded staging geometry materialization apply script that writes only source feature hash/bbox/centroid/validation metadata for selected inactive staging rows;
- runtime tables must remain empty until a later runtime promotion apply checkpoint.

## Pilot geometry materialization applied checkpoint

Status date: 2026-08-24.

The guarded pilot geometry materializer has now been applied for the selected 10 DIRECT_VLCODE_MATCH pilot source features only.

Observed result:

- script: `backend/scripts/materialize_nwdp_boundary_pilot_geometry.py`;
- regression: `backend/scripts/test_nwdp_boundary_pilot_geometry_materializer.py`;
- selected_candidate_count: 10;
- planned_staging_geometry_update_count: 10;
- staging_rows_updated: 10;
- validated_geometry_count: 10;
- runtime_write_count: 0;
- runtime_tables_written: false;
- runtime_rows_effective: 0;
- runtime_spatial_matching_changed: false.

Local verification confirmed:

- pilot_count: 10;
- hash_count: 10;
- bbox_count: 10;
- centroid_count: 10;
- validated_count: 10;
- runtime table counts remain 0 for runtime sets, features, crosswalks, and promotion events.

Guardrails preserved:

- no runtime rows were loaded;
- no runtime table was written;
- no candidate was activated;
- no candidate was promoted;
- no runtime lookup API was enabled;
- Android behavior remains unchanged.

Current decision:

The tiny pilot now has staging geometry hash, transformed bbox, transformed centroid, and VALIDATED geometry status. The next implementation should be a guarded reviewer-metadata approval checkpoint for these same 10 direct-code candidates, still without runtime rows or lookup behavior.

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

## Pilot reviewer metadata checkpoint

Status date: 2026-08-24.

The guarded pilot reviewer-metadata checkpoint has been applied for the same 10 DIRECT_VLCODE_MATCH pilot candidates that already had materialized staging geometry.

Observed reviewer metadata result:

- script: `backend/scripts/review_nwdp_boundary_pilot_candidates.py`;
- regression: `backend/scripts/test_nwdp_boundary_pilot_reviewer_metadata.py`;
- selected_candidate_count: 10;
- staging_review_rows_updated: 10;
- planned_review_status: APPROVED_FOR_PROMOTION;
- planned_reviewer_decision: ACCEPT_DIRECT_CODE_MATCH;
- runtime_write_count: 0;
- runtime_tables_written: false;
- runtime_rows_effective: 0;
- runtime_spatial_matching_changed: false;
- android_behavior_changed: false.

Observed runtime promotion dry-run after reviewer metadata:

- schema_version: nwdp_boundary_runtime_promotion_importer.v1;
- healthy: true;
- db_writes_attempted: false;
- runtime_tables_written: false;
- runtime_rows_effective: 0;
- candidate_count: 29,789;
- promotable_candidate_count: 10;
- excluded_candidate_count: 29,779;
- eligibility_counts:
  - NOT_REVIEW_APPROVED: 29,779;
  - PROMOTABLE: 10;
- planned_runtime_set_insert_count: 1;
- planned_runtime_feature_insert_count: 10;
- planned_runtime_crosswalk_insert_count: 10;
- ready_for_runtime_table_write: false;
- ready_for_runtime_spatial_matching: false.

Guardrails preserved:

- pilot candidates remain inactive;
- pilot candidates remain NOT_PROMOTED;
- no runtime rows were loaded;
- runtime table counts remain zero;
- no runtime lookup API was enabled;
- Android behavior remains unchanged.

Current decision:

The pilot now demonstrates that reviewer metadata plus materialized geometry produces exactly 10 promotable candidates in dry-run. The runtime importer remains dry-run-first and still blocks runtime table writes. A future runtime apply checkpoint must be explicit, separately reviewed, and followed by verification before any lookup API is introduced.

## Runtime apply design checkpoint

Status date: 2026-08-24.

Current runtime importer state:

- `backend/scripts/promote_nwdp_boundary_runtime.py` remains dry-run-first;
- `--apply` is blocked by design;
- blocked apply error: `APPLY_BLOCKED_PENDING_REVIEWED_RUNTIME_PROMOTION_POLICY`;
- `ready_for_runtime_table_write` remains false;
- `ready_for_runtime_spatial_matching` remains false;
- runtime table counts remain zero.

The future runtime apply implementation should be a separate checkpoint and should keep these design constraints:

1. only eligible PROMOTABLE rows may be written;
2. the tiny pilot must write exactly:
   - 1 inactive runtime set;
   - 10 inactive runtime features;
   - 10 inactive runtime crosswalks;
   - 1 promotion event;
3. staging candidates must remain inactive;
4. staging candidates must remain NOT_PROMOTED until a separate activation/supersession policy exists;
5. runtime set activation must remain false/inactive at initial write;
6. lookup APIs must remain absent;
7. Android behavior must remain unchanged;
8. post-apply verification must prove runtime row counts and candidate guardrails before any lookup work starts.

Current decision:

Do not remove the apply block in-place as a small edit. The next implementation should add an explicit runtime apply policy gate and regression around the tiny pilot write shape before any runtime lookup endpoint is introduced.

## Tiny pilot runtime apply checkpoint

Status date: 2026-08-24.

The runtime importer now supports an explicit tiny-pilot policy gate:

- script: `backend/scripts/promote_nwdp_boundary_runtime.py`;
- policy flag: `--allow-tiny-pilot-runtime-write`;
- regression: `backend/scripts/test_nwdp_boundary_runtime_tiny_pilot_apply.py`;
- runner: `backend/scripts/run_nwdp_boundary_regressions.py`.

Observed applied runtime row shape:

- geography_boundary_runtime_sets: 1;
- geography_boundary_runtime_features: 10;
- geography_boundary_runtime_crosswalks: 10;
- geography_boundary_runtime_promotion_events: 1.

Observed inactive guardrails:

- runtime active counts are zero for sets, features, crosswalks, and promotion events;
- runtime set status: `PILOT_IMPORTED_INACTIVE`;
- runtime set activation_status: `INACTIVE`;
- promotion event mode: `TINY_PILOT_REVIEWED_BATCH`;
- promotion event status: `APPLIED`;
- promotion event is_active: false;
- candidate_count: 10;
- runtime_feature_count: 10;
- runtime_crosswalk_count: 10.

Observed staging guardrails:

- pilot staging candidates remain inactive: 10/10;
- pilot staging candidates remain NOT_PROMOTED: 10/10;
- pilot staging candidates remain APPROVED_FOR_PROMOTION: 10/10;
- pilot staging candidates retain ACCEPT_DIRECT_CODE_MATCH: 10/10.

Repeat apply guard:

- repeat apply exits non-zero;
- repeat apply error: `RUNTIME_TABLES_NOT_EMPTY_TINY_PILOT_APPLY_REQUIRES_EMPTY_RUNTIME_TABLES`;
- repeat apply reports `db_writes_attempted = false`;
- repeat apply reports `runtime_rows_effective = 0`;
- existing runtime counts remain 1/10/10/1.

Current decision:

The tiny pilot runtime rows exist only as inactive runtime materialization. Runtime spatial matching is still not ready, no runtime lookup API is enabled, and Android behavior remains unchanged. The next checkpoint should verify read-only inspection/reporting for inactive runtime rows before any activation or lookup work is considered.

## Runtime pilot inspection checkpoint — 2026-08-24

After the tiny pilot inactive runtime write, a read-only inspection checkpoint was added and verified.

Inspection artifacts:

- `backend/scripts/inspect_nwdp_boundary_runtime_pilot.py`
- `backend/scripts/test_nwdp_boundary_runtime_pilot_inspection.py`
- `backend/scripts/run_nwdp_boundary_regressions.py`

Observed runtime shape:

- runtime sets: 1
- runtime features: 10
- runtime crosswalks: 10
- runtime promotion events: 1
- active runtime rows: 0 across all runtime tables

Observed guardrails:

- runtime set status remains `PILOT_IMPORTED_INACTIVE`
- runtime set `activation_status` remains `INACTIVE`
- runtime set `is_active=false`
- promotion event mode is `TINY_PILOT_REVIEWED_BATCH`
- promotion event status is `APPLIED`
- promotion event `is_active=false`
- linked staging candidates remain inactive
- linked staging candidates remain `promotion_status=NOT_PROMOTED`
- linked staging candidates remain reviewer-approved only, not activated

Readiness remains intentionally constrained:

- `runtime_rows_available_for_review=true`
- `runtime_rows_active=false`
- `lookup_api_enabled=false`
- `ready_for_runtime_spatial_matching=false`
- `android_behavior_changed=false`

Decision: inactive runtime rows are now inspectable for review, but they are not eligible for runtime lookup, Android behavior, or spatial matching until a separate activation policy and verification checkpoint is approved.

## Admin runtime pilot inspection endpoint checkpoint — 2026-08-24

An admin-view-only API endpoint now exposes the inactive runtime pilot rows for inspection:

- `GET /api/v1/master-data/geography/boundary-runtime-pilot/inspection?limit=10`
- response schema: `nwdp_boundary_runtime_pilot_inspection.v1`
- mode: `READ_ONLY_RUNTIME_PILOT_INSPECTION`
- permission: admin view permission
- source: inactive runtime tables only

Verified guardrails:

- `db_writes_attempted=false`
- `runtime_tables_written=false`
- `runtime_spatial_matching_changed=false`
- `android_behavior_changed=false`
- runtime row shape remains 1 runtime set, 10 runtime features, 10 runtime crosswalks, and 1 promotion event
- all runtime active counts remain zero
- staging candidates remain inactive and `promotion_status=NOT_PROMOTED`
- `lookup_api_enabled=false`
- `ready_for_runtime_spatial_matching=false`

Regression coverage:

- `backend/scripts/test_nwdp_boundary_admin_read_endpoints.py`
- `backend/scripts/run_nwdp_boundary_regressions.py`

Decision: the endpoint is review/inspection-only. It does not represent runtime activation, does not expose public lookup behavior, and must not be consumed by Android or spatial matching until a separate activation checkpoint is designed, reviewed, applied, and verified.


## Runtime activation readiness policy checkpoint — 2026-08-24

This checkpoint defines the required policy gates before any inactive runtime boundary rows can become active or reachable by lookup behavior.

Activation is not implemented by this checkpoint.

Required pre-activation gates:

- runtime pilot inspection endpoint must remain healthy;
- runtime row shape must remain exactly 1 runtime set, 10 runtime features, 10 runtime crosswalks, and 1 promotion event for the tiny pilot;
- all runtime rows must still be inactive before activation starts;
- linked staging candidates must still be inactive;
- linked staging candidates must still be `promotion_status=NOT_PROMOTED`;
- linked staging candidates must still be `APPROVED_FOR_PROMOTION`;
- linked staging candidates must still have `ACCEPT_DIRECT_CODE_MATCH`;
- runtime features must retain `VALIDATED` geometry status;
- runtime features must retain geometry hash, bbox, and centroid metadata;
- repeat runtime apply must remain blocked against non-empty runtime tables;
- Android behavior must remain unchanged before activation;
- public lookup API must remain absent before activation.

Required activation shape, if a later checkpoint approves it:

- activate exactly one runtime set;
- activate exactly 10 runtime features;
- activate exactly 10 runtime crosswalks;
- keep the promotion event as immutable audit evidence;
- mark activation timestamp and actor on the runtime set;
- do not mutate source feature geometry;
- do not mutate staged candidate geometry;
- do not create/delete staged candidates;
- do not change Android behavior in the same checkpoint.

Required post-activation verification:

- exactly one runtime set has `is_active=true`;
- active runtime set has `activation_status=ACTIVE`;
- exactly 10 runtime features have `is_active=true`;
- exactly 10 runtime crosswalks have `is_active=true`;
- no additional runtime rows are created;
- no staging candidate is deleted;
- no unrelated candidate is activated;
- no unrelated candidate is promoted;
- public lookup remains disabled unless separately introduced;
- Android behavior remains unchanged unless separately introduced.

Rollback requirement:

A rollback/supersession design must exist before activation is applied. At minimum it must define how to return the runtime set, features, and crosswalks to inactive or superseded state without deleting audit rows.

Current decision:

The next implementation should not activate runtime rows yet. The next safe implementation checkpoint is an activation dry-run/planner that reports the exact activation diff and rollback plan while keeping all runtime rows inactive.

## Runtime activation planner checkpoint — 2026-08-24

A read-only activation planner now reports the exact tiny-pilot activation diff without applying any writes.

Artifacts:

- `backend/scripts/plan_nwdp_boundary_runtime_activation.py`
- `backend/scripts/test_nwdp_boundary_runtime_activation_plan.py`
- `backend/scripts/run_nwdp_boundary_regressions.py`

Observed planner result:

- schema_version: `nwdp_boundary_runtime_activation_plan.v1`
- mode: `READ_ONLY_ACTIVATION_DRY_RUN`
- healthy: true
- activation_applied: false
- db_writes_attempted: false
- runtime_tables_written: false
- runtime_spatial_matching_changed: false
- android_behavior_changed: false
- lookup_api_enabled: false

Observed preconditions:

- runtime row shape matches tiny pilot: true
- runtime rows all inactive: true
- single inactive runtime set: true
- runtime features validated: true
- runtime crosswalks link valid staging rows: true
- promotion event audit shape valid: true

Planned activation diff only:

- runtime sets to activate: 1
- runtime features to activate: 10
- runtime crosswalks to activate: 10
- promotion events to activate: 0
- staging candidates to activate: 0
- staging candidates to promote: 0
- lookup API enabled: false
- Android behavior changed: false

Rollback requirement:

The planner explicitly keeps rollback policy as required before apply. The minimum rollback shape must preserve audit rows, avoid deleting runtime rows, and avoid mutating source features or staged candidates.

Current decision:

The system is ready for a separately reviewed activation apply checkpoint, but activation has not been implemented or applied. Runtime spatial matching, lookup API behavior, and Android behavior remain disabled.

## All-state NWDP boundary acquisition manifest checkpoint — 2026-08-24

A read-only all-state NWDP village boundary acquisition plan was created from the National Water Data Portal resource audit.

Observed source inventory:

- state/UT count: 36
- GeoJSON resources: 36
- KML resources: 36
- SHP resources: 36
- GeoJSON coverage is complete for all states/UTs
- SHP has known source issues:
  - Uttarakhand SHP missing from the expected state/format matrix
  - Telangana SHP appears duplicated

Decision:

Use GeoJSON as the all-state acquisition format for the next checkpoint. SHP remains useful for audit/comparison only, because the SHP state/format matrix is not clean.

Manifest artifact:

- `data/staged/nwdp_boundary_all_state/20260824T105417Z/geojson_acquisition_manifest.json`

Guardrails preserved:

- downloads_attempted=false
- db_writes_attempted=false
- runtime_tables_written=false
- runtime_spatial_matching_changed=false
- android_behavior_changed=false
- activation_allowed=false
- lookup_api_enabled=false

Next checkpoint:

Download the 36 GeoJSON resources into a local raw cache with checksums, then audit feature count, properties, coordinate sanity, geometry types, bbox, and duplicate source village codes before producing all-state staging candidate CSVs.

## All-state NWDP boundary match plan checkpoint — 2026-08-24

A read-only all-state match/non-match plan was generated from the downloaded NWDP/GSI GeoJSON raw cache.

Artifacts:

- raw cache manifest: `data/staged/nwdp_boundary_all_state/20260824T110250Z/geojson_raw_cache_manifest.json`
- committed summary artifact: `data/staged/nwdp_boundary_all_state/20260824T110250Z/all_state_match_plan_summary.json`
- large local artifacts not committed:
  - `/tmp/nwdp-boundary-all-state-match-plan.json`
  - `/tmp/nwdp-boundary-all-state-match-plan.csv`

Observed all-state plan:

- state/UT count: 36
- source feature count: 654,285
- planned candidate count: 654,285
- `DIRECT_VLCODE_MATCH`: 313,667
- `DIRECT_VLCODE_PARENT_MISMATCH`: 157,381
- `MANUAL_REVIEW`: 263,324
- `BLOCKED`: 77,294
- `AUTO_CANDIDATE`: 313,667

Guardrails preserved:

- `db_writes_attempted=false`
- `runtime_tables_written=false`
- `runtime_spatial_matching_changed=false`
- `android_behavior_changed=false`
- `lookup_api_enabled=false`

Decision:

All-state inactive staging import is feasible, but it must be designed as a guarded, idempotent, state-by-state import. The all-state match plan must not be imported directly to runtime, and parent-mismatch/manual/blocked buckets must remain review-only until separate review and promotion checkpoints exist.

## All-state inactive staging import planner checkpoint — 2026-08-25

A reusable read-only planner and regression now verify the all-state inactive staging import shape.

Artifacts:

- `backend/scripts/plan_nwdp_boundary_all_state_inactive_staging_import.py`
- `backend/scripts/test_nwdp_boundary_all_state_inactive_staging_import_plan.py`
- `backend/scripts/run_nwdp_boundary_regressions.py`

Observed planner result:

- schema version: `nwdp_boundary_all_state_inactive_staging_import_plan.v1`
- mode: `READ_ONLY_INACTIVE_STAGING_IMPORT_PLAN`
- healthy: true
- planned import batches: 36
- planned inactive source feature inserts: 654,285
- planned inactive candidate inserts: 654,285
- planned active source features: 0
- planned active candidates: 0
- planned runtime writes: 0

Observed all-state bucket plan:

- `DIRECT_VLCODE_MATCH`: 313,667
- `DIRECT_VLCODE_PARENT_MISMATCH`: 157,381
- `PARENT_MATCH_VILLAGE_UNRESOLVED`: 70,456
- `DISTRICT_SCOPED_AMBIGUOUS`: 23,423
- `SPECIAL_REFERENCE_FEATURE`: 5,885
- `PARENT_SCOPED_NAME_MATCH`: 5,255
- `PARENT_SCOPED_NAME_AMBIGUOUS`: 513
- `DISTRICT_ONLY_UNRESOLVED`: 411
- `BLOCKED_SOURCE_CAVEAT`: 77,294

Observed review status plan:

- `AUTO_CANDIDATE`: 313,667
- `MANUAL_REVIEW`: 263,324
- `BLOCKED`: 77,294

Guardrails verified:

- `db_writes_attempted=false`
- `runtime_tables_written=false`
- `runtime_spatial_matching_changed=false`
- `android_behavior_changed=false`
- `lookup_api_enabled=false`
- apply remains unimplemented
- inactive staging apply requires a separate checkpoint

Regression coverage:

- focused planner regression passed
- full `backend/scripts/run_nwdp_boundary_regressions.py` passed

Decision:

The all-state inactive staging import design is now reusable and regression-guarded. The next implementation checkpoint may add a guarded inactive staging apply path, but it must write only inactive staging import batches, source features, and candidates. Runtime tables, lookup behavior, Android behavior, candidate activation, and candidate promotion must remain disabled.

## All-state inactive staging import planner checkpoint — 2026-08-25

A reusable read-only planner and regression now verify the all-state inactive staging import shape.

Artifacts:

- `backend/scripts/plan_nwdp_boundary_all_state_inactive_staging_import.py`
- `backend/scripts/test_nwdp_boundary_all_state_inactive_staging_import_plan.py`
- `backend/scripts/run_nwdp_boundary_regressions.py`

Observed planner result:

- schema version: `nwdp_boundary_all_state_inactive_staging_import_plan.v1`
- mode: `READ_ONLY_INACTIVE_STAGING_IMPORT_PLAN`
- healthy: true
- planned import batches: 36
- planned inactive source feature inserts: 654,285
- planned inactive candidate inserts: 654,285
- planned active source features: 0
- planned active candidates: 0
- planned runtime writes: 0

Observed all-state bucket plan:

- `DIRECT_VLCODE_MATCH`: 313,667
- `DIRECT_VLCODE_PARENT_MISMATCH`: 157,381
- `PARENT_MATCH_VILLAGE_UNRESOLVED`: 70,456
- `DISTRICT_SCOPED_AMBIGUOUS`: 23,423
- `SPECIAL_REFERENCE_FEATURE`: 5,885
- `PARENT_SCOPED_NAME_MATCH`: 5,255
- `PARENT_SCOPED_NAME_AMBIGUOUS`: 513
- `DISTRICT_ONLY_UNRESOLVED`: 411
- `BLOCKED_SOURCE_CAVEAT`: 77,294

Observed review status plan:

- `AUTO_CANDIDATE`: 313,667
- `MANUAL_REVIEW`: 263,324
- `BLOCKED`: 77,294

Guardrails verified:

- `db_writes_attempted=false`
- `runtime_tables_written=false`
- `runtime_spatial_matching_changed=false`
- `android_behavior_changed=false`
- `lookup_api_enabled=false`
- apply remains unimplemented
- inactive staging apply requires a separate checkpoint

Regression coverage:

- focused planner regression passed
- full `backend/scripts/run_nwdp_boundary_regressions.py` passed

Decision:

The all-state inactive staging import design is now reusable and regression-guarded. The next implementation checkpoint may add a guarded inactive staging apply path, but it must write only inactive staging import batches, source features, and candidates. Runtime tables, lookup behavior, Android behavior, candidate activation, and candidate promotion must remain disabled.

## All-state inactive staging importer gate checkpoint — 2026-08-25

A guarded all-state inactive staging importer checkpoint was added.

Artifacts:

- `backend/scripts/import_nwdp_boundary_all_state_inactive_staging.py`
- `backend/scripts/test_nwdp_boundary_all_state_inactive_staging_importer.py`
- `backend/scripts/run_nwdp_boundary_regressions.py`

Observed dry-run result:

- schema version: `nwdp_boundary_all_state_inactive_staging_importer.v1`
- healthy: true
- state/UT scope: `ALL_STATES`
- source format: `GeoJSON`
- planned batches: 36
- planned source feature rows: 654,285
- planned candidate rows: 654,285
- unsafe counts: empty
- active source features planned: 0
- active candidates planned: 0
- runtime writes planned: 0

Observed apply gate:

- `--apply --allow-all-state-inactive-staging-write` exits non-zero
- error: `ALL_STATE_INACTIVE_STAGING_APPLY_NOT_IMPLEMENTED_REQUIRES_SEPARATE_CHECKPOINT`
- `db_writes_attempted=false`
- `runtime_tables_written=false`

Guardrails verified:

- no DB writes
- no runtime table writes
- no runtime spatial matching changes
- no Android behavior changes
- no lookup API enabled
- no candidate activation
- no candidate promotion

Decision:

The all-state importer is now safely gated and regression-covered, but inactive staging apply remains intentionally unimplemented. The next checkpoint may implement state-by-state inactive staging writes behind the explicit all-state policy flag, followed immediately by post-apply verification.

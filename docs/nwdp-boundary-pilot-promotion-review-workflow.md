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

## Chandigarh inactive staging apply checkpoint — 2026-08-25

The first state-scoped all-state inactive staging apply checkpoint was completed for Chandigarh.

Artifacts:

- `backend/scripts/import_nwdp_boundary_all_state_inactive_staging.py`
- `backend/scripts/test_nwdp_boundary_all_state_chandigarh_inactive_staging_apply.py`
- `backend/scripts/test_nwdp_boundary_all_state_inactive_staging_importer.py`
- `backend/scripts/run_nwdp_boundary_regressions.py`

Observed apply result:

- state/UT: `Chandigarh`
- apply mode: true
- policy flag: `--allow-all-state-inactive-staging-write`
- state scope required: true
- healthy: true
- DB writes attempted: true
- inactive import batches: 1
- inactive source features: 13
- inactive candidates: 13
- active source features: 0
- active candidates: 0
- promoted candidates: 0

Observed repeat apply/idempotency:

- repeat apply exits zero
- existing source features: 13
- existing candidates: 13
- inserted source features: 0
- inserted candidates: 0
- post counts remain 1 batch, 13 source features, and 13 candidates
- active/promoted counts remain zero

Guardrails preserved:

- runtime tables written: false
- runtime spatial matching changed: false
- Android behavior changed: false
- lookup API enabled: false
- candidate activation changed: false
- candidate promotion changed: false

Regression coverage:

- all-state importer gate regression passed
- Chandigarh inactive staging apply regression passed
- full `backend/scripts/run_nwdp_boundary_regressions.py` passed

Decision:

State-scoped inactive staging apply is now proven on the smallest all-state source, Chandigarh. The next rollout should continue state-by-state, preferably from smallest to largest, verifying idempotency and inactive guardrails after each state. Runtime promotion, runtime lookup, spatial matching, Android behavior, and candidate promotion remain out of scope.

## Small-state inactive staging rollout checkpoint — 2026-08-25

A state-scoped inactive staging rollout was completed for the smallest all-state GeoJSON NWDP sources.

States/UTs staged:

- Chandigarh: 13
- Lakshadweep: 34
- Dadra and Nagar Haveli and Daman & Diu: 101
- Puducherry: 101
- Ladakh: 250
- Delhi: 254
- Goa: 412
- Sikkim: 484
- Andaman and Nicobar Islands: 669

Observed verified aggregate:

- staged states/UTs: 9
- inactive source features: 2,318
- inactive candidates: 2,318
- active source features: 0
- active candidates: 0
- promoted candidates: 0

Guardrails preserved:

- runtime tables written: false
- runtime spatial matching changed: false
- Android behavior changed: false
- lookup API enabled: false
- candidate activation changed: false
- candidate promotion changed: false

Decision:

The all-state inactive staging importer has now been proven beyond Chandigarh across the smallest state/UT band. Continue rollout state-by-state in increasing size/risk bands, verifying idempotency and inactive guardrails after each band. Runtime promotion, lookup behavior, spatial matching, Android behavior, candidate activation, and candidate promotion remain out of scope.

## Mid-small inactive staging rollout checkpoint — 2026-08-25

The next state-scoped inactive staging rollout band was completed and verified.

Additional states/UTs staged in this band:

- Mizoram: 881
- Tripura: 917
- Kerala: 1,556
- Nagaland: 1,564
- Manipur: 2,674
- Arunachal Pradesh: 5,803
- Jammu & Kashmir: 6,593
- Meghalaya: 6,897
- Haryana: 7,010

Observed verified cumulative aggregate:

- staged states/UTs: 18
- inactive source features: 36,213
- inactive candidates: 36,213
- active source features: 0
- active candidates: 0
- promoted candidates: 0

Guardrails preserved:

- runtime tables written: false
- runtime spatial matching changed: false
- Android behavior changed: false
- lookup API enabled: false
- candidate activation changed: false
- candidate promotion changed: false

Decision:

The inactive staging rollout has now covered 18 states/UTs with no active candidates, no promoted candidates, and no runtime table writes. Continue rollout in state-scoped bands. Runtime promotion, lookup behavior, spatial matching, Android behavior, candidate activation, and candidate promotion remain out of scope until separately reviewed checkpoints.

## Moderate-state inactive staging rollout checkpoint — 2026-08-25

The next state-scoped inactive staging rollout band was completed and verified.

Additional states staged in this band:

- Telangana: 10,718
- Punjab: 12,860
- Uttarakhand: 16,920
- Tamil Nadu: 17,119
- Andhra Pradesh: 18,100
- Gujarat: 18,838

Observed verified aggregate excluding the earlier Karnataka pilot:

- staged rollout states/UTs: 24
- inactive source features: 130,768
- inactive candidates: 130,768
- active source features: 0
- active candidates: 0
- promoted candidates: 0

Observed verified aggregate including the earlier Karnataka pilot:

- NWDP staging states/UTs: 25
- inactive source features: 160,557
- inactive candidates: 160,557
- active source features: 0
- active candidates: 0
- promoted candidates: 0

Guardrails preserved:

- runtime tables written: false
- runtime spatial matching changed: false
- Android behavior changed: false
- lookup API enabled: false
- candidate activation changed: false
- candidate promotion changed: false

Decision:

The inactive staging rollout has now covered 24 all-state rollout states/UTs, plus the earlier Karnataka pilot. Continue in state-scoped bands. Runtime promotion, lookup behavior, spatial matching, Android behavior, candidate activation, and candidate promotion remain out of scope until separately reviewed checkpoints.

## Large-small inactive staging rollout checkpoint — 2026-08-25

The next state-scoped inactive staging rollout band was completed and verified.

Additional states staged in this band:

- Himachal Pradesh: 20,773
- Chhattisgarh: 20,811
- Assam: 26,662

Observed verified aggregate excluding the earlier Karnataka pilot:

- staged rollout states/UTs: 27
- inactive source features: 199,014
- inactive candidates: 199,014
- active source features: 0
- active candidates: 0
- promoted candidates: 0

Observed verified aggregate including the earlier Karnataka pilot:

- NWDP staging states/UTs: 28
- inactive source features: 228,803
- inactive candidates: 228,803
- active source features: 0
- active candidates: 0
- promoted candidates: 0

Guardrails preserved:

- runtime tables written: false
- runtime spatial matching changed: false
- Android behavior changed: false
- lookup API enabled: false
- candidate activation changed: false
- candidate promotion changed: false

Decision:

The inactive staging rollout has now covered 27 all-state rollout states/UTs, plus the earlier Karnataka pilot. Continue state-scoped rollout for the remaining high-volume states. Runtime promotion, lookup behavior, spatial matching, Android behavior, candidate activation, and candidate promotion remain out of scope until separately reviewed checkpoints.

## Final-heavy inactive staging rollout checkpoint — 2026-08-26

The final high-volume state-scoped inactive staging rollout band was completed and verified.

Additional states staged in this band:

- Odisha: 53,320
- Madhya Pradesh: 55,937
- Uttar Pradesh: 107,816

Observed verified final aggregate:

- NWDP staging states/UTs: 36
- inactive source features: 654,285
- inactive candidates: 654,285
- active source features: 0
- active candidates: 0
- promoted candidates: 0

Guardrails preserved:

- runtime tables written: false
- runtime spatial matching changed: false
- Android behavior changed: false
- lookup API enabled: false
- candidate activation changed: false
- candidate promotion changed: false

Decision:

All 36 NWDP/GSI all-state village-boundary sources are now loaded into inactive staging. This completes the geography staging coverage checkpoint only. Runtime promotion, lookup behavior, point-in-polygon spatial matching, Android behavior, candidate activation, and candidate promotion remain out of scope until separately reviewed and applied checkpoints.

## Project matching eligible candidates endpoint checkpoint — 2026-08-26

A read-only admin/project matching candidate endpoint is now available for future project matching review workflows.

Endpoint:

- `GET /api/v1/master-data/geography/nwdp-boundary-project-matching/eligible-candidates`

Required scope:

- `state_or_ut`, or
- `village_id`

The endpoint intentionally rejects unbounded requests.

Eligible candidate predicate:

- `candidate_bucket = DIRECT_VLCODE_MATCH`
- `review_status = AUTO_CANDIDATE`
- `is_active = false`
- `promotion_status = NOT_PROMOTED`
- `proposed_village_id is not null`

Excluded rows:

- manual review candidates
- blocked candidates
- parent mismatch candidates until reviewed
- special/reference-only features
- active or promoted candidates

Guardrails preserved:

- runtime tables written: false
- runtime spatial matching changed: false
- lookup API enabled: false
- Android behavior changed: false
- candidate activation changed: false
- candidate promotion changed: false

Regression coverage:

- `backend/scripts/test_nwdp_boundary_project_matching_eligible_candidates_endpoint.py`
- full `backend/scripts/run_nwdp_boundary_regressions.py`

Decision:

This endpoint creates the safe read-only bridge from inactive NWDP staging to future admin/project matching review. It does not enable application behavior or runtime point-in-polygon matching. Any apply path that uses these candidates for project matching must be separately designed, checkpointed, guarded by feature/state/project switches, and reversible without mutating manual-review or blocked rows.

## Boundary review UI project matching reuse checkpoint — 2026-08-26

The existing NWDP boundary review admin UI has been reused for all-state staged boundary review and future project matching inspection.

UI route:

- `/nwdp-boundary-review`

Reuse scope:

- keeps the existing batch and candidate review queues;
- generalizes the page copy from the earlier Karnataka pilot to all staged states/UTs;
- adds a read-only project matching panel backed by the state-wise summary and eligible-candidates endpoints;
- allows admins to inspect inactive direct-code candidates by state/UT;
- allows clicking an eligible row into the existing candidate detail/review evidence workflow.

Project matching read model shown in the UI:

- `DIRECT_VLCODE_MATCH`
- `AUTO_CANDIDATE`
- `is_active = false`
- `promotion_status = NOT_PROMOTED`
- proposed village id present

Excluded from project matching UI readiness:

- manual-review candidates
- blocked candidates
- parent mismatch candidates until reviewed
- special/reference-only features
- active or promoted candidates

Guardrails preserved:

- runtime tables written: false
- runtime spatial matching changed: false
- lookup API enabled: false
- Android behavior changed: false
- candidate activation changed: false
- candidate promotion changed: false

Regression coverage:

- `backend/scripts/test_nwdp_boundary_review_ui_project_matching_reuse.py`
- `backend/scripts/run_nwdp_boundary_regressions.py`
- `web` lint for `src/app/(admin)/nwdp-boundary-review/page.tsx`

Decision:

This is a UI/read-model reuse checkpoint only. It does not add project matching apply behavior, runtime point-in-polygon lookup, Android lookup behavior, candidate activation, or candidate promotion. Those remain separate guarded checkpoints.

## Project matching project preview positive coverage checkpoint — 2026-08-27

The read-only project matching project preview now has positive coverage regression proof.

What was verified:

- a temporary project was created for the regression;
- the temporary project was linked to one existing backend village that has an eligible NWDP direct-code boundary candidate;
- the project preview endpoint returned one covered project village;
- `eligible_candidate_count >= 1`;
- `coverage_ratio = 1.0`;
- sample candidate/source evidence was returned for admin inspection;
- temporary project/farmer/enrollment rows were cleaned up after the test.

Endpoint covered:

- `GET /api/v1/master-data/geography/nwdp-boundary-project-matching/project-preview?project_id=...`

Regression coverage:

- `backend/scripts/test_nwdp_boundary_project_matching_project_preview_positive_coverage.py`
- included in `backend/scripts/run_nwdp_boundary_regressions.py`

Guardrails preserved:

- NWDP staging candidates unchanged: 654,285
- active candidates: 0
- promoted candidates: 0
- runtime tables written: false
- runtime spatial matching changed: false
- lookup API enabled: false
- Android behavior changed: false
- candidate activation changed: false
- candidate promotion changed: false

Decision:

This checkpoint proves that project-scoped boundary coverage can be previewed with non-zero eligible coverage. It remains inspection-only. Project matching apply, runtime point-in-polygon lookup, candidate activation, candidate promotion, and Android lookup behavior remain out of scope until separately designed, reviewed, guarded, and checkpointed.

## Project matching apply dry-run plan checkpoint — 2026-08-27

The project matching apply path now has a dry-run-only plan and positive selection regression proof.

What was verified:

- the dry-run plan is project scoped;
- selected candidates are limited to inactive NWDP direct-VLCODE matches;
- selected candidates must be `AUTO_CANDIDATE`;
- selected candidates must remain `NOT_PROMOTED`;
- selected candidates must have a proposed backend village id;
- manual-review candidates are excluded;
- blocked candidates are excluded;
- non-direct buckets are excluded;
- a positive-selection fixture found one eligible candidate for one project village;
- the dry-run produced candidate evidence for admin/design review;
- the dry-run did not write project matching records.

Regression coverage:

- `backend/scripts/test_nwdp_boundary_project_matching_apply_dry_run_plan.py`
- `backend/scripts/test_nwdp_boundary_project_matching_apply_dry_run_positive_selection.py`
- included in `backend/scripts/run_nwdp_boundary_regressions.py`

Guardrails preserved:

- NWDP staging candidates unchanged: 654,285
- active candidates: 0
- promoted candidates: 0
- runtime tables written: false
- runtime spatial matching changed: false
- lookup API enabled: false
- Android behavior changed: false
- candidate activation changed: false
- candidate promotion changed: false
- project matching apply implemented: false

Required before any real apply:

- explicit admin confirmation flow;
- feature flag or equivalent project/state gate;
- rollback policy;
- write-target schema/review for project matching records;
- post-apply verification that staging, runtime, lookup, and Android guardrails remain bounded.

Decision:

This checkpoint advances the project matching flow from preview-only to dry-run apply design review. It still does not implement apply behavior, runtime point-in-polygon lookup, candidate activation, candidate promotion, lookup API enablement, or Android behavior changes. Those remain separate guarded checkpoints.

## Project matching apply design plan checkpoint — 2026-08-27

The project matching apply path now has a read-only design contract regression.

What the design plan defines:

- proposed write target: `geography_boundary_project_matches`;
- project-scoped linkage from a project village to one reviewed NWDP boundary candidate;
- required rollback token for future apply rows;
- one active NWDP boundary project match per `project_id + village_id + source_system`;
- candidate selection limited to inactive direct-VLCODE NWDP candidates;
- selected candidates must be `AUTO_CANDIDATE`;
- selected candidates must remain `NOT_PROMOTED`;
- manual-review candidates are excluded;
- blocked candidates are excluded;
- non-direct buckets are excluded.

Required apply gates:

- feature flag or equivalent project/state gate;
- explicit admin confirmation;
- project scope;
- dry-run immediately before apply;
- rollback token;
- post-apply verification.

Rollback policy:

- rollback unit: rollback token;
- rollback action: deactivate project match rows created by the apply token;
- rollback must not delete staging candidates;
- rollback must not mutate runtime tables;
- rollback must not change Android behavior;
- rollback must not promote candidates.

Regression coverage:

- `backend/scripts/test_nwdp_boundary_project_matching_apply_design_plan.py`
- included in `backend/scripts/run_nwdp_boundary_regressions.py`

Guardrails preserved:

- DB writes attempted: false
- project matching records written: false
- candidate activation changed: false
- candidate promotion changed: false
- runtime tables written: false
- runtime spatial matching changed: false
- lookup API enabled: false
- Android behavior changed: false

Decision:

This checkpoint records the apply design contract only. It does not create the write-target table, implement project matching apply, activate candidates, promote candidates, write runtime tables, enable lookup APIs, or change Android behavior. Those remain separate guarded checkpoints.

## Project match schema checkpoint — 2026-08-27

The future project matching apply path now has an explicit schema write target.

Migration added:

- `backend/alembic/versions/056_add_nwdp_boundary_project_matches.py`

Proposed table:

- `geography_boundary_project_matches`

Purpose:

- records a project-scoped linkage from one project village to one reviewed NWDP boundary candidate;
- provides an explicit rollback unit for future apply rows;
- keeps project matching separate from runtime spatial matching tables.

Key fields:

- `tenant_id`
- `project_id`
- `village_id`
- `boundary_candidate_id`
- `source_system`
- `match_source`
- `match_status`
- `applied_by`
- `applied_at`
- `rolled_back_by`
- `rolled_back_at`
- `rollback_token`
- `dry_run_report`
- `apply_report`
- `rollback_report`
- `metadata`
- audit columns

Constraints and indexes:

- foreign key to `tenants`;
- foreign key to `projects`;
- foreign key to `geography_villages`;
- foreign key to `geography_boundary_crosswalk_candidates`;
- `match_status` constrained to `PLANNED`, `APPLIED`, `ROLLED_BACK`, or `FAILED`;
- active rows must have `match_status = APPLIED`;
- partial unique index allows only one active project match per `project_id + village_id + source_system`.

Regression coverage:

- `backend/scripts/test_nwdp_boundary_project_match_schema_migration.py`
- included in `backend/scripts/run_nwdp_boundary_regressions.py`

Guardrails preserved:

- project matching apply implemented: false
- candidate activation changed: false
- candidate promotion changed: false
- runtime tables mutated: false
- lookup API enabled: false
- Android behavior changed: false

Decision:

This checkpoint creates the schema contract for future project matching apply, but does not apply project matches. Runtime spatial matching, candidate activation, candidate promotion, lookup behavior, and Android behavior remain separate guarded checkpoints.

## Project match schema local DB validation checkpoint — 2026-08-27

The project match schema migration was applied and validated against the local development database.

Migration applied:

- Alembic upgrade `055 -> 056`
- migration: `backend/alembic/versions/056_add_nwdp_boundary_project_matches.py`

Validated table:

- `geography_boundary_project_matches`

Observed local DB validation:

- table exists: true
- column count: 21
- project match rows: 0
- expected indexes present:
  - `idx_geography_boundary_project_matches_candidate`
  - `idx_geography_boundary_project_matches_project`
  - `idx_geography_boundary_project_matches_rollback`
  - `idx_geography_boundary_project_matches_village`
  - `uq_geography_boundary_project_matches_one_active`
- expected constraints present:
  - primary key
  - tenant foreign key
  - project foreign key
  - village foreign key
  - boundary candidate foreign key
  - match status check
  - active status check

NWDP staging guardrail verification:

- candidates: 654,285
- active candidates: 0
- promoted candidates: 0

Guardrails preserved:

- project matching rows created: false
- candidate activation changed: false
- candidate promotion changed: false
- runtime tables changed: false
- lookup API enabled: false
- Android behavior changed: false

Decision:

The write-target schema is now validated locally. This remains a schema checkpoint only. Project matching apply, rollback execution, runtime lookup, candidate activation, candidate promotion, lookup API enablement, and Android behavior changes remain separate guarded checkpoints.

## Project matching disabled apply contract endpoint checkpoint — 2026-08-27

The project matching apply route now exists as a disabled contract endpoint.

Endpoint:

- `POST /api/v1/master-data/geography/nwdp-boundary-project-matching/apply`

Current behavior:

- requires admin edit permission;
- requires a valid project id;
- reports supplied future apply gates;
- always returns `501 PROJECT_MATCHING_APPLY_NOT_IMPLEMENTED`;
- does not create project matching rows;
- does not activate candidates;
- does not promote candidates;
- does not write runtime tables;
- does not enable lookup behavior;
- does not change Android behavior.

Future apply gates surfaced by the endpoint:

- feature flag enabled;
- dry-run confirmed;
- admin confirmation;
- rollback token present.

Candidate selection contract preserved:

- source system: `NWDP_GSI_VILLAGE_BOUNDARY`;
- candidate bucket: `DIRECT_VLCODE_MATCH`;
- review status: `AUTO_CANDIDATE`;
- candidate `is_active = false`;
- candidate `promotion_status = NOT_PROMOTED`;
- proposed village id required;
- manual-review candidates excluded;
- blocked candidates excluded;
- non-direct candidates excluded.

Regression coverage:

- `backend/scripts/test_nwdp_boundary_project_matching_apply_disabled_endpoint.py`
- included in `backend/scripts/run_nwdp_boundary_regressions.py`

Observed verification:

- unauthenticated apply denied;
- admin editor receives `501`;
- all supplied gates are reported;
- project match row count remained unchanged;
- NWDP candidates remained unchanged:
  - candidates: 654,285
  - active candidates: 0
  - promoted candidates: 0
- full NWDP regression runner passed.

Decision:

This checkpoint exposes the future apply route without implementing apply behavior. Actual project matching apply, rollback execution, runtime spatial matching, candidate activation, candidate promotion, lookup API enablement, and Android behavior changes remain separate guarded checkpoints.

## CoRE Stack climate/ecology region class metadata verification checkpoint — 2026-08-27

The CoRE Stack climate/ecology region class metadata is present in the local development database and was re-verified with the existing importer.

Importer:

- `backend/scripts/import_core_stack_climate_regions.py`

Source manifest:

- `data/staged/core_stack/core_stack_climate_layer_manifest.json`

Local source zone layers:

- `data/staged/core_stack/exports_normalized/Agro_Climatic_Zones.normalized.geojson`
- `data/staged/core_stack/exports_normalized/Agro_Ecological_Zones.normalized.geojson`
- `data/staged/core_stack/exports_normalized/Biogeographic_Zone_pan_india.normalized.geojson`

Observed import verification:

- dry-run exit: 0
- apply exit: 0
- classes seen: 45
- created: 0
- updated: 0
- unchanged: 45

Observed DB class metadata counts:

- `CORE_STACK_AGRO_CLIMATIC_ZONE`: 15
- `CORE_STACK_AGRO_ECOLOGICAL_ZONE`: 20
- `CORE_STACK_BIOGEOGRAPHIC_ZONE`: 10
- total CoRE Stack climate/ecology classes: 45
- review status: `MANUAL_REVIEW`
- active class-reference rows: 45

Notes:

- the normalized biogeographic GeoJSON contains more polygon/province features than broad class rows;
- overlay analysis should preserve both broad `biogeozone` and finer `biogeoprov` / `prov_code` where available;
- the class metadata importer does not create LGD/village mappings.

Guardrails preserved:

- village-zone mappings written: false
- NWDP candidates activated: false
- NWDP candidates promoted: false
- project matching records written: false
- runtime lookup enabled: false
- Android behavior changed: false

Decision:

The CoRE/agro/ecological region class catalog is already available in DB. The next step is a read-only sampled polygon overlay using local NWDP village GeoJSON and normalized CoRE zone GeoJSON to estimate how much earlier CoRE/LGD ambiguity can be reduced at village level.


## NWDP × CoRE agro-zone national sampled overlay checkpoint — 2026-08-27

The NWDP village boundary layer has now been proven usable as an additional polygon layer for read-only CoRE/agro-climatic, agro-ecological, and biogeographic overlay analysis.

This checkpoint does not create village-zone mappings. It proves the overlay mechanics and preserves manual review where polygons do not resolve cleanly to a dominant zone.

Input layers verified:

- NWDP raw village polygons: `data/raw/nwdp_boundary_all_state/20260824T110250Z/*.geojson`
- NWDP source CRS: `EPSG:7755`
- transformed target CRS: `EPSG:4326`
- equal-area overlay CRS: `EPSG:6933`
- normalized agro-climatic zones: `data/staged/core_stack/exports_normalized/Agro_Climatic_Zones.normalized.geojson`
- normalized agro-ecological zones: `data/staged/core_stack/exports_normalized/Agro_Ecological_Zones.normalized.geojson`
- normalized biogeographic zones: `data/staged/core_stack/exports_normalized/Biogeographic_Zone_pan_india.normalized.geojson`

Progression proven:

- feasibility audit confirmed local zone layers and NWDP candidate coverage are available;
- CRS-fixed Andaman sample proved `EPSG:7755 -> EPSG:4326` transforms raw NWDP coordinates into valid lon/lat bounds;
- three-state pilot covered Andaman and Nicobar Islands, Karnataka, and Maharashtra;
- national sampled overlay covered all 36 staged states/UTs.

Observed national sampled overlay:

- states/UTs covered: 36
- sampled eligible candidates: 171
- sampled villages overlaid: 171
- invalid or missing sampled geometries: 0

Observed national sampled classification:

- agro-climatic:
  - dominant zone: 169
  - manual-review zone: 2
- agro-ecological:
  - dominant zone: 169
  - manual-review zone: 2
- biogeographic:
  - dominant zone: 160
  - manual-review zone: 9
  - no zone overlap: 1
  - unresolved multi-zone: 1

Regression coverage:

- `backend/scripts/plan_nwdp_boundary_core_agro_zone_ambiguity_reduction.py`
- `backend/scripts/audit_nwdp_core_agro_zone_overlay_feasibility.py`
- `backend/scripts/sample_nwdp_core_agro_zone_overlay.py`
- `backend/scripts/pilot_nwdp_core_agro_zone_overlay_report.py`
- `backend/scripts/test_nwdp_core_agro_zone_national_sample_overlay_report.py`
- included in `backend/scripts/run_nwdp_boundary_regressions.py`

Guardrails preserved:

- DB writes attempted: false
- CoRE/village zone mappings written: false
- NWDP candidates activated: false
- NWDP candidates promoted: false
- project matching records written: false
- runtime tables written: false
- lookup API enabled: false
- Android behavior changed: false

Decision:

The NWDP layer can reduce earlier CoRE/agro-zone ambiguity by moving from coarse district/block assumptions to village-polygon overlay. The national sample proves all-state mechanics, but it remains read-only. The next checkpoint should be a batched full read-only national overlay report before any mapping apply, runtime lookup, or Android behavior change is designed.

## NWDP × CoRE agro-zone overlay timing checkpoint — 2026-08-28

A capped all-state timing run was completed for the read-only NWDP village polygon × CoRE agro-zone overlay report.

Command shape:

- `backend/scripts/report_nwdp_core_agro_zone_full_overlay.py`
- `--limit-per-state 1000`
- `--sample-limit-per-state 1`

Result:

- states/UTs processed: 36
- healthy states/UTs: 36
- eligible/overlaid rows: 22,280
- invalid or missing geometry: 0
- elapsed time: 2,021.6 seconds, about 33.7 minutes
- throughput: about 11.02 rows/second
- estimated full eligible villages: 451,465
- estimated full national run time: about 40,964 seconds, 682.7 minutes, or 11.38 hours

Layer outcome in the capped run:

- agro-climatic: 22,107 dominant, 155 manual-review, 16 unresolved multi-zone, 2 no-overlap
- agro-ecological: 22,069 dominant, 193 manual-review, 16 unresolved multi-zone, 2 no-overlap
- biogeographic: 21,563 dominant, 644 manual-review, 47 unresolved multi-zone, 26 no-overlap

Slowest capped states:

- Gujarat: 1,000 rows in 298.92 seconds, 3.35 rows/second
- Rajasthan: 1,000 rows in 123.84 seconds, 8.08 rows/second
- Madhya Pradesh: 1,000 rows in 118.75 seconds, 8.42 rows/second
- Karnataka: 1,000 rows in 104.91 seconds, 9.53 rows/second

Decision:

The overlay mechanics are healthy and the current single-process full national estimate is roughly 11.4 hours. A cautious 2-worker state-split parallel run is the next safe test. This remains read-only and does not write CoRE village-zone mappings, activate NWDP candidates, promote NWDP candidates, write project matches, enable lookup APIs, or change Android behavior.

## NWDP demographic enrichment schema plan checkpoint — 2026-08-28

The NWDP raw village boundary properties have been confirmed as a strong demographic/amenity-like enrichment source, while official Census 2011 PCA/DCHB data remains separate and not locally loaded.

Current evidence:

- geography master villages: `576,083`
- geography master villages with LGD code: `576,083`
- geography master villages with `census_name`: `0`
- geography master villages with `census_village_code`: `0`
- NWDP raw GeoJSON files: `36`
- NWDP raw boundary features: `654,285`
- NWDP features with non-zero population: `605,657`
- NWDP features with non-zero households: `605,657`
- NWDP population/household coverage: about `92.57%`

The planned enrichment target is a separate source-versioned profile table:

- `geography_village_demographic_profiles`

The table should attach to canonical LGD geography using `village_id`, not replace the geography master identity.

Official Census remains separate:

- `geography_census_locations`
- `geography_census_village_profiles`
- `geography_census_lgd_crosswalk_candidates`

Decision:

NWDP demographic properties can be used as a near-term enrichment candidate layer for matched villages, but they must be labelled as NWDP source attributes, not official Census. LGD remains canonical for Android/admin village identity. No DB writes, demographic profile rows, LGD overwrites, official Census import claims, runtime lookup enablement, or Android behavior changes are made by this checkpoint.

## NWDP × CoRE agro-zone full national read-only overlay checkpoint — 2026-08-30

The two-worker full national read-only NWDP × CoRE/agro-zone overlay completed successfully.

This checkpoint confirms that the overlay pipeline can process all currently eligible direct-code NWDP village boundary candidates without writing runtime mappings, activating candidates, enabling lookup APIs, or changing Android behavior.

Run location:

- `data/staged/core_stack/nwdp_full_overlay_runs/20260829_full_national_2worker/`

Compact combined summary:

- `data/staged/core_stack/nwdp_full_overlay_runs/20260829_full_national_2worker/combined_national_overlay_summary.json`

Verified result:

- worker report count: 2
- state/UT count processed: 34
- healthy state/UT count: 34
- eligible candidate count: 452,930
- overlaid count: 452,930
- duplicate states: none
- unhealthy states: none
- invalid or missing geometry count: 0

Excluded zero-eligible states:

- Dadra and Nagar Haveli and Daman Diu
- Jammu Kashmir

These two states were excluded because they currently have zero eligible direct-code auto candidates in the staging crosswalk selection used for this read-only overlay.

Timing:

- slowest worker wall-clock lower bound: 8.09 hours
- approximate combined worker runtime: 8.26 hours
- observed rows/sec by slowest-worker wall clock: 15.5561

Guardrails verified false:

- DB writes attempted: false
- CoRE zone mappings written: false
- NWDP candidates activated: false
- NWDP candidates promoted: false
- project matching records written: false
- runtime tables written: false
- lookup API enabled: false
- Android behavior changed: false

Decision:

The full national read-only overlay is now proven for the currently eligible 34-state/UT candidate set. The next safe step is to create a compact regression/checkpoint script that validates the combined summary and preserves the distinction between read-only overlay evidence and any future mapping apply/runtime lookup behavior.

## NWDP regression self-contained fixture checkpoint — 2026-08-30

The NWDP boundary regression runner is now self-contained for the inactive staging importer checks that previously depended on `/tmp/nwdp-boundary-all-state-match-plan.csv`.

Problem fixed:

- `/tmp` is ephemeral and may be cleared after reboot or laptop shutdown.
- The all-state inactive staging importer regression previously expected a match-plan CSV to already exist in `/tmp`.
- The Chandigarh inactive staging apply regression also depended on that same `/tmp` input.
- After reboot, the regression runner could fail with `INPUT_CSV_NOT_FOUND` even though the importer and guarded apply behavior were otherwise valid.

Fix:

- `test_nwdp_boundary_all_state_inactive_staging_importer.py` now creates its own deterministic 36-row all-state fixture input before running.
- `test_nwdp_boundary_all_state_chandigarh_inactive_staging_apply.py` now recreates the deterministic Chandigarh fixture input before running.
- `import_nwdp_boundary_all_state_inactive_staging.py` supports explicit regression expected-count overrides while keeping production defaults unchanged.

Validation:

- targeted full national overlay summary regression passed;
- targeted all-state inactive staging importer regression passed;
- targeted Chandigarh inactive staging apply regression passed;
- full `backend/scripts/run_nwdp_boundary_regressions.py` passed.

Guardrails preserved:

- no runtime table writes;
- no runtime spatial matching enablement;
- no lookup API enablement;
- no Android behavior change;
- no candidate activation or promotion outside explicitly guarded inactive staging apply scope.

Decision:

The NWDP regression runner no longer relies on manually preserved `/tmp` match-plan artifacts for these checkpoints. Future long-running output should continue to use durable project paths for artifacts that must survive shutdown.

## NWDP demographic enrichment schema migration plan checkpoint — 2026-08-30

A dry-run schema migration plan has been added for NWDP-derived village demographic enrichment profiles.

This checkpoint does not create or apply a database migration. It records the intended target schema and validates that the next step can be migration-file authoring without importing profile rows or changing runtime behavior.

Target table planned:

- `geography_village_demographic_profiles`

Purpose:

- attach source-versioned NWDP demographic, land-use, water-source, and amenity-like attributes to canonical LGD `geography_villages`;
- preserve source lineage through `source_system`, `source_version`, `source_feature_id`, `source_vlcode`, source names, `source_properties`, and `match_evidence`;
- avoid overwriting LGD geography identity;
- keep official Census PCA/DCHB as a separate future source lineage.

Scripts added:

- `backend/scripts/plan_nwdp_demographic_enrichment_schema_migration.py`
- `backend/scripts/test_nwdp_demographic_enrichment_schema_migration_plan.py`

Regression runner status:

- `backend/scripts/run_nwdp_boundary_regressions.py` includes the schema migration plan check;
- full NWDP boundary regression runner passed after wiring.

Guardrails preserved:

- schema migration file created: false
- schema migration applied: false
- demographic profile rows written: false
- LGD geography overwritten: false
- official Census claimed imported: false
- NWDP candidates activated: false
- NWDP candidates promoted: false
- runtime lookup enabled: false
- Android behavior changed: false

Decision:

The demographic enrichment track is ready for actual migration-file authoring as a separate checkpoint. The migration should create the empty `geography_village_demographic_profiles` table and indexes only. It must not insert demographic rows or enable any admin/runtime/Android behavior by itself.

## NWDP demographic enrichment schema migration file checkpoint — 2026-08-30

A schema-only Alembic migration file has been authored for the NWDP-derived village demographic enrichment profile table.

Migration file:

- `backend/alembic/versions/057_add_village_demographic_profiles.py`

Target table:

- `geography_village_demographic_profiles`

The migration creates an empty table for source-versioned demographic, land-use, water-source, and amenity-like attributes attached to canonical LGD `geography_villages`.

Regression added:

- `backend/scripts/test_nwdp_demographic_enrichment_schema_migration_file.py`

Regression coverage:

- verifies revision `057`;
- verifies `down_revision = 056`;
- verifies the `geography_village_demographic_profiles` table is created;
- verifies foreign key to `geography_villages.id`;
- verifies source lineage columns;
- verifies population, household, land-use, amenity, source-properties, and match-evidence columns;
- verifies default inactive / not-promoted profile state;
- verifies source-feature and active-promoted uniqueness indexes;
- verifies the migration file avoids row insertion, bulk insert, geography master updates, Android behavior, and lookup API fragments.

Runner status:

- `backend/scripts/run_nwdp_boundary_regressions.py` now includes both the schema migration plan regression and migration file regression;
- full NWDP boundary regression runner passed after wiring.

Guardrails preserved:

- migration file authored, but not applied by this checkpoint;
- no demographic profile rows inserted;
- no LGD geography rows overwritten;
- no official Census import claimed;
- no NWDP candidate activation or promotion;
- no runtime lookup enabled;
- no Android behavior changed.

Decision:

The demographic profile table schema is ready for local migration-apply validation as a separate checkpoint. Applying the migration should create only the empty table and indexes; profile import/apply remains a later guarded step.

## NWDP demographic schema migration apply-validation plan checkpoint — 2026-08-30

A dry-run validation plan has been added for local application of Alembic migration `057`.

This checkpoint does not run Alembic, connect to the database, apply DDL, insert demographic profile rows, enable runtime lookup, or change Android behavior.

Scripts added:

- `backend/scripts/plan_nwdp_demographic_schema_migration_apply_validation.py`
- `backend/scripts/test_nwdp_demographic_schema_migration_apply_validation_plan.py`

Target migration:

- `backend/alembic/versions/057_add_village_demographic_profiles.py`

Target table:

- `geography_village_demographic_profiles`

Planned local apply command:

- `cd backend && ../venv/bin/alembic upgrade head`

Pre-apply checks:

- confirm working tree has no unintended tracked modifications;
- confirm migration file regression passes;
- confirm Alembic current revision before upgrade;
- confirm the target table does not already exist, or stop and inspect if it does.

Post-apply checks:

- confirm Alembic current/head is revision `057`;
- confirm `geography_village_demographic_profiles` exists;
- confirm the table row count is `0` immediately after migration;
- confirm expected columns exist;
- confirm expected indexes exist;
- confirm foreign key to `geography_villages.id` exists;
- confirm no `geography_villages` rows were updated;
- confirm full NWDP boundary regression runner passes.

Guardrails preserved:

- Alembic upgrade executed: false
- DB connection attempted: false
- schema migration applied: false
- demographic profile rows written: false
- LGD geography overwritten: false
- official Census claimed imported: false
- runtime lookup enabled: false
- Android behavior changed: false

Decision:

The migration is ready for local apply validation as a separate, explicit checkpoint. Applying migration `057` should create only the empty demographic profile table and indexes. Profile import/apply remains blocked until its own guarded import checkpoint.

## NWDP demographic schema migration local apply checkpoint — 2026-08-30

Alembic migration `057` was applied successfully in the local development database.

Migration applied:

- `backend/alembic/versions/057_add_village_demographic_profiles.py`

Before apply:

- Alembic current revision: `056`
- `geography_village_demographic_profiles` existed: false
- migration file regression passed

Apply command:

- `cd backend && ../venv/bin/alembic upgrade head`

Apply result:

- upgrade path: `056 -> 057`
- Alembic current after apply: `057 (head)`

Post-apply validation:

- `geography_village_demographic_profiles` exists: true
- row count immediately after migration: 0
- missing expected columns: none
- missing expected indexes: none
- foreign key count: 1
- post-apply health: true

Regression status:

- full `backend/scripts/run_nwdp_boundary_regressions.py` passed after local migration apply.

Guardrails preserved:

- demographic profile rows inserted: false
- LGD geography overwritten: false
- official Census import claimed: false
- NWDP candidates activated: false
- NWDP candidates promoted: false
- runtime lookup enabled: false
- Android behavior changed: false

Decision:

The local development database is now at Alembic revision `057`, with the empty demographic profile table available for the next guarded checkpoint. The next step should be a disabled/admin-preview or dry-run import validation layer before any demographic profile rows are written.

## NWDP demographic schema migration DB-state regression checkpoint — 2026-08-30

A read-only DB-state regression has been added for Alembic migration `057`.

Regression added:

- `backend/scripts/test_nwdp_demographic_schema_migration_db_state.py`

The regression connects to the local development database and verifies that the migration has been applied correctly without inserting demographic profile rows.

Checks performed:

- Alembic version is `057`;
- `geography_village_demographic_profiles` exists;
- table row count is `0`;
- expected columns are present;
- expected indexes are present;
- at least one foreign key exists for the table;
- guardrails remain false.

Runner status:

- `backend/scripts/run_nwdp_boundary_regressions.py` includes the DB-state regression;
- full NWDP boundary regression runner passed after wiring.

Important operational note:

Because this DB-state regression expects Alembic revision `057`, developers must run `cd backend && ../venv/bin/alembic upgrade head` before running the full NWDP boundary regression suite on a fresh or older local database.

Guardrails preserved:

- DB-state check is read-only;
- demographic profile rows written: false;
- LGD geography overwritten: false;
- runtime lookup enabled: false;
- Android behavior changed: false.

Decision:

Migration `057` is now the expected local schema baseline for the NWDP demographic enrichment track. The next checkpoint should be an admin-preview or guarded dry-run importer over the empty profile table, before any demographic profile rows are written.

## NWDP demographic admin preview endpoint plan checkpoint — 2026-08-30

A disabled/read-only admin preview endpoint plan has been added for NWDP demographic enrichment profiles.

Planned endpoint:

- `GET /api/v1/master-data/geography/nwdp-demographic-profiles/preview`

Target table:

- `geography_village_demographic_profiles`

Scripts added:

- `backend/scripts/plan_nwdp_demographic_admin_preview_endpoint.py`
- `backend/scripts/test_nwdp_demographic_admin_preview_endpoint_plan.py`

Intended current behavior while no profiles are imported:

- endpoint remains disabled;
- response reason: `NO_DEMOGRAPHIC_PROFILE_ROWS_IMPORTED`;
- profile row count: 0;
- active profile row count: 0;
- promoted profile row count: 0;
- ready for profile apply: false;
- ready for Android behavior change: false.

Future preview fields planned:

- state/UT;
- district;
- village name and LGD code;
- source system and source version;
- source village code;
- total population;
- total households;
- rural/urban;
- review status;
- promotion status;
- active flag.

Runner status:

- `backend/scripts/run_nwdp_boundary_regressions.py` includes the admin preview endpoint plan regression;
- full NWDP boundary regression runner passed after wiring.

Guardrails preserved:

- endpoint implemented: false;
- DB writes attempted: false;
- demographic profile rows written: false;
- profiles promoted: false;
- runtime lookup enabled: false;
- Android behavior changed: false;
- official Census claimed imported: false.

Decision:

The endpoint contract is ready for implementation as a read-only admin preview. The implementation should return a disabled/empty response while the profile table has zero rows and must not expose Android/runtime behavior.

## NWDP demographic admin preview endpoint implementation checkpoint — 2026-08-30

The read-only admin preview endpoint for NWDP demographic enrichment profiles has been implemented.

Endpoint:

- `GET /api/v1/master-data/geography/nwdp-demographic-profiles/preview`

Implementation:

- `backend/app/modules/master_data/api/geography.py`

Regression:

- `backend/scripts/test_nwdp_demographic_admin_preview_endpoint.py`

Current behavior while the profile table is empty:

- requires admin view authentication;
- unauthenticated requests are denied;
- authenticated admin request returns `200`;
- response schema: `nwdp_demographic_profiles_admin_preview.v1`;
- `healthy`: true;
- `enabled`: false;
- `reason`: `NO_DEMOGRAPHIC_PROFILE_ROWS_IMPORTED`;
- `profile_row_count`: 0;
- `active_profile_row_count`: 0;
- `promoted_profile_row_count`: 0.

Guardrails verified by regression:

- DB writes attempted: false;
- demographic profile rows written: false;
- profiles promoted: false;
- runtime lookup enabled: false;
- Android behavior changed: false;
- official Census claimed imported: false.

Runner status:

- `backend/scripts/run_nwdp_boundary_regressions.py` includes the admin preview endpoint regression;
- full NWDP boundary regression runner passed after endpoint implementation.

Decision:

The demographic profile table now has a safe admin read surface. Because no profile rows have been imported, the endpoint correctly stays disabled and reports an explicit empty-table reason. The next checkpoint should be a guarded profile import dry-run against the migrated table, not Android/runtime enablement.

## NWDP demographic admin preview review-analysis checkpoint — 2026-08-30

Status:
The NWDP demographic admin preview endpoint now keeps the same admin geography review style used by earlier boundary APIs.

Endpoint:
- `GET /api/v1/master-data/geography/nwdp-demographic-profiles/preview`

Current behavior:
- requires admin view authentication;
- remains read-only;
- supports `state_or_ut`, `district`, and `limit` filters;
- returns top-level profile counts for backward compatibility;
- returns a `summary` object with profile, active, promoted, not-promoted, auto-candidate, manual-review, approved-for-promotion, rejected, and blocked counts;
- returns `approved_vs_manual_review` for quick admin comparison;
- returns `state_district_summary` grouped by state/UT and district;
- returns `items` for preview rows when profile rows exist;
- remains disabled while the profile table is empty with reason `NO_DEMOGRAPHIC_PROFILE_ROWS_IMPORTED`.

Regression:
- `backend/scripts/test_nwdp_demographic_admin_preview_endpoint.py`

Validation:
- unauthenticated request denied;
- authenticated admin request returns `200`;
- empty-table response remains healthy and disabled;
- state/district filter echo is verified;
- approved versus manual-review counts are present;
- state/district summary is empty before import;
- preview items are empty before import;
- endpoint does not mutate the profile table.

Guardrails preserved:
- DB writes attempted by endpoint: false;
- demographic profile rows written by endpoint: false;
- profiles promoted: false;
- runtime lookup enabled: false;
- Android behavior changed: false;
- official Census claimed imported: false.

Decision:
The preview API can now support admin analysis of approved versus manual-review demographic profiles by state/district combo once guarded profile rows exist. The next checkpoint should add a positive fixture regression or guarded dry-run import validation before any real demographic profile import/apply.

## NWDP demographic admin preview positive state/district fixture checkpoint — 2026-08-30

Status:
The NWDP demographic admin preview regression now verifies positive state/district review analysis with temporary fixture profile rows.

Regression:
- `backend/scripts/test_nwdp_demographic_admin_preview_endpoint.py`

Validated behavior:
- unauthenticated preview is denied;
- authenticated admin preview returns `200`;
- empty-table behavior remains healthy and disabled;
- endpoint supports `state_or_ut` and `district` filters;
- filtered fixture profiles are returned in `items`;
- `summary` reports review-status counts;
- `approved_vs_manual_review` reports approved versus manual-review counts;
- `state_district_summary` groups profile counts by state/UT and district.

Positive fixture result:
- state/UT: `Fixture State`;
- district: `Fixture District`;
- fixture profile rows: 3;
- `APPROVED_FOR_PROMOTION`: 1;
- `MANUAL_REVIEW`: 2;
- active profile rows: 0;
- promoted profile rows: 0.

Cleanup:
The regression deletes its fixture rows after execution and verifies profile table counts return to the pre-test state.

Guardrails preserved:
- endpoint remains read-only;
- real NWDP demographic profile rows imported: false;
- real profiles promoted: false;
- runtime lookup enabled: false;
- Android behavior changed: false;
- official Census claimed imported: false.

Decision:
The admin preview path can now analyze approved versus manual-review demographic profiles by state/district combo once guarded profile rows exist. The next checkpoint should be a demographic profile import dry-run plan that computes candidate insert rows without writing them.

## NWDP demographic profile import dry-run rollup checkpoint — 2026-08-30

Status:
The NWDP demographic enrichment import planner now produces admin-review-friendly rollups without writing demographic profile rows.

Scripts:
- `backend/scripts/plan_nwdp_demographic_enrichment_import.py`
- `backend/scripts/test_nwdp_demographic_enrichment_import_plan.py`

Validation:
- full NWDP boundary regression runner passed;
- dry-run planner exits healthy;
- safe candidate universe is loaded from guarded direct-code candidates;
- sampled candidates attach to canonical `geography_villages`;
- sampled raw NWDP features are found;
- population, household, land-use, and amenity preview fields are preserved;
- sample profile rows include `review_status`, `promotion_status`, and `is_active`;
- planned profiles remain inactive;
- planned profiles remain not promoted;
- planned review buckets are reported;
- planned promotion buckets are reported;
- approved-versus-manual-review summary is reported;
- planned state/district rollups are reported.

Guardrails preserved:
- DB writes attempted: false;
- demographic profile rows written: false;
- profiles promoted: false;
- LGD geography overwritten: false;
- NWDP candidates activated: false;
- NWDP candidates promoted: false;
- project matching records written: false;
- runtime lookup enabled: false;
- Android behavior changed: false;
- official Census claimed imported: false.

Decision:
The dry-run planner now matches the admin preview shape closely enough to support a guarded inactive-profile import checkpoint. The next implementation step can be an apply-disabled/import-apply plan that only allows inactive, not-promoted demographic profile rows and still keeps runtime/Android behavior disabled.

## NWDP demographic profile import apply-disabled checkpoint — 2026-08-30

Status:
A hard apply-disabled guard now exists for NWDP demographic profile import.

Scripts:
- `backend/scripts/apply_nwdp_demographic_profile_import.py`
- `backend/scripts/test_nwdp_demographic_profile_import_apply_disabled.py`

Runner:
- `backend/scripts/run_nwdp_boundary_regressions.py` includes the apply-disabled regression.
- Full NWDP boundary regression runner passed after wiring.

Current behavior:
- no-scope apply exits non-zero;
- no-scope apply reports `NWDP_DEMOGRAPHIC_PROFILE_IMPORT_APPLY_REQUIRES_STATE_SCOPE`;
- scoped apply still exits non-zero;
- scoped apply reports `NWDP_DEMOGRAPHIC_PROFILE_IMPORT_APPLY_NOT_IMPLEMENTED`;
- scoped apply echoes the requested state/UT;
- apply output records that a state scope is required;
- apply output records that apply is not implemented.

Future allowed scope:
- single state/UT only;
- inactive profile rows only;
- `DIRECT_VLCODE_MATCH` source candidates only;
- `AUTO_CANDIDATE` source candidates only;
- `NOT_PROMOTED` source candidates only;
- inserted profile rows must remain `AUTO_CANDIDATE`;
- inserted profile rows must remain `NOT_PROMOTED`;
- inserted profile rows must remain `is_active = false`.

Guardrails preserved:
- DB writes attempted: false;
- demographic profile rows written: false;
- profiles promoted: false;
- LGD geography overwritten: false;
- official Census claimed imported: false;
- NWDP candidates activated: false;
- NWDP candidates promoted: false;
- project matching records written: false;
- runtime lookup enabled: false;
- Android behavior changed: false.

Decision:
The project now has an explicit safety gate before demographic profile import. The next checkpoint may design a one-state inactive profile apply path, but implementation should remain scoped, idempotent, and separate from promotion/runtime/Android enablement.

## NWDP demographic one-state inactive apply plan checkpoint — 2026-08-30

Status:
A plan-only checkpoint now defines the future one-state inactive NWDP demographic profile apply contract.

Scripts:
- `backend/scripts/plan_nwdp_demographic_one_state_inactive_apply.py`
- `backend/scripts/test_nwdp_demographic_one_state_inactive_apply_plan.py`

Runner:
- `backend/scripts/run_nwdp_boundary_regressions.py` includes the one-state inactive apply plan regression.
- Full NWDP boundary regression runner passed after wiring.

Current behavior:
- no-scope plan exits non-zero;
- no-scope plan reports `NWDP_DEMOGRAPHIC_ONE_STATE_APPLY_PLAN_REQUIRES_STATE_SCOPE`;
- scoped plan exits zero;
- scoped plan echoes the requested state/UT;
- scoped plan remains plan-only and performs no inserts.

Selection policy:
- source system: `NWDP_GSI_VILLAGE_BOUNDARY`;
- source version: `20260824T110250Z`;
- state/UT scope is required;
- all-state apply is not allowed;
- source candidate bucket must be `DIRECT_VLCODE_MATCH`;
- source candidate review status must be `AUTO_CANDIDATE`;
- source candidate promotion status must be `NOT_PROMOTED`;
- source candidate must have `proposed_village_id`;
- matching raw NWDP feature is required.

Future insert policy:
- insert scope: inactive demographic profile rows only;
- profile review status: `AUTO_CANDIDATE`;
- profile promotion status: `NOT_PROMOTED`;
- profile active flag: `false`;
- runtime table writes not allowed;
- candidate activation not allowed;
- candidate promotion not allowed.

Idempotency policy:
- primary dedupe key: `source_system`, `source_version`, `source_feature_id`;
- existing source-feature profiles are skipped;
- existing profiles are not updated;
- existing profiles are not deleted;
- active/promoted uniqueness remains separately guarded by table indexes.

Guardrails preserved:
- DB writes attempted: false;
- demographic profile rows written: false;
- profiles promoted: false;
- LGD geography overwritten: false;
- official Census claimed imported: false;
- NWDP candidates activated: false;
- NWDP candidates promoted: false;
- project matching records written: false;
- runtime lookup enabled: false;
- Android behavior changed: false.

Decision:
The next checkpoint may implement the first guarded one-state inactive apply, preferably against a tiny state/UT scope such as Chandigarh if it has eligible safe candidates. That implementation must remain idempotent and must not promote profiles, enable runtime lookup, or change Android behavior.

## NWDP demographic one-state apply to admin-preview stitch checkpoint — 2026-08-31

Status:
A stitched regression now verifies that guarded one-state demographic profile apply feeds the admin preview endpoint correctly.

Scripts:
- `backend/scripts/test_nwdp_demographic_one_state_apply_admin_preview.py`
- `backend/scripts/test_nwdp_demographic_one_state_inactive_apply.py`
- `backend/scripts/apply_nwdp_demographic_profile_import.py`

Runner:
- `backend/scripts/run_nwdp_boundary_regressions.py` includes the stitched apply/admin-preview regression.
- Full NWDP boundary regression runner passed after wiring.

Validated flow:
1. Apply a tiny guarded batch for `Andaman & Nicobar Island`.
2. Insert 5 demographic profile rows.
3. Keep rows inactive.
4. Keep rows `AUTO_CANDIDATE`.
5. Keep rows `NOT_PROMOTED`.
6. Call admin demographic preview with `state_or_ut=Andaman & Nicobar Island`.
7. Verify preview sees at least 5 scoped rows.
8. Verify preview returns state/district grouped rows.
9. Verify preview returns applied rows in `items`.
10. Clean up the inserted rows and verify table counts return to pre-test state.

Observed stitched preview grouping:
- `Nicobars`: 4 rows
- `North And Middle Andaman`: 1 row

Guardrails preserved:
- no profile promotion;
- no candidate activation;
- no candidate promotion;
- no LGD geography overwrite;
- no project matching records written;
- no runtime lookup enabled;
- no Android behavior changed;
- no official Census import claim.

Decision:
The apply-to-preview path is verified with cleanup. The next checkpoint may run a persistent, guarded one-state inactive apply for all eligible `Andaman & Nicobar Island` demographic profile rows, then validate admin preview counts before considering broader state/all-state import.

## NWDP demographic Andaman persistent inactive apply checkpoint — 2026-08-31

Status:
The first persistent guarded one-state NWDP demographic profile import has been applied for `Andaman & Nicobar Island`.

Command:
- `backend/scripts/apply_nwdp_demographic_profile_import.py --state-or-ut "Andaman & Nicobar Island" --apply --max-rows 600`

Result:
- planned insert rows: 512
- inserted rows: 512
- skipped existing rows: 0
- missing raw features: 0

Idempotency validation:
- rerun planned rows: 512
- rerun inserted rows: 0
- rerun skipped existing rows: 512

Persistent DB validation:
- profile rows: 512
- `AUTO_CANDIDATE`: 512
- `NOT_PROMOTED`: 512
- inactive rows: 512
- promoted rows: 0
- active rows: 0

District split:
- `Nicobars`: 162
- `North And Middle Andaman`: 227
- `South Andamans`: 123

Admin preview validation:
- preview enabled: true
- preview reason: null
- preview profile row count: 512
- state/district summary returned expected district counts
- preview returned scoped items
- preview endpoint remained read-only

Guardrails preserved:
- profile promotion: false
- active profile rows: false
- LGD geography overwrite: false
- NWDP candidate activation: false
- NWDP candidate promotion: false
- project matching records written: false
- runtime lookup enabled: false
- Android behavior changed: false
- official Census import claimed: false

Decision:
The one-state persistent inactive import path is validated. The next checkpoint can either apply the next small state scope or prepare an all-state guarded apply plan with per-state caps, idempotency, and resumable audit output.

## NWDP demographic fast all-state inactive apply plan checkpoint — 2026-08-31

Status:
A fast all-state inactive demographic profile apply plan now exists. It uses DB aggregate counts only and avoids raw GeoJSON scanning in the regression runner.

Scripts:
- `backend/scripts/plan_nwdp_demographic_all_state_inactive_apply.py`
- `backend/scripts/test_nwdp_demographic_all_state_inactive_apply_plan.py`

Runner:
- `backend/scripts/run_nwdp_boundary_regressions.py` includes the fast all-state plan regression.
- Full NWDP boundary regression runner passed after wiring.

Behavior:
- computes planned profile rows by state/UT from guarded direct-code boundary candidates;
- computes existing imported demographic profile rows by state/UT;
- computes remaining insert rows by state/UT;
- accounts for the already-persisted `Andaman & Nicobar Island` inactive import;
- recommends one-state-at-a-time apply execution;
- explicitly blocks a single all-state transaction;
- records a performance policy showing no raw GeoJSON scan.

Guardrails preserved:
- DB writes attempted by planner: false;
- demographic profile rows written by planner: false;
- profiles promoted: false;
- LGD geography overwritten: false;
- official Census claimed imported: false;
- NWDP candidates activated: false;
- NWDP candidates promoted: false;
- project matching records written: false;
- runtime lookup enabled: false;
- Android behavior changed: false.

Decision:
All-state import should be performed by a resumable orchestrator that calls the existing guarded one-state apply command per state/UT, writes durable per-state audit files, skips completed states on resume, and exposes a separate read-only progress monitor.

## NWDP demographic all-state inactive apply checkpoint - 2026-08-31

Status:
The guarded resumable all-state inactive demographic profile apply completed locally.

Run:
- run id: 20260831_nwdp_demographic_all_state_inactive_apply
- run directory: data/staged/core_stack/nwdp_demographic_profile_apply_runs/20260831_nwdp_demographic_all_state_inactive_apply
- orchestrator: backend/scripts/run_nwdp_demographic_all_state_inactive_apply.py
- monitor: backend/scripts/monitor_nwdp_demographic_apply_run.py

Final monitor summary:
- status: COMPLETE_OR_NO_REMAINING_STATES
- state plans: 36
- completed state markers: 34
- failed state markers: 0
- planned rows completed by monitor: 448,076
- inserted rows completed by monitor: 448,076
- skipped existing rows completed by monitor: 0
- remaining rows estimate: 0
- total demographic profile table rows after apply: 453,036

Prior checkpoint rows:
- Andaman & Nicobar Island had already been persistently imported with 512 inactive rows.
- The all-state resumable run inserted the remaining 448,076 inactive rows.

Post-apply DB-state validation:
- Alembic revision: 057
- target table exists: true
- total profile rows: 453,036
- active profile rows: 0
- promoted profile rows: 0
- non-AUTO_CANDIDATE rows: 0
- expected columns: present
- expected indexes: present
- foreign key to canonical geography_villages: present

Admin preview validation:
- admin preview endpoint enabled: true
- response reason: null
- profile row count: 453,036
- active profile row count: 0
- promoted profile row count: 0
- approved/manual-review counts: 0/0 for the imported NWDP baseline
- endpoint remains read-only
- positive fixture regression still verifies approved vs manual-review state/district analysis and cleans up fixture rows

Guardrails preserved:
- profile promotion: false
- active profile rows: false
- LGD geography overwrite: false
- NWDP candidate activation: false
- NWDP candidate promotion: false
- project matching records written: false
- runtime lookup enabled: false
- Android behavior changed: false
- official Census import claimed: false

Operational notes:
- The all-state apply ran through a resumable state-by-state orchestrator, not a single national transaction.
- The orchestrator is plan-only by default; real writes require --execute.
- Resume is idempotent through source-feature de-duplication and completed-state markers.
- The read-only monitor reports completed markers, inserted/skipped counts, errors, remaining estimate, elapsed time, and rows/second.

Decision:
The national NWDP demographic enrichment table is now populated only with inactive, not-promoted AUTO_CANDIDATE profiles for admin review. The next checkpoint should be admin review/promotion planning. Runtime lookup and Android behavior remain blocked until a separate guarded promotion/activation checkpoint.

## NWDP demographic admin review/promotion plan checkpoint — 2026-09-01

Commit: `abfe4fb test: plan nwdp demographic admin review promotion`

### Current imported demographic profile state

The all-state inactive demographic profile import has completed locally.

- Target table: `geography_village_demographic_profiles`
- Imported rows: `453036`
- Active profile rows: `0`
- Promoted profile rows: `0`
- Review status: all imported rows remain `AUTO_CANDIDATE`
- Promotion status: all imported rows remain `NOT_PROMOTED`
- Runtime lookup: not enabled
- Android behavior: unchanged
- Official Census import: not claimed

### Admin review/promotion planning checkpoint

Added:

- `backend/scripts/plan_nwdp_demographic_admin_review_promotion.py`
- `backend/scripts/test_nwdp_demographic_admin_review_promotion_plan.py`

The plan is read-only and DB-aggregate based. It lets admins analyze imported inactive demographic profiles by state/UT and district before any review mutation or promotion workflow exists.

The plan exposes:

- total profile counts;
- active/promoted profile counts;
- `AUTO_CANDIDATE`, `MANUAL_REVIEW`, `APPROVED_FOR_PROMOTION`, `REJECTED`, and `BLOCKED` review buckets;
- approved-vs-manual-review summary;
- state/district summary rows;
- future review-update endpoint shape;
- future promotion dry-run endpoint shape.

### Review policy

The next implementation should follow the existing admin geography API style used for boundary candidate review.

Planned future review transition surface:

- `AUTO_CANDIDATE -> MANUAL_REVIEW`
- `AUTO_CANDIDATE -> APPROVED_FOR_PROMOTION`
- `AUTO_CANDIDATE -> REJECTED`
- `AUTO_CANDIDATE -> BLOCKED`

Guarded policy:

- review notes required for non-trivial review status changes;
- bulk review must be state/district scoped;
- review update must only touch inactive `NOT_PROMOTED` NWDP demographic profile rows;
- review update must not activate profile rows;
- review update must not promote profile rows.

### Promotion policy

Promotion is not implemented in this checkpoint.

Future promotion must remain a separate explicit dry-run and apply workflow requiring:

- `review_status = APPROVED_FOR_PROMOTION`
- `promotion_status = NOT_PROMOTED`
- `is_active = false`
- state/district-scoped dry-run before apply

### Guardrails verified

- DB writes attempted by plan: false
- demographic profile rows written by plan: false
- profile review statuses changed: false
- profiles promoted: false
- profile rows activated: false
- LGD geography overwritten: false
- NWDP candidates activated/promoted: false
- project matching records written: false
- runtime lookup enabled: false
- Android behavior changed: false
- official Census import claimed: false

### Validation

Regression passed:

- `backend/scripts/test_nwdp_demographic_admin_review_promotion_plan.py`
- full `backend/scripts/run_nwdp_boundary_regressions.py`

The all-state inactive apply plan regression was also updated so readiness reflects remaining rows. After the full import, `ready_for_one_state_at_a_time_apply` is false because there are no remaining rows to import.

### Next checkpoint

Implement the admin review update endpoint in the same style as existing boundary admin geography review APIs:

`PATCH /api/v1/master-data/geography/nwdp-demographic-profiles/{profile_id}/review`

It should mutate only review metadata/status for inactive, not-promoted demographic profile rows and must keep promotion, activation, runtime lookup, and Android behavior disabled.

## NWDP demographic admin review endpoint implementation checkpoint — 2026-09-01

Commit: `cae827b test: add nwdp demographic admin review endpoint`

### Endpoint added

`PATCH /api/v1/master-data/geography/nwdp-demographic-profiles/{profile_id}/review`

The endpoint follows the existing guarded admin geography review style used for NWDP boundary candidates.

It allows an authenticated admin editor to update review status metadata for one imported NWDP demographic profile row at a time.

### Supported review transitions

The regression verifies:

- `AUTO_CANDIDATE -> APPROVED_FOR_PROMOTION`
- `APPROVED_FOR_PROMOTION -> MANUAL_REVIEW`

Planned/allowed review target statuses:

- `MANUAL_REVIEW`
- `APPROVED_FOR_PROMOTION`
- `REJECTED`
- `BLOCKED`

Reviewer decision/status pairing is enforced:

- `MARK_MANUAL_REVIEW` requires `MANUAL_REVIEW`
- `APPROVE_FOR_PROMOTION` requires `APPROVED_FOR_PROMOTION`
- `REJECT_PROFILE` requires `REJECTED`
- `BLOCK_PROFILE` requires `BLOCKED`

Reviewer notes are required.

### Mutability boundary

The endpoint only updates:

- `review_status`
- `match_evidence.review_history`
- `match_evidence.latest_review_event`
- `match_evidence.review_guardrail`
- `updated_at`

It does not update:

- `promotion_status`
- `is_active`
- runtime lookup tables
- LGD geography
- Android behavior
- official Census import state

### Regression coverage

Added:

- `backend/scripts/test_nwdp_demographic_admin_review_endpoint.py`

Verified:

- unauthenticated request is denied;
- missing notes are rejected;
- reviewer decision/status mismatch is rejected;
- admin approval transition succeeds;
- admin manual-review transition succeeds;
- review history is appended;
- review guardrail records no promotion;
- fixture rows are cleaned up back to the pre-test table counts.

Current local persistent table state after regression cleanup:

- `profile_row_count`: `453036`
- `active_profile_row_count`: `0`
- `promoted_profile_row_count`: `0`

### Guardrails preserved

- profile review status changed only for test fixture rows;
- regression cleanup restored profile counts;
- profiles promoted: false;
- profile rows activated: false;
- runtime lookup enabled: false;
- Android behavior changed: false;
- official Census import claimed: false;
- LGD geography overwritten: false.

### Validation

Passed:

- `backend/scripts/test_nwdp_demographic_admin_review_endpoint.py`
- full `backend/scripts/run_nwdp_boundary_regressions.py`

### Next checkpoint

Add a read-only promotion dry-run endpoint:

`GET /api/v1/master-data/geography/nwdp-demographic-profiles/promotion/dry-run?state_or_ut=<STATE>&district=<DISTRICT>`

It should count and sample only rows where:

- `review_status = APPROVED_FOR_PROMOTION`
- `promotion_status = NOT_PROMOTED`
- `is_active = false`

The dry-run must not promote, activate, enable runtime lookup, or change Android behavior.

## NWDP demographic promotion dry-run endpoint checkpoint — 2026-09-01

Commit: `a53bdf2 test: add nwdp demographic promotion dry run`

### Endpoint added

`GET /api/v1/master-data/geography/nwdp-demographic-profiles/promotion/dry-run`

The endpoint is read-only and admin-view guarded. It reports profile rows that would be eligible for a later demographic profile promotion workflow.

### Selection policy

The dry-run only includes rows matching all of the following:

- `source_system = NWDP_GSI_VILLAGE_BOUNDARY`
- `review_status = APPROVED_FOR_PROMOTION`
- `promotion_status = NOT_PROMOTED`
- `is_active = false`

Optional filters:

- `state_or_ut`
- `district`
- `limit`

### Response shape

The dry-run returns:

- stable schema version: `nwdp_demographic_profile_promotion_dry_run.v1`
- `enabled`
- explicit empty reason: `NO_APPROVED_INACTIVE_NOT_PROMOTED_DEMOGRAPHIC_PROFILES`
- selection policy
- summary counts
- state/district summary
- eligible sample items
- readiness flags
- guardrails

### Regression coverage

Added:

- `backend/scripts/test_nwdp_demographic_promotion_dry_run_endpoint.py`

Verified:

- unauthenticated dry-run is denied;
- empty scoped dry-run returns `200` with explicit disabled reason;
- approved inactive not-promoted fixture row is included;
- manual-review fixture row is excluded;
- state/district summary is returned;
- sample item remains inactive and not promoted;
- dry-run does not write DB rows;
- dry-run does not change review status;
- dry-run does not promote profiles;
- dry-run does not activate rows;
- dry-run does not enable runtime lookup;
- dry-run does not change Android behavior;
- fixture cleanup returns profile table to pre-test counts.

Persistent local table after regression cleanup:

- `profile_row_count`: `453036`
- `active_profile_row_count`: `0`
- `promoted_profile_row_count`: `0`

### Guardrails preserved

- profiles promoted: false
- profile rows activated: false
- runtime lookup enabled: false
- Android behavior changed: false
- official Census import claimed: false
- LGD geography overwritten: false

### Validation

Passed:

- `backend/scripts/test_nwdp_demographic_promotion_dry_run_endpoint.py`
- full `backend/scripts/run_nwdp_boundary_regressions.py`

### Next checkpoint

Plan the demographic profile promotion apply guard.

Recommended sequence:

1. Add a disabled promotion apply endpoint/script regression.
2. Require explicit state/district scope.
3. Require dry-run evidence first.
4. Verify disabled apply mutates nothing.
5. Only after that, add a tiny fixture promotion apply regression that promotes test rows and cleans them up.

Promotion apply must still not enable runtime lookup or Android behavior.

## NWDP demographic profile promotion apply disabled checkpoint — 2026-09-01

Commit: `166eab9 test: block nwdp demographic profile promotion apply`

### Script added

`backend/scripts/apply_nwdp_demographic_profile_promotion.py`

The script is a guarded promotion apply entry point, currently disabled by policy. It writes an audit JSON and mutates nothing.

### Regression added

`backend/scripts/test_nwdp_demographic_profile_promotion_apply_disabled.py`

### Current behavior

The disabled apply guard verifies three pre-apply blocks:

1. missing explicit `--apply` flag;
2. missing state/district scope;
3. scoped apply attempt while promotion apply remains disabled by policy.

All cases exit non-zero and write audit output.

### Required future promotion selection policy

Future promotion apply may only consider rows matching all of:

- `source_system = NWDP_GSI_VILLAGE_BOUNDARY`
- `review_status = APPROVED_FOR_PROMOTION`
- `promotion_status = NOT_PROMOTED`
- `is_active = false`
- state scope present
- district scope present
- dry-run performed first

### Current persistent table state

The local demographic profile table remains in the imported-but-not-promoted state:

- `profile_row_count`: `453036`
- `active_profile_row_count`: `0`
- `promoted_profile_row_count`: `0`

The disabled promotion apply guard reported zero eligible rows for the sampled Andaman/Nicobars scope because no real demographic profile rows have been approved for promotion.

### Guardrails verified

- DB writes attempted: false
- profile review status changed: false
- profiles promoted: false
- profile rows activated: false
- runtime lookup enabled: false
- Android behavior changed: false
- official Census import claimed: false
- LGD geography overwritten: false

### Validation

Passed:

- `backend/scripts/test_nwdp_demographic_profile_promotion_apply_disabled.py`
- full `backend/scripts/run_nwdp_boundary_regressions.py`

### Next checkpoint

Add a tiny fixture-only promotion apply regression.

That next checkpoint should:

- insert one or more temporary approved inactive `NOT_PROMOTED` fixture rows;
- run promotion apply with state/district scope;
- promote/activate only fixture rows;
- verify promoted/active counts for fixture rows;
- verify runtime lookup remains disabled;
- verify Android remains unchanged;
- clean up fixture rows and return table counts to pre-test state.

Real imported demographic rows should remain unpromoted until a later explicit state/district approval and promotion checkpoint.

## NWDP demographic profile promotion tiny fixture apply checkpoint — 2026-09-01

Commit: `896b143 test: apply nwdp demographic promotion tiny fixture`

### Script updated

`backend/scripts/apply_nwdp_demographic_profile_promotion.py`

The promotion script now has an explicit fixture-safe apply path guarded by:

- `--apply`
- `--enable-policy`
- `--state-or-ut`
- `--district`

Without the explicit policy flag, promotion apply remains disabled by policy.

### Regression added

`backend/scripts/test_nwdp_demographic_profile_promotion_tiny_fixture_apply.py`

The regression inserts two temporary approved inactive `NOT_PROMOTED` NWDP demographic profile fixture rows, runs scoped promotion apply, verifies the mutation, reruns apply for idempotency, and cleans up the fixture rows.

### Fixture promotion behavior verified

First apply:

- planned promotion count: `2`
- promoted count: `2`
- activated count: `2`
- DB writes attempted: true
- profile rows activated: true
- profiles promoted: true

Second apply:

- planned promotion count: `0`
- promoted count: `0`
- activated count: `0`
- confirms idempotency after rows are already promoted/active

### Important unique constraint coverage

The regression uses two distinct `village_id` values because the target table has an active/promoted uniqueness guard on:

- `village_id`
- `source_system`
- `source_version`

This verifies that promotion respects the active promoted uniqueness model.

### Cleanup and persistent state

After cleanup, the persistent local demographic profile table returned to:

- `profile_row_count`: `453036`
- `active_profile_row_count`: `0`
- `promoted_profile_row_count`: `0`

No real imported demographic profile rows were promoted or activated.

### Guardrails preserved

Even during fixture promotion apply:

- runtime lookup enabled: false
- Android behavior changed: false
- official Census import claimed: false
- LGD geography overwritten: false
- project matching records written: false
- NWDP boundary candidates activated/promoted: false

### Validation

Passed:

- `backend/scripts/test_nwdp_demographic_profile_promotion_apply_disabled.py`
- `backend/scripts/test_nwdp_demographic_profile_promotion_tiny_fixture_apply.py`
- full `backend/scripts/run_nwdp_boundary_regressions.py`

### Next checkpoint

Choose one of:

1. Add an admin endpoint wrapper for promotion apply, still disabled for real rows by policy.
2. Plan a real scoped approval + promotion dry-run for one small state/district.
3. Add a state/district promotion readiness report before any real promotion.

Recommended next step: option 3, because it lets admins see which state/district combinations have approved rows, auto-candidates, and promotion readiness before we touch real imported profiles.

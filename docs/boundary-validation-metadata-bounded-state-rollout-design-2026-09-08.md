# Boundary validation metadata bounded state rollout design

Status date: 2026-09-08

## Purpose

This document defines the next controlled step after the successful
tiny-fixture boundary validation metadata apply.

It does not authorize broad or national application. It defines a bounded,
state-scoped rollout that must remain disabled until its implementation,
regression coverage, dry-run evidence, and rollback verification are reviewed.

## Proven baseline

The committed baseline includes:

- national read-only validation of 654,285 NWDP source features
- 654,093 source geometries valid without repair
- 192 source geometries classified as repairable with `make_valid()`
- zero manual-review or CRS/reimport blockers
- validation metadata dry-run committed in `faaa666`
- disabled validation metadata guard committed in `fa396ea`
- tiny-fixture apply committed in `110ce32`
- tiny-fixture apply, idempotency, wrong-token rejection, and exact rollback
  regression passed
- source files, runtime eligibility, candidates, runtime tables, LGD geography,
  runtime lookup, and Android behavior remained unchanged

## Decision

The next implementation may validate metadata for one state at a time in
batches of no more than 500 rows.

It may process only source features classified as `VALIDATED_NO_REPAIR`.

It must not process `REPAIRABLE_MAKE_VALID`, `VALIDATION_REVIEW`, missing,
misaligned, or checksum-mismatched features.

Broad and national validation metadata application remains disabled.

## Initial rollout scope

The first proposed state is Andaman and Nicobar Islands because:

- its persistent GeoJSON source is available
- its database import batch aligns exactly by `source_feature_index`
- the source checksum is known
- it contains 669 source features
- 660 are valid without repair
- 9 require separate geometry-repair handling
- the tiny-fixture lifecycle has already been proven on source feature index 0

Pinned source:

- state slug: `andaman_and_nicobar_islands`
- state name: `Andaman and Nicobar Islands`
- source feature count: 669
- source checksum:
  `46236e51de89a034b99863600b9f46d24a4ed3e01905362fc90ac4b73de20591`
- aligned import batch:
  `0a93be10-e508-50b9-97ba-b43659899e9b`

## Batch policy

Each apply invocation must require:

- exactly one state
- exactly one aligned import batch
- exact source checksum
- explicit start position or deterministic continuation cursor
- row limit between 1 and 500
- dry-run report checksum
- explicit validation-metadata policy flag
- rollback or supersession token
- dry-run review confirmation
- admin confirmation
- named operator
- output directory for JSON and CSV audit

Rows must be selected deterministically by:

1. aligned import batch
2. current status `NOT_VALIDATED`
3. classification `VALIDATED_NO_REPAIR`
4. ascending `source_feature_index`
5. bounded row limit

The apply must record the exact selected source-feature IDs before mutation.

## Allowed target

The only mutable table is:

`geography_boundary_source_features`

The only fields permitted to change are:

- `source_geometry_hash`
- `source_bbox`
- `transformed_bbox`
- `transformed_centroid`
- `geometry_validation_status`
- validation-specific audit metadata

The allowed status transition is:

`NOT_VALIDATED -> VALIDATED`

No other status transition is authorized by this rollout.

## Explicitly forbidden changes

The rollout must not change:

- raw or persistent source GeoJSON files
- source feature identity
- import batch identity
- source feature index
- source codes or names
- source properties
- source geometry coordinates
- `eligible_for_runtime_after_promotion`
- candidate review status
- candidate promotion status
- candidate activation
- project boundary matches
- runtime sets
- runtime features
- runtime crosswalks
- runtime promotion events
- runtime lookup configuration
- LGD geography
- PIN-code geography
- Android behavior

## Geometry-repair separation

Rows classified as `REPAIRABLE_MAKE_VALID` must be excluded.

This rollout does not call `make_valid()` for persisted output and does not
store repaired geometry.

The 192 nationally repairable geometries remain governed by the separate
geometry-repair design and apply guard.

Geometry validation and geometry repair are separate operations:

- validation metadata records evidence about unchanged source geometry
- repair creates or selects different geometry and requires separate review
- neither operation grants runtime eligibility
- neither operation promotes a boundary candidate

## Hash and transformation policy

Geometry hashes must use:

`NWDP_GEOJSON_GEOMETRY_CANONICAL_V1`

The hash input is the canonical raw GeoJSON geometry object serialized with:

- UTF-8
- sorted keys
- compact separators
- no ASCII coercion

Coordinate transformation must use:

- source CRS declared by the pinned GeoJSON
- target CRS `EPSG:4326`
- `always_xy=True`
- full geometry transformation
- transformed geometry validity check
- India-bounds plausibility check

A row cannot become `VALIDATED` if any check fails.

## Idempotency

A deterministic apply identity must include:

- schema version
- state
- import batch ID
- source checksum
- dry-run report checksum
- source feature ID
- rollback token

Replaying the same approved batch must:

- change zero rows
- report `IDEMPOTENT_NO_OP`
- leave all database counts unchanged
- preserve the original apply evidence
- write a new invocation audit without duplicating mutation evidence

Rows already `VALIDATED` outside the approved apply identity must not be
silently adopted into the batch.

## Audit model

Before a bounded apply is enabled, add a dedicated validation metadata event
table or an equivalent immutable audit mechanism.

Each event must contain:

- event ID
- source feature ID
- import batch ID
- state
- source feature index
- source checksum
- dry-run report checksum
- hash algorithm
- before values
- planned values
- after values
- apply status
- rollback token
- applied by and applied at
- rollback status
- rolled back by and rolled back at
- schema version
- active/superseded state

The event identity must be unique for the approved source feature, source
checksum, dry-run checksum, and rollback token.

## Rollback

Rollback must require:

- the original rollback token
- the same state and import batch
- the same source checksum
- the exact active apply event
- admin confirmation
- named operator

Rollback must restore exactly:

- previous geometry hash
- previous source bounding box
- previous transformed bounding box
- previous transformed centroid
- previous validation status
- previous metadata

Rollback must not infer previous values from defaults.

After rollback:

- selected rows must match their pre-apply snapshots
- state and national counts must return to baseline
- apply events must remain as immutable rolled-back evidence
- a second rollback must be an idempotent no-op

## Transaction policy

Each bounded batch must execute in one database transaction.

The transaction must fail completely if:

- selected count differs from the approved dry-run
- any source feature ID differs
- any current status differs
- any source checksum differs
- any planned hash differs
- any transformed metadata differs
- any row would change runtime eligibility
- affected row count differs from the approved count
- audit-event persistence fails

Partial success is forbidden.

## Required guardrails

For a validation metadata apply:

- `db_writes_attempted=true`
- `source_features_changed=true`
- `validation_metadata_written=true`

The following must remain false:

- `source_files_changed`
- `geometry_repair_persisted`
- `source_runtime_eligibility_changed`
- `boundary_candidates_promoted`
- `boundary_candidates_activated`
- `project_boundary_matches_written`
- `runtime_tables_written`
- `runtime_lookup_enabled`
- `lgd_geography_overwritten`
- `android_behavior_changed`

## Required regression coverage

Before enabling the first bounded state batch, regressions must prove:

- invocation without apply intent is rejected
- missing state scope is rejected
- missing or mismatched checksum is rejected
- missing dry-run checksum is rejected
- row limit above 500 is rejected
- missing rollback token is rejected
- missing review or admin confirmation is rejected
- misaligned source/database identity is rejected
- repair-required rows are excluded
- validation-review rows are excluded
- only approved fields change
- runtime eligibility remains false
- candidate and runtime counts remain unchanged
- first apply changes exactly the approved number of rows
- repeated apply changes zero rows
- wrong-token rollback is rejected
- rollback restores exact row snapshots
- repeated rollback changes zero rows
- failure during a batch rolls back the entire transaction
- source checksum and modification time remain unchanged
- Android behavior remains unchanged

## Proposed implementation sequence

1. Add a read-only bounded state batch planner.
2. Add an immutable validation metadata apply-event schema.
3. Add a disabled bounded state apply guard.
4. Run the planner for Andaman and Nicobar Islands.
5. Review selected IDs and exclude all repair-required rows.
6. Implement a fixture-sized multi-row transaction regression.
7. Prove apply, idempotency, failure rollback, explicit rollback, and repeated
   rollback.
8. Keep the real state apply disabled pending review of all evidence.
9. Only then consider one administratively approved batch of at most 500 rows.

## Readiness decision

Ready now:

- bounded state planner design
- dry-run implementation
- tiny-fixture lifecycle proof
- apply-event schema design
- regression design

Not ready:

- bounded state real apply
- broad validation metadata apply
- geometry repair persistence
- runtime eligibility changes
- candidate promotion or activation
- runtime boundary promotion
- runtime lookup enablement
- Android behavior change

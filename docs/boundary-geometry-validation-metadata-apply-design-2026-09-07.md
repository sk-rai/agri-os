# Boundary geometry validation metadata apply design

Status date: 2026-09-07
Status: design baseline; real broad apply disabled

## Purpose

Define a guarded workflow for recording source-file geometry validation results
in `geography_boundary_source_features`.

This workflow records validation metadata only. It does not overwrite source
GeoJSON, store runtime polygons, promote candidates, enable lookup, modify LGD,
or change Android behavior.

## Evidence baseline

National read-only validation covered all 654,285 NWDP source features:

- 654,093 valid without repair
- 192 invalid but repairable in memory with `make_valid()`
- 0 manual-review blockers
- 0 reimport or CRS-review blockers
- 654,285 valid after in-memory transformation
- 654,285 inside India bounds after transformation

Evidence is recorded in
`docs/boundary-geometry-national-validation-evidence-2026-09-07.md`.

## Existing database posture

`geography_boundary_source_features` currently contains:

- 10 `VALIDATED` rows
- 654,275 `NOT_VALIDATED` rows
- 0 explicitly invalid rows
- 0 runtime-eligible source rows

`NOT_VALIDATED` must never be interpreted as confirmed invalid geometry.

## Allowed target

The only proposed mutable table is:

`geography_boundary_source_features`

Allowed columns:

- `source_geometry_hash`
- `source_bbox`
- `transformed_bbox`
- `transformed_centroid`
- `geometry_validation_status`
- validation-specific keys inside `metadata`
- `updated_at`

No other source-feature fields may change.

## Validation statuses

Proposed statuses:

- `VALIDATED`: source geometry is valid and transformed geometry passes checks.
- `REPAIR_REQUIRED`: source geometry is invalid but safely repairable in memory.
- `VALIDATION_REVIEW`: geometry requires manual, CRS, bounds, or reimport review.
- `NOT_VALIDATED`: validation has not been recorded.

A `REPAIR_REQUIRED` row is not runtime-ready. In-memory repairability alone does
not permit runtime promotion.

## Runtime eligibility separation

`eligible_for_runtime_after_promotion` must remain `false` during validation
metadata apply.

Runtime eligibility requires a separate reviewed workflow after:

- validation metadata is applied;
- repaired geometry handling is approved;
- candidate and village linkage is reviewed;
- rollback/supersession policy is approved.

## Identity and matching

A source-file feature must match a database row using:

- source system;
- import batch;
- state/UT;
- `source_feature_index`;
- source village code where available.

The apply must reject missing or ambiguous matches.

The unique database boundary remains:

`(import_batch_id, source_feature_index)`

## Dry-run requirements

The dry-run must:

- require explicit state/UT scope;
- accept optional district scope;
- enforce a maximum-row limit;
- reopen the persistent source GeoJSON;
- validate source and transformed geometry;
- calculate planned hashes, bounds, centroid, and status;
- compare planned values with current database values;
- report insert/update/no-change/review counts;
- emit JSON and CSV;
- perform no database writes.

## Apply prerequisites

Any future apply must require:

- `--apply`;
- state/UT scope;
- validation policy confirmation;
- source checksum confirmation;
- maximum-row cap;
- rollback/supersession token;
- admin confirmation;
- successful dry-run review.

Broad national apply remains disabled until tiny-fixture apply and rollback
regressions pass.

## Idempotency

Reapplying identical validation evidence must produce no database change.

The idempotency identity must include:

- source-feature ID;
- source-file SHA-256;
- source-geometry hash;
- planned validation status;
- validator schema version.

## Audit and rollback

Before-values must be retained for every changed row:

- source geometry hash;
- source and transformed bounds;
- transformed centroid;
- validation status;
- validation metadata;
- update timestamp where required.

Rollback must be token-scoped and restore only rows written by the matching
apply event.

A dedicated validation event/audit table should be preferred over embedding
the entire rollback record in source-feature metadata.

## Guardrails

Dry-run guardrails must remain:

- `db_writes_attempted=false`
- `source_files_changed=false`
- `source_features_changed=false`
- `geometry_repair_persisted=false`
- `source_runtime_eligibility_changed=false`
- `boundary_candidates_promoted=false`
- `boundary_candidates_activated=false`
- `runtime_tables_written=false`
- `runtime_lookup_enabled=false`
- `lgd_geography_overwritten=false`
- `android_behavior_changed=false`

A future tiny-fixture apply may set only `db_writes_attempted` and
`source_features_changed` to true. Every runtime, candidate, LGD, source-file,
and Android guardrail must remain false.

## Implementation sequence

1. Implement a read-only state-scoped metadata dry-run.
2. Add regression coverage using a tiny fixture.
3. Add a disabled apply guard.
4. Design a dedicated validation audit-event table.
5. Implement one-feature apply, idempotency, and rollback regression.
6. Review national evidence again before considering any broader apply.
7. Keep runtime eligibility and runtime promotion as separate workflows.

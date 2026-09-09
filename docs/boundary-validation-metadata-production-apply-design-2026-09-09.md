# Boundary validation metadata production apply design

Status date: 2026-09-09

## Purpose

This document defines the production-shaped bounded apply contract for NWDP
boundary geometry validation metadata.

It builds on the completed read-only national validation, bounded state
planner, immutable event schema, disabled bounded apply guard, and three-row
transaction lifecycle proof.

This design does not authorize a real apply.

## Evidence baseline

The relevant committed controls are:

- bounded state rollout design: `93bd4a6`
- bounded state planner: `edfca74`
- planner formatting cleanup: `cf97886`
- validation metadata event schema: `8496c39`
- disabled bounded apply guard: `95b578b`
- bounded control roadmap evidence: `6ea3d47`
- multi-row transactional lifecycle proof: `2e8a111`

The three-row lifecycle regression proved:

- rejection when required confirmation is absent
- atomic rollback after a forced mid-batch failure
- successful source-row and event-row writes in one transaction
- exact affected-row accounting
- deterministic apply idempotency
- rejection of a rollback with an incorrect token
- exact restoration from immutable event `before_values`
- deterministic rollback idempotency
- preservation of source-file checksum and modification time
- restoration of the database fixture baseline after regression cleanup

## Existing disabled implementation

The production-shaped disabled implementation is:

`backend/scripts/apply_boundary_geometry_validation_metadata_bounded_state_disabled.py`

Its regression is:

`backend/scripts/test_boundary_geometry_validation_metadata_bounded_state_apply_disabled_guard.py`

The disabled implementation validates the complete request and reviewed plan
before returning:

`BOUNDED_STATE_VALIDATION_METADATA_APPLY_DISABLED_BY_POLICY`

Even a fully confirmed invocation performs no database writes.

A duplicate disabled implementation must not be introduced. Future enabled
work should preserve this guard as the default policy boundary.

## Allowed scope

A future enabled bounded apply may operate only on:

`geography_boundary_source_features`

The only fields eligible for mutation are:

- `source_geometry_hash`
- `source_bbox`
- `transformed_bbox`
- `transformed_centroid`
- `geometry_validation_status`
- `metadata`

Every selected row must:

- belong to one explicitly named state or UT
- belong to the import batch recorded in the reviewed plan
- match the pinned source-file checksum
- have `NOT_VALIDATED` as its current database status
- have `VALIDATED` as its planned status
- have classification `VALIDATED_NO_REPAIR`
- have `runtime_eligibility_change_planned=false`
- remain runtime-ineligible
- contain a canonical source geometry hash
- contain transformed bounding-box metadata
- contain transformed centroid metadata

A batch must contain at least one and at most 500 rows.

## Prohibited scope

The bounded validation metadata apply must not:

- persist repaired geometry
- include `REPAIR_REQUIRED` rows
- include `VALIDATION_REVIEW` rows
- change `eligible_for_runtime_after_promotion`
- promote or activate boundary candidates
- write boundary runtime sets, features, or crosswalks
- enable runtime boundary lookup
- overwrite LGD geography
- change Android behavior
- enable a broad state or national apply
- infer runtime readiness from geometry validity

Geometry repair and runtime eligibility remain separate governed workflows.

## Required inputs

A future enabled invocation must require:

- explicit state slug
- explicit state or UT name
- reviewed planner JSON
- exact canonical plan checksum
- pinned source-file SHA-256
- rollback or supersession token
- named operator
- explicit apply intent
- bounded-write policy flag
- dry-run review confirmation
- event-schema review confirmation
- batch-specific administrative approval confirmation

Generic approval is insufficient. Approval must identify the exact plan
checksum and source checksum.

## Preflight validation

Before opening a write transaction, the implementation must verify:

1. The plan schema version is supported.
2. The plan reports `healthy=true`.
3. The plan contains between 1 and 500 rows.
4. The recorded row count equals the actual row count.
5. The canonical plan-content checksum matches the supplied checksum.
6. The state scope matches the invocation.
7. The source checksum matches the invocation and current source file.
8. The import batch identity is unique and aligned.
9. Every row is `VALIDATED_NO_REPAIR`.
10. Every row plans `VALIDATED`.
11. No row plans a runtime eligibility change.
12. The validation event schema is present.
13. No conflicting active validation event exists.
14. All required confirmations are present.
15. The exact plan has a batch-specific approval artifact.

Any failed preflight check must produce a non-zero exit, JSON and CSV audit
evidence, and zero database writes.

## Transaction contract

The enabled apply must use one database transaction for the complete batch.

Within that transaction it must:

1. Lock every selected source row.
2. Recheck source-feature identity and import-batch identity.
3. Recheck that the current status remains `NOT_VALIDATED`.
4. Recheck that runtime eligibility remains false.
5. Insert one inactive `PLANNED` event per row.
6. Update only the approved validation metadata fields.
7. Verify that exactly one source row changed for each planned row.
8. Record the resulting values in each event.
9. Mark each event `APPLIED` and active.
10. Verify exact batch-level source and event counts.
11. Commit only after every assertion succeeds.

Any exception must roll back all source-row and event-row changes.

## Idempotency

A repeated apply with the same:

- source feature IDs
- source checksum
- plan checksum
- rollback token

must return `IDEMPOTENT_NO_OP`.

It must change zero source rows, change zero event rows, and preserve all
database counts.

A partial or conflicting event set must be rejected. It must never be treated
as an idempotent success.

## Rollback contract

Rollback must require the exact rollback token and plan checksum.

It must:

- find the complete active event set
- lock the affected source rows and events
- restore every approved source field from immutable `before_values`
- mark all corresponding events `ROLLED_BACK`
- make all corresponding events inactive
- record the named rollback operator and timestamp
- preserve the event rows as immutable lifecycle evidence
- execute as one transaction

A wrong token, partial event set, or mismatched plan must be rejected without
writes.

A repeated completed rollback must return `IDEMPOTENT_ROLLBACK_NO_OP`.

## Initial production candidate

The first candidate for separate administrative review is Andaman and Nicobar
Islands bounded batch 1.

Pinned evidence:

- source feature count: 669
- valid without repair: 660
- repair required: 9
- validation review: 0
- selected batch rows: 500
- remaining safe rows after batch: 160
- source checksum:
  `46236e51de89a034b99863600b9f46d24a4ed3e01905362fc90ac4b73de20591`
- plan checksum:
  `822ed7575c67de714e1599de243d7ecbd77828471de308c1a087ff38de12ef4d`

All 9 `REPAIR_REQUIRED` rows are excluded.

This candidate is not approved by this document.

## Administrative approval artifact

Before an enabled implementation may accept the initial candidate, a committed
approval artifact must record:

- state and import batch
- source checksum
- plan checksum
- selected row count
- first and last source-feature indexes
- reviewed exclusions
- operator
- approver
- approval timestamp
- rollback token
- rollback procedure
- expected before and after counts
- confirmation that runtime eligibility remains false
- confirmation that downstream runtime and Android behavior remain unchanged

The approval artifact must be reviewed separately from the implementation.

## Current decision

Ready:

- production-shaped apply contract
- read-only bounded planning
- full disabled guard
- immutable event schema
- three-row atomic transaction proof
- apply and rollback idempotency proof
- forced-failure rollback proof

Not ready:

- enabled 500-row apply
- broad state apply
- national validation metadata apply
- repair persistence
- runtime eligibility changes
- candidate promotion or activation
- runtime boundary lookup
- Android behavior changes

The next implementation step is to create and review a batch-specific
administrative approval artifact. Until that review is complete, the bounded
state apply remains disabled.

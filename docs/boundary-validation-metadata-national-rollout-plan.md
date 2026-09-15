# Boundary Validation Metadata National Rollout Plan

Status: implementation planning
Mode: read-only until separately authorized

## Objective

Generalize the proven bounded-state validation-metadata process across all 36
available Indian state and Union Territory source streams.

The national process coordinates state batches. It does not use one national
database transaction.

## Proven baseline

- 36 pinned state/UT GeoJSON sources
- 36 aligned database import batches
- zero multi-batch states
- zero source-index alignment failures
- 654,285 source features
- 510 currently validated rows
- 653,775 rows currently not validated
- 500 active approved Andaman validation events
- zero runtime-eligible source rows
- zero active or promoted boundary candidates
- 192 geometries remain in the separate repair workflow

## Transaction boundary

Every apply and rollback transaction remains state-scoped and batch-scoped.

A failure in one state must:

- roll back that state batch atomically
- stop later scheduled work unless explicitly resumed
- preserve previously verified state batches
- leave other state streams unchanged

## Batch policy

- maximum 500 rows per batch
- deterministic ascending `source_feature_index`
- only `NOT_VALIDATED` rows
- only `VALIDATED_NO_REPAIR` classification
- exact source checksum required
- exact plan checksum required
- unique state/batch rollback token
- immutable per-row validation events
- explicit operator, approver and authorization reference
- idempotent replay and rollback

## National planner outputs

The planner must produce:

1. National JSON execution index.
2. National CSV state/batch summary.
3. One exact JSON plan for the next eligible batch of every state.
4. One exact CSV row manifest for each generated batch.
5. Per-state source checksum.
6. Per-batch plan checksum and deterministic batch ID.
7. Per-state remaining eligible count and estimated batch count.
8. Explicit repair, review and blocked counts.
9. Per-state rollback-token proposal.
10. Before/after database count proof showing no writes.

## Durable run storage

Operational planner output is written under:

`data/staged/core_stack/boundary_validation_metadata_rollout_runs/<run-id>/`

This generated run root is ignored by Git but persists across terminal closure,
shutdown and restart.

- `--run-id` creates or identifies a stable run.
- `--resume` continues an existing run after validating its checkpoints.
- `--force` deliberately regenerates a run and cannot be combined with resume.
- `--output-dir` is retained for isolated regression runs.
- Disposable regression artifacts may use `/tmp`; operational artifacts must not.

Each completed state directory contains:

- the bounded state plan in JSON and CSV form
- a durable `checkpoint.json`
- pinned state, import-batch, source-checksum and database-baseline identity
- the deterministic plan checksum and batch ID

Resume behavior is fail closed:

- valid checkpoints are reused without recomputing the state plan
- missing or incomplete checkpoint pairs are rejected
- changed source, database baseline, state identity or batch limit is rejected
- altered plan or checkpoint checksums are rejected
- `--force` is required for deliberate regeneration
- execution status is reported separately as `GENERATED`, `RESUMED`,
  `GENERATION_FAILED` or `CHECKPOINT_REJECTED`
- resume status and filesystem paths do not affect deterministic plan checksums

## Planner execution model

The first planner run creates wave 1:

- at most one next batch per state
- at most 500 rows in each state batch
- all 36 states assessed
- states with no remaining safe rows recorded as complete
- no database mutation

Later planner runs may create additional waves using the prior accepted cursor
for each state.

A later wave must not silently skip or adopt rows changed outside its accepted
predecessor plan.

## Stop conditions

The planner must fail or mark the state blocked for:

- source checksum mismatch
- missing source file
- missing or duplicate import batch
- source/database feature-count mismatch
- source-index gap or duplicate
- unknown geometry classification
- database mutation during planning
- runtime eligibility change
- candidate activation or promotion
- runtime-table change
- LGD geography change
- Android behavior change

## Generic authorized state-batch engine

The generic engine is implemented separately from the historical
Andaman-pinned executor. It contains no embedded state, source, batch, plan,
operator, approver or rollback-token identity.

Every invocation must independently pin:

- a state-batch authorization JSON document
- the authorization document checksum
- the national plan checksum
- the bounded state plan checksum
- the source checksum
- the rollback token
- operator, approver and approval reference
- explicit apply or rollback mode
- write-policy, review and administrator confirmations

Authorization is fail closed. The engine rejects proposed, malformed, altered,
oversized or unsafe authorization documents. Geometry repair, runtime
eligibility, candidate writes, runtime-table writes, runtime lookup and Android
behavior remain prohibited.

Fixture regressions prove:

- forced mid-batch failure rolls back source and event writes atomically
- an exact authorized batch can be applied and rolled back
- apply and rollback retries are idempotent
- rollback restores exact source-row values
- rollback evidence is immutable and inactive
- the outer fixture transaction leaves no persistent database changes

The generic engine does not make the national proposal executable. National
apply remains unauthorized until a separately reviewed authorization changes
the explicit authorization and readiness fields.

## National execution orchestrator authorization gate

The national orchestrator currently implements a fail-closed authorization
gate and does not dispatch state transactions.

The gate verifies:

- exactly one of apply or rollback is requested
- the externally supplied manifest checksum
- the externally supplied national-plan checksum
- all 36 unique state, batch, plan and rollback-token identities
- a maximum of 500 rows per state transaction
- global apply or rollback authorization
- matching per-state apply or rollback authorization
- operator, approver, approval reference and approval timestamp
- stop-on-first-failure and one-state-batch-per-transaction policy
- exact plan, source, import-batch and rollback-token requirements
- explicit plan, integrity, rollback and administrator confirmations

The manifest checksum includes status, evidence, authorization, execution
policy, readiness and deterministic state identities. Changing authorization
or readiness therefore invalidates the externally pinned checksum.

Unsafe policy permissions remain prohibited. A fully authorized synthetic
manifest reaches the explicit `NATIONAL_EXECUTION_ENGINE_NOT_ENABLED` gate.
The real proposal remains `PROPOSED_NOT_AUTHORIZED` and is rejected before
any state execution or database write.

Immediately before dispatch, every state artifact is revalidated against:

- manifest state and import-batch identity
- current source-file SHA-256
- bounded-plan content checksum
- durable checkpoint plan checksum and batch ID
- source feature and validation-status counts
- selected-row count and 500-row ceiling
- first and last source-feature indexes
- ordered, duplicate-free indexes
- `VALIDATED_NO_REPAIR` classification
- `NOT_VALIDATED` to `VALIDATED` transition
- unchanged runtime eligibility

The 36-state operational artifact audit validates all 15,308 wave-1 rows with
no artifact errors. The manifest remains non-authorizing.

## Apply authorization boundary

Planner completion does not authorize application.

A future national execution authorization must pin:

- national index checksum
- included state batches
- operator and approver
- authorization reference
- rollback-token namespace
- stop-on-first-failure policy
- post-state and final national reconciliation

## Explicit exclusions

This rollout does not:

- repair geometry
- alter source geometry
- grant runtime eligibility
- activate or promote candidates
- modify project boundary assignments
- write runtime boundary tables
- enable runtime lookup
- alter Android behavior
- overwrite LGD or PIN-code geography

## Implementation sequence

1. Implement and regress the read-only national wave planner.
2. Generate wave-1 plans for all 36 state streams.
3. Review national and per-state checksums and exclusions.
4. Implement a generic state-batch apply engine without embedded Andaman constants.
5. Prove generic apply and rollback using isolated fixtures.
6. Produce a separately reviewable national execution authorization.
7. Apply state batches independently with stop-on-first-failure.
8. Reconcile exact national counts and immutable events.

## Resumable national dispatch

The authorized national execution path dispatches exactly one state batch at a
time through the generic authorized state-batch engine. Apply order is ascending
by the manifest's deterministic state sequence. Rollback order is the exact
reverse.

Each state receives a durable directory containing:

- the derived state authorization document;
- the state engine audit and row report;
- an atomic dispatch checkpoint pinned to the manifest, national plan, state
  batch, source, rollback token and authorization checksums.

A successful resume reuses only checkpoints whose checksum, identity and
underlying state-engine audit all remain valid. Missing evidence, stale
identity, modified audit data or a failed state stops the national dispatcher
before the next state begins. Existing checkpoints require explicit
`--resume`; they are never silently overwritten.

The dispatcher validates all 36 source files, plans and planning checkpoints
before invoking the first state engine process. It also retains the existing
requirements for explicit apply or rollback selection, the national metadata
write flag, plan and integrity review, rollback-procedure review, administrator
confirmation, safe execution policy and complete national and per-state
authorization.

The durable operational proposal remains
`PROPOSED_NOT_AUTHORIZED`. Wiring the dispatcher does not authorize that
proposal. An actual national apply requires a separate checksum-pinned
authorized manifest and an explicit operator command. Runtime promotion,
candidate writes, geometry repair, runtime lookup and Android behavior remain
outside this execution boundary.

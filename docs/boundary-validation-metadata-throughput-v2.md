# Boundary validation metadata throughput V2

Status: implementation foundation only; disconnected from live execution.

## Objective

Drain each state's remaining eligible validation-metadata rows continuously,
without repeating a national planning and authorization cycle for every 500
rows. The target is 25,000 rows per state transaction, with an authorization
ceiling of 50,000 rows.

## Execution model

- Order states by remaining eligible row count so short states finish early.
- Keep one active transaction per state.
- Start with one database writer.
- Permit two writers only after lock, WAL, latency and rollback benchmarks pass.
- Plan the next state chunk while the current chunk is applying.
- Checkpoint after every committed state transaction.
- Continue a state from its last committed source-feature index.
- Retain deterministic identities, checksums, rollback tokens and source
  checksums.

The V2 apply primitive stages an authorization-pinned JSON row set once. It
then uses set-based event insertion, source update and event activation. Every
SQL result count must equal the authorized row count or the transaction must
roll back.

## Guardrails retained

- Only `NOT_VALIDATED` rows classified valid without repair are eligible.
- Runtime eligibility remains false and cannot be changed.
- Geometry repair remains prohibited.
- Candidate writes, activation and promotion remain prohibited.
- Runtime-table writes and runtime lookup enablement remain prohibited.
- Android behavior changes remain prohibited.
- Rollback restores source values from active event snapshots.
- Campaign row budget, transaction ceiling, state identity and writer count
  are authorization-pinned.
- V1 remains unchanged and available for audit and recovery.

## Required gates before national V2 execution

1. PostgreSQL fixture apply, idempotency, forced-failure and rollback tests.
2. Explain/analyze and timing runs at 500, 5,000, 25,000 and 50,000 rows.
3. Observe lock duration, WAL volume, database growth, memory and API latency
   with one writer.
4. Repeat the benchmark with two writers on different states.
5. Use 25,000 by default, or a lower measured safe value. The 50,000 value is
   an authorization ceiling, not the default.
6. Generate and explicitly authorize a new V2 proposal. Existing V1 campaign
   authorizations cannot authorize V2 execution.

## Benchmark evidence

Rollback-only PostgreSQL benchmarks were run against Uttar Pradesh with the
outer transaction always rolled back and post-run source, event, candidate,
runtime and eligibility counts verified unchanged.

| Rows | Planning | Apply | Rollback | Transaction | Apply rate |
|---:|---:|---:|---:|---:|---:|
| 500 | 83.5 s | 1.4 s | 0.1 s | 1.5 s | 354 rows/s |
| 5,000, original planner | 94-140 s | 6.0-7.6 s | 1.3-1.4 s | 7.6-9.2 s | 658-829 rows/s |
| 5,000, windowed V2 planner | 43.0 s | 7.2 s | 1.1 s | 8.5 s | 690 rows/s |
| 25,000, windowed V2 planner | 67.2 s | 19.3 s | 7.2 s | 27.6 s | 1,298 rows/s |

The 25,000-row transaction generated approximately 505 MB of observed
cluster-wide WAL. This observation can include unrelated PostgreSQL activity
and is not an exact per-transaction measurement.

The benchmark supports 25,000 rows as the initial production transaction
default. The 50,000-row authorization ceiling remains available but is not
approved as a default and was intentionally not benchmarked.

In throughput V2 mode, the planner classifies only the selected window.
Therefore `remaining_valid_not_validated_count` is retained for schema
compatibility but explicitly marked as an upper bound. The authoritative V2
field is `remaining_not_validated_candidate_upper_bound_count`. A final state
drain may encounter repair-required rows and return fewer selected rows than
the configured transaction target.

# Queued `CROP_ACTIVITY CREATE` backend implementation proposal

Status: proposed implementation design for independent review. This document
does not authorize source changes, schema migration, tests, API calls,
deployment, Android enablement, or activity submission.

Governing contract:
`docs/backend-queued-crop-activity-create-contract-decision.md`.

`PRODUCTION_RECOVERY_LIVE_NOT_APPROVED` remains closed.

## Scope and non-goals

This proposal defines the smallest backend change that can make direct and
queued `CROP_ACTIVITY CREATE` use one canonical command while preserving exact
identity, effects, replay, and response correlation.

It does not enable Android activity submission. It does not cover activity
update/delete, stage transitions, general sync reconciliation, automatic retry,
automatic conflict resolution, durable domain-event publication, or historical
data repair. Existing activities and processed events are not backfilled or
claimed.

Current source boundaries motivating the proposal are:

- `ActivityCreate` already contains the supported direct fields and optional
  stable activity ID (`backend/app/modules/workflow/api.py:314-344`);
- `CropActivity` persists traceability, dosage, cost, date, GPS, actor, and notes
  (`backend/app/modules/workflow/models.py:380-448`);
- the direct handler performs the fuller validation and business effects
  (`backend/app/modules/workflow/api.py:1946-2101`);
- queued materialization currently applies a different subset and replay rule
  (`backend/app/modules/sync/service.py:1355-1431`); and
- generic sync replay and response identify acceptance by event ID alone
  (`backend/app/modules/sync/service.py:1571-1592,1915-1925`,
  `backend/app/modules/sync/api.py:61-65`).

## Proposed storage

A new migration after revision `070` creates two append-only binding tables and
adds two nullable irrigation columns described below. No existing
`crop_activities` or `sync_processed_events` row value is rewritten.

### `crop_activity_command_bindings`

One row records the authoritative request intent and commit result for one
activity identity:

| Column | Type and constraint | Purpose |
| --- | --- | --- |
| `activity_id` | UUID primary key, FK to `crop_activities.id`, `ON DELETE RESTRICT` | Globally stable activity identity. |
| `tenant_id` | VARCHAR(50), not null | Tenant boundary used in every lookup. |
| `actor_id` | UUID, not null | Original authenticated actor. |
| `farmer_id` | UUID, not null | Original authorized farmer. |
| `crop_cycle_id` | UUID, not null | Exact cycle binding. |
| `origin_kind` | VARCHAR(10), check `DIRECT` or `SYNC` | Entry point that owns replay. |
| `origin_event_id` | UUID, nullable | Required only for `SYNC`; null for `DIRECT`. |
| `intent_version` | VARCHAR(40), not null | Initially `crop_activity_intent.v1`. |
| `intent_canonical` | TEXT, not null | Exact canonical UTF-8 JSON text used for comparison. |
| `intent_sha256` | CHAR(64), not null | Lowercase hash of the canonical UTF-8 bytes. |
| `resolved_stage_id` | UUID, nullable | Stage selected during first materialization. |
| `result_version` | VARCHAR(40), not null | Initially `crop_activity_result.v1`. |
| `result_payload` | JSONB, not null | Original reconstructable committed response. |
| `audit_correlation_id` | UUID, not null | Correlates the one business audit. |
| `created_at` | TIMESTAMPTZ, not null | Commit time. |

Constraints require `origin_event_id IS NULL` for `DIRECT` and non-null for
`SYNC`. Add indexes on `(tenant_id, crop_cycle_id)` and
`(tenant_id, origin_event_id)`. The primary key deliberately remains global so
the same UUID in another tenant cannot create a second activity binding.

The binding table references only the activity row. Farmer/cycle/stage
relationships are validated by the command and retained as immutable values;
this proposal does not restore the offline-blocking foreign keys removed by
migration `070`.

### `crop_activity_sync_event_bindings`

One row binds a queued event to the already defined activity command:

| Column | Type and constraint | Purpose |
| --- | --- | --- |
| `event_id` | UUID primary key, FK to `sync_processed_events.event_id`, `ON DELETE RESTRICT` | Exact sync operation identity. |
| `tenant_id` | VARCHAR(50), not null | Tenant boundary. |
| `actor_id` | UUID, not null | Original authenticated actor. |
| `activity_id` | UUID, not null, unique, FK to `crop_activity_command_bindings.activity_id`, `ON DELETE RESTRICT` | Prevents another event from adopting the activity. |
| `intent_version` | VARCHAR(40), not null | Copy of the compared intent version. |
| `intent_canonical` | TEXT, not null | Exact queued intent representation. |
| `intent_sha256` | CHAR(64), not null | Hash of the canonical text. |
| `outcome` | VARCHAR(20), check `COMMITTED` | Only committed acceptance is stored here. |
| `created_at` | TIMESTAMPTZ, not null | Commit time. |

The unique `activity_id` implements the decision that one activity can have at
most one sync event identity. Rejections and unresolved conflicts do not create
a committed binding row. Their existing processed-event/conflict records remain
operational diagnostics and cannot later be interpreted as committed bindings.

For queued activity CREATE, any globally occupied event ID without this trusted
committed binding is terminally unavailable. Before any business write, the
service performs a global event-ledger and binding lookup under the event lock:

- no processed row and no binding permits first-time processing;
- one consistent `COMMITTED` processed row plus both exact activity/event
  bindings permits replay comparison;
- a processed row in `FAILED`, `CONFLICT`, `DEPENDENCY_MISSING`, or any other
  status without the exact committed bindings returns sanitized
  `EVENT_ID_REUSE`;
- a legacy `COMMITTED` row without the exact bindings returns
  `EVENT_ID_REUSE`;
- a row for another entity, operation, activity, actor, or tenant returns
  `EVENT_ID_REUSE` without disclosing the occupant; and
- a binding without its consistent activity and committed processed rows is an
  internal integrity failure and cannot be repaired in this path.

Queued activity CREATE is excluded from the generic event-ID-only
`filter_already_processed` acceptance shortcut. The activity adapter performs
the disposition above and never updates a diagnostic processed row into a
committed activity binding. This activity-specific rule does not change retry
semantics for other sync entity types.

### Migration and legacy behavior

The migration creates empty binding tables/indexes and the two nullable columns.
It does not backfill existing activities, infer bindings, or alter existing
activity values. An activity without a binding is `LEGACY_UNVERIFIED` for replay
purposes and any attempted identity reuse returns the generic
identity-unavailable conflict.

The same migration adds nullable `irrigation_source VARCHAR(100)` and
`duration_hours DECIMAL(10,2)` columns to `crop_activities`. These fields are
already accepted by the direct DTO but are not currently persisted. Existing
rows remain null. First-slice validation permits them only for
`activity_type=IRRIGATION`; non-irrigation commands with either value reject.
They participate in canonical intent, persistence, result reconstruction, and
exact replay.

Downgrade must fail closed when either binding table contains rows or any
activity has a non-null value in either new irrigation column. Dropping those
records/columns would erase replay authority or accepted activity content and
permit an older application version to use weaker identity rules. A separately
approved export, retention, and application-version rollback procedure is
required before any such downgrade. The migration does not implement repair or
deletion.

## Canonical request intent v1

The backend constructs one internal `CropActivityCreateCommand` after entry
validation. The canonical representation is a JSON object with a fixed complete
key set; optional values are explicit `null`, never omitted.

Canonical encoding rules are:

- UTF-8 without BOM;
- Unicode strings normalized to NFC;
- keys sorted lexicographically, no insignificant whitespace, separators `,`
  and `:`, and non-ASCII characters emitted directly;
- UUIDs as lowercase hyphenated strings;
- dates as ISO `YYYY-MM-DD` strings;
- enum/code fields in their validated canonical case;
- decimal values as normalized base-10 strings at the exact accepted database
  scale, with no exponent and with negative zero normalized to zero;
- floats, NaN, infinity, locale formatting, and binary floating-point strings
  prohibited in the canonical object;
- queued dependency UUIDs retained in their original array order with their
  original multiplicity after each value is normalized to a UUID string; and
- booleans encoded as JSON booleans.

Inputs that require silent precision loss are rejected rather than rounded.
The service stores the exact canonical text and
`sha256(intent_canonical.encode("utf-8"))`. Replay requires matching version,
canonical text, and hash; the hash alone is insufficient.

The canonical object contains:

- tenant, actor, farmer, cycle, activity, requested stage ID and requested stage
  code;
- activity type/date;
- input code/name, input-rule ID, product ID/code, package ID/SKU;
- quantity/unit, applied area/unit, recommended quantity/unit, actual
  quantity/unit, dosage variance reason;
- cost amount/currency, GPS latitude/longitude, irrigation source/duration, and
  notes; and
- for queued origin only: event ID, entity type, operation, client version, and
  the ordered dependency array with retained multiplicity.

Resolved stage identity is not part of request intent when the caller omitted
stage identity. It is retained in the commit result.

Dependency resolution may use a separate deduplicated set, but it must not
replace or rewrite the retained ordered dependency array. Different order or
multiplicity therefore produces a different intent and cannot compare as an
exact replay.

### Exact numeric ingress

The current direct DTO uses binary `float` for several fields. The implementation
must change activity numeric fields to `Decimal` and parse the direct request
body with a strict bounded JSON parser configured with `parse_float=Decimal` and
`parse_int=Decimal` before model validation. Duplicate object keys, NaN,
infinity, exponent/scale outside the accepted contract, booleans in numeric
fields, and silent precision loss reject. This preserves ordinary JSON numeric
syntax without first converting decimals through binary float.

Queued `crop_activity` v1 payloads must encode every non-integral decimal field
as a canonical base-10 JSON string. The activity-specific queued parser rejects
binary-float values before constructing the command. This rule is required only
for the future, still-disabled Android producer; compatibility for existing
non-activity sync entities is unchanged.

Canonicalization is a versioned backend module, not endpoint-local code. Any
future normalization change requires a new intent version; old bindings remain
comparable with their original version.

## Shared command and transaction

Create a backend-owned activity command service used by both entry points. The
service accepts the authenticated principal, normalized command, optional
queued envelope, and SQLAlchemy session. It does not commit independently.

For a first-time command it must, within the caller's transaction:

1. acquire concurrency locks described below;
2. load the exact tenant-scoped cycle and recheck current farmer authorization;
3. validate writability, traceability, catalog eligibility, every supported
   field, and the stage rule;
4. insert exactly one `CropActivity`;
5. flush before applying cost or audit effects;
6. apply the canonical cycle-cost effect once;
7. append one `ACTIVITY_LOGGED` business audit;
8. construct the committed result;
9. insert the activity binding;
10. for queued origin, insert a fresh `COMMITTED` processed-event row and the
    sync-event binding; and
11. flush all rows before leaving the transaction/savepoint.

The direct endpoint commits the enclosing transaction once. Sync executes the
same command, binding writes, processed-event outcome, and business audit inside
its existing per-event savepoint; the batch commit remains outside that
savepoint. Any failure rolls back all business effects for that event.

The current `_materialize_crop_activity_event` becomes an adapter to the shared
command or is removed after callers migrate. It must not retain separate
defaults, validation, replay, cost, or audit logic.

Operational rejection diagnostics may be written only after the business
savepoint rolls back. They use fixed public categories and sanitized metadata;
raw exception text and arbitrary payloads are excluded from API responses and
diagnostic audit metadata.

For queued batches, lock planning occurs once before per-event savepoints. The
batch parser validates identities sufficiently to collect every event UUID,
every queued activity UUID, and every referenced activity cycle UUID without
performing business writes. It then acquires the complete transaction-wide lock
set in the order defined below. Per-event processing may not acquire an earlier
lock class later.

### Batch-wide duplicate and operation preflight

The sync endpoint must not accept `SyncBatchRequest` as an already parsed FastAPI
body for this preflight. A custom ingress boundary reads the raw request body
once, before Pydantic defaults or ordinary binary-float parsing can alter it.

The ingress boundary:

- checks a valid `Content-Length` and rejects immediately when it exceeds 2 MiB,
  but never trusts that header as the enforcement mechanism;
- consumes the ASGI request stream incrementally, adds each chunk's actual byte
  length with overflow-safe arithmetic, and stops reading/retaining data as soon
  as the cumulative count exceeds 2 MiB;
- copies at most the remaining allowed bytes plus one boundary byte from each
  delivered chunk into an application buffer, releases the chunk reference, and
  keeps that buffer bounded to 2 MiB plus one byte; it never calls an API that
  first buffers the complete body; an absent, understated, overstated,
  malformed, or conflicting length header cannot bypass the actual streamed-byte
  limit;
- rejects over-limit input before UTF-8 decoding or JSON construction, does not
  log or persist buffered bytes, and does not attempt to drain or parse the
  remaining body as an application request;
- requires strict UTF-8 without BOM;
- uses a strict JSON parser with maximum depth 32, maximum 100,000 value nodes,
  and maximum 262,144 UTF-8 bytes for any one string;
- rejects duplicate object member names at every depth;
- retains object-member presence separately from value, so omission, explicit
  null, false/zero, and an explicit default remain distinguishable;
- represents every JSON number with its original token plus an exact arbitrary-
  precision decimal value, never a binary float;
- rejects NaN, infinity, invalid numeric grammar, and trailing content; and
- requires one top-level object containing an `events` array with 1–100 object
  entries before deeper validation.

Before grouping or collapse, **every occurrence** independently passes
presence-aware envelope-schema validation, UUID/operation/type validation,
field-specific token validation, and ordinary Pydantic business-shape validation
using values derived from the lossless tree. Any invalid occurrence rejects the
entire HTTP batch even if another occurrence with the same event ID would be
valid. No authorization or database mutation occurs in this validation phase.

Only after all occurrences pass may preflight logically deduplicate them. Each
surviving logical event is then converted exactly once into the internal event
model for authorization and processing. The request models must forbid unknown
envelope fields rather than silently discard them. Pydantic defaults may support
later business processing, but they never participate in duplicate comparison
and cannot rewrite the retained presence-aware envelope used for binding.

Before authorization partitioning, lock acquisition, dependency processing, or
any database mutation, preflight groups all received occurrences by a strictly
validated, globally normalized event UUID.

For duplicate comparison it constructs a deterministic, presence-aware
`sync_envelope.v1` representation containing entity type, entity ID, operation,
payload, client version, dependency array in original order/multiplicity, and
metadata. Object key order is insignificant; member presence, scalar JSON type,
exact numeric token and decimal value, array order/multiplicity, null versus
absence, and every scalar value remain significant. Numeric comparison uses both
the original valid JSON token and its arbitrary-precision value. Therefore `1`,
`1.0`, and `1e0` do not collapse even when downstream mathematics would be
equivalent, and distinct values that collide after binary-float conversion also
remain different. Tokens are retained only in bounded process memory for
validation/comparison and are never logged.

- If every occurrence in a group is exactly identical, the group is collapsed
  to one logical event before authorization and processing. It produces exactly
  one accepted, conflict, or failed outcome and at most one correlated detail.
- If any occurrence differs, the entire HTTP batch is rejected at preflight with
  fixed `DUPLICATE_EVENT_ID_CONFLICT`. No event in that request is authorized,
  locked, materialized, audited, or written to the processed-event ledger. This
  is a conclusive request rejection, not a partial batch result.
- `total_processed` counts logical deduplicated events. For ordinary batches it
  is unchanged; an exact duplicate group contributes one.

This rule is independent of input order. In particular, an activity/generic
pair sharing an event ID is conflicting and rejects the whole request before
the activity occurrence can create a business effect.

The same preflight enforces this slice's operation boundary. Queued
`CROP_ACTIVITY UPDATE` and `CROP_ACTIVITY DELETE` are unsupported and receive a
fixed `ACTIVITY_OPERATION_UNSUPPORTED` rejection before any event in the batch
mutates business state, whether the operation is alone or mixed with CREATE.
The whole HTTP batch is rejected; other events are not partially processed.
They are not routed to the existing activity materializer. Enabling either
operation requires a separate contract and lock/effect review.

Activity classification recognizes both currently routed spellings,
`crop_activity` and `cropactivity`, after case normalization only. Whitespace,
punctuation, or any other alias rejects. Classification is used solely to choose
the activity branch and operation prohibition; it does not rewrite the retained
envelope. The exact submitted entity-type string remains in
`sync_envelope.v1`, the queued request-intent binding, and the client-verifiable
digest. Thus changing between the canonical spelling and legacy alias under one
event ID is not an exact duplicate or exact replay. UPDATE/DELETE under either
recognized spelling is rejected at the same whole-batch preflight boundary and
cannot reach the generic `cropactivity` materializer alias.

### Activity branch ownership in `process_sync_batch`

Queued `CROP_ACTIVITY CREATE` branches before the generic already-processed
filter, generic conflict detector, generic materializer, and generic audit and
failure handlers. The activity branch exclusively owns all effects for that
event:

- dependency disposition;
- canonical command execution;
- `CropActivity`, cycle-cost, and `ACTIVITY_LOGGED` business effects;
- the fresh `SyncProcessedEvent(COMMITTED)` row and both binding rows;
- one sanitized operational `SYNC_COMMIT` audit with an empty payload and only
  event ID, activity ID, outcome, intent version, and intent hash metadata;
- terminal sanitized rejection diagnostics; and
- the legacy accepted event ID plus its correlated `accepted_details` entry.

The generic loop must not write another processed outcome, `SYNC_COMMIT`,
`SYNC_FAILED`, conflict row, audit, or response entry for an activity event
handled by this branch.

For first commit, the business effects, business audit, processed outcome,
bindings, and sanitized operational `SYNC_COMMIT` are flushed in the same
per-event savepoint. Only after that savepoint succeeds does the in-memory result
receive its accepted ID/detail. An exact replay writes no audit or ledger row and
returns the retained correlated detail. The HTTP response is constructed only
after the outer batch commit succeeds; commit failure returns no acceptance.

On activity rejection, the business savepoint rolls back first. The branch may
then retain only a fixed processed status and a sanitized operational diagnostic
with empty payload, fixed error/detail code, event/activity IDs, and observation
time. It must not retain arbitrary payload, raw exception text, business audit,
cost, activity, binding, or conflict-resolution authority. For this first slice,
activity identity/content conflicts are terminal failures; they do not enter the
generic `SyncConflict` workflow. A prior diagnostic row cannot later advance to
committed activity state.

Reciprocal protection runs before the generic event-ID shortcut for **every**
incoming event. If `crop_activity_sync_event_bindings` already owns the global
event ID, only the exact matching queued activity CREATE is routed to the
activity replay branch. Any generic entity, other operation, tenant, actor, or
activity using that event ID receives sanitized `EVENT_ID_REUSE` before generic
acknowledgement or mutation. A binding/ledger inconsistency fails closed as an
internal integrity error. This prevents a generic event from adopting an
activity-bound event ID; global locking alone is not treated as enforcement.

## Concurrency and collision strategy

Use PostgreSQL transaction-scoped locks before any replay lookup or insert. Lock
classes and order are:

1. global event-identity advisory locks for **all** events in the batch, sorted
   by UUID bytes;
2. global activity-identity advisory locks for every admitted activity writer
   (currently queued activity CREATE only), sorted by UUID bytes; and
3. global cycle-identity advisory locks for every cycle affected by any cycle
   writer in the mixed batch, sorted by UUID bytes; and
4. tenant-scoped `CropCycle` row locks (`SELECT ... FOR UPDATE`) for those
   existing cycles in the same sorted order.

Use distinct fixed namespaces for event, activity, and cycle advisory locks.
Their lock keys must not include tenant ID because the corresponding primary
keys are globally unique and cross-tenant collisions must serialize without
disclosure.
The existing tenant-prefixed generic event lock is replaced by the same global
event lock for all sync events, not layered beside it. Thus activity and
non-activity writers coordinate on one event-ID lock. Mixed batches acquire the
whole sorted event set before any per-event savepoint, so transaction-scoped
locks retained until batch commit cannot be acquired in opposite event order by
another batch.

A direct command has no event lock; it acquires its activity lock, cycle advisory
lock, and cycle row lock, preserving the same EVENT -> ACTIVITY -> CYCLE class
order while skipping EVENT. No direct or queued path may hold a cycle lock and
then request an activity/event lock.

The batch cycle plan includes every admitted sync operation that can write a
cycle, not only activity CREATE:

- `CROP_CYCLE` CREATE/UPDATE/DELETE: the target cycle identity;
- `CROP_STAGE` operations: the payload cycle identity or the immutable cycle
  resolved from the existing stage identity;
- `CROP_ACTIVITY CREATE`: the exact payload cycle identity; UPDATE/DELETE have
  already been rejected by preflight and cannot reach planning; and
- any future materializer declaring a `CropCycle` write.

Planning reads may resolve immutable stage/activity-to-cycle identity but perform
no mutation. If the exact affected cycle set cannot be determined before lock
acquisition, that event is rejected with fixed `CYCLE_LOCK_PLAN_INVALID` before
any per-event mutation. A materializer may not discover and lock an additional
cycle later. A future cycle-writing operation cannot join sync processing until
it declares its affected cycles to this planner.

After all locks are held, each event reloads and revalidates its actual target
before mutation. Activity CREATE must still have identical event entity ID,
payload activity ID, planned activity ID, payload cycle ID, and planned cycle
ID; the loaded tenant-scoped cycle and farmer must match the planned context.
Any difference is `CYCLE_LOCK_PLAN_INVALID` or the applicable sanitized identity
error and causes no business mutation. Planning never grants authority to use a
different target discovered during execution.

After the cycle row is locked, cost is recomputed from the tenant-scoped sum of
persisted activities for that cycle after the new activity flush. The locked
cycle row serializes distinct activity IDs targeting the same cycle, so a waiter
sees the earlier commit and both contributions survive. Endpoint-local
read/modify/write increments are removed. Focused tests must force both opposite
batch event orders and two distinct activities on one cycle.

The only admitted activity-cost writers in this slice are direct activity CREATE
and queued activity CREATE. Both use the shared command and the same activity and
cycle lock/recompute helper. Existing queued activity UPDATE/DELETE is rejected
at preflight rather than allowed to use its current recomputation path. Any
future direct or queued cost writer must use the same helper before it can be
enabled.

After locking, reload bindings and rows:

- no binding/no activity: perform first-time validation and materialization;
- matching same-origin binding: reauthorize current farmer scope, compare
  version plus canonical text/hash, and return the retained result without
  new-write checks or effects;
- exact concurrent duplicate: the loser reloads the winner after the lock,
  reauthorizes, verifies both bindings, and returns `EXACT_REPLAY`;
- activity row without trustworthy binding: generic `ACTIVITY_ID_REUSE`;
- binding, activity, event, origin, or canonical mismatch: generic
  `ACTIVITY_ID_REUSE` or `EVENT_ID_REUSE`, with no conflicting-row disclosure;
  and
- unrelated integrity violation: roll back and re-raise to the fixed sanitized
  server-error boundary; never reinterpret it as identity replay.

Database unique constraints are the final guard, not the primary collision
classifier. Any integrity recovery must inspect PostgreSQL SQLSTATE and exact
constraint name, then reacquire/reload as required and repeat authorization and
binding comparison before returning a winner.

## Cross-entry-point and different-event decisions

Replay ownership never changes:

- `DIRECT` binding + direct request with the same supplied activity ID and exact
  intent: exact replay is permitted after current authorization;
- `SYNC` binding + the same sync event ID and exact intent: exact replay is
  permitted after current authorization;
- `DIRECT` binding + any queued event: reject, even if content matches;
- `SYNC` binding + any direct request: reject, even if content matches;
- `SYNC` binding + a different event ID: reject, even if activity and content
  match; and
- any conflicting content or unverifiable legacy identity: reject.

These rules deliberately prohibit the historical direct-to-queue fallback and
prevent a new event ID from bypassing conflict or uncertainty. No endpoint may
create a second binding, transfer origin ownership, or convert an unresolved
diagnostic into a committed binding.

## Compatible response shape

Keep the existing top-level sync fields for non-activity consumers:

```json
{
  "accepted": ["event-uuid"],
  "accepted_details": [
    {
      "event_id": "event-uuid",
      "entity_type": "crop_activity",
      "entity_id": "activity-uuid",
      "outcome": "COMMITTED",
      "intent_version": "crop_activity_intent.v1",
      "intent_sha256": "64-lowercase-hex"
    }
  ],
  "conflicts": [],
  "failed": [],
  "total_processed": 1
}
```

`accepted` remains for compatibility. `accepted_details` is additive and
defaults to an empty list for existing entity types. A committed or exact replay
of queued activity CREATE must emit exactly one matching detail; Android must
not settle such an activity from the legacy string alone. `outcome` is
`COMMITTED` for the first commit and `EXACT_REPLAY` for verified replay.

### Client-verifiable queued binding

The `intent_sha256` in `accepted_details` is not trusted merely because the
server returned it. Before enqueue, Android must compute and durably store its
expected `crop_activity_intent.v1` canonical text/hash with the immutable queue
row. The client-verifiable inputs are exactly:

- the captured origin tenant and user IDs;
- event ID, entity type, entity/activity ID, operation, client version, and the
  dependency array in retained order with retained multiplicity;
- explicit farmer ID and crop-cycle ID from the selected form context;
- requested stage ID/code, including null; and
- every submitted business field listed in the canonical contract, represented
  under the same cross-platform decimal, UUID, date, string, null, and key-order
  rules.

Queued payload must include `farmer_id`. The backend loads the cycle and requires
its farmer to equal that supplied ID; it does not substitute a server-derived
farmer into the request-intent digest. Resolved stage identity, resolved catalog
objects/codes, resulting cost, audit correlation, and other server-derived
result fields are excluded from the request-intent digest and returned only in
the retained commit result where applicable.

The backend independently computes the same digest from authenticated
tenant/actor identity and the received immutable envelope/payload. Acceptance
requires it to match the retained backend binding. Android settlement later
requires the returned version/hash to equal the independently stored local
version/hash as well as matching owner, claim, event ID, activity ID, and
content snapshot. The response cannot teach Android its expected value.

Cross-language canonicalization fixtures covering Unicode, nulls, decimal
scales, dependency order/multiplicity, and every field are required before the
response shape is considered implementable. Android DTO/storage/settlement work
remains separately gated.

Failure/conflict entries retain `event_id` but use fixed codes and sanitized
messages. They do not return intent hashes, conflicting activity details, raw
exceptions, or cross-tenant facts.

The direct response preserves its existing fields and adds:

- `outcome`: `COMMITTED` or `EXACT_REPLAY`;
- `intent_version`; and
- `intent_sha256`.

It contains no synthetic event ID. `events_published`, if retained, remains a
compatibility label and is not evidence of durable publication.

Android DTO and settlement changes are outside this backend proposal and remain
separately reviewed. Until Android requires and validates the exact activity
detail, queued activity submission stays blocked.

## Error categories

Use fixed public categories for this slice:

- `ACTIVITY_ID_REUSE` — occupied, cross-origin, legacy-unverified, or conflicting
  activity identity;
- `EVENT_ID_REUSE` — event binding mismatch;
- `ACTIVITY_CONTEXT_INVALID` — cycle/stage relationship or writability failure;
- `ACTIVITY_TRACEABILITY_INVALID` — input/product/package/rule failure;
- `ACTIVITY_PAYLOAD_INVALID` — field or canonicalization failure;
- `DUPLICATE_EVENT_ID_CONFLICT` — conflicting occurrences of one event ID in
  the submitted batch;
- `ACTIVITY_OPERATION_UNSUPPORTED` — queued activity UPDATE or DELETE in this
  CREATE-only slice;
- `CYCLE_LOCK_PLAN_INVALID` — exact affected cycle could not be determined
  before transaction-wide lock acquisition;
- `ACTIVITY_AUTHORIZATION_DENIED` — existing sanitized authorization policy; and
- `ACTIVITY_CREATE_FAILED` — unexpected internal failure without raw detail.

Public responses must not distinguish cross-tenant occupation from other
unavailable identity cases. Operational diagnostics may record fixed internal
detail codes but no raw exception text, credentials, or arbitrary payload.

## Accepted database-free ingress evidence

On 2026-11-17, an operator ran the two focused WSL host scripts with Python
assertions enabled:

- `scripts/test_sync_lossless_ingress_static.py` returned
  `SYNC_LOSSLESS_INGRESS_STATIC_OK` with exit code `0`;
- `scripts/test_sync_lossless_ingress.py` returned
  `SYNC_LOSSLESS_INGRESS_OK` with exit code `0`.

The run used Python 3.10.12, FastAPI 0.109.0, and Pydantic 2.5.3. The repository
pins FastAPI 0.111.0 and Pydantic 2.7.1, so pinned-version compatibility remains
unverified. This is operator-run, database-free host evidence. It covers the
script assertions, including the check that importing the production ingress
and schema modules leaves `app.core.database` unloaded. It does not establish
application startup, HTTP routing, database-session behavior, migration
behavior, or any activity CREATE capability.

No rerun is required for this evidence gate. Queued activity CREATE remains
disabled.

## Focused verification proposal

After separate implementation and database-test approval, use only a fresh
disposable PostgreSQL clone. Focused tests must prove:

1. direct and queued paths persist identical canonical fields and business
   effects for equivalent commands;
2. queued stage ID/code must belong to and match the active stage on the exact
   cycle;
3. completed-cycle, authorization, traceability, catalog, precision, and payload
   failures create no activity, cost, business audit, or committed binding;
4. all supported traceability, dosage, cost, GPS, irrigation, and note fields
   survive queued creation;
5. first commit creates one activity, one cost effect, one `ACTIVITY_LOGGED`
   audit, one activity binding, and—only for sync—one event binding;
6. exact direct replay and exact same-event queued replay return the retained
   result with no repeated effects after stage change or cycle completion;
7. concurrent exact duplicates return one commit and one verified replay;
8. conflicting concurrent duplicates, unrelated integrity failures,
   cross-tenant collisions, legacy activities, cross-origin reuse, and different
   event IDs reject without disclosure or second effects;
9. sync response details correlate event, activity, outcome, version, and hash;
10. event-ID-only legacy acceptance cannot settle an activity in future Android
    integration;
11. sanitized rejection diagnostics contain no raw exceptions or payloads; and
12. migration upgrade/reopen succeeds, existing rows remain byte-for-byte
    unchanged, new tables start empty, downgrade succeeds only while empty, and
    non-empty downgrade fails closed without data loss.

Also force transaction interleavings for overlapping mixed batches submitted in
opposite event order and for two different activity IDs updating the same cycle;
prove no deadlock, lost cost contribution, duplicate audit, or partial binding.
At least one forced mixed interleaving must combine activity CREATE with a second
admitted cycle-writing operation (`CROP_STAGE` or `CROP_CYCLE`) addressing the
opposite cycle order. Prove an unplannable cycle writer rejects before mutation.
Verify direct and queued CREATE coordinate through the same cycle
lock/recompute helper. Verify queued activity UPDATE and DELETE reject the whole
batch before mutation in standalone and mixed input.
Verify legacy committed, failed, conflicted, dependency-missing, unrelated-type,
and cross-tenant occupation of an event ID all reject before business writes.
After committing an activity event binding, submit a generic entity with that
event ID and prove it receives `EVENT_ID_REUSE` before the generic replay
shortcut, with no generic ledger/audit/mutation effect. Prove the exact matching
activity replay still returns one correlated acceptance without a second audit.
Submit exact duplicate occurrences in both orders and prove one logical outcome,
one correlated detail, and one set of effects. Submit conflicting
activity/activity and activity/generic duplicate groups in both orders and prove
the entire request rejects before authorization-side mutation, business writes,
ledger rows, bindings, or audits.
Add lossless-ingress cases where one duplicate omits a field and the other sends
explicit null, zero, false, or the declared default; each must remain distinct
and reject as a conflicting group. Use two numeric values that become equal when
converted to binary float but differ as exact decimals and prove they remain
conflicting. Submit `1` versus `1.0`, `1` versus `1e0`, and an occurrence with a
token invalid for its field beside a valid equivalent occurrence, in both input
orders; no invalid occurrence may disappear through collapse. Cover strict
UTF-8, BOM, duplicate keys, depth/node/string limits, invalid numeric grammar,
unknown envelope fields, and trailing content. Exercise the streaming body cap
with missing, correct, understated, overstated, malformed, and conflicting
`Content-Length`, chunk boundaries immediately below/at/above 2 MiB, and an
oversized delivered chunk; prove the application buffer never exceeds the cap
plus one byte and JSON parsing never starts for over-limit input.
Run CREATE classification and UPDATE/DELETE whole-batch rejection for both
`crop_activity` and `cropactivity`; prove switching spellings under one event ID
is not an exact duplicate and neither alias can reach the generic materializer.
Canonicalization fixtures must prove that dependency order/multiplicity changes
the digest and that direct numeric ingress never passes through binary float.

No test may use the development database. Migration and focused tests require a
separately reviewed disposable-database procedure and retained sanitized
evidence.

## Compatibility and rollout gates

- The backend may deploy additive empty tables and additive response fields only
  after migration and old-client compatibility review.
- Runtime code must not require activity bindings for unrelated sync entity
  types.
- Existing direct creation without an activity ID remains available but is
  explicitly not lost-response replay-safe.
- Existing activities remain readable; only identity reuse is denied when a
  trustworthy binding is absent.
- Android activity submission stays blocked until it validates
  `accepted_details` and its worker hold behavior passes separate review.
- Stage transitions remain blocked and are not coupled to this rollout.
- No backfill, repair, conflict release, uncertain-row retransmission, or live
  data mutation is authorized.

## Approval sequence

1. Independent review of this implementation proposal.
2. Separate approval for migration and backend source implementation.
3. Independent source review before execution.
4. Separately approved disposable-database migration and focused regression run.
5. Independent retained-evidence review.
6. Separate Android DTO, settlement, worker-hold, and queue-only form proposal.
7. Isolated Android verification and distinct release decision.

Until those gates pass, direct Android activity submission, queued Android
activity submission, and stage transitions remain blocked.

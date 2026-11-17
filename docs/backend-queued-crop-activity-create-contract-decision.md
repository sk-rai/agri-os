# Queued `CROP_ACTIVITY CREATE` contract decision

Status: proposed contract for independent review. This document does not close
the identified gaps or authorize implementation, migration, Android enablement,
tests, API calls, deployment, or activity submission.

`PRODUCTION_RECOVERY_LIVE_NOT_APPROVED` remains closed.

## Decision and scope

The first Android activity-submission slice, if later approved, will be
**queue-only**. Android must not send a direct activity request and then create a
queue event after an exception. Direct submission, queued submission, and stage
transitions remain blocked until the requirements and evidence gates below are
satisfied.

This decision covers only authenticated `CROP_ACTIVITY CREATE`. It does not
select behavior for activity update/delete, stage transitions, general sync
reconciliation, account switching, migrations, or automatic restore.

The current queued implementation is not conforming:

- sync authorization derives tenant and actor from the principal and resolves a
  farmer, but the materializer can select an explicit stage by tenant without
  proving that it belongs to the event's cycle
  (`backend/app/modules/sync/authorization.py:281-295`,
  `backend/app/modules/sync/service.py:1385-1393`);
- queued materialization defaults fields, omits direct-path validation and
  traceability fields, and applies different effects
  (`backend/app/modules/sync/service.py:1395-1431`,
  `backend/app/modules/workflow/api.py:1974-2088`);
- existing same-cycle activity identity and existing event identity can be
  accepted without exact retained-content comparison
  (`backend/app/modules/sync/service.py:1376-1383`,
  `backend/app/modules/sync/service.py:1915-1925`);
- accepted sync responses contain only event IDs, while failures can expose raw
  exception text (`backend/app/modules/sync/api.py:47-65`,
  `backend/app/modules/sync/service.py:2006-2030`).

## One canonical activity command

Direct and queued entry points must call one backend-owned canonical activity
command. Neither entry point may independently reproduce validation, identity,
economics, event publication, or business-audit behavior.

Before any mutation, the canonical command must:

1. bind tenant and actor exclusively to the authenticated principal;
2. load the exact tenant-scoped cycle and recheck the principal's current farmer
   scope;
3. reject a completed or otherwise non-writable cycle;
4. apply the entry-point-specific identity rules below before constructing the
   shared command;
5. validate activity type and date without silently defaulting an omitted or
   malformed required field;
6. run the same traceability and project/crop catalog checks for input rule,
   input, product, and package identities;
7. validate quantity, units, applied area, recommended and actual dosage,
   variance reason, cost, GPS, and notes under the same rules for both entry
   points; and
8. determine the stage under one rule.

For the first slice, an explicitly supplied stage ID or code must resolve to a
stage on the exact cycle and must equal the backend-selected currently active
stage. If no stage is supplied, the backend may select that same active stage.
If the cycle has no active stage, only a null stage is valid. A stage from
another cycle, a stale stage, contradictory ID/code, or ambiguous selection is
a terminal rejection. Android must not choose a different rule.

These writability, catalog, and stage-selection checks apply to first-time
materialization. Exact replay follows the separate replay procedure below and
does not reselect a stage or apply new-write checks after the original commit.

### Entry-point identity rules

Queued ingress must supply a stable event ID and activity ID. Its event entity
ID, payload activity ID, and validated command activity ID must all be present
and identical. Queued ingress validates that agreement and the complete event
envelope before it constructs the shared activity command.

Direct ingress has no sync-event envelope. It constructs the same validated
activity command without an event binding. To preserve the existing API shape,
a direct request may omit `activity_id`; the backend then generates the command
activity ID once for that first request. Such a request has no client-stable
identity with which to recover a lost response and must not be described as
replay-safe. A direct caller that requires exact replay must supply its stable
activity ID.

Both entry points pass the same normalized business fields and activity ID to
the canonical command. Event ID, dependencies, and client event version are
queued-envelope data retained alongside, but not invented for, a direct call.
An existing activity that lacks a trustworthy retained intent/result binding is
not accepted as an exact replay, even if tenant and cycle appear to match. It
returns the same generic identity-unavailable conflict used for other
unverifiable or conflicting identity reuse. The command must not infer a
binding from the current row or silently add one to a legacy activity.

## Immutable request intent, commit result, and exact replay

The retained **request intent** comprises at least:

- tenant, actor, activity ID, exact cycle and farmer binding, and the requested
  stage ID/code (including an explicit absence);
- for queued ingress only, event ID, entity type, operation, client version, and
  dependency IDs;
- activity type and date;
- all input-rule, input, product, package, quantity, unit, area, dosage,
  variance, cost, GPS, and note fields; and
- the normalization/version rules used to interpret those fields.

The retained **commit result** is separate. It contains the activity ID, exact
resolved stage identity (which may be null), normalized persisted activity
content, resulting cycle-cost value/effect, business-audit correlation, outcome,
and the response fields returned for the original commit. A caller that omitted
a stage therefore retains an intent with no requested stage and a result with
the stage selected during the original materialization.

The implementation proposal must define a deterministic canonical
representation and binding value for the complete request intent, plus a
durably retained commit result. Both must be available for replay comparison
and response reconstruction; this document does not choose a table, column,
migration, or hashing format.

Replay rules are:

- every replay first rechecks the authenticated principal's current tenant and
  farmer authorization; loss of current authorization is a sanitized rejection;
- after authorization, the same event ID is accepted as a replay only when its
  tenant, actor, activity ID, operation, version, dependencies, and complete
  canonical request intent match the retained event binding;
- the same activity ID is accepted as an existing result only when its retained
  request-intent binding matches the incoming intent and its retained commit
  result belongs to the same tenant, farmer, and cycle;
- an exact replay returns the original retained commit result without checking
  current cycle writability, reselecting the active stage, or reapplying
  first-write catalog/traceability checks; a later stage change or cycle
  completion does not rewrite an already committed exact result;
- different content, cycle, stage, actor, tenant, operation, or binding under an
  existing event or activity identity is never accepted as a replay;
- a new event ID or activity ID cannot bypass a retained uncertainty or
  conflict; and
- an exact replay produces no second activity, economic change, domain event,
  or business-audit effect.

For concurrency, one first-time command may win the commit. An exact concurrent
duplicate may return that committed result only after rollback/reload as
necessary, renewed current authorization, and verification of the durable
request-intent and commit-result bindings. A conflicting or unverifiable
concurrent duplicate returns the generic identity-unavailable conflict and
causes no second business effect.

Cross-tenant identity occupation and unavailable identities return the same
sanitized terminal category and disclose no row, tenant, farmer, cycle, stage,
or content details.

## Commit effects

A first successful commit must atomically:

1. create exactly one activity with the supplied stable activity ID and every
   validated field;
2. bind it to the exact tenant, farmer, cycle, resolved stage, and actor;
3. apply the canonical cycle-cost effect exactly once;
4. append the canonical `ACTIVITY_LOGGED` business audit exactly once;
5. retain the exact request-intent binding and commit result; and
6. retain the committed event outcome for queued ingress.

The activity, economics, business audit, bindings, and applicable committed
event outcome form one transaction. Partial success is not permitted within one
activity command.

Durable domain-event publication is not part of this slice. The current direct
response's `events_published` value is a response label; the inspected source
does not establish a transactional outbox or other durable publication effect.
The shared command may preserve that response field for compatibility, but it
must not be treated as proof of publication. Adding a durable domain event,
delivery semantics, or an outbox requires a separate contract and review.

## Response and correlation

A queued accepted outcome must correlate all of the following:

- event ID;
- activity ID;
- tenant-bound operation and entity type;
- terminal outcome (`COMMITTED` or `EXACT_REPLAY`); and
- the retained request-intent binding version/value required for exact
  comparison.

An event-ID-only accepted list is insufficient for Android confirmation.
Backward-compatible response design, if required, must be proposed and reviewed
separately. Android may settle its retained row only after an exact correlated
outcome matches the reserved event, activity, owner, claim, and retained
content.

A direct response has no event ID or queue claim. It must return the activity ID
and the retained commit result. If the direct caller supplied a stable activity
ID, an exact replay returns that original result; if the caller omitted the ID,
the generated activity ID is returned but a lost response remains unrecoverable
through exact client replay. No synthetic sync event identity is created for a
direct call.

## Rejection and diagnostic audit

A rejected activity command must create no activity, cost change, domain event,
or `ACTIVITY_LOGGED`/other business audit effect.

Sanitized operational rejection evidence is permitted and is distinct from a
business audit. It may retain tenant, actor, event ID, activity ID, fixed error
category/detail code, and observation time. It must not contain raw exception
text, arbitrary request bodies, credentials, cross-tenant facts, or claim that
the business activity occurred. The API must return fixed public categories;
internal exception text must not be copied into the response.

Whether operational diagnostics use the existing audit chain, the processed
event ledger, or another mechanism is an implementation/storage decision that
requires separate review. Merely recording a rejection never authorizes retry.

## Android claim, uncertainty, and WorkManager retry

Queue-only removes the direct/fallback ambiguity but not transport uncertainty.
For `CROP_ACTIVITY CREATE`:

- local activity intent and its queue row must be committed atomically under
  one captured owner/session before scheduling;
- dispatch must reserve the exact immutable row under a durable claim before
  network transmission;
- a complete exact correlated response may settle only that claim and retained
  content;
- a known terminal rejection remains rejected and is not automatically reset;
- a missing outcome, malformed response, account/epoch replacement, HTTP result
  without an exact outcome, cancellation after admission, or transport
  exception after reservation is `UNCERTAIN_HELD` and cannot be automatically
  retransmitted;
- returning to the original account, process restart, periodic work, manual
  Sync Now, or a new WorkManager attempt does not release the hold; and
- no replacement event/activity ID, fallback request, cleanup, or repair is
  implicit.

Current Android source reserves a batch before `syncEvents`, excludes reserved
rows from selection, leaves missing outcomes reserved, and treats transport
exceptions as unresolved (`SyncManager.kt:103-122`, `164-223`). Consequently,
`SyncWorker.Result.retry()` can reschedule a worker without, by itself,
authorizing reselection of the held row (`SyncWorker.kt:119-139`). This is source
evidence, not sufficient restart/execution proof. The activity slice must add
focused evidence that every ambiguous activity attempt remains excluded across
worker retry and restart. If any generic repair, recovery, or status method can
clear or bypass that hold, activity submission remains blocked.

No automatic retransmission policy is selected here. Releasing an uncertain
activity requires a separate explicit decision based on independently reviewed
reconciliation evidence and policy.

## Required evidence before Android enablement

The future backend proposal and isolated verification must prove at least:

- direct and queued entry points invoke the shared canonical command;
- exact cycle/stage binding and current authorization;
- completed-cycle, traceability, catalog, field, and relationship rejection;
- preservation of all supported activity fields;
- exactly one activity, cost effect, and business audit, with no claim of a
  durable domain event;
- exact event replay and exact activity replay with no repeated effects;
- different-content reuse, different-cycle reuse, cross-tenant collision, and
  concurrent identity collision reject without disclosure or business mutation,
  while an exact concurrent duplicate may return the verified committed result;
- rejected materialization rolls back business effects while retaining only
  permitted sanitized operational diagnostics;
- accepted responses bind event, activity, outcome, and retained intent;
- missing/contradictory responses cannot settle the Android claim; and
- WorkManager retry, process restart, periodic sync, and manual Sync Now cannot
  retransmit an uncertain held activity.

Backend database verification must use a separately approved disposable
database. Android host/Room/Compose/device verification requires separate
approval. Live API and production verification remain prohibited.

## Approval sequence

1. Independent review of this contract decision.
2. Separately approved backend implementation proposal, including compatibility
   and any schema/migration decision.
3. Narrow backend implementation and disposable-database verification.
4. Independent backend evidence review.
5. Android worker hold/restart source review and focused evidence.
6. Queue-only Android form implementation and isolated verification.
7. Separate release decision for the explicit queue-only action.

Until all applicable gates pass, direct activity submission, queued activity
submission, and stage transitions remain blocked.

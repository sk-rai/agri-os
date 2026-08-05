# Android partial-batch success + conflict test

Status date: 2026-08-05

This contract covers one `/api/v1/sync/events` batch with mixed outcomes:

1. one valid `crop_activity` CREATE that commits;
2. one deterministic `WORKFLOW_INVALID` `crop_stage` event that returns `conflicts[]`.

Backend returns HTTP 200 with partial results. Android should mark the accepted
activity row synced and route the conflict row to the existing server-authority
workflow conflict UI, not the retry queue.

Expected Android UX for the conflict row:

- title: `Workflow changed on backend`;
- guidance: `Refresh this crop cycle/stage before retrying the action.`;
- do not show stale-context refresh guidance;
- do not show version-mismatch manual review copy.

## Fixed backend context

```text
tenant_id=android-dynamic-test
project_id=0f7e0a6b-8472-5d6d-8a14-a9d000000001
cycle_id=aa346148-468b-47de-9c86-47ad41aa1f11
stage_code=NURSERY
expected_new_activity_cost=325.50
```

The prep script ensures the existing dynamic Rice cycle is `ACTIVE` and the
NURSERY stage is already `ACTIVE`. That makes `action=START` invalid and
therefore deterministic as `WORKFLOW_INVALID`.

## WSL prep/baseline command

Run before Android starts flow 25:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_partial_batch_conflict.py --apply
```

This writes:

```text
/tmp/android_partial_batch_conflict_baseline.json
```

Baseline records:

- NURSERY activity count;
- stage-cost `totals.actual_expense`;
- P&L `totals.total_expenses`;
- NURSERY stage status;
- expected new activity cost `325.50`.

Do not rerun prep after Android has sent the mixed batch unless restarting flow
25 from scratch.

If reusing explicit IDs during local/manual development, cleanup just those rows:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_partial_batch_conflict.py --apply \
  --reset-event-id {activity_event_id} \
  --reset-event-id {conflict_event_id} \
  --reset-entity-id {activity_id}
```

Android may generate random UUIDs for all event/entity IDs.

## Canonical mixed-batch payload

Headers:

```http
X-Tenant-ID: android-dynamic-test
X-Actor-ID: 11111111-1111-4111-8111-111111111111
```

Endpoint:

```http
POST /api/v1/sync/events
```

### Event 1: valid crop_activity CREATE

```json
{
  "event_id": "{activity_event_id}",
  "entity_type": "crop_activity",
  "entity_id": "{activity_id}",
  "operation": "CREATE",
  "version": 1,
  "dependency_ids": [],
  "payload": {
    "crop_cycle_id": "aa346148-468b-47de-9c86-47ad41aa1f11",
    "stage_code": "NURSERY",
    "activity_date": "2026-08-02",
    "activity_type": "FERTILIZER",
    "input_code": "DAP_18_46_0",
    "input_name": "DAP 18-46-0",
    "quantity": 1,
    "quantity_unit": "KG",
    "cost_amount": 325.5,
    "currency": "INR",
    "notes": "Partial batch success plus conflict activity test"
  },
  "metadata": {
    "source": "android_maestro_partial_batch_conflict_test"
  }
}
```

### Event 2: deterministic WORKFLOW_INVALID crop_stage UPDATE

```json
{
  "event_id": "{conflict_event_id}",
  "entity_type": "crop_stage",
  "entity_id": "{conflict_stage_entity_id}",
  "operation": "UPDATE",
  "version": 1,
  "dependency_ids": [],
  "payload": {
    "crop_cycle_id": "aa346148-468b-47de-9c86-47ad41aa1f11",
    "stage_code": "NURSERY",
    "action": "START",
    "actual_start_date": "2026-08-02"
  },
  "metadata": {
    "source": "android_maestro_partial_batch_conflict_test"
  }
}
```

`conflict_stage_entity_id` is a client sync entity ID, not the real server stage
row ID. Backend targets the real stage through `payload.stage_code=NURSERY`.

## Expected `/api/v1/sync/events` response

Current backend response shape:

```json
{
  "accepted": [
    "{activity_event_id}"
  ],
  "conflicts": [
    {
      "event_id": "{conflict_event_id}",
      "conflict_type": "WORKFLOW_INVALID",
      "resolution_strategy": "SERVER_AUTHORITY",
      "detail": "Invalid stage transition: cannot START from ACTIVE"
    }
  ],
  "failed": [],
  "total_processed": 2
}
```

## Android local queue expectation

Android should:

- mark the accepted activity row `SYNCED`;
- mark the conflict row as non-retry conflict/server-authority workflow state;
- not keep the conflict row in retryable dependency queue;
- not delete unrelated pending rows;
- continue to read durable pending conflicts from `/api/v1/sync/conflicts/pending`.

`WORKFLOW_INVALID` is not `DEPENDENCY_MISSING`. It is a server-authority
workflow conflict and should use the existing workflow-changed drawer/UI.

## Verification after mixed batch

After Android sends the mixed batch:

```bash
cd ~/projects/farmint/backend
ANDROID_PARTIAL_CONFLICT_ACTIVITY_EVENT_ID={activity_event_id} \
ANDROID_PARTIAL_CONFLICT_ACTIVITY_ID={activity_id} \
ANDROID_PARTIAL_CONFLICT_STAGE_EVENT_ID={conflict_event_id} \
ANDROID_PARTIAL_CONFLICT_STAGE_ENTITY_ID={conflict_stage_entity_id} \
../venv/bin/python scripts/verify_android_partial_batch_conflict.py
```

To make WSL/backend send and verify the mixed batch itself:

```bash
cd ~/projects/farmint/backend
ANDROID_PARTIAL_CONFLICT_ACTIVITY_EVENT_ID={activity_event_id} \
ANDROID_PARTIAL_CONFLICT_ACTIVITY_ID={activity_id} \
ANDROID_PARTIAL_CONFLICT_STAGE_EVENT_ID={conflict_event_id} \
ANDROID_PARTIAL_CONFLICT_STAGE_ENTITY_ID={conflict_stage_entity_id} \
../venv/bin/python scripts/verify_android_partial_batch_conflict.py --send-mixed-batch
```

The verifier checks:

- accepted activity materialized exactly once;
- accepted activity is linked to NURSERY;
- accepted activity processed event is `COMMITTED`;
- stage-cost actual expense increases exactly once by `325.50`;
- P&L total expenses increases exactly once by `325.50`;
- conflict processed event status is `CONFLICT`;
- durable `sync_conflicts.conflict_type=WORKFLOW_INVALID`;
- durable `sync_conflicts.resolution_strategy=SERVER_AUTHORITY`;
- Android pending conflicts endpoint includes the row with
  `android_action=SHOW_SERVER_AUTHORITY_WORKFLOW_MESSAGE`;
- `failed[]` stays empty and no `SYNC_FAILED` audit is created for either event;
- conflict sync entity ID does not materialize as a server stage row.

## Recovery / acknowledgement

After Android user refreshes context and discards the conflicted local action,
acknowledge the backend conflict with existing conflict lifecycle:

```http
PATCH /api/v1/sync/conflicts/{conflict_id}
```

Body:

```json
{
  "strategy": "ACCEPT_SERVER"
}
```

Verifier command:

```bash
cd ~/projects/farmint/backend
ANDROID_PARTIAL_CONFLICT_ACTIVITY_EVENT_ID={activity_event_id} \
ANDROID_PARTIAL_CONFLICT_ACTIVITY_ID={activity_id} \
ANDROID_PARTIAL_CONFLICT_STAGE_EVENT_ID={conflict_event_id} \
ANDROID_PARTIAL_CONFLICT_STAGE_ENTITY_ID={conflict_stage_entity_id} \
../venv/bin/python scripts/verify_android_partial_batch_conflict.py --ack-conflict
```

Expected durable state after ACK:

- accepted activity remains committed and materialized once;
- conflict row moves to `RESOLVED_SERVER`;
- conflict processed event remains `CONFLICT`;
- no failed audit rows are created.

## Optional resend/idempotency proof

If Android resends the same mixed batch after losing the response, the accepted
activity remains one materialized row and the finance impact remains counted once.
The workflow-invalid event remains a conflict response until Android resolves it.

WSL proof command:

```bash
cd ~/projects/farmint/backend
ANDROID_PARTIAL_CONFLICT_ACTIVITY_EVENT_ID={activity_event_id} \
ANDROID_PARTIAL_CONFLICT_ACTIVITY_ID={activity_id} \
ANDROID_PARTIAL_CONFLICT_STAGE_EVENT_ID={conflict_event_id} \
ANDROID_PARTIAL_CONFLICT_STAGE_ENTITY_ID={conflict_stage_entity_id} \
../venv/bin/python scripts/verify_android_partial_batch_conflict.py --send-mixed-batch --resend-mixed-batch
```
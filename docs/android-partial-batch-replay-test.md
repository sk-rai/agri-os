# Android partial-batch offline sync replay test

Status date: 2026-08-05

This contract covers one `/api/v1/sync/events` batch with mixed outcomes:

1. one valid `crop_activity` CREATE that commits;
2. one `crop_stage` START blocked by a missing dependency;
3. optional duplicate resend/idempotency checks.

Backend should return HTTP 200 with partial results. Android should mark the
accepted row synced and keep the dependency-missing row retryable.

## Fixed backend context

### A. Valid existing active Rice/NURSERY cycle

```text
tenant_id=android-dynamic-test
project_id=0f7e0a6b-8472-5d6d-8a14-a9d000000001
valid_cycle_id=aa346148-468b-47de-9c86-47ad41aa1f11
valid_stage_code=NURSERY
```

The prep script ensures the cycle and NURSERY stage are `ACTIVE`.

### B. Missing dependency retry context

```text
farmer_id=4df387e8-114f-5c44-a129-a9d000000003
parcel_id=4df387e8-114f-5c44-a129-a9d000000004
crop_code=RICE
season_code=KHARIF
```

This is the dedicated crop-cycle fixture. Prep resets it so the parcel is
eligible and no crop cycle exists until Android/backend commits the missing
dependency event.

## WSL prep/reset command

Run before Android starts flow 24:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_partial_batch_replay.py --apply
```

This writes:

```text
/tmp/android_partial_batch_replay_baseline.json
```

Baseline records:

- valid NURSERY activity count;
- valid cycle stage-cost `totals.actual_expense`;
- valid cycle P&L `totals.total_expenses`;
- dependency fixture parcel eligibility;
- expected new activity cost `325.50`.

Do not rerun prep after Android has sent the mixed batch unless restarting flow
24 from scratch.

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

Android may generate random UUIDs:

- `valid_activity_event_id`;
- `valid_activity_id`;
- `missing_cycle_event_id`;
- `missing_cycle_entity_id`;
- `missing_stage_event_id`;
- `missing_stage_entity_id`.

Android should use sync event IDs for `dependency_ids`.

### Event 1: valid crop_activity CREATE

```json
{
  "event_id": "{valid_activity_event_id}",
  "entity_type": "crop_activity",
  "entity_id": "{valid_activity_id}",
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
    "notes": "Partial batch valid activity test"
  },
  "metadata": {
    "source": "android_maestro_partial_batch_replay_test"
  }
}
```

### Event 2: dependency-missing crop_stage START

```json
{
  "event_id": "{missing_stage_event_id}",
  "entity_type": "crop_stage",
  "entity_id": "{missing_stage_entity_id}",
  "operation": "UPDATE",
  "version": 1,
  "dependency_ids": ["{missing_cycle_event_id}"],
  "payload": {
    "crop_cycle_id": "{missing_cycle_entity_id}",
    "stage_code": "NURSERY",
    "action": "START",
    "actual_start_date": "2026-08-02"
  },
  "metadata": {
    "source": "android_maestro_partial_batch_replay_test"
  }
}
```

## Expected mixed-batch response

Current backend response shape:

```json
{
  "accepted": [
    "{valid_activity_event_id}"
  ],
  "conflicts": [],
  "failed": [
    {
      "event_id": "{missing_stage_event_id}",
      "error_code": "DEPENDENCY_MISSING",
      "detail_code": null,
      "message": "Missing dependencies: ['{missing_cycle_event_id}']"
    }
  ],
  "total_processed": 2
}
```

There is no `retryable` boolean in the current response. Android should treat
`error_code=DEPENDENCY_MISSING` as retryable.

## Android local queue expectation

Android should:

- mark the accepted valid activity row `SYNCED`;
- keep the dependency-missing stage row pending/retryable;
- not permanently fail the dependency-missing row;
- not delete unrelated rows;
- not retry the accepted row unless it is in an uncertain-result retry path;
- optionally show partial success / waiting dependency if the UI exposes this.

`DEPENDENCY_MISSING` is not a manual conflict. It means replay order/context is
incomplete and the row should be retried after the missing dependency commits.

## Verification after mixed batch

After Android sends the mixed batch:

```bash
cd ~/projects/farmint/backend
ANDROID_PARTIAL_VALID_ACTIVITY_EVENT_ID={valid_activity_event_id} \
ANDROID_PARTIAL_VALID_ACTIVITY_ID={valid_activity_id} \
ANDROID_PARTIAL_MISSING_CYCLE_EVENT_ID={missing_cycle_event_id} \
ANDROID_PARTIAL_MISSING_CYCLE_ID={missing_cycle_entity_id} \
ANDROID_PARTIAL_MISSING_STAGE_EVENT_ID={missing_stage_event_id} \
ANDROID_PARTIAL_MISSING_STAGE_ENTITY_ID={missing_stage_entity_id} \
../venv/bin/python scripts/verify_android_partial_batch_replay.py
```

To make WSL/backend send the mixed batch itself:

```bash
cd ~/projects/farmint/backend
ANDROID_PARTIAL_VALID_ACTIVITY_EVENT_ID={valid_activity_event_id} \
ANDROID_PARTIAL_VALID_ACTIVITY_ID={valid_activity_id} \
ANDROID_PARTIAL_MISSING_CYCLE_EVENT_ID={missing_cycle_event_id} \
ANDROID_PARTIAL_MISSING_CYCLE_ID={missing_cycle_entity_id} \
ANDROID_PARTIAL_MISSING_STAGE_EVENT_ID={missing_stage_event_id} \
ANDROID_PARTIAL_MISSING_STAGE_ENTITY_ID={missing_stage_entity_id} \
../venv/bin/python scripts/verify_android_partial_batch_replay.py --send-mixed-batch
```

The verifier checks:

- valid activity materialized exactly once;
- valid event status is `COMMITTED`;
- missing-stage event row exists as `DEPENDENCY_MISSING` before retry;
- missing cycle is not materialized before retry;
- no `sync_conflicts` rows;
- no `SYNC_FAILED` audit for the accepted valid activity;
- no `SYNC_FAILED` audit for retryable dependency missing;
- valid cycle stage-cost actual expense increases exactly once by `325.50`;
- valid cycle P&L total expenses increases exactly once by `325.50`.

## Retry path for failed dependency event

Android should later commit the missing crop-cycle dependency, then retry the
same missing-stage event with the same:

- `event_id`;
- `entity_id`;
- `dependency_ids`;
- `payload`.

Missing crop-cycle dependency event:

```json
{
  "event_id": "{missing_cycle_event_id}",
  "entity_type": "crop_cycle",
  "entity_id": "{missing_cycle_entity_id}",
  "operation": "CREATE",
  "version": 1,
  "dependency_ids": [],
  "payload": {
    "farmer_id": "4df387e8-114f-5c44-a129-a9d000000003",
    "parcel_id": "4df387e8-114f-5c44-a129-a9d000000004",
    "project_id": "0f7e0a6b-8472-5d6d-8a14-a9d000000001",
    "crop_code": "RICE",
    "season_code": "KHARIF",
    "planned_sowing_date": "2026-08-02",
    "status": "PLANNED"
  },
  "metadata": {
    "source": "android_maestro_partial_batch_replay_test"
  }
}
```

Expected dependency create response:

```json
{
  "accepted": ["{missing_cycle_event_id}"],
  "conflicts": [],
  "failed": [],
  "total_processed": 1
}
```

Expected missing-stage retry response:

```json
{
  "accepted": ["{missing_stage_event_id}"],
  "conflicts": [],
  "failed": [],
  "total_processed": 1
}
```

WSL/backend can perform the dependency create and retry:

```bash
cd ~/projects/farmint/backend
ANDROID_PARTIAL_VALID_ACTIVITY_EVENT_ID={valid_activity_event_id} \
ANDROID_PARTIAL_VALID_ACTIVITY_ID={valid_activity_id} \
ANDROID_PARTIAL_MISSING_CYCLE_EVENT_ID={missing_cycle_event_id} \
ANDROID_PARTIAL_MISSING_CYCLE_ID={missing_cycle_entity_id} \
ANDROID_PARTIAL_MISSING_STAGE_EVENT_ID={missing_stage_event_id} \
ANDROID_PARTIAL_MISSING_STAGE_ENTITY_ID={missing_stage_entity_id} \
../venv/bin/python scripts/verify_android_partial_batch_replay.py --commit-dependency-and-retry
```

## Expected durable state after retry

After dependency commit and retry:

- valid activity is still materialized exactly once;
- valid activity finance impact is still counted exactly once;
- missing crop cycle exists exactly once;
- missing-stage event moves to `COMMITTED`;
- NURSERY stage on the missing cycle becomes `ACTIVE`;
- no conflicts;
- no non-retryable failed rows;
- no duplicate valid activity materialization.

## Optional duplicate/idempotent proof

Before dependency exists, resending the original mixed batch should return:

- valid activity event in `accepted`;
- missing-stage event still in `failed[]` with `DEPENDENCY_MISSING`.

After dependency exists and missing-stage is committed, resending the original
mixed batch should return both event IDs in `accepted`.

Command:

```bash
cd ~/projects/farmint/backend
ANDROID_PARTIAL_VALID_ACTIVITY_EVENT_ID={valid_activity_event_id} \
ANDROID_PARTIAL_VALID_ACTIVITY_ID={valid_activity_id} \
ANDROID_PARTIAL_MISSING_CYCLE_EVENT_ID={missing_cycle_event_id} \
ANDROID_PARTIAL_MISSING_CYCLE_ID={missing_cycle_entity_id} \
ANDROID_PARTIAL_MISSING_STAGE_EVENT_ID={missing_stage_event_id} \
ANDROID_PARTIAL_MISSING_STAGE_ENTITY_ID={missing_stage_entity_id} \
../venv/bin/python scripts/verify_android_partial_batch_replay.py --resend-mixed-batch
```


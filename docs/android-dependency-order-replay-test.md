# Android dependency-ordered offline replay test

Status date: 2026-08-05

This contract covers an offline “story” that spans multiple dependent sync
events. Android queues the events while backend is unavailable, app/device
restarts before sync, then Android replays the local queue after relaunch.

## Goal

Android queues:

1. `crop_cycle` CREATE;
2. `crop_stage` START;
3. `crop_activity` CREATE.

Backend should accept the ordered replay, materialize the cycle/stage/activity
once, and keep finance impact counted once even if Android retries the same
events after an uncertain result.

## Fixed backend fixture

Use the dedicated Android crop-cycle fixture:

```text
tenant_id=android-dynamic-test
project_id=0f7e0a6b-8472-5d6d-8a14-a9d000000001
farmer_id=4df387e8-114f-5c44-a129-a9d000000003
parcel_id=4df387e8-114f-5c44-a129-a9d000000004
crop_code=RICE
season_code=KHARIF
```

This fixture is separate from the dynamic profile farmer used by flows 14-22.

## WSL prep/reset command

Run before Android starts flow 23:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_dependency_order_replay.py --apply
```

This resets and recreates the fixture farmer/parcel, confirms the parcel is
eligible for RICE/KHARIF, and writes:

```text
/tmp/android_dependency_order_replay_baseline.json
```

The clean baseline expects:

- no existing crop cycle for the fixture farmer/parcel/season;
- no existing activity rows;
- eligible parcel returned by `eligible-parcels`;
- expected new activity cost `325.50`.

Do not rerun the prep after Android has queued or synced the events unless you
want to restart flow 23 from scratch.

## Dependency ID contract

Canonical Android contract: use sync event IDs in `dependency_ids`.

Recommended:

- `crop_cycle` CREATE: `dependency_ids=[]`;
- `crop_stage` START: `dependency_ids=["{cycle_event_id}"]`;
- `crop_activity` CREATE: `dependency_ids=["{cycle_event_id}", "{stage_event_id}"]`.

Current backend validator accepts committed `event_id` or committed operational
`entity_id`, but Android should use event IDs because they map cleanly to local
queue ordering.

## Android payloads

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

- `cycle_event_id`;
- `cycle_entity_id`;
- `stage_event_id`;
- `stage_entity_id`;
- `activity_event_id`;
- `activity_entity_id`.

Android must preserve those IDs through app/device restart and retry.

### 1. crop_cycle CREATE

```json
{
  "event_id": "{cycle_event_id}",
  "entity_type": "crop_cycle",
  "entity_id": "{cycle_entity_id}",
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
    "source": "android_maestro_dependency_order_replay_test"
  }
}
```

### 2. crop_stage START

```json
{
  "event_id": "{stage_event_id}",
  "entity_type": "crop_stage",
  "entity_id": "{stage_entity_id}",
  "operation": "UPDATE",
  "version": 1,
  "dependency_ids": ["{cycle_event_id}"],
  "payload": {
    "crop_cycle_id": "{cycle_entity_id}",
    "stage_code": "NURSERY",
    "action": "START",
    "actual_start_date": "2026-08-02"
  },
  "metadata": {
    "source": "android_maestro_dependency_order_replay_test"
  }
}
```

Android may supply a random `stage_entity_id`; backend addresses the actual
stage by `payload.crop_cycle_id + payload.stage_code`. The stage row itself is
server-generated from the crop-cycle template.

### 3. crop_activity CREATE

```json
{
  "event_id": "{activity_event_id}",
  "entity_type": "crop_activity",
  "entity_id": "{activity_entity_id}",
  "operation": "CREATE",
  "version": 1,
  "dependency_ids": ["{cycle_event_id}", "{stage_event_id}"],
  "payload": {
    "crop_cycle_id": "{cycle_entity_id}",
    "stage_code": "NURSERY",
    "activity_date": "2026-08-02",
    "activity_type": "FERTILIZER",
    "input_code": "DAP_18_46_0",
    "input_name": "DAP 18-46-0",
    "quantity": 1,
    "quantity_unit": "KG",
    "cost_amount": 325.5,
    "currency": "INR",
    "notes": "Dependency ordered replay after restart test"
  },
  "metadata": {
    "source": "android_maestro_dependency_order_replay_test"
  }
}
```

## Expected response for correct order

If Android sends all three events in one `/api/v1/sync/events` batch in the
order above:

```json
{
  "accepted": [
    "{cycle_event_id}",
    "{stage_event_id}",
    "{activity_event_id}"
  ],
  "conflicts": [],
  "failed": [],
  "total_processed": 3
}
```

Backend supports this in a single pass. A second retry with the same three
events should return the same accepted event IDs and should not duplicate
materialization.

## Expected response for out-of-order stage

If Android sends `crop_stage` before the cycle event has committed:

```json
{
  "accepted": [],
  "conflicts": [],
  "failed": [
    {
      "event_id": "{stage_event_id}",
      "error_code": "DEPENDENCY_MISSING",
      "detail_code": null,
      "message": "Missing dependencies: ['{cycle_event_id}']"
    }
  ],
  "total_processed": 1
}
```

`DEPENDENCY_MISSING` is retryable. Backend records the event as
`DEPENDENCY_MISSING`; when Android resubmits the same event after dependencies
exist, backend can advance it to `COMMITTED`.

If Android sends `crop_activity` before both cycle and stage have committed,
the same shape is returned with the missing dependency event IDs in `message`.

## Verification commands

After Android replays the ordered batch:

```bash
cd ~/projects/farmint/backend
ANDROID_DEP_ORDER_CYCLE_EVENT_ID={cycle_event_id} \
ANDROID_DEP_ORDER_CYCLE_ID={cycle_entity_id} \
ANDROID_DEP_ORDER_STAGE_EVENT_ID={stage_event_id} \
ANDROID_DEP_ORDER_STAGE_ENTITY_ID={stage_entity_id} \
ANDROID_DEP_ORDER_ACTIVITY_EVENT_ID={activity_event_id} \
ANDROID_DEP_ORDER_ACTIVITY_ID={activity_entity_id} \
../venv/bin/python scripts/verify_android_dependency_order_replay.py
```

After Android retries the same ordered batch, run the same verifier again.

To make WSL/backend perform one extra duplicate resend and assert idempotency:

```bash
cd ~/projects/farmint/backend
ANDROID_DEP_ORDER_CYCLE_EVENT_ID={cycle_event_id} \
ANDROID_DEP_ORDER_CYCLE_ID={cycle_entity_id} \
ANDROID_DEP_ORDER_STAGE_EVENT_ID={stage_event_id} \
ANDROID_DEP_ORDER_STAGE_ENTITY_ID={stage_entity_id} \
ANDROID_DEP_ORDER_ACTIVITY_EVENT_ID={activity_event_id} \
ANDROID_DEP_ORDER_ACTIVITY_ID={activity_entity_id} \
../venv/bin/python scripts/verify_android_dependency_order_replay.py --resend
```

To let WSL/backend probe the out-of-order stage response before ordered replay:

```bash
cd ~/projects/farmint/backend
ANDROID_DEP_ORDER_CYCLE_EVENT_ID={cycle_event_id} \
ANDROID_DEP_ORDER_CYCLE_ID={cycle_entity_id} \
ANDROID_DEP_ORDER_STAGE_EVENT_ID={stage_event_id} \
ANDROID_DEP_ORDER_STAGE_ENTITY_ID={stage_entity_id} \
ANDROID_DEP_ORDER_ACTIVITY_EVENT_ID={activity_event_id} \
ANDROID_DEP_ORDER_ACTIVITY_ID={activity_entity_id} \
../venv/bin/python scripts/verify_android_dependency_order_replay.py --send-out-of-order-stage
```

After that probe, Android/backend may still replay the same ordered batch; the
stage event can move from `DEPENDENCY_MISSING` to `COMMITTED`.

## Expected durable backend state

After ordered replay plus retry:

- exactly one `crop_cycles` row for `{cycle_entity_id}`;
- crop cycle status becomes `ACTIVE` after NURSERY START;
- NURSERY stage is `ACTIVE`;
- NURSERY `actual_start_date=2026-08-02`;
- exactly one `crop_activities` row for `{activity_entity_id}`;
- activity is linked to NURSERY;
- stage-cost summary `totals.actual_expense=325.50`;
- P&L summary `totals.total_expenses=325.50`;
- `sync_processed_events` rows exist for all three event IDs;
- all three processed events have `status=COMMITTED`;
- no `sync_conflicts` rows for these events;
- no `SYNC_FAILED` audit rows for these events;
- duplicate retry does not duplicate cycle, stage transition, activity, or
  finance impact.

## Android app restart expectation

Android should persist all three local queue rows before network replay. After
app/device restart, Android should reload them from local storage, preserve
dependency order, and replay them in order. WorkManager may help trigger replay,
but local queue ordering should not depend on in-memory worker state.


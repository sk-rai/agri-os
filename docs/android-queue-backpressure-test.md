# Android queue pagination/backpressure sync test

Status date: 2026-08-05

This contract supports Android Flow 27: a larger offline sync backlog replayed in bounded batches without duplicate materialization or duplicate finance impact.

## Goal

Android queues many `crop_activity` CREATE rows while the backend is unavailable or before the user taps Sync Now. The sync engine should send bounded batches, mark accepted rows synced per batch, keep UI quiet unless there are failures/conflicts, and eventually clear the local queue.

Initial test size:

- event count: 25;
- amount per activity: INR 20.00;
- expected finance delta: INR 500.00.

## Fixed backend context

Use the existing Android dynamic Rice/NURSERY cycle:

```text
tenant=android-dynamic-test
project_id=0f7e0a6b-8472-5d6d-8a14-a9d000000001
farmer_id=e1ee0941-2bad-4a18-a239-2a4119608a06
parcel_id=98c1a0fa-4f5f-4b8c-97ae-d84992db1c44
cycle_id=aa346148-468b-47de-9c86-47ad41aa1f11
stage_code=NURSERY
```

The NURSERY stage must be ACTIVE before Android starts the flow.

## WSL prep/baseline command

Run this before Android queues the Flow 27 backlog:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_queue_backpressure.py --reset-indexed --apply
```

The prep command:

- ensures the Rice cycle is ACTIVE;
- ensures NURSERY is ACTIVE;
- deletes deterministic WSL sample rows from earlier Flow 27 runs;
- records baseline activity count, stage-cost actual expense, and P&L total expenses;
- writes baseline JSON to `/tmp/android_queue_backpressure_baseline.json`;
- writes an optional deterministic sample manifest to `/tmp/android_queue_backpressure_sample_events.json`.

Latest WSL proof baseline after cleanup:

```text
activity_count=16
stage_summary_actual_expense=5208.00
pnl_total_expenses=5208.00
expected_count=25
amount_per_activity=20.00
expected_finance_delta=500.00
```

## Canonical Android payload shape

Android may generate random `event_id` and `entity_id` values. The verifier can use exact IDs if Android exports them, or infer rows from metadata/source/index and stable notes.

For each index `i = 1..25`:

```json
{
  "event_id": "{android_generated_event_id}",
  "entity_type": "crop_activity",
  "entity_id": "{android_generated_activity_id}",
  "operation": "CREATE",
  "version": 1,
  "dependency_ids": [],
  "payload": {
    "crop_cycle_id": "aa346148-468b-47de-9c86-47ad41aa1f11",
    "stage_code": "NURSERY",
    "activity_date": "2026-08-02",
    "activity_type": "LABOR",
    "input_name": "Offline labor log",
    "quantity": 1,
    "quantity_unit": "HOURS",
    "cost_amount": 20.0,
    "currency": "INR",
    "notes": "Queue backpressure activity 01 source=android_maestro_queue_backpressure_test"
  },
  "metadata": {
    "source": "android_maestro_queue_backpressure_test",
    "queue_backpressure_index": 1,
    "queue_backpressure_count": 25
  }
}
```

For index 2, use note suffix `02` and metadata index `2`, and so on through `25`.

Headers:

```text
X-Tenant-ID: android-dynamic-test
X-Actor-ID: 11111111-1111-4111-8111-111111111111
```

## Expected Android sync behavior

Android should:

- hold all 25 local queue rows while offline;
- process them in bounded batches, for example 10 + 10 + 5;
- mark accepted rows synced per batch;
- reuse the same `event_id` and `entity_id` if a batch result is uncertain and retried;
- avoid farmer-facing raw queue internals;
- show quiet progress such as ?x items waiting? / ?synced?; only surface intervention UI for failures or conflicts.

## Expected backend response per batch

For a 10-item batch:

```json
{
  "accepted": ["{event_id_1}", "{event_id_2}"],
  "conflicts": [],
  "failed": [],
  "total_processed": 10
}
```

The accepted list contains only event IDs from that submitted batch. The final 5-item batch should return `total_processed=5`.

## WSL verifier after Android replay

After Android taps Sync Now and the queue drains:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/verify_android_queue_backpressure.py
```

This verifies:

- all 25 events have `sync_processed_events.status=COMMITTED`;
- exactly 25 new `crop_activities` materialized;
- no duplicate activity IDs;
- no `sync_conflicts` rows for those events;
- no `SYNC_FAILED` audit rows for those events;
- stage-cost `actual_expense` increased exactly by INR 500.00;
- P&L `total_expenses` increased exactly by INR 500.00.

If Android exports a manifest, pass it explicitly:

```bash
../venv/bin/python scripts/verify_android_queue_backpressure.py --events-json /path/to/android_flow27_events.json
```

If no manifest is exported, the verifier infers exact event coverage from `SYNC_COMMIT` audit metadata and activity notes/indices.

## Optional WSL sample proof

Backend deterministic proof, useful before handing to Android:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_queue_backpressure.py --reset-indexed --apply
../venv/bin/python scripts/verify_android_queue_backpressure.py --send-sample --batch-size 10
../venv/bin/python scripts/verify_android_queue_backpressure.py --resend-sample --batch-size 10
../venv/bin/python scripts/prepare_android_queue_backpressure.py --reset-indexed --apply
```

The resend proof posts the same deterministic 25 events again. Backend should return accepted IDs idempotently, with no duplicate activities and no second finance impact.

## Durable backend state after successful Android run

Expected durable state:

- one `sync_processed_events` row per event ID;
- each processed row status is `COMMITTED`;
- one `crop_activities` row per activity/entity ID;
- no duplicate activity materialization;
- no sync conflict rows;
- no failed sync audit rows;
- the Rice/NURSERY stage remains ACTIVE;
- finance delta is counted once only.

## Cleanup/reset for another run

If Android uses random IDs, prefer a new unique `metadata.source` or export exact IDs for cleanup. The WSL reset command only deletes deterministic WSL sample rows generated by `/tmp/android_queue_backpressure_sample_events.json`.

For the canonical Android test, repeatable verification is easiest when Android exports the event manifest or uses stable test notes/index metadata exactly as above.

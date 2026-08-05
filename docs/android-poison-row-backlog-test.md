# Android poison-row backlog sync test

Status date: 2026-08-05

This contract supports Android Flow 29: a larger offline sync backlog contains one `WORKFLOW_INVALID` poison row in the first batch, but later valid rows still drain and commit.

## Goal

Android queues 25 offline rows under the existing active Rice/NURSERY cycle:

- rows 1..9: valid `crop_activity` CREATE;
- row 10: invalid `crop_stage` START against already ACTIVE NURSERY, expected `WORKFLOW_INVALID` conflict;
- rows 11..25: valid `crop_activity` CREATE.

This proves one non-accepted row does not stop queue traversal.

Expected final durable state:

- 24 activity events are `COMMITTED`;
- one stage event remains `CONFLICT` / pending review;
- exactly 24 activities materialize;
- no duplicate entity IDs or activities;
- no conflicts for valid activity rows;
- no `SYNC_FAILED` audit rows;
- finance increases exactly once by `24 ? INR 20.00 = INR 480.00`;
- pending-conflict API exposes the poison row for Android workflow conflict UI;
- replaying all 25 remains idempotent and adds no second finance impact.

## Fixed backend context

```text
tenant=android-dynamic-test
project_id=0f7e0a6b-8472-5d6d-8a14-a9d000000001
farmer_id=e1ee0941-2bad-4a18-a239-2a4119608a06
parcel_id=98c1a0fa-4f5f-4b8c-97ae-d84992db1c44
cycle_id=aa346148-468b-47de-9c86-47ad41aa1f11
stage_code=NURSERY
```

NURSERY must be ACTIVE before Android starts the flow.

## WSL prep/baseline command

Run this before Android queues Flow 29:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_poison_row_backlog.py --reset-indexed --apply
```

The prep command:

- ensures the Rice cycle is ACTIVE;
- ensures NURSERY is ACTIVE;
- deletes deterministic WSL sample rows from earlier Flow 29 runs;
- records baseline activity count, stage-cost actual expense, and P&L total expenses;
- writes baseline JSON to `/tmp/android_poison_row_backlog_baseline.json`;
- writes an optional deterministic sample manifest to `/tmp/android_poison_row_backlog_sample_events.json`.

Default values:

```text
N=25
batch_size=10
valid_activity_count=24
poison_index=10
amount_per_activity=20.00
expected_final_finance_delta=480.00
metadata.source=android_maestro_poison_row_backlog_test
```

## Canonical Android event sequence

Android may generate random `event_id` and `entity_id` values. If possible, export the exact manifest used by Android for WSL verification. If not, the verifier can infer committed valid activity rows from audit metadata plus stable notes/index.

### Rows 1..9 and 11..25: valid activity

For valid index `i`:

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
    "input_name": "Poison backlog labor log",
    "quantity": 1,
    "quantity_unit": "HOURS",
    "cost_amount": 20.0,
    "currency": "INR",
    "notes": "Poison backlog valid activity 01 source=android_maestro_poison_row_backlog_test"
  },
  "metadata": {
    "source": "android_maestro_poison_row_backlog_test",
    "poison_backlog_index": 1,
    "poison_backlog_count": 25,
    "poison_backlog_role": "VALID_ACTIVITY"
  }
}
```

Use matching note suffix/index for each valid row. There is no valid activity row for index 10.

### Row 10: poison workflow conflict

```json
{
  "event_id": "{android_generated_poison_event_id}",
  "entity_type": "crop_stage",
  "entity_id": "{android_generated_poison_stage_entity_id}",
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
    "source": "android_maestro_poison_row_backlog_test",
    "poison_backlog_index": 10,
    "poison_backlog_count": 25,
    "poison_backlog_role": "WORKFLOW_INVALID_STAGE"
  }
}
```

Headers:

```text
X-Tenant-ID: android-dynamic-test
X-Actor-ID: 11111111-1111-4111-8111-111111111111
```

## Expected backend responses

With batch size 10:

### Batch 1: rows 1..10

```json
{
  "accepted": ["{event_id_1}", "...", "{event_id_9}"],
  "conflicts": [
    {
      "event_id": "{event_id_10}",
      "entity_type": "crop_stage",
      "conflict_type": "WORKFLOW_INVALID",
      "resolution_strategy": "SERVER_AUTHORITY"
    }
  ],
  "failed": [],
  "total_processed": 10
}
```

### Batch 2: rows 11..20

```json
{
  "accepted": ["{event_id_11}", "...", "{event_id_20}"],
  "conflicts": [],
  "failed": [],
  "total_processed": 10
}
```

### Batch 3: rows 21..25

```json
{
  "accepted": ["{event_id_21}", "...", "{event_id_25}"],
  "conflicts": [],
  "failed": [],
  "total_processed": 5
}
```

## Expected Android behavior

Android should:

- mark the 24 accepted activity rows synced;
- route only row 10 to workflow conflict UI;
- continue draining rows 11..25 despite row 10 returning `conflicts[]`;
- not retry accepted activity rows unless an uncertain-result path requires it;
- if accepted rows are retried with the same IDs, handle idempotent accepted responses;
- not show raw queue internals to farmers.

Use existing conflict copy for row 10:

```text
Workflow changed on backend
Refresh this crop cycle/stage before retrying the action.
```

## WSL verifier after Android replay

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/verify_android_poison_row_backlog.py
```

If Android exports exact IDs:

```bash
../venv/bin/python scripts/verify_android_poison_row_backlog.py --events-json /path/to/android_flow29_events.json
```

The verifier proves:

- 24 valid activity events are committed;
- one poison stage event is `CONFLICT`;
- exactly 24 activities materialized;
- the poison stage entity did not materialize;
- no duplicate activity IDs;
- no conflicts for valid activities;
- no failed audit rows;
- pending-conflict API exposes the poison row;
- stage-cost and P&L increased by INR 480.00.

## Optional deterministic WSL sample proof

Backend-only proof:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_poison_row_backlog.py --reset-indexed --apply
../venv/bin/python scripts/verify_android_poison_row_backlog.py --send-sample --batch-size 10
../venv/bin/python scripts/verify_android_poison_row_backlog.py --resend-sample --batch-size 10
../venv/bin/python scripts/prepare_android_poison_row_backlog.py --reset-indexed --apply
```

The resend proof posts all 25 deterministic events again after completion. Backend should accept valid rows idempotently, keep the poison row as one pending workflow conflict, and not duplicate activities or finance impact.

## Cleanup/reset for another run

For deterministic WSL sample rows:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_poison_row_backlog.py --reset-indexed --apply
```

For Android random rows, either export exact IDs for custom cleanup or use unique notes/source/index metadata per run.

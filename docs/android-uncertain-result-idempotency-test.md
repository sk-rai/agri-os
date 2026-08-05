# Android uncertain-result offline sync idempotency test

Status date: 2026-08-05

This contract covers the case where Android sends an offline sync event, the
backend commits it, but Android loses the response before it can mark the local
`sync_queue` row as synced. On the next app launch or manual **Sync Now**,
Android retries the exact same local queue row.

## Goal

Android queues a `crop_activity` CREATE under the existing active Rice/NURSERY
cycle, sends it once, simulates app/network loss before local success handling,
then retries the same row.

Backend must treat the retry as idempotent:

- no duplicate `crop_activities` row;
- no duplicate finance impact;
- no conflict;
- no failed sync audit.

## Fixed backend context

```text
tenant_id=android-dynamic-test
project_id=0f7e0a6b-8472-5d6d-8a14-a9d000000001
farmer_id=e1ee0941-2bad-4a18-a239-2a4119608a06
parcel_id=98c1a0fa-4f5f-4b8c-97ae-d84992db1c44
cycle_id=aa346148-468b-47de-9c86-47ad41aa1f11
stage_code=NURSERY
```

## WSL prep/baseline command

Run this before Android sends the event:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_uncertain_result_idempotency.py --apply
```

This ensures the known Rice cycle and NURSERY stage are `ACTIVE`, then writes:

```text
/tmp/android_uncertain_result_idempotency_baseline.json
```

The baseline records:

- NURSERY activity count;
- stage-cost summary `totals.actual_expense`;
- P&L summary `totals.total_expenses`;
- expected new activity cost `325.50`.

Do not rerun the prep after Android sends the event. Rerunning it would move the
baseline forward and make the verifier unable to prove the single delta.

## Android payload

Android may generate random UUIDs, but it must reuse the same UUIDs on retry.

Headers:

```http
X-Tenant-ID: android-dynamic-test
X-Actor-ID: 11111111-1111-4111-8111-111111111111
```

Request:

```http
POST /api/v1/sync/events
```

Body:

```json
{
  "events": [
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
        "activity_type": "FERTILIZER",
        "input_code": "DAP_18_46_0",
        "input_name": "DAP 18-46-0",
        "quantity": 1,
        "quantity_unit": "KG",
        "cost_amount": 325.5,
        "currency": "INR",
        "notes": "Uncertain-result idempotency retry test"
      },
      "metadata": {
        "source": "android_maestro_uncertain_result_idempotency_test"
      }
    }
  ]
}
```

## Android retry rule

Android must retry with the exact same:

- `event_id`;
- `entity_id`;
- `entity_type`;
- `operation`;
- `version`;
- `dependency_ids`;
- `payload`.

Android must not create a new event ID or activity/entity ID when the previous
send result is uncertain.

## Expected backend response

Current backend response shape for duplicate same-event retry is:

```json
{
  "accepted": ["{same_event_id}"],
  "conflicts": [],
  "failed": [],
  "total_processed": 1
}
```

The backend does not currently include an `idempotent: true` field. Android
should treat `accepted` containing the same event ID, with empty `conflicts` and
`failed`, as a successful idempotent replay.

## Verification commands

After Android sends the event the first time:

```bash
cd ~/projects/farmint/backend
ANDROID_UNCERTAIN_ACTIVITY_EVENT_ID={android_generated_event_id} \
ANDROID_UNCERTAIN_ACTIVITY_ID={android_generated_activity_id} \
../venv/bin/python scripts/verify_android_uncertain_result_idempotency.py
```

After Android retries the same event:

```bash
cd ~/projects/farmint/backend
ANDROID_UNCERTAIN_ACTIVITY_EVENT_ID={android_generated_event_id} \
ANDROID_UNCERTAIN_ACTIVITY_ID={android_generated_activity_id} \
../venv/bin/python scripts/verify_android_uncertain_result_idempotency.py
```

To make WSL/backend perform one extra duplicate resend and assert the exact
response shape:

```bash
cd ~/projects/farmint/backend
ANDROID_UNCERTAIN_ACTIVITY_EVENT_ID={android_generated_event_id} \
ANDROID_UNCERTAIN_ACTIVITY_ID={android_generated_activity_id} \
../venv/bin/python scripts/verify_android_uncertain_result_idempotency.py --resend
```

Calling the verifier with `--resend` after Android has already retried is safe:
it becomes a third same-event replay and should still not duplicate the activity.

## Expected durable backend state

After first send plus retry:

- exactly one `sync_processed_events` row for `event_id`;
- `sync_processed_events.status=COMMITTED`;
- `sync_processed_events.entity_type=crop_activity`;
- `sync_processed_events.entity_id={android_generated_activity_id}`;
- exactly one `crop_activities` row for `{android_generated_activity_id}`;
- activity is linked to the Rice cycle and NURSERY stage;
- no `sync_conflicts` row for the event;
- no `SYNC_FAILED` audit row for the event;
- NURSERY activity count increased by exactly one from baseline;
- stage-cost summary `totals.actual_expense` increased by exactly `325.50`;
- P&L summary `totals.total_expenses` increased by exactly `325.50`.

## Random UUID support

Random Android-generated UUIDs are supported. Android should pass the generated
values to WSL verification:

```text
ANDROID_UNCERTAIN_ACTIVITY_EVENT_ID
ANDROID_UNCERTAIN_ACTIVITY_ID
```

Stable hardcoded UUIDs are not required, but the same generated IDs must be
reused across the uncertain-result retry.

## Android UI expectation

This should not show conflict or stale-context guidance. If the retry response
contains the same event ID in `accepted`, Android may mark the local row synced
and remove it from the pending queue.


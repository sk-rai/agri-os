# Android interrupted multi-batch replay resume test

Status date: 2026-08-05

This contract supports Android Flow 28: a larger offline sync backlog is interrupted after the first bounded batch, then resumed after app/backend restart without duplicating already committed rows.

## Goal

Android queues 25 offline `crop_activity` CREATE events under the existing active Rice/NURSERY cycle. Sync uses bounded batches of 10. The first batch commits, then Android/backend/network is interrupted before the remaining 15 rows are fully replayed or acknowledged. After relaunch/retry, Android resumes safely.

This proves the ?tractor drives out of signal halfway through sync? case:

- first 10 rows remain committed once;
- remaining 15 rows stay pending locally until retry;
- final durable backend state has 25 committed rows exactly once;
- finance impact is counted once only.

## Fixed backend context

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

Run this before Android queues the Flow 28 backlog:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_interrupted_multibatch_resume.py --reset-indexed --apply
```

The prep command:

- ensures the Rice cycle is ACTIVE;
- ensures NURSERY is ACTIVE;
- deletes deterministic WSL sample rows from earlier Flow 28 runs;
- records baseline activity count, stage-cost actual expense, and P&L total expenses;
- writes baseline JSON to `/tmp/android_interrupted_multibatch_resume_baseline.json`;
- writes an optional deterministic sample manifest to `/tmp/android_interrupted_multibatch_resume_sample_events.json`.

Default values:

```text
N=25
batch_size=10
amount_per_activity=20.00
expected_final_finance_delta=500.00
metadata.source=android_maestro_interrupted_multibatch_resume_test
```

## Canonical Android payload shape

Android may generate random `event_id` and `entity_id` values. If possible, export the exact manifest used by Android for WSL verification. If not, the verifier can infer committed rows from `SYNC_COMMIT` audit metadata plus stable notes/index.

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
    "input_name": "Interrupted resume labor log",
    "quantity": 1,
    "quantity_unit": "HOURS",
    "cost_amount": 20.0,
    "currency": "INR",
    "notes": "Interrupted resume activity 01 source=android_maestro_interrupted_multibatch_resume_test"
  },
  "metadata": {
    "source": "android_maestro_interrupted_multibatch_resume_test",
    "interrupted_resume_index": 1,
    "interrupted_resume_count": 25
  }
}
```

For index 2, use note suffix `02` and metadata index `2`, and so on through `25`.

Headers:

```text
X-Tenant-ID: android-dynamic-test
X-Actor-ID: 11111111-1111-4111-8111-111111111111
```

## Expected Android sequence

1. Queue all 25 rows while backend is unavailable.
2. Start sync with bounded batch size 10.
3. Let batch 1 commit successfully.
4. Interrupt backend/network/app before batch 2 or batch 3 is acknowledged.
5. Relaunch app/restart backend.
6. Tap Sync Now or let the worker resume.
7. Send only pending rows if local acknowledgement is certain; or safely resend already committed rows if the first batch acknowledgement is uncertain.

Android should:

- mark accepted batch-1 rows synced when the response is known;
- keep unaccepted rows pending;
- reuse the same `event_id` and `entity_id` on uncertain retry;
- show quiet progress only;
- avoid farmer-facing raw queue internals unless a failure/conflict appears.

## Expected backend response per batch

For the first 10-item batch:

```json
{
  "accepted": ["{event_id_1}", "{event_id_2}"],
  "conflicts": [],
  "failed": [],
  "total_processed": 10
}
```

The resumed second batch should similarly accept only that submitted batch. With `N=25` and `batch_size=10`, expected bounded replay is `10 + 10 + 5`.

## WSL verifier after first batch

If Android intentionally stops after the first accepted batch and wants WSL confirmation:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/verify_android_interrupted_multibatch_resume.py --phase first_batch
```

This proves:

- first 10 rows are committed and materialized;
- indices 11..25 are not materialized on backend yet;
- no conflicts;
- no failed audit;
- finance delta is `10 ? 20.00 = 200.00`.

Note: WSL cannot see Android?s local pending queue. Android must verify locally that rows 11..25 remain pending.

## WSL verifier after resume completion

After Android resumes and drains the remaining rows:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/verify_android_interrupted_multibatch_resume.py --phase complete
```

This proves:

- all 25 events have `sync_processed_events.status=COMMITTED`;
- exactly 25 new `crop_activities` materialized;
- no duplicate activity IDs;
- no `sync_conflicts` rows;
- no `SYNC_FAILED` audit rows;
- stage-cost `actual_expense` increased exactly by INR 500.00;
- P&L `total_expenses` increased exactly by INR 500.00.

If Android exports its exact event manifest:

```bash
../venv/bin/python scripts/verify_android_interrupted_multibatch_resume.py --phase complete --events-json /path/to/android_flow28_events.json
```

## Optional deterministic WSL sample proof

Backend-only proof:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_interrupted_multibatch_resume.py --reset-indexed --apply
../venv/bin/python scripts/verify_android_interrupted_multibatch_resume.py --send-first-batch --phase first_batch --batch-size 10
../venv/bin/python scripts/verify_android_interrupted_multibatch_resume.py --send-remaining --phase complete --batch-size 10
../venv/bin/python scripts/verify_android_interrupted_multibatch_resume.py --resend-all --phase complete --batch-size 10
../venv/bin/python scripts/prepare_android_interrupted_multibatch_resume.py --reset-indexed --apply
```

The resend proof posts all 25 deterministic events again after completion. Backend should accept idempotently and should not duplicate activities or finance impact.

## Durable backend state after successful Android run

Expected durable state:

- one `sync_processed_events` row per event ID;
- each processed row status is `COMMITTED`;
- one `crop_activities` row per activity/entity ID;
- no duplicate materialization;
- no conflict rows;
- no failed sync audit rows;
- NURSERY remains ACTIVE;
- final finance delta is counted once only.

## Cleanup/reset for another run

For deterministic WSL sample rows:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_interrupted_multibatch_resume.py --reset-indexed --apply
```

For Android random rows, either export exact IDs for custom cleanup or use unique notes/source/index metadata per run.

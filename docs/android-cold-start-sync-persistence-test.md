# Android cold-start offline sync persistence test

Status date: 2026-08-05

This contract verifies that Android's local offline sync queue survives process death / app relaunch while backend is unavailable.

## Goal

Android queues a `crop_activity` while backend is unavailable, force-stops or relaunches the app before backend returns, then after backend restart the pending local queue row is still visible and replayable.

The backend does not see the queue row while Android is offline. Backend verification happens only after Android relaunches and taps Sync Now.

## Fixture context

- Tenant: `android-dynamic-test`
- Farmer: `e1ee0941-2bad-4a18-a239-2a4119608a06`
- Parcel: `98c1a0fa-4f5f-4b8c-97ae-d84992db1c44`
- Crop cycle: `aa346148-468b-47de-9c86-47ad41aa1f11`
- Stage code: `NURSERY`
- Expected activity cost: `325.50`

## WSL prep/reset command

Run before Android queues the offline activity:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_cold_start_activity_persistence.py --apply
```

This ensures the known Rice cycle and NURSERY stage are `ACTIVE`, then writes a baseline to:

```text
/tmp/android_cold_start_activity_persistence_baseline.json
```

Do not run this again after Android queues the offline row. It would overwrite the baseline.

## Android offline payload

Android may generate random UUIDs for `event_id` and `entity_id`.

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
        "cost_amount": 325.50,
        "currency": "INR",
        "notes": "Cold-start offline queue persistence test"
      },
      "metadata": {
        "source": "android_maestro_cold_start_persistence_test"
      }
    }
  ]
}
```

Headers when replaying:

```text
X-Tenant-ID: android-dynamic-test
X-Actor-ID: 11111111-1111-4111-8111-111111111111
```

## Android expected behavior

1. Backend is unavailable.
2. Android queues the activity locally.
3. Android app is force-stopped or emulator/app process is restarted.
4. After app relaunch, the pending sync row is still visible in local sync status.
5. Backend is restarted.
6. User taps Sync Now.
7. `/api/v1/sync/events` returns the activity event under `accepted[]`.
8. The local row is marked synced/committed and no duplicate local row remains.

## WSL verification command

If Android can provide exact UUIDs:

```bash
cd ~/projects/farmint/backend
ANDROID_COLD_START_ACTIVITY_EVENT_ID={android_generated_event_id} \
ANDROID_COLD_START_ACTIVITY_ID={android_generated_activity_id} \
../venv/bin/python scripts/verify_android_cold_start_activity_persistence.py
```

If Android uses random UUIDs and does not expose them to the WSL operator:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/verify_android_cold_start_activity_persistence.py
```

The verifier supports random Android event/activity UUIDs. Without exact UUIDs it compares against the baseline written during prep and verifies a new NURSERY activity with cost `325.50` exists after Sync Now.

## Expected backend durable state

After successful replay:

- a new `crop_activities` row exists under cycle `aa346148-468b-47de-9c86-47ad41aa1f11`;
- activity is linked to NURSERY;
- activity cost is `325.50`;
- stage-cost summary actual expense includes the activity;
- P&L total expenses include the activity;
- if `ANDROID_COLD_START_ACTIVITY_EVENT_ID` is provided, `sync_processed_events.status=COMMITTED`;
- no `sync_conflicts` row for that event;
- no `SYNC_FAILED` audit row for that event.

## App data guidance

For this test, Android must not clear app data after queueing the offline row. The point is to verify local durable queue persistence across process death/relaunch, not a full data wipe.

Acceptable:

- force-stop app;
- swipe app away;
- restart emulator while preserving app data;
- relaunch app.

Not acceptable for this specific test:

- clear app storage/data after queueing;
- reinstall app after queueing.

# Android device/emulator restart offline sync persistence test

Status date: 2026-08-05

This contract verifies that Android's durable local offline sync queue survives an emulator/device restart while backend is unavailable.

This is the next layer after app force-stop cold-start persistence. Backend verification is the same class of check: the backend only sees the event after Android relaunches and taps Sync Now.

## Goal

Android queues a `crop_activity` while backend is unavailable. Then the emulator/device is restarted while preserving app data. After emulator restart, app launch, and backend restart, the pending local sync row should still be visible and replayable.

## Fixture context

- Tenant: `android-dynamic-test`
- Farmer: `e1ee0941-2bad-4a18-a239-2a4119608a06`
- Parcel: `98c1a0fa-4f5f-4b8c-97ae-d84992db1c44`
- Crop cycle: `aa346148-468b-47de-9c86-47ad41aa1f11`
- Stage code: `NURSERY`
- Expected activity cost: `325.50`

## WSL prep/baseline command

Run before Android queues the offline activity:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_cold_start_activity_persistence.py --apply
```

This ensures the Rice cycle and NURSERY stage are `ACTIVE`, then writes the baseline to:

```text
/tmp/android_cold_start_activity_persistence_baseline.json
```

Do not rerun this after Android queues the offline row. It would overwrite the baseline.

## Expected Android payload

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
        "notes": "Device restart offline queue persistence test"
      },
      "metadata": {
        "source": "android_maestro_device_restart_persistence_test"
      }
    }
  ]
}
```

Replay headers:

```text
X-Tenant-ID: android-dynamic-test
X-Actor-ID: 11111111-1111-4111-8111-111111111111
```

## Android expected behavior

1. Backend is unavailable.
2. Android queues the activity locally.
3. Confirm the pending row appears in local sync status.
4. Restart emulator/device while preserving app data.
5. Relaunch Android app.
6. Pending sync row should still appear.
7. Restart backend.
8. Tap Sync Now.
9. `/api/v1/sync/events` returns the activity event under `accepted[]`.
10. Android marks the row synced/committed and does not create a duplicate row.

## WSL verification command

If Android can provide exact UUIDs:

```bash
cd ~/projects/farmint/backend
ANDROID_COLD_START_ACTIVITY_EVENT_ID={android_generated_event_id} \
ANDROID_COLD_START_ACTIVITY_ID={android_generated_activity_id} \
../venv/bin/python scripts/verify_android_cold_start_activity_persistence.py
```

If Android does not expose UUIDs:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/verify_android_cold_start_activity_persistence.py
```

The verifier supports random Android event/activity UUIDs. Without exact UUIDs, it compares against the WSL baseline and verifies a new NURSERY activity with cost `325.50` exists after Sync Now.

## Expected backend durable state

After successful replay:

- new `crop_activities` row exists under cycle `aa346148-468b-47de-9c86-47ad41aa1f11`;
- activity is linked to NURSERY;
- activity cost is `325.50`;
- stage-cost summary actual expense includes the activity;
- P&L total expenses include the activity;
- if exact event id is supplied, `sync_processed_events.status=COMMITTED`;
- no `sync_conflicts` row for the event;
- no `SYNC_FAILED` audit row for the event.

## WorkManager / reboot guidance

Android should not rely on an in-memory worker or in-flight request surviving device restart. The durable source of truth for pending offline sync rows must be local storage.

Recommended behavior:

- persist the queued event before attempting network replay;
- after app relaunch, rehydrate pending sync rows from local DB;
- show pending row before network replay;
- enqueue or trigger WorkManager sync after app startup/network availability;
- use stable local row id / event id so retry after reboot does not create duplicate queue rows;
- keep backoff/retry state durable enough that reboot does not lose the row;
- manual `Sync Now` should replay the same stored event, not regenerate a semantically duplicate event.

If a BOOT_COMPLETED receiver is used later, keep it as a convenience trigger only. App launch + manual Sync Now must still work without relying on boot receiver delivery.

## App data guidance

Allowed:

- emulator/device restart while preserving app data;
- app process death;
- network/backend unavailable during queue creation.

Not allowed for this specific test:

- clear app data after queueing;
- uninstall/reinstall app after queueing;
- regenerate a new offline event after reboot instead of replaying the persisted one.

# Android stale-context sync failure test

Status date: 2026-08-02

This test validates Android Home Sync Status handling for stale local context. The expected UX is a refresh-local-data message, not manual conflict review.

## Fixture

- Tenant header: `X-Tenant-ID: android-dynamic-test`
- Project: `0f7e0a6b-8472-5d6d-8a14-a9d000000001`
- Farmer: `e1ee0941-2bad-4a18-a239-2a4119608a06`
- Parcel: `98c1a0fa-4f5f-4b8c-97ae-d84992db1c44`
- Existing cycle: `aa346148-468b-47de-9c86-47ad41aa1f11`

## Preferred scenario

Use a new offline `crop_cycle` create event, not the existing cycle id. Android should queue it while the backend is stopped, using the original project id above.

Then WSL mutates the parcel to a different test project. When Android syncs, backend rejects the replay as stale context:

```json
{
  "error_code": "MATERIALIZATION_FAILED",
  "detail_code": "PARCEL_PROJECT_MISMATCH"
}
```

No `sync_conflicts` manual-review row should be created. Backend also records a retryable `sync_processed_events.status=FAILED` row and a `SYNC_FAILED` audit entry with `metadata.sync_event_id`, `metadata.error_code`, `metadata.detail_code`, and `metadata.message`.

## Android queued payload shape

Use Android-generated UUIDs for `event_id` and `entity_id`.

```json
{
  "events": [
    {
      "event_id": "{android_generated_event_id}",
      "entity_type": "crop_cycle",
      "entity_id": "{android_generated_crop_cycle_id}",
      "operation": "CREATE",
      "version": 1,
      "dependency_ids": [],
      "payload": {
        "farmer_id": "e1ee0941-2bad-4a18-a239-2a4119608a06",
        "parcel_id": "98c1a0fa-4f5f-4b8c-97ae-d84992db1c44",
        "project_id": "0f7e0a6b-8472-5d6d-8a14-a9d000000001",
        "crop_code": "RICE",
        "season_code": "KHARIF",
        "planned_sowing_date": "2026-08-02"
      },
      "metadata": {
        "source": "android_maestro_stale_context_test"
      }
    }
  ]
}
```

## WSL commands

### 1. Optional pre-check

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_stale_context_sync_failure.py
```

### 2. After Android queues the offline event, before backend restart/sync

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_stale_context_sync_failure.py --apply
```

This sets only parcel `98c1a0fa-4f5f-4b8c-97ae-d84992db1c44` to alternate test project `0f7e0a6b-8472-5d6d-8a14-a9d000000002`.

### 3. After Android restarts backend and taps Sync Now

Replace `{android_generated_event_id}` with the queued offline crop-cycle event id.

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/verify_android_stale_context_sync_failure.py --event-id {android_generated_event_id}
```

### 4. Restore fixture

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_stale_context_sync_failure.py --restore --apply
```

## Expected `/api/v1/sync/events` response fragment

```json
{
  "accepted": [],
  "conflicts": [],
  "failed": [
    {
      "event_id": "{android_generated_event_id}",
      "error_code": "MATERIALIZATION_FAILED",
      "detail_code": "PARCEL_PROJECT_MISMATCH",
      "message": "crop_cycle sync project does not match parcel project"
    }
  ]
}
```

Android should map this to:

- title: `Refresh required: local context is stale`
- action: refresh profile hydration, parcels, and eligible parcels;
- do not show manual conflict UI.

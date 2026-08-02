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


## Recovery lifecycle after Android shows stale-context guidance

When `/api/v1/sync/events` returns `failed[]` with `error_code=MATERIALIZATION_FAILED` and stale-context `detail_code` such as `PARCEL_PROJECT_MISMATCH`, `PARCEL_FARMER_MISMATCH`, `INVALID_PARCEL_FOR_FARMER`, `INVALID_FARMER_FOR_TENANT`, or `INVALID_PROJECT_FOR_TENANT`, Android should treat the queued draft as stale local context.

Android should refresh backend-owned context before allowing retry/rebuild:

```http
GET /api/v1/app-config/bootstrap?project_id=0f7e0a6b-8472-5d6d-8a14-a9d000000001
X-Tenant-ID: android-dynamic-test

GET /api/v1/auth/mode-bootstrap
X-Tenant-ID: android-dynamic-test

GET /api/v1/farmers/e1ee0941-2bad-4a18-a239-2a4119608a06/launch-context
X-Tenant-ID: android-dynamic-test

GET /api/v1/farmers/profile-readiness?project_id=0f7e0a6b-8472-5d6d-8a14-a9d000000001
X-Tenant-ID: android-dynamic-test

GET /api/v1/crop-cycles/eligible-parcels?farmer_id=e1ee0941-2bad-4a18-a239-2a4119608a06&season=KHARIF
X-Tenant-ID: android-dynamic-test
```

If the failed draft was crop-cycle/stage/activity related and a known cycle exists, Android may also refresh:

```http
GET /api/v1/crop-cycles/aa346148-468b-47de-9c86-47ad41aa1f11
X-Tenant-ID: android-dynamic-test

GET /api/v1/crop-cycles/aa346148-468b-47de-9c86-47ad41aa1f11/activities
X-Tenant-ID: android-dynamic-test
```

### Cleanup rule

Android should discard or mark discarded only the stale local queue row and its local draft data. This is client-side cleanup only.

Android should not call a backend cleanup/acknowledgement endpoint for stale-context failures. There is currently no backend failed-sync acknowledgement endpoint. The backend intentionally keeps:

- `sync_processed_events.status=FAILED` for the failed event id;
- `audit_chain.action=SYNC_FAILED` with `metadata.sync_event_id`, `metadata.error_code`, `metadata.detail_code`, and `metadata.message`.

Android should not delete:

- synced server rows;
- unrelated pending local sync rows;
- unrelated failed/conflicted rows.

Suggested action button copy:

```text
Refresh and discard draft
```

Alternative shorter copy:

```text
Refresh data
```

Suggested helper text:

```text
This draft was created from old parcel or project data. Refresh your profile and parcel list, then create it again if needed.
```

## Recovery verifier

After Android refreshes context and discards the stale local row, run:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/verify_android_stale_context_recovery_state.py --event-id {failed_stale_context_event_id}
```

Expected verifier result:

- durable `sync_processed_events.status=FAILED` remains;
- durable `SYNC_FAILED` audit remains;
- no `sync_conflicts` row exists for that event;
- event was not later accepted/committed;
- failed crop-cycle draft was not materialized;
- backend cleanup endpoint required: false.

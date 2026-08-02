# Android VERSION_MISMATCH conflict test

Status date: 2026-08-02

This test validates Android Home Sync Status handling for manual conflict review.

Expected Android UX:

- show `Manual review needed: server has a newer version`;
- do not show stale-context refresh guidance;
- route to manual/server-version conflict handling.

## Fixture

- Tenant header: `X-Tenant-ID: android-dynamic-test`
- Actor header: `X-Actor-ID: 11111111-1111-4111-8111-111111111111`
- Entity type: `crop_activity`
- Android event id: `0f7e0a6b-8472-5d6d-8a14-a9d000000111`
- Activity entity id: `0f7e0a6b-8472-5d6d-8a14-a9d000000112`
- Existing cycle: `aa346148-468b-47de-9c86-47ad41aa1f11`
- Stage code: `NURSERY`

## Why this creates VERSION_MISMATCH

WSL seeds a committed server sync record for the same `entity_type + entity_id` with `server_version=1` and a server payload hash.

Android then syncs a different offline payload for the same `entity_id` and `version=1`.

Backend conflict detection sees:

- same entity already committed;
- committed server version `1 >= client version 1`;
- payload hash differs.

So the event returns `conflicts[]` with `conflict_type=VERSION_MISMATCH`.

## WSL prepare command

Run before Android queues/syncs the offline event:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_version_mismatch_conflict.py --reset --apply
```

## Android queued payload

```json
{
  "events": [
    {
      "event_id": "0f7e0a6b-8472-5d6d-8a14-a9d000000111",
      "entity_type": "crop_activity",
      "entity_id": "0f7e0a6b-8472-5d6d-8a14-a9d000000112",
      "operation": "CREATE",
      "version": 1,
      "dependency_ids": [],
      "payload": {
        "crop_cycle_id": "aa346148-468b-47de-9c86-47ad41aa1f11",
        "stage_code": "NURSERY",
        "activity_date": "2026-08-02",
        "activity_type": "FERTILIZER",
        "input_code": "DAP_18_46_0",
        "description": "Android offline changed activity payload",
        "quantity": 1,
        "quantity_unit": "KG",
        "cost_amount": 325.5,
        "currency": "INR"
      },
      "metadata": {
        "source": "android_maestro_version_mismatch_test"
      }
    }
  ]
}
```

## Expected `/api/v1/sync/events` response fragment

```json
{
  "accepted": [],
  "conflicts": [
    {
      "event_id": "0f7e0a6b-8472-5d6d-8a14-a9d000000111",
      "conflict_type": "VERSION_MISMATCH",
      "resolution_strategy": "MANUAL_REVIEW",
      "detail": "Entity already has a committed payload for this version; changed offline payload requires conflict resolution."
    }
  ],
  "failed": []
}
```

## WSL verify command

Run after Android taps Sync Now:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/verify_android_version_mismatch_conflict.py
```

The verifier checks:

- `sync_processed_events.status=CONFLICT`;
- `sync_conflicts.conflict_type=VERSION_MISMATCH`;
- `sync_conflicts.resolution_strategy=MANUAL_REVIEW`;
- no `FAILED` processed-event row;
- `SYNC_CONFLICT` audit metadata has the matching `sync_event_id`.

## Restore/reset command

Use the same prepare command before each repeat run:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_version_mismatch_conflict.py --reset --apply
```

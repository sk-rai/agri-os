# Android WORKFLOW_INVALID conflict test

Status date: 2026-08-02

This test validates Android Home Sync Status handling for workflow/server-authority conflicts.

Expected Android UX:

- show `Workflow changed on backend`;
- show `Refresh this crop cycle/stage before retrying the action.`;
- do not show stale-context refresh guidance;
- do not show version-mismatch manual review copy.

## Fixture

- Tenant header: `X-Tenant-ID: android-dynamic-test`
- Actor header: `X-Actor-ID: 11111111-1111-4111-8111-111111111111`
- Entity type: `crop_stage`
- Operation: `UPDATE`
- Android event id: `0f7e0a6b-8472-5d6d-8a14-a9d000000121`
- Sync entity id: `0f7e0a6b-8472-5d6d-8a14-a9d000000122`
- Existing cycle: `aa346148-468b-47de-9c86-47ad41aa1f11`
- Stage code: `NURSERY`
- Invalid action: `START`

The sync `entity_id` is a deterministic conflict entity id, not the real stage row id. The backend workflow validator targets the real stage by `payload.stage_code=NURSERY`. This avoids accidental `VERSION_MISMATCH` if a prior successful stage-start replay committed against the real stage id.

## Why this creates WORKFLOW_INVALID

WSL ensures the NURSERY stage is already `ACTIVE`.

Android then queues `action=START` for that stage. `START` is valid only from `PENDING`; from `ACTIVE`, backend returns:

```json
{
  "conflict_type": "WORKFLOW_INVALID",
  "resolution_strategy": "SERVER_AUTHORITY",
  "detail": "Invalid stage transition: cannot START from ACTIVE"
}
```

No `failed[]` row should be returned.

## WSL prepare command

Run before Android queues/syncs the offline event:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_workflow_invalid_conflict.py --reset --apply
```

## Android queued payload

```json
{
  "events": [
    {
      "event_id": "0f7e0a6b-8472-5d6d-8a14-a9d000000121",
      "entity_type": "crop_stage",
      "entity_id": "0f7e0a6b-8472-5d6d-8a14-a9d000000122",
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
        "source": "android_maestro_workflow_invalid_test"
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
      "event_id": "0f7e0a6b-8472-5d6d-8a14-a9d000000121",
      "conflict_type": "WORKFLOW_INVALID",
      "resolution_strategy": "SERVER_AUTHORITY",
      "detail": "Invalid stage transition: cannot START from ACTIVE"
    }
  ],
  "failed": []
}
```

## WSL verify command

Run after Android taps Sync Now:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/verify_android_workflow_invalid_conflict.py
```

The verifier checks:

- `sync_processed_events.status=CONFLICT`;
- `sync_conflicts.conflict_type=WORKFLOW_INVALID`;
- `sync_conflicts.resolution_strategy=SERVER_AUTHORITY`;
- no `FAILED` processed-event row;
- `SYNC_CONFLICT` audit metadata has the matching `sync_event_id`.

## Restore/reset command

No separate restore is required. Use the same prepare command before each repeat run:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_workflow_invalid_conflict.py --reset --apply
```

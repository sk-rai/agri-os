# Android multi-conflict pending drawer ordering/dedup test

Status date: 2026-08-05

This contract validates the Android Home/Sync Status surface when the backend has
multiple durable pending sync conflicts at the same time:

1. one `VERSION_MISMATCH` `crop_activity` conflict;
2. one `WORKFLOW_INVALID` `crop_stage` conflict.

It also validates resend/dedup behavior so Android does not show duplicate cards
for the same `event_id`.

## Fixed backend context

```text
tenant_id=android-dynamic-test
project_id=0f7e0a6b-8472-5d6d-8a14-a9d000000001
cycle_id=aa346148-468b-47de-9c86-47ad41aa1f11
stage_code=NURSERY
```

Headers:

```http
X-Tenant-ID: android-dynamic-test
X-Actor-ID: 11111111-1111-4111-8111-111111111111
```

## WSL prep/reset command

Run before Android starts flow 26:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_multi_conflict_pending_drawer.py --reset --apply
```

The prep script:

- deletes prior deterministic Android conflict rows for this flow;
- ensures the server-side committed payload needed for `VERSION_MISMATCH`;
- ensures the existing Rice/NURSERY stage is already `ACTIVE`, making `START`
  deterministic as `WORKFLOW_INVALID`;
- writes `/tmp/android_multi_conflict_pending_drawer_baseline.json`.

## Canonical Android payloads

Endpoint:

```http
POST /api/v1/sync/events
```

### Event 1: VERSION_MISMATCH crop_activity

```json
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
    "source": "android_maestro_multi_conflict_pending_drawer_test"
  }
}
```

Why it conflicts: backend has already recorded a different committed payload for
this same `entity_id` and version.

### Event 2: WORKFLOW_INVALID crop_stage

```json
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
    "source": "android_maestro_multi_conflict_pending_drawer_test"
  }
}
```

Why it conflicts: NURSERY is already `ACTIVE`; `START` from `ACTIVE` is invalid.

## Expected `/api/v1/sync/events` response

Current response shape when Android sends both events in one batch:

```json
{
  "accepted": [],
  "conflicts": [
    {
      "event_id": "0f7e0a6b-8472-5d6d-8a14-a9d000000111",
      "conflict_type": "VERSION_MISMATCH",
      "resolution_strategy": "MANUAL_REVIEW",
      "detail": "Entity already has a committed payload for this version; changed offline payload requires conflict resolution."
    },
    {
      "event_id": "0f7e0a6b-8472-5d6d-8a14-a9d000000121",
      "conflict_type": "WORKFLOW_INVALID",
      "resolution_strategy": "SERVER_AUTHORITY",
      "detail": "Invalid stage transition: cannot START from ACTIVE"
    }
  ],
  "failed": [],
  "total_processed": 2
}
```

## Expected pending conflicts endpoint

Android should read:

```http
GET /api/v1/sync/conflicts/pending?limit=100
```

Each row includes Android-safe fields:

```json
{
  "id": "{conflict_id}",
  "event_id": "{event_id}",
  "entity_type": "crop_activity | crop_stage",
  "entity_id": "{entity_id}",
  "conflict_type": "VERSION_MISMATCH | WORKFLOW_INVALID",
  "resolution_strategy": "MANUAL_REVIEW | SERVER_AUTHORITY",
  "status": "PENDING_REVIEW",
  "created_at": "{iso_datetime}",
  "detail": "{safe backend detail}",
  "client_payload_summary": {},
  "server_payload_summary": {},
  "android_action": "SHOW_MANUAL_REVIEW_CONFLICT | SHOW_SERVER_AUTHORITY_WORKFLOW_MESSAGE"
}
```

Ordering rule: newest first by `created_at`.

Dedup rule: the pending endpoint returns one visible row per unresolved
`event_id`. If the same conflict event is resent and multiple durable conflict
rows exist internally, Android still receives one card for that `event_id`.

For this deterministic fixture, the workflow conflict is created after the
version conflict, so it should appear before the version conflict in the pending
endpoint result.

## Android UI expectation

For `VERSION_MISMATCH`:

- title: `Manual review needed: server has a newer version`;
- guidance: manual-review copy such as `Activity changed on both device and backend...`;
- `android_action=SHOW_MANUAL_REVIEW_CONFLICT`.

For `WORKFLOW_INVALID`:

- title: `Workflow changed on backend`;
- guidance: `Refresh this crop cycle/stage before retrying the action.`;
- `android_action=SHOW_SERVER_AUTHORITY_WORKFLOW_MESSAGE`.

Android should not:

- show raw queue internals to farmers;
- duplicate cards when the same conflict event is resent;
- hide the second conflict when the first is resolved.

## WSL verification commands

After Android sends both conflicts:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/verify_android_multi_conflict_pending_drawer.py
```

To make WSL/backend send and verify the batch itself:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/verify_android_multi_conflict_pending_drawer.py --send-conflict-batch
```

To prove resend/dedup behavior:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/verify_android_multi_conflict_pending_drawer.py --send-conflict-batch --resend-conflict-batch
```

The verifier checks:

- both `sync_processed_events` rows exist and have `status=CONFLICT`;
- both durable `sync_conflicts` rows exist;
- pending endpoint includes both conflicts;
- pending endpoint maps `VERSION_MISMATCH` to `SHOW_MANUAL_REVIEW_CONFLICT`;
- pending endpoint maps `WORKFLOW_INVALID` to
  `SHOW_SERVER_AUTHORITY_WORKFLOW_MESSAGE`;
- pending endpoint returns one visible row per unresolved `event_id` after resend;
- fixture conflict ordering is newest first;
- no `SYNC_FAILED` audit rows are created for either conflict event.

## Recovery / acknowledgement lifecycle

Android should acknowledge conflicts with existing conflict lifecycle after the
user refreshes context and discards/resolves the local conflicted row:

```http
PATCH /api/v1/sync/conflicts/{conflict_id}
```

Body:

```json
{
  "strategy": "ACCEPT_SERVER"
}
```

To verify resolving one card leaves the other visible:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/verify_android_multi_conflict_pending_drawer.py --ack-version
```

Expected: version conflict disappears; workflow conflict remains pending.

To verify resolving both leaves no pending row for either deterministic event:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/verify_android_multi_conflict_pending_drawer.py --ack-both
```

Expected durable state:

- processed events remain `CONFLICT`;
- resolved conflict rows move to `RESOLVED_SERVER`;
- pending endpoint no longer shows those event IDs;
- unrelated pending conflicts, if any, are untouched.
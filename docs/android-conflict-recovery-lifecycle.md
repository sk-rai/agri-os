# Android conflict recovery lifecycle

Status date: 2026-08-04

This document covers Android recovery/dismiss behavior after backend returns `conflicts[]` from `POST /api/v1/sync/events`.

Covered conflict types:

- `VERSION_MISMATCH`
- `WORKFLOW_INVALID`

## Backend expectation

Android should not resolve these only locally. Android should refresh backend-owned context, discard the local conflicted queue row/draft, and acknowledge the backend conflict as server-authority accepted.

Use:

```http
PATCH /api/v1/sync/conflicts/{conflict_id}
X-Tenant-ID: android-dynamic-test
X-Actor-ID: 11111111-1111-4111-8111-111111111111
Content-Type: application/json

{
  "strategy": "ACCEPT_SERVER",
  "comment": "Android user discarded local conflicted draft after refreshing context."
}
```

This endpoint already exists. It updates the conflict row and appends a `CONFLICT_RESOLVED` audit entry. It does not apply the Android client payload to operational tables.

Android should obtain `conflict_id` from:

```http
GET /api/v1/sync/conflicts/pending?limit=100
X-Tenant-ID: android-dynamic-test
```

Android should not use the full admin conflict detail endpoint for MVP conflict UI.

## VERSION_MISMATCH recovery

Meaning:

- server already has a committed payload for the same entity/version;
- Android offline payload differs;
- this should not be silently retried.

Android recovery flow:

1. show `Manual review needed: server has a newer version`;
2. refresh relevant server entity/context;
3. let user discard local conflicted draft or recreate a new edit from fresh server data;
4. call `PATCH /api/v1/sync/conflicts/{conflict_id}` with `ACCEPT_SERVER` after discard;
5. delete/mark discarded only that local conflicted queue row.

Suggested button copy:

```text
Use server version
```

Alternative:

```text
Discard local edit
```

Suggested helper text:

```text
This item changed on the server while you were offline. Refresh and use the server version, then make a new edit if needed.
```

## WORKFLOW_INVALID recovery

Meaning:

- backend workflow/stage state changed or Android attempted an action that is no longer valid;
- backend is server authority for crop-stage transitions.

Android recovery flow:

1. show `Workflow changed on backend`;
2. refresh crop cycle/stage state;
3. discard the invalid local workflow action;
4. call `PATCH /api/v1/sync/conflicts/{conflict_id}` with `ACCEPT_SERVER` after discard;
5. delete/mark discarded only that local conflicted queue row.

Suggested button copy:

```text
Refresh stage
```

Alternative:

```text
Discard action
```

Suggested helper text:

```text
The crop-cycle stage changed on the server. Refresh the stage timeline before retrying this action.
```

## Expected durable backend state after Android recovery

After Android local recovery and backend acknowledgement:

- `sync_processed_events.status` remains `CONFLICT` for the event id;
- `sync_conflicts.status=RESOLVED_SERVER`;
- `sync_conflicts.resolved_at` is set;
- `sync_conflicts.resolved_by` is set from `X-Actor-ID`;
- a `CONFLICT_RESOLVED` audit row exists;
- no `FAILED` processed-event row exists;
- no pending conflict remains for that event.

Android should not delete:

- synced server rows;
- unrelated pending local sync rows;
- unrelated backend conflict rows.

## Verifier commands

For deterministic `VERSION_MISMATCH` fixture:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/verify_android_conflict_recovery_state.py --conflict-type VERSION_MISMATCH
```

For deterministic `WORKFLOW_INVALID` fixture:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/verify_android_conflict_recovery_state.py --conflict-type WORKFLOW_INVALID
```

# Android stale conflict 404 dismissal test contract

This contract covers the Android-only recovery case where a pending conflict card exists locally, but the backend conflict row is already gone because the backend fixture/database was reset or the conflict was otherwise resolved outside the current Android session.

The goal is to prevent stale local conflict cards from surviving forever or showing a fatal sync error when the backend returns 404 for a conflict refresh/acknowledgement.

## Background

Fresh Android sync resilience evidence already passed for:

- stale-context sync failure;
- VERSION_MISMATCH conflict;
- WORKFLOW_INVALID conflict;
- multi-conflict pending drawer;
- partial-batch and queue/backpressure flows.

Known remaining edge case:

- Android has a local pending conflict card.
- Backend reset removes the corresponding /api/v1/sync/conflicts/{conflict_id} row.
- Android tries to refresh or acknowledge that conflict.
- Backend returns 404 because the row no longer exists.

For this edge case, 404 means server-side state is already gone/resolved from Android's point of view.

## Android behavior

Android should:

- treat conflict refresh/ACK 404 as SERVER_ALREADY_GONE;
- dismiss or mark the local conflict card resolved;
- remove the local pending conflict reference;
- avoid retrying the same stale conflict forever;
- avoid fatal sync error copy;
- avoid stale-context refresh guidance unless the original sync error is actually stale-context materialization failure.

Android should not:

- keep the conflict card visible after 404;
- show manual-review conflict copy after the server row is gone;
- show workflow-invalid or version-mismatch copy after the server row is gone;
- recreate or resend the original stale local draft automatically.

## Suggested Maestro evidence lines

    stale_conflict_ack_404_dismissed=true
    stale_conflict_card_visible_after_404=false
    stale_conflict_resolution=SERVER_ALREADY_GONE
    stale_conflict_fatal_error_visible=false
    stale_conflict_retry_loop=false

## Backend posture

No new backend endpoint is required for this V1 behavior.

Backend already returns normal 404 when a conflict id no longer exists. Android should map that response to local cleanup for this specific pending-conflict UX path.

## Existing backend verifiers for surrounding lifecycle

Use these for non-404 conflict lifecycle checks:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/verify_android_conflict_recovery_state.py --conflict-type VERSION_MISMATCH
    ../venv/bin/python scripts/verify_android_conflict_recovery_state.py --conflict-type WORKFLOW_INVALID

Use this for stale-context materialization recovery checks:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/verify_android_stale_context_recovery_state.py

## Completion criteria

Mark this closed when Android Maestro evidence confirms that a locally cached pending conflict card disappears cleanly after backend 404, without fatal sync/error copy and without a retry loop.


## Android Flow 40 evidence

Android commit:

    f7f842b test: cover stale conflict 404 dismissal

Maestro flow:

    maestro/40-stale-conflict-404-dismissal.yaml

Validated behavior:

- Android debug flow seeds a local CONFLICTED sync row with a fake backend conflict_id.
- Android taps Use server version / ACK.
- Android calls existing PATCH /api/v1/sync/conflicts/{conflict_id}.
- Backend returns 404 because the conflict id does not exist.
- Android maps 404 to SERVER_ALREADY_GONE.
- Android deletes the stale local conflict row/card.
- Non-404 errors still use the existing failure path.
- Existing successful conflict ACK path remains unchanged.

Evidence lines:

    stale_conflict_ack_404_dismissed=true
    stale_conflict_card_visible_after_404=false
    stale_conflict_resolution=SERVER_ALREADY_GONE
    stale_conflict_fatal_error_visible=false
    stale_conflict_retry_loop=false

Logcat evidence:

    Stale conflict 404 test card queued: eventId=0f7e0a6b-8472-5d6d-8a14-a9d000000404, conflictId=0f7e0a6b-8472-5d6d-8a14-a9d000404404
    Cleared stale local conflict row after 404 acknowledgement: eventId=0f7e0a6b-8472-5d6d-8a14-a9d000000404, conflictId=0f7e0a6b-8472-5d6d-8a14-a9d000404404

# Broadcast pending follow-up web smoke

Status date: 2026-08-13

This smoke verifies the FPO/admin follow-up view after one farmer has read and acknowledged a project closure notice while the remaining farmers are still pending.

## Scope

The backend verifier calls `retry-undelivered` once and proves retry safety:

- 11 PENDING rows remain pending.
- 1 ACKNOWLEDGED row remains acknowledged.
- Pending rows receive retry metadata.
- The acknowledged read/ack row is skipped and not mutated.
- Audit includes `RETRY_DELIVERIES` in addition to read/ack events.

The web smoke is read-only after the verifier and proves `/broadcasts` exposes the pending cohort and retry/audit metadata.

Expected evidence:

    broadcast_pending_delivery_count=11
    broadcast_acknowledged_delivery_count=1
    broadcast_retry_retried_rows=11
    broadcast_retry_skipped_ack_read_rows=1
    broadcast_pending_drilldown_count=11
    broadcast_retry_audit_visible=true
    broadcast_read_ack_audit_still_visible=true

## Commands

From backend:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/prepare_android_fpo_multi_village_workflow.py --reset --apply
    ../venv/bin/python scripts/prepare_android_fpo_project_closure_migration_notice.py --reset --apply
    ../venv/bin/python scripts/verify_android_broadcast_read_ack_lifecycle.py
    ../venv/bin/python scripts/verify_broadcast_pending_followup_retry_safety.py

Then from repo root:

    cd ~/projects/farmint
    set -a
    source /tmp/web-smoke-env.sh
    set +a

    WEB_BASE_URL=http://localhost:3000 \
    NEXT_PUBLIC_API_URL=http://localhost:8000 \
    NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 \
    node web/smoke/broadcast_pending_followup_smoke.mjs \
      > /tmp/broadcast-pending-followup-web-smoke.json \
      2>&1

    cat /tmp/broadcast-pending-followup-web-smoke.json

Restore:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/prepare_android_fpo_project_closure_migration_notice.py --restore

## Closure evidence

Backend verifier passed with:

    pending_followup_cohort_covered=true
    retry_pending_rows_covered=true
    retry_skips_acknowledged_rows=true
    ready_for_broadcast_pending_followup_web_smoke=true

Playwright smoke passed with:

    broadcast_pending_delivery_count=11
    broadcast_acknowledged_delivery_count=1
    broadcast_retry_retried_rows=11
    broadcast_retry_skipped_ack_read_rows=1
    broadcast_pending_drilldown_count=11
    broadcast_retry_audit_visible=true
    broadcast_read_ack_audit_still_visible=true

Smoke output:

    /tmp/broadcast-pending-followup-web-smoke.json

Screenshot:

    /home/lynksavvy/projects/farmint/web/smoke/screenshots/broadcast-pending-followup.png

Restore was run after the smoke and confirmed the selected FPO farmer returned to PROJECT context with active enrollment.

Closed assessment:

- FPO/admin can identify the pending-recipient cohort after one farmer has acknowledged.
- Retry-undelivered touches only pending rows and records retry metadata.
- Read/ack rows are skipped and remain acknowledged.
- Admin `/broadcasts` exposes retry metadata, pending drill-down, and retry/read/ack audit actions.
## Product note

This gives FPO operators the practical next step after a closure notice: inspect who still has not acknowledged and safely retry pending deliveries without altering farmers who already read or acknowledged the message.
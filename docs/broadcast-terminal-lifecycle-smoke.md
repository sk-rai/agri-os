# Broadcast terminal lifecycle smoke

Status date: 2026-08-13

This smoke verifies terminal broadcast campaign states for FPO/admin and Android-visible behavior.

Terminal states covered:

- `EXPIRED`
- `CANCELLED`

## Scope

The backend verifier transitions the deterministic FPO project closure campaign from `PUBLISHED` to either `EXPIRED` or `CANCELLED` and verifies:

- selected farmer sees the campaign before terminal transition;
- selected farmer feed hides the campaign after terminal transition;
- admin detail still exposes the terminal campaign;
- delivery history/counts remain preserved;
- audit contains `EXPIRE_CAMPAIGN` or `CANCEL_CAMPAIGN`.

The Playwright smoke verifies the `/broadcasts` admin screen can filter to the terminal status, open campaign detail, and load audit history.

Expected evidence per terminal status:

    broadcast_terminal_campaign_visible_in_admin=true
    broadcast_terminal_status=EXPIRED|CANCELLED
    broadcast_terminal_delivery_total_preserved=12
    broadcast_terminal_farmer_feed_count=0
    broadcast_terminal_audit_action_visible=EXPIRE_CAMPAIGN|CANCEL_CAMPAIGN

## Commands

Run EXPIRED path:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/prepare_android_fpo_multi_village_workflow.py --reset --apply
    ../venv/bin/python scripts/prepare_android_fpo_project_closure_migration_notice.py --reset --apply
    ../venv/bin/python scripts/verify_broadcast_terminal_lifecycle.py --action expire

    cd ~/projects/farmint
    set -a
    source /tmp/web-smoke-env.sh
    set +a
    BROADCAST_TERMINAL_STATUS=EXPIRED \
    WEB_BASE_URL=http://localhost:3000 \
    NEXT_PUBLIC_API_URL=http://localhost:8000 \
    NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 \
    node web/smoke/broadcast_terminal_lifecycle_smoke.mjs \
      > /tmp/broadcast-terminal-expired-web-smoke.json \
      2>&1
    cat /tmp/broadcast-terminal-expired-web-smoke.json

Run CANCELLED path:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/prepare_android_fpo_multi_village_workflow.py --reset --apply
    ../venv/bin/python scripts/prepare_android_fpo_project_closure_migration_notice.py --reset --apply
    ../venv/bin/python scripts/verify_broadcast_terminal_lifecycle.py --action cancel

    cd ~/projects/farmint
    set -a
    source /tmp/web-smoke-env.sh
    set +a
    BROADCAST_TERMINAL_STATUS=CANCELLED \
    WEB_BASE_URL=http://localhost:3000 \
    NEXT_PUBLIC_API_URL=http://localhost:8000 \
    NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 \
    node web/smoke/broadcast_terminal_lifecycle_smoke.mjs \
      > /tmp/broadcast-terminal-cancelled-web-smoke.json \
      2>&1
    cat /tmp/broadcast-terminal-cancelled-web-smoke.json

Restore fixture baseline after terminal smoke:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/prepare_android_fpo_project_closure_migration_notice.py --restore

## Closure evidence

EXPIRED backend verifier and Playwright smoke passed with:

    broadcast_terminal_campaign_visible_in_admin=true
    broadcast_terminal_status=EXPIRED
    broadcast_terminal_delivery_total_preserved=12
    broadcast_terminal_farmer_feed_count=0
    broadcast_terminal_audit_action_visible=EXPIRE_CAMPAIGN

CANCELLED backend verifier and Playwright smoke passed with:

    broadcast_terminal_campaign_visible_in_admin=true
    broadcast_terminal_status=CANCELLED
    broadcast_terminal_delivery_total_preserved=12
    broadcast_terminal_farmer_feed_count=0
    broadcast_terminal_audit_action_visible=CANCEL_CAMPAIGN

Smoke outputs:

    /tmp/broadcast-terminal-expired-web-smoke.json
    /tmp/broadcast-terminal-cancelled-web-smoke.json

Screenshots:

    /home/lynksavvy/projects/farmint/web/smoke/screenshots/broadcast-terminal-expired.png
    /home/lynksavvy/projects/farmint/web/smoke/screenshots/broadcast-terminal-cancelled.png

A web UI gap was fixed during the smoke: the `/broadcasts` status filter now includes `CANCELLED`, matching the backend-supported status and table display.

Restore was run after the smoke and confirmed the selected FPO farmer returned to PROJECT context with active enrollment.

Closed assessment:

- EXPIRED and CANCELLED campaigns disappear from Android-visible farmer feeds.
- Admin `/broadcasts` can filter to and inspect terminal campaigns.
- Delivery history remains preserved for terminal campaigns.
- Audit history exposes EXPIRE_CAMPAIGN and CANCEL_CAMPAIGN lifecycle events.
## Product note

This closes the broadcast campaign lifecycle for farmer-facing delivery: admins can end a campaign without deleting delivery/audit history, and Android no longer receives terminal campaigns in the active farmer broadcast feed.
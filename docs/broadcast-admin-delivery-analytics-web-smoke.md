# Broadcast admin delivery analytics web smoke

Status date: 2026-08-13

This smoke verifies the admin web surface for backend-triggered broadcast communication analytics after Android has marked a farmer closure notice as read and acknowledged.

It builds on:

- `scripts/prepare_android_fpo_multi_village_workflow.py`
- `scripts/prepare_android_fpo_project_closure_migration_notice.py`
- `scripts/verify_android_broadcast_read_ack_lifecycle.py`
- `web/smoke/broadcast_admin_delivery_analytics_smoke.mjs`

## Scope

The web smoke is read-only. It does not mark deliveries read or acknowledged. It expects the broadcast lifecycle verifier or Android Flow 44 to have already produced at least one acknowledged delivery.

Expected admin evidence:

    broadcast_admin_campaign_visible=true
    broadcast_admin_delivery_total=12
    broadcast_admin_read_count>=1
    broadcast_admin_acknowledged_count>=1
    broadcast_admin_ack_drilldown_selected_farmer_visible=true
    broadcast_admin_audit_mark_read_visible=true
    broadcast_admin_audit_acknowledge_visible=true

## Commands

From repo root, after backend/web servers are running:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/prepare_android_fpo_multi_village_workflow.py --reset --apply
    ../venv/bin/python scripts/prepare_android_fpo_project_closure_migration_notice.py --reset --apply
    ../venv/bin/python scripts/verify_android_broadcast_read_ack_lifecycle.py

Then from repo root:

    cd ~/projects/farmint
    set -a
    source /tmp/web-smoke-env.sh
    set +a

    WEB_BASE_URL=http://localhost:3000 \
    NEXT_PUBLIC_API_URL=http://localhost:8000 \
    NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 \
    node web/smoke/broadcast_admin_delivery_analytics_smoke.mjs \
      > /tmp/broadcast-admin-delivery-analytics-web-smoke.json \
      2>&1

    cat /tmp/broadcast-admin-delivery-analytics-web-smoke.json

Restore the fixture baseline:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/prepare_android_fpo_project_closure_migration_notice.py --restore

## Web closure evidence

The Playwright smoke passed with this evidence:

    broadcast_admin_campaign_visible=true
    broadcast_admin_delivery_total=12
    broadcast_admin_read_count=1
    broadcast_admin_acknowledged_count=1
    broadcast_admin_ack_drilldown_selected_farmer_visible=true
    broadcast_admin_audit_mark_read_visible=true
    broadcast_admin_audit_acknowledge_visible=true

Smoke output:

    /tmp/broadcast-admin-delivery-analytics-web-smoke.json

Screenshot:

    /home/lynksavvy/projects/farmint/web/smoke/screenshots/broadcast-admin-delivery-analytics.png

Closed assessment:

- Admin `/broadcasts` shows the FPO project closure campaign.
- Delivery lifecycle counts expose read and acknowledged delivery state.
- Delivery drill-down can filter to ACKNOWLEDGED and show the selected FPO farmer.
- Audit history exposes both MARK_DELIVERY_READ and ACKNOWLEDGE_DELIVERY.
- API cross-checks confirmed the same campaign, delivery, and audit state.
## Product note

This closes the admin/FPO visibility side of the communication loop: backend can target and generate notices, Android can read/ack them, and web admins can inspect delivery counts, acknowledged recipient drill-down, and audit events.
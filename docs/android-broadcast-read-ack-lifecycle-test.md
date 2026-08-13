# Android broadcast read/ack lifecycle test

Status date: 2026-08-13

This contract verifies that backend-triggered farmer communications are not only delivered but can be marked read and acknowledged by Android.

It builds on the FPO project closure migration notice fixture.

## Backend prepare and verify

From backend:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/prepare_android_fpo_multi_village_workflow.py --reset --apply
    ../venv/bin/python scripts/prepare_android_fpo_project_closure_migration_notice.py --reset --apply
    ../venv/bin/python scripts/verify_android_broadcast_read_ack_lifecycle.py

The verifier expects the selected farmer closure notice delivery to start as PENDING, then calls the Android-visible read and acknowledge endpoints.

## Fixture

Tenant header:

    X-Tenant-ID: android-fpo-multi-village-test

Project:

    project_id=0f7e0a6b-8472-5d6d-8a14-a9d000002001

Campaign:

    campaign_id=0f7e0a6b-8472-5d6d-8a14-a9d000002950
    event_type=PROJECT_CLOSURE_MIGRATION_NOTICE

Selected farmer:

    mobile=+919900002106
    farmer_id=0f7e0a6b-8472-5d6d-8a14-a9d000002106

## Android-visible endpoints

Fetch farmer broadcasts:

    GET /api/v1/broadcasts/farmers/{farmer_id}/broadcasts?language_code=en&include_read=true

Mark delivery read:

    POST /api/v1/broadcasts/deliveries/{delivery_id}/read

Acknowledge delivery:

    POST /api/v1/broadcasts/deliveries/{delivery_id}/acknowledge

Unread-only feed check:

    GET /api/v1/broadcasts/farmers/{farmer_id}/broadcasts?language_code=en&include_read=false

## Expected Android evidence

    broadcast_read_ack_initial_status=PENDING
    broadcast_read_status=DELIVERED
    broadcast_read_at_set=true
    broadcast_ack_status=ACKNOWLEDGED
    broadcast_acknowledged_at_set=true
    broadcast_unread_feed_count_after_read=0
    broadcast_feed_status_after_ack=ACKNOWLEDGED
    broadcast_audit_mark_read=true
    broadcast_audit_acknowledge=true

## Restore

After Android smoke, restore fixture baseline:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/prepare_android_fpo_project_closure_migration_notice.py --restore

If a test needs to rerun from PENDING delivery state, rerun the full prepare sequence.

## Product note

Read/ack state gives Agri-OS a foundation for communication analytics: delivered, read, acknowledged, and farmer-actioned. V1 is API-backed and Android-visible; V2 can add admin dashboards for acknowledgement rates and campaign follow-up queues.
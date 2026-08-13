# Android FPO project closure migration notice test

Status date: 2026-08-13

This contract covers the project-exit side of an FPO/commercial program. When a project is coming to closure, the backend should notify affected farmers and give them a clear path to continue using Agri-OS independently.

V1 keeps this simple and auditable:

- backend/admin creates a project-scoped broadcast campaign;
- the campaign explains that the project is closing;
- every active farmer in that project receives one broadcast delivery;
- Android displays the notice as actionable information;
- Android CTA copy is Continue as independent farmer;
- the notice does not block Home or force re-registration;
- when the enrollment is completed/cancelled, profile hydration moves to SELF_SERVICE context;
- farmer, parcel, crop-cycle, and profile data remain linked and auditable.

## Backend verifier

From backend:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/prepare_android_fpo_multi_village_workflow.py --reset --apply
    ../venv/bin/python scripts/verify_android_fpo_project_closure_migration_notice.py

The verifier creates a temporary project-closure broadcast campaign, publishes it, generates farmer deliveries, verifies selected farmer feed visibility, completes one selected project enrollment, verifies self-service continuation context, and restores the fixture row afterward.

## Fixture

Tenant header:

    X-Tenant-ID: android-fpo-multi-village-test

Project:

    project_id=0f7e0a6b-8472-5d6d-8a14-a9d000002001

Selected farmer:

    mobile=+919900002106
    farmer_id=0f7e0a6b-8472-5d6d-8a14-a9d000002106
    enrollment_id=0f7e0a6b-8472-5d6d-8a14-a9d000002406
    crop=MAIZE

Temporary campaign id:

    campaign_id=0f7e0a6b-8472-5d6d-8a14-a9d000002950

## Android-visible endpoints

Broadcast feed:

    GET /api/v1/broadcasts/farmers/{farmer_id}/broadcasts?language_code=en&include_read=true

Hydration before and after enrollment completion:

    GET /api/v1/farmers/by-mobile/+919900002106?include_form_contract=true&project_id=0f7e0a6b-8472-5d6d-8a14-a9d000002001

Crop-cycle continuity:

    GET /api/v1/crop-cycles?farmer_id=0f7e0a6b-8472-5d6d-8a14-a9d000002106

Admin lifecycle mutation used by verifier:

    PATCH /api/v1/farmer-project-enrollments/0f7e0a6b-8472-5d6d-8a14-a9d000002406/status

## Expected Android evidence

    fpo_closure_notice_delivery_count=12
    fpo_closure_notice_selected_farmer_visible=true
    fpo_closure_notice_event_type=PROJECT_CLOSURE_MIGRATION_NOTICE
    fpo_closure_notice_cta=Continue as independent farmer
    fpo_closure_notice_deeplink=agrios://project-closure/continue-independent
    fpo_before_closure_context=PROJECT
    fpo_after_closure_context=SELF_SERVICE
    fpo_after_closure_can_continue_independently=true
    fpo_after_closure_active_project_count=0
    fpo_after_closure_farmer_data_preserved=true

## Product note

This is intentionally framed as a migration/continuation notice, not a hard conversion wizard. The backend owns the trigger and audit trail. Android V1 only needs to display the notice and route the farmer to a safe self-service context after the project enrollment is completed/cancelled. A later V2 can add explicit farmer acknowledgement, consent capture, or a richer guided migration screen.
## Stateful Android Maestro prepare

Android Flow 43 needs the backend state to remain observable after setup. Use this stateful prepare command before running Maestro:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/prepare_android_fpo_multi_village_workflow.py --reset --apply
    ../venv/bin/python scripts/prepare_android_fpo_project_closure_migration_notice.py --reset --apply

This leaves:

- campaign published;
- 12 farmer deliveries generated;
- selected farmer feed count equals 1;
- selected enrollment status equals COMPLETED;
- selected farmer hydration mode equals SELF_SERVICE.

After Android smoke, restore reusable baseline with:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/prepare_android_fpo_project_closure_migration_notice.py --restore

The regression verifier remains restore-safe and can still be used for backend-only validation:

    ../venv/bin/python scripts/verify_android_fpo_project_closure_migration_notice.py
## Android closure evidence

Android Flow 43 passed in commit 1dc778a test: add fpo closure migration notice smoke.

Evidence reported by Android:

    fpo_closure_notice_delivery_count=1
    fpo_closure_notice_selected_farmer_visible=true
    fpo_closure_notice_event_type=PROJECT_CLOSURE_MIGRATION_NOTICE
    fpo_closure_notice_cta=Continue as independent farmer
    fpo_closure_notice_deeplink=agrios://project-closure/continue-independent
    fpo_before_closure_context=PROJECT
    fpo_after_closure_context=SELF_SERVICE
    fpo_after_closure_can_continue_independently=true
    fpo_after_closure_active_project_count=0
    fpo_after_closure_farmer_data_preserved=true

Backend restore was run after the flow and selected farmer returned to PROJECT context with active enrollment.

Closed assessment:

Project closure now has an end-to-end V1 path: backend-triggered closure notice, Android-visible continuation CTA, enrollment completion, self-service hydration, data preservation, and fixture restore. This is sufficient for MVP demo and Android regression coverage. A later V2 can add explicit consent capture, acknowledgement analytics, and richer guided migration UX.

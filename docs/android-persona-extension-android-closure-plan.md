# Android persona lifecycle extension closure plan

Status date: 2026-08-12

This plan turns the existing backend persona lifecycle extension fixture into Android Maestro closure evidence.

Backend fixture contract:

    docs/android-persona-lifecycle-test.md
    docs/android-persona-lifecycle-extension-tests.md

Backend prepare and baseline verify:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/prepare_android_persona_lifecycle_extensions.py --reset --apply
    ../venv/bin/python scripts/verify_android_persona_lifecycle_extensions.py

Canonical tenant:

    X-Tenant-ID: android-persona-lifecycle-test

Canonical projects:

    project_1=0f7e0a6b-8472-5d6d-8a14-a9d000000201
    project_2=0f7e0a6b-8472-5d6d-8a14-a9d000000202

## Flow A: project picker for multiple active memberships

Fixture:

    mobile=+919900001601
    user_id=0f7e0a6b-8472-5d6d-8a14-a9d000001601
    farmer_id=0f7e0a6b-8472-5d6d-8a14-a9d000001602

Expected Android behavior:

- hydration reports mode PROJECT_PICKER;
- active_project_count=2;
- project_selection_required=true;
- active_project_candidate=null;
- Android shows project picker;
- Android does not silently choose a default project;
- after user selects a project, Android calls bootstrap with selected project_id.

Suggested evidence lines:

    project_picker_visible=true
    project_picker_active_project_count=2
    project_selection_required=true
    project_default_silently_selected=false
    selected_project_bootstrap_project_id=0f7e0a6b-8472-5d6d-8a14-a9d000000201

## Flow B: independent/project membership transition

Fixture:

    mobile=+919900001501
    user_id=0f7e0a6b-8472-5d6d-8a14-a9d000001501
    farmer_id=0f7e0a6b-8472-5d6d-8a14-a9d000001502

Backend states:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/prepare_android_persona_lifecycle.py --state transition-associated --apply
    ../venv/bin/python scripts/verify_android_persona_lifecycle.py --state transition-associated

    ../venv/bin/python scripts/prepare_android_persona_lifecycle.py --state transition-inactive --apply
    ../venv/bin/python scripts/verify_android_persona_lifecycle.py --state transition-inactive

Expected Android behavior:

- same farmer_id is preserved;
- no duplicate farmer profile is created;
- transition-associated shows PROJECT context with one active enrollment;
- transition-inactive shows SELF_SERVICE context with zero active enrollments;
- cancelled enrollment remains auditable but not active.

Suggested evidence lines:

    transition_farmer_id_preserved=true
    transition_duplicate_farmer_created=false
    transition_associated_mode=PROJECT
    transition_associated_active_project_count=1
    transition_inactive_mode=SELF_SERVICE
    transition_inactive_active_project_count=0

## Flow C: duplicate farmer detection and cleanup

Fixture:

    mobile=+919900001801
    primary_farmer_id=0f7e0a6b-8472-5d6d-8a14-a9d000001802
    duplicate_farmer_id=0f7e0a6b-8472-5d6d-8a14-a9d000001805

Backend verifier with archive:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/prepare_android_persona_lifecycle_extensions.py --reset --apply
    ../venv/bin/python scripts/verify_android_persona_lifecycle_extensions.py --archive-duplicate

Expected Android behavior:

- hydration selects richer primary farmer;
- duplicate_farmer_count=1 before cleanup;
- duplicate list recommends primary farmer;
- Android shows duplicate cleanup action, suggested copy: Use existing profile;
- archive endpoint returns success;
- duplicate_farmer_count=0 after cleanup;
- primary parcel/soil/project context remains preserved.

Suggested evidence lines:

    duplicate_primary_selected=true
    duplicate_farmer_count_before=1
    duplicate_cleanup_action_visible=true
    duplicate_cleanup_archived=true
    duplicate_farmer_count_after=0
    duplicate_primary_context_preserved=true

## Flow D: agent reassignment lifecycle UI

Fixtures:

    assisted_farmer_id=0f7e0a6b-8472-5d6d-8a14-a9d000001402
    primary_agent_user_id=0f7e0a6b-8472-5d6d-8a14-a9d000001301
    second_agent_user_id=0f7e0a6b-8472-5d6d-8a14-a9d000001701
    project_id=0f7e0a6b-8472-5d6d-8a14-a9d000000201

Backend verifier with reassignment:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/prepare_android_persona_lifecycle_extensions.py --reset --apply
    ../venv/bin/python scripts/verify_android_persona_lifecycle_extensions.py --perform-reassignment

Expected Android behavior:

- assisted farmer starts visible to primary agent;
- assisted farmer is not visible to second agent initially;
- after reassignment, primary assigned-only worklist no longer includes assisted farmer;
- after reassignment, second assigned-only worklist includes assisted farmer;
- empty assigned-only worklist uses copy: No assigned farmers;
- no orphan farmer, parcel, soil, enrollment, or agent links.

Suggested evidence lines:

    reassignment_primary_initial_visible=true
    reassignment_second_initial_visible=false
    reassignment_unassign_primary_success=true
    reassignment_assign_second_success=true
    reassignment_primary_after_visible=false
    reassignment_second_after_visible=true
    reassignment_empty_state=No assigned farmers

## Multi-village parcel status

Backend support exists for a single farmer having plots/parcel scope across multiple villages or PINs.

Evidence:

- parcel location_scope supports object payloads;
- profile update regression stores secondary_villages and multiple pin_codes;
- docs describe farmer home location and parcel land location as separate concepts;
- Android should use backend PIN/village lookup when parcel land location differs from farmer home.

Backend proof:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/test_profile_update_endpoints.py

Current assessment:

- backend covered;
- Android named Maestro coverage is not closed yet;
- not a blocker for persona extension closure;
- recommended as a later small Android smoke if we want explicit demo confidence.

Suggested future evidence lines:

    parcel_multi_village_scope_saved=true
    parcel_secondary_villages_count=1
    parcel_pin_codes_count=2
    farmer_home_location_distinct_from_parcel=true

## FPO / many affiliated farmers status

Backend support exists through project enrollment and project enrollment CSV lifecycle.

Evidence:

- project enrollment APIs support farmer memberships;
- project enrollment CSV lifecycle supports company/FPO/insurer/dealer-led bulk onboarding;
- persona lifecycle covers project-associated farmer hydration and project picker;
- field-agent worklist covers assigned farmers, including more than one assigned farmer.

Current assessment:

- backend/project membership mechanics covered;
- Android MVP project-associated farmer behavior is covered by existing persona fixtures;
- not yet a dedicated FPO-scale Android test;
- recommended later for commercial demo: seed 25 to 100 farmers under one FPO/project and verify admin enrollment list plus Android hydration/worklist/search behavior.

Suggested future evidence lines:

    fpo_project_farmer_count=25
    fpo_affiliated_farmer_hydrates_project=true
    fpo_project_enrollment_list_visible=true
    fpo_agent_worklist_search_works=true

## Completion criteria

Mark persona lifecycle extensions closed when Android provides Maestro evidence for:

- Flow A project picker;
- Flow B independent/project transition;
- Flow C duplicate cleanup;
- Flow D agent reassignment.

Multi-village parcel and FPO-scale tests can remain separate follow-ups unless product/demo needs them immediately.

## Android closure evidence

Android implementation and Maestro closure passed in commit becfdae test: close persona extension android flows.

Changed Android areas:

- app/src/main/java/com/agrios/app/ui/home/HomeScreen.kt
- maestro/33a-persona-transition-associated.yaml
- maestro/33b-persona-transition-inactive.yaml
- maestro/34-persona-project-picker.yaml
- maestro/35a-persona-agent-reassignment-before.yaml
- maestro/35b-persona-agent-reassignment-after.yaml
- maestro/35c-persona-agent-reassignment-second-initial-empty.yaml
- maestro/35d-persona-agent-reassignment-primary-after.yaml
- maestro/36-persona-duplicate-profile.yaml
- maestro/36b-persona-duplicate-cleanup-after.yaml

Validation reported by Android:

- ./gradlew.bat :app:assembleDebug passed.
- Backend extension reset plus verifier passed.
- Flow 34 project picker passed.
- Flow 36 duplicate-before passed.
- Flow 35a primary-before passed.
- Flow 35c second-agent initial empty passed.
- Backend transition-associated verifier passed.
- Flow 33a transition-associated passed.
- Backend transition-inactive verifier passed.
- Flow 33b transition-inactive passed.
- Backend reassignment verifier with --perform-reassignment passed.
- Flow 35d primary-after passed.
- Flow 35b second-after passed.
- Backend archive duplicate after fresh reset passed.
- Flow 36b duplicate-after passed.

Closed Android-visible behavior:

- project picker appears for two active project memberships and does not silently select a default project;
- independent/project transition preserves the same farmer and does not create a duplicate;
- duplicate profile detection selects the richer primary farmer and cleanup/archive removes the empty duplicate state;
- agent reassignment before/after worklist visibility is covered for primary and second agents;
- empty assigned-agent worklist copy remains No assigned farmers.

Remaining optional follow-ups:

- single farmer with parcels across multiple villages/PINs: backend-supported and regression-covered, but no named Android Maestro smoke yet;
- FPO-scale affiliated farmer load: existing project enrollment mechanics are sufficient for MVP behavior, but a dedicated 25 to 100 farmer Android/admin smoke is recommended before a commercial FPO demo.

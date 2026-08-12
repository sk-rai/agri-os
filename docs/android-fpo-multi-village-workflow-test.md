# Android FPO multi-village workflow smoke plan

Status date: 2026-08-12

This fixture demonstrates a commercial FPO-style project: one FPO tenant has many affiliated farmers across multiple villages, growing different crops, with crop cycles sitting at different workflow stages.

It is intended for Android/Admin demo confidence after the persona lifecycle closure work.

## Backend prepare

From backend:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/prepare_android_fpo_multi_village_workflow.py --reset --apply
    ../venv/bin/python scripts/verify_android_fpo_multi_village_workflow.py

If crop/workflow seed data is missing, run the normal seed scripts first:

    ../venv/bin/python scripts/seed_reference_data.py
    ../venv/bin/python scripts/seed_crops_up.py
    ../venv/bin/python scripts/seed_enhanced_templates.py
    ../venv/bin/python scripts/seed_workflow_templates.py

## Canonical fixture

Tenant header:

    X-Tenant-ID: android-fpo-multi-village-test

Project:

    project_id=0f7e0a6b-8472-5d6d-8a14-a9d000002001

Expected shape:

    farmer_count=12
    village_count=4
    crop_codes=MAIZE,RICE,SUGARCANE,WHEAT
    stage_statuses=ACTIVE,COMPLETED,PARTIALLY_COMPLETED,PENDING

Villages:

    FPO Rampur
    FPO Chikkapura
    FPO Harohalli
    FPO Nelamangala

Android-visible endpoints:

    GET /api/v1/projects/{project_id}/farmer-enrollments?status=ACTIVE
    GET /api/v1/farmers/by-mobile/{mobile}?include_form_contract=true&project_id={project_id}
    GET /api/v1/crop-cycles?farmer_id={farmer_id}
    GET /api/v1/reports/projects/{project_id}/trace
    GET /api/v1/reports/projects/{project_id}/trace/filter-options
    GET /api/v1/app-config/bootstrap?project_id={project_id}

## Suggested Android flow

1. Load the FPO project id from a debug/admin smoke entry.
2. Assert active enrollment count is 12.
3. Assert farmer list/search includes farmers from at least 4 villages.
4. Open one farmer from each crop family: RICE, WHEAT, MAIZE, SUGARCANE.
5. For each selected farmer, fetch crop cycles and assert crop code and workflow stages render.
6. Assert different stage statuses are visible across the sample set.
7. Assert admin/project trace summary agrees with Android-visible project counts.

Suggested evidence lines:

    fpo_project_id=0f7e0a6b-8472-5d6d-8a14-a9d000002001
    fpo_affiliated_farmer_count=12
    fpo_village_count=4
    fpo_crop_codes=MAIZE,RICE,SUGARCANE,WHEAT
    fpo_stage_statuses=ACTIVE,COMPLETED,PARTIALLY_COMPLETED,PENDING
    fpo_project_enrollment_api_count=12
    fpo_project_trace_farmer_count=12
    fpo_project_trace_crop_cycle_count=12
    fpo_android_farmer_hydration_project_context=true
    fpo_android_crop_cycles_rendered=true
    fpo_android_multi_village_filter_visible=true

## Assessment

This closes the earlier commercial question more strongly than the persona fixtures alone:

- one FPO/company can manage many affiliated farmers;
- farmers can belong to the same FPO project across multiple villages/PINs;
- different crops can coexist in one project;
- each farmer can have an Android-visible crop cycle and workflow stages;
- admin trace/filter APIs can summarize and filter the project.

This is still a compact smoke, not a load test. A later scale test can raise the farmer count to 100 or 1,000 after the UI flow is stable.

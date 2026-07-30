# Android Dynamic Profile Test Context

Status date: 2026-07-29

This document defines the dedicated backend test context for Android Maestro flows that need backend-driven profile forms and land-intelligence guidance.

Default tenant remains legacy/gated off. Android fallback to legacy profile screens on default tenant is expected and correct.

## Purpose

Use this context for Android dynamic profile form testing without changing default/production posture.

Enabled only here:

- `backend_driven_farmer_forms=true`
- `backend_driven_parcel_forms=true`
- `backend_driven_soil_forms=true`
- `profile_forms.farmer_registration.enabled=true`
- `profile_forms.parcel_registration.enabled=true`
- `profile_forms.soil_profile.enabled=true`

## Seed script

Backend script:

    backend/scripts/seed_android_dynamic_profile_test_context.py

Seed/apply:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/seed_android_dynamic_profile_test_context.py --apply

Reset test profile data:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/seed_android_dynamic_profile_test_context.py --reset --apply

## Android test config

Tenant header:

    X-Tenant-ID: android-dynamic-test

Project ID:

    0f7e0a6b-8472-5d6d-8a14-a9d000000001

Test mobile:

    +919900000002

Bootstrap URL:

    /api/v1/app-config/bootstrap?project_id=0f7e0a6b-8472-5d6d-8a14-a9d000000001

## Windows curl checks

Run after backend is available at `http://localhost:8000`.

### App bootstrap

    curl.exe -sS -H "X-Tenant-ID: android-dynamic-test" "http://localhost:8000/api/v1/app-config/bootstrap?project_id=0f7e0a6b-8472-5d6d-8a14-a9d000000001"

Expected snippet:

    {
      "feature_flags": {
        "backend_driven_farmer_forms": true,
        "backend_driven_parcel_forms": true,
        "backend_driven_soil_forms": true
      },
      "profile_forms": {
        "farmer_registration": { "enabled": true },
        "parcel_registration": { "enabled": true },
        "soil_profile": { "enabled": true }
      }
    }

### Farmer form

    curl.exe -sS -H "X-Tenant-ID: android-dynamic-test" "http://localhost:8000/api/v1/forms/farmer_registration?project_id=0f7e0a6b-8472-5d6d-8a14-a9d000000001"

Expected:

- HTTP 200;
- title: `Farmer Registration`;
- submit endpoint: `/api/v1/farmers`.

### Parcel form

    curl.exe -sS -H "X-Tenant-ID: android-dynamic-test" "http://localhost:8000/api/v1/forms/parcel_registration?project_id=0f7e0a6b-8472-5d6d-8a14-a9d000000001"

Expected:

- HTTP 200;
- title: `Land Parcel`;
- submit endpoint: `/api/v1/parcels`.

### Soil form

    curl.exe -sS -H "X-Tenant-ID: android-dynamic-test" "http://localhost:8000/api/v1/forms/soil_profile?project_id=0f7e0a6b-8472-5d6d-8a14-a9d000000001"

Expected:

- HTTP 200;
- title: `Soil Profile`;
- submit endpoint: `/api/v1/soil-profiles`.

### Land intelligence, PIN only

    curl.exe -sS -H "X-Tenant-ID: android-dynamic-test" "http://localhost:8000/api/v1/profile/land-intelligence-context?pin_code=560001"

Expected:

- HTTP 200;
- `schema_version=land_intelligence_context.v1`;
- contains `climate_context`;
- contains `soil_capture_guidance`.

### Land intelligence, crop and season

    curl.exe -sS -H "X-Tenant-ID: android-dynamic-test" "http://localhost:8000/api/v1/profile/land-intelligence-context?pin_code=560001&crop_code=RICE&season_code=KHARIF"

Expected:

- HTTP 200;
- `schema_version=land_intelligence_context.v1`;
- contains `climate_context`;
- contains `soil_capture_guidance`;
- contains `crop_suitability`.

## Dynamic submit contract

When Android submits the farmer in this test context, include the project ID so backend can attach the farmer to the project and project-scoped readiness/worklist endpoints can see the new profile:

    POST /api/v1/farmers
    X-Tenant-ID: android-dynamic-test

    {
      "mobile_number": "+919900000002",
      "project_id": "0f7e0a6b-8472-5d6d-8a14-a9d000000001",
      "display_name": "Android Dynamic Test Farmer",
      "pin_code": "560001",
      "village_name_manual": "Android Dynamic Test Village",
      "primary_crop_code": "RICE",
      "assistance_mode": "SELF_SERVICE"
    }

Expected farmer response includes:

    {
      "tenant_id": "android-dynamic-test",
      "project_id": "0f7e0a6b-8472-5d6d-8a14-a9d000000001",
      "mobile_number": "+919900000002",
      "status": "ACTIVE"
    }

Backend also creates an ACTIVE `farmer_project_enrollments` row with `enrollment_source=ANDROID_PROFILE_CREATE`.

## Offline sync farmer project enrollment

When Android creates a farmer through offline sync replay, include the same `project_id` in the farmer payload:

    POST /api/v1/sync/events
    X-Tenant-ID: android-dynamic-test
    X-Actor-ID: {actor uuid}

    {
      "events": [
        {
          "entity_type": "farmer",
          "operation": "CREATE",
          "entity_id": "{android local farmer uuid}",
          "payload": {
            "mobile_number": "+919900000004",
            "project_id": "0f7e0a6b-8472-5d6d-8a14-a9d000000001",
            "display_name": "Android Sync Test Farmer",
            "village_name_manual": "Android Sync Test Village",
            "primary_crop_code": "RICE"
          },
          "version": 1,
          "dependency_ids": []
        }
      ]
    }

Backend now mirrors direct farmer create behavior for synced farmers: it creates/maintains an ACTIVE `farmer_project_enrollments` row with `enrollment_source=ANDROID_SYNC_FARMER_CREATE`.

Hydration then returns the project assignment under `project_enrollments`:

    GET /api/v1/farmers/by-mobile/+919900000004

Expected: `project_enrollments` contains the dynamic test project with `status=ACTIVE`.

Synced parcel replay also preserves Android project/geography context. When Android replays a parcel create event, include `farmer_id`, `project_id`, `pin_code`, and object-shaped `location_scope` in the parcel payload. Backend validates the farmer/project context, materializes the parcel under the same project, and hydration returns the synced parcel under `parcels`.

Expected hydration fields for synced parcels:

- `project_id`: `0f7e0a6b-8472-5d6d-8a14-a9d000000001`;
- `pin_code`: `560001`;
- `location_scope.scope_type`: `SINGLE_VILLAGE`;
- `geometry_source`: `PIN_DROP` when Android sends a pin-drop point.

Offline sync soil profile replay is also supported for the dynamic profile test context. After synced farmer and parcel events are accepted, Android may replay:

    POST /api/v1/sync/events
    X-Tenant-ID: android-dynamic-test
    X-Actor-ID: {actor uuid}

    {
      "events": [
        {
          "entity_type": "soil_profile",
          "operation": "CREATE",
          "entity_id": "{android local soil profile uuid}",
          "payload": {
            "farmer_id": "{synced farmer uuid}",
            "parcel_id": "{synced parcel uuid}",
            "project_id": "0f7e0a6b-8472-5d6d-8a14-a9d000000001",
            "data_source": "MANUAL",
            "test_date": "2026-07-30",
            "soil_texture": "LOAM",
            "soil_color": "BLACK",
            "ph": "7.0",
            "organic_carbon": "0.62",
            "boron_b": "0.44"
          },
          "version": 1,
          "dependency_ids": ["{synced parcel event id}"]
        }
      ]
    }

Backend preserves the Android local UUID as `soil_profiles.id`, validates farmer/parcel/project consistency, accepts the Android `boron_b` alias, and returns the profile in hydration under `soil_profiles`. The soil profile table does not store `project_id`; project context is validated and inferred through parcel/farmer/project enrollment.

Expected readiness after synced farmer + parcel + soil profile replay: project-scoped `soil_profile_recommended_count=0`.

For direct or synced parcel submit, `location_scope` is an object, not a string:

    {
      "farmer_id": "{farmer_id}",
      "project_id": "0f7e0a6b-8472-5d6d-8a14-a9d000000001",
      "reported_area": "1.25",
      "reported_area_unit": "ACRE",
      "ownership_type": "OWNED",
      "pin_code": "560001",
      "village_name_manual": "Android Dynamic Test Village",
      "location_scope": {
        "scope_type": "SINGLE_VILLAGE",
        "village_name_manual": "Android Dynamic Test Village",
        "pin_code": "560001"
      },
      "geometry_source": "PIN_DROP",
      "centroid_lat": "15.4589",
      "centroid_lng": "75.0078"
    }

Regression command:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/test_android_dynamic_profile_submit_flow.py

Expected final line:

    Android dynamic profile submit flow validated
## Android-visible labels

Expected current labels from backend schemas:

- farmer form title: `Farmer Registration`;
- parcel form title: `Land Parcel`;
- soil form title: `Soil Profile`;
- PIN field: use backend field label, expected similar to `PIN Code`;
- village/manual village field: use backend field label, expected similar to `Village Name`;
- save button: Android-renderer controlled, likely `Save` or `Continue`;
- land intelligence card: show when response includes `climate_context` or `soil_capture_guidance`; when crop/season is supplied, also show `crop_suitability`.

## Android rules

Android should:

- use `X-Tenant-ID: android-dynamic-test`;
- include the test `project_id` in app bootstrap and form calls;
- use `+919900000002` for new dynamic enrollment testing;
- run reset before repeatable Maestro flows;
- display land intelligence as guidance only.

Android should not:

- expect dynamic forms on default tenant;
- globally assume backend-driven profile forms are enabled;
- treat land intelligence as blocking validation;
- hardcode climate/suitability rules locally.


## Related crop-cycle fixture

For crop-cycle creation Maestro tests, use:

    docs/android-crop-cycle-test-fixture.md

This fixture uses the same `android-dynamic-test` tenant but a different mobile/farmer/parcel from dynamic profile enrollment.

# Android Crop-Cycle Test Fixture

Status date: 2026-07-29

This document defines the deterministic backend fixture for Android Maestro crop-cycle creation tests.

## Purpose

Use this fixture when Android needs a farmer and parcel where crop-cycle creation eligibility is clean and repeatable.

This fixture is separate from completed-history tests.

## Seed script

Backend script:

    backend/scripts/seed_android_crop_cycle_test_fixture.py

Reset and seed before Maestro rerun:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/seed_android_crop_cycle_test_fixture.py --reset --apply
    ../venv/bin/python scripts/seed_android_crop_cycle_test_fixture.py --apply

## Android test config

Tenant header:

    X-Tenant-ID: android-dynamic-test

Project ID:

    0f7e0a6b-8472-5d6d-8a14-a9d000000001

Farmer:

    farmer_id=4df387e8-114f-5c44-a129-a9d000000003
    mobile=+919900000003

Parcel:

    parcel_id=4df387e8-114f-5c44-a129-a9d000000004

Crop/season:

    crop_code=RICE
    season=KHARIF

## Windows curl checks

Run after backend is available at `http://localhost:8000`.

### Eligible parcels

    curl.exe -sS -H "X-Tenant-ID: android-dynamic-test" "http://localhost:8000/api/v1/crop-cycles/eligible-parcels?farmer_id=4df387e8-114f-5c44-a129-a9d000000003&season=KHARIF"

Expected response shape: bare JSON array.

Expected key fields:

    [
      {
        "parcel_id": "4df387e8-114f-5c44-a129-a9d000000004",
        "farmer_id": "4df387e8-114f-5c44-a129-a9d000000003",
        "eligible": true,
        "eligibility_status": "ELIGIBLE",
        "active_cycle": null,
        "completed_cycles": []
      }
    ]

Android should parse this endpoint as `List<EligibleParcel>`, not as an object with `schema_version`.

### Rice Kharif template

    curl.exe -sS -H "X-Tenant-ID: android-dynamic-test" "http://localhost:8000/api/v1/crop-cycles/templates/RICE?season=KHARIF"

Expected key fields:

    {
      "crop_code": "RICE",
      "crop_name": "Rice (Paddy)",
      "season_code": "KHARIF",
      "stages": [...]
    }

### Create crop cycle

Android create payload for this fixture:

    POST /api/v1/crop-cycles
    X-Tenant-ID: android-dynamic-test

    {
      "farmer_id": "4df387e8-114f-5c44-a129-a9d000000003",
      "parcel_id": "4df387e8-114f-5c44-a129-a9d000000004",
      "project_id": "0f7e0a6b-8472-5d6d-8a14-a9d000000001",
      "crop_code": "RICE",
      "season_code": "KHARIF",
      "planned_sowing_date": "{future ISO date}",
      "seed_source": "OWN_SAVED"
    }

Expected create response:

    {
      "parcel_id": "4df387e8-114f-5c44-a129-a9d000000004",
      "farmer_id": "4df387e8-114f-5c44-a129-a9d000000003",
      "status": "PLANNED",
      "crop_code": "RICE",
      "season_code": "KHARIF",
      "workflow_template_pinning_status": "PINNED",
      "stages": [...]
    }

A duplicate create without reset should return HTTP 409 with `PARCEL_HAS_IN_PROGRESS_CYCLE`.

After successful create, eligible-parcels should still include the parcel row but with:

    {
      "eligible": false,
      "eligibility_status": "HAS_ACTIVE_CYCLE",
      "active_cycle": {
        "status": "PLANNED"
      }
    }

Backend regression command:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/test_android_crop_cycle_create_flow.py

Expected final line:

    Android crop-cycle create flow validated

### Stage transition and activity logging

After creating a crop cycle, Android can start the first stage and log an activity against that active stage.

Start first stage:

    PATCH /api/v1/crop-cycles/{cycle_id}/stages/{stage_id}
    X-Tenant-ID: android-dynamic-test

    {
      "action": "START",
      "gps_lat": 15.4589,
      "gps_lng": 75.0078,
      "notes": "Start first stage"
    }

Expected response includes:

    {
      "new_status": "ACTIVE",
      "cycle_status": "ACTIVE",
      "crop_cycle": {
        "inferred_current_stage": "NURSERY"
      }
    }

Log activity:

    POST /api/v1/crop-cycles/{cycle_id}/activities
    X-Tenant-ID: android-dynamic-test

    {
      "activity_type": "LABOR",
      "input_name": "Nursery bed preparation labor",
      "quantity": "1",
      "quantity_unit": "DAY",
      "area_applied": "1.25",
      "area_unit": "ACRE",
      "cost_amount": "325.50",
      "activity_date": "{today ISO date}",
      "gps_lat": 15.4589,
      "gps_lng": 75.0078,
      "notes": "Android activity log"
    }

Expected activity response includes:

    {
      "activity_type": "LABOR",
      "stage_code": "NURSERY",
      "cycle_total_input_cost": "325.50",
      "events_published": ["crop_activity_logged.v1"]
    }

Summary endpoints should then show the logged cost:

    GET /api/v1/crop-cycles/{cycle_id}/activities
    GET /api/v1/crop-cycles/{cycle_id}/stage-cost-summary
    GET /api/v1/crop-cycles/{cycle_id}/profit-loss-summary

Expected summary snippets:

    {
      "schema_version": "crop_cycle_stage_cost_summary.v1",
      "totals": {
        "activity_count": 1,
        "actual_expense": "325.50"
      }
    }

    {
      "schema_version": "crop_cycle_profit_loss_summary.v1",
      "totals": {
        "total_expenses": "325.50",
        "profit_or_loss": "-325.50"
      }
    }

Backend regression command:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/test_android_crop_cycle_activity_logging_flow.py

Expected final line:

    Android crop-cycle activity logging flow validated
## Repeatability rule

Before each Maestro crop-cycle creation test run:

1. reset the fixture;
2. seed the fixture;
3. verify eligible-parcels returns the fixture parcel as `ELIGIBLE`;
4. create the crop cycle;
5. subsequent calls should show the parcel blocked/used for that season until reset.

## Android rules

Android should:

- use `X-Tenant-ID: android-dynamic-test`;
- use the fixture farmer ID/mobile;
- use the fixture parcel when testing crop-cycle creation;
- parse eligible parcels as an array;
- show blocking state after crop-cycle creation if rerun without reset.

Android should not:

- reuse the completed-history farmer for crop-cycle creation tests;
- assume all eligible-parcels responses have `schema_version`;
- create duplicate crop cycles for the same parcel/season/year without reset.

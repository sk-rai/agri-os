# Android Crop-Cycle Test Fixture

Status date: 2026-07-28

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

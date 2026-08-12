# Android DigiPin GPS materialization test contract

This validates that Android captures latitude/longitude and backend computes canonical DigiPin values for farmer home and parcel centroid locations.

DigiPin is backend-owned. Android may capture GPS and display returned DigiPin, but Android should not compute or infer DigiPin locally.

Backend computes DigiPin from:
- farmer enrollment_gps_lat + enrollment_gps_lng into home_digipin;
- parcel centroid_lat + centroid_lng into centroid_digipin;
- parcel geometry update centroid into centroid_digipin.

Deterministic coordinates:

    enrollment_gps_lat=12.9716
    enrollment_gps_lng=77.5946
    centroid_lat=12.9716
    centroid_lng=77.5946

Android should:
- send farmer GPS lat/lon to backend;
- send parcel centroid/geometry to backend;
- display backend-returned home_digipin and centroid_digipin;
- gracefully show empty/null DigiPin when GPS is unavailable;
- hydrate DigiPin after reload/reinstall.

Android should not:
- calculate DigiPin locally;
- infer DigiPin from PIN, village, district, or address;
- replace PIN/village with DigiPin;
- block onboarding if GPS is unavailable.

Backend verifiers:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/test_digipin_utility.py
    ../venv/bin/python scripts/test_digipin_farmer_parcel_fields.py
    ../venv/bin/python scripts/test_sync_digipin_materialization.py

Expected:
- utility encode/decode/validate passes;
- farmer with GPS gets valid home_digipin;
- farmer without GPS gets null home_digipin;
- farmer GPS update recomputes home_digipin;
- parcel with centroid gets valid centroid_digipin;
- parcel without centroid gets null centroid_digipin;
- parcel geometry update recomputes centroid_digipin;
- offline sync materialization computes/recomputes DigiPin.


## Android Flow 39 evidence

Android commit:

    fe45f56 test: add land summary digipin maestro smoke

Maestro flow:

    maestro/39-land-summary-digipin-debug-smoke.yaml

Validated behavior:

- Android triggers PIN_DROP parcel geometry update.
- Android sends centroid_lat=12.9716 and centroid_lng=77.5946.
- Backend returns centroid_digipin=4P3JK852C9.
- Android displays backend-returned DigiPin.
- Android emits digipin_source=BACKEND_RESPONSE.
- Android emits android_computed_digipin=false.
- No local DigiPin computation.
- No Room migration required for first debug/probe smoke.

Evidence lines:

    parcel_geometry_digipin=4P3JK852C9
    digipin_source=BACKEND_RESPONSE
    android_computed_digipin=false


## Farmer home DigiPin follow-up contract

This follow-up completes the Android DigiPin path for farmer home GPS.

Backend already exposes these farmer response fields:

    home_digipin
    home_digipin_algorithm_version
    home_digipin_generated_at

Backend accepts farmer GPS update fields:

    enrollment_gps_lat
    enrollment_gps_lng

Deterministic farmer GPS update:

    enrollment_gps_lat=12.9716
    enrollment_gps_lng=77.5946

Expected backend-computed DigiPin:

    home_digipin=4P3JK852C9

Android first-pass behavior:

- add farmer response DTO fields for home_digipin, home_digipin_algorithm_version, and home_digipin_generated_at;
- send farmer GPS lat/lng to backend through create/update or a debug probe;
- render backend-returned home_digipin;
- emit evidence that the DigiPin came from backend response;
- do not compute DigiPin locally;
- do not require Room migration for first debug/probe smoke unless the UI persists the value across process death;
- gracefully show null/empty DigiPin when farmer GPS is unavailable.

Recommended Maestro evidence lines:

    farmer_home_digipin=4P3JK852C9
    farmer_home_digipin_source=BACKEND_RESPONSE
    android_computed_farmer_digipin=false
    farmer_home_digipin_null_without_gps=true

Backend verifier:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/test_digipin_farmer_parcel_fields.py

Backend evidence already covered by verifier:

- farmer with GPS create returns valid home_digipin;
- farmer without GPS returns null home_digipin;
- farmer GPS update recomputes home_digipin;
- PIN code remains separate from DigiPin.


## Android farmer home DigiPin evidence

Android commit:

    46eb407 test: cover farmer home digipin smoke

Maestro flow:

    maestro/39-land-summary-digipin-debug-smoke.yaml

Validated behavior:

- Android extended farmer create/update DTO coverage for village_id, village_name_manual, pin_code, and enrollment_gps_lat/lng.
- Android creates a throwaway farmer without GPS and verifies null home_digipin.
- Android patches an existing dynamic farmer GPS to deterministic Bengaluru coordinates.
- Backend returns home_digipin=4P3JK852C9.
- Android displays backend-returned home_digipin.
- Android emits farmer_home_digipin_source=BACKEND_RESPONSE.
- Android emits android_computed_farmer_digipin=false.
- Parcel centroid DigiPin remains covered in the same flow.
- No local DigiPin computation.
- No Room migration required for this smoke.

Evidence lines:

    digipin_smoke=farmer:4P3JK852C9 farmer_null_without_gps:true parcel:4P3JK852C9 source:BACKEND_RESPONSE android:false
    farmer_home_digipin=4P3JK852C9
    farmer_home_digipin_source=BACKEND_RESPONSE
    android_computed_farmer_digipin=false
    farmer_home_digipin_null_without_gps=true
    parcel_geometry_digipin=4P3JK852C9
    digipin_source=BACKEND_RESPONSE
    android_computed_digipin=false

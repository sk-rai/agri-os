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

# Android land-intelligence summary screen test contract

This validates the Android-facing informational land summary for region, season/weather, soil-water context, suitable main crops, and suitable alternate crops.

Runtime endpoint:

    GET /api/v1/profile/land-intelligence-summary

Recommended Android smoke query:

    scope_type=PIN
    scope_code=560001
    language_code=en
    season_code=KHARIF
    crop_code=RICE

Header:

    X-Tenant-ID: default

Android should:
- show this as informational guidance only;
- not block onboarding or crop-cycle creation;
- render title, subtitle, summary cards, main crops, alternate crops, and caveats;
- preserve English fallback when selected language labels are missing;
- treat detail click-through as deferred to V2.

Android should not:
- infer suitability locally;
- call weather/location providers directly;
- treat this as mandatory agronomist approval.

Backend verifier:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/test_land_intelligence_summary_api.py

Expected lifecycle:

    DEFAULT_GENERATED -> TENANT_OVERRIDE -> DEFAULT_GENERATED

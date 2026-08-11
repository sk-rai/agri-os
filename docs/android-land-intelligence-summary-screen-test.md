# Android land-intelligence summary screen test contract

This validates the Android-facing informational land summary for region, season/weather, soil-water context, suitable main crops, and suitable alternate crops.

Runtime endpoint:

    GET /api/v1/profile/land-intelligence-summary

Recommended Android smoke query:

    pin_code=560001

Compatible alias also accepted:

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

Android should prefer pin_code for V1 because it maps directly to the current onboarding/location form. scope_type/scope_code is retained as a backend-compatible alias for admin/runtime symmetry.

Backend verifier:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/test_land_intelligence_summary_api.py

Expected lifecycle:

    DEFAULT_GENERATED -> TENANT_OVERRIDE -> DEFAULT_GENERATED


## Android Flow 39 evidence

Android commit:

    fe45f56 test: add land summary digipin maestro smoke

Maestro flow:

    maestro/39-land-summary-digipin-debug-smoke.yaml

Validated behavior:

- Android calls GET /api/v1/profile/land-intelligence-summary.
- Android renders backend land summary contract values.
- Android confirms informational-only flags.
- Android renders 4 summary cards.
- Android renders 2 main crops and 2 alternate crops.
- Android does not block onboarding from this screen.
- No Room migration required for first debug/probe smoke.

Evidence lines:

    land_summary_schema=land_intelligence_summary.v1
    land_summary_scope=PIN 560001
    land_summary_informational_only=true
    land_summary_do_not_block_onboarding=true
    land_summary_detail_clickthrough_deferred=true
    land_summary_card_count=4
    land_summary_main_crops=2
    land_summary_alternate_crops=2

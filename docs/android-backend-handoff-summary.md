# Android Backend Handoff Summary

Status date: 2026-07-27

Backend/admin status: ready for Android MVP emulator integration.

## Verified closeout

The following checks passed locally:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/audit_android_emulator_persona_readiness.py
    ../venv/bin/python scripts/pre_android_handoff_check.py

    cd ~/projects/farmint/web
    npm run build

## Persona coverage verified

Android emulator persona readiness is green.

Verified local fixtures include:

- direct farmer;
- field agent;
- company/project-associated farmer;
- independent farmer.

Latest verified readiness counts:

- 123 active farmers;
- 97 active parcels;
- 65 farmers with active parcels;
- 4 company/project-associated farmers;
- 119 independent active farmers;
- 2 agent profiles;
- 72 broadcast/advisory campaigns;
- 92 broadcast/advisory deliveries.

## Android integration principle

Android should act as a thin client.

Android should render backend-owned:

- profile forms;
- option sets;
- geography/PIN guardrail results;
- crop/workflow/stage metadata;
- input/product choices;
- advisories/broadcasts;
- weather and soil snapshots;
- profile readiness;
- finance summaries.

Android should not locally duplicate backend rules for:

- form validation/options;
- project eligibility;
- workflow/stage rules;
- PIN-to-village mapping;
- weather/soil provider execution;
- finance/P&L formulas;
- product/source trust decisions.

## Key docs

- docs/android-backend-handoff-packet.md
- docs/android-handoff-readiness-matrix.md
- docs/android-endpoint-allowlist.md
- docs/android-sample-payloads.md
- docs/samples/android/README.md

## Sample payloads

The Android sample payload bundle is under:

    docs/samples/android/

Current bundle has 25 sample payloads, including:

- mode bootstrap;
- app config bootstrap;
- PIN-code guardrail lookup;
- farmer/parcel/soil profile forms;
- profile readiness;
- weather/latest;
- broadcast feed/detail/read/ack;
- crop workflow/template;
- stage-cost and P&L summaries;
- finance analytics summary;
- sync dependency error.

## Important endpoint contracts

Android should use the endpoint allowlist:

    docs/android-endpoint-allowlist.md

Important contracts include:

- GET /api/v1/auth/mode-bootstrap
- GET /api/v1/config/app-bootstrap
- GET /api/v1/profile/contract
- GET /api/v1/forms/...
- GET /api/v1/master-data/geography/hierarchy-profile
- GET /api/v1/master-data/geography/villages/by-pin-code
- GET /api/v1/profile/readiness
- broadcast feed/detail/read/ack endpoints;
- crop workflow/cycle endpoints;
- backend-computed finance summary endpoints.

## PIN/geography rule

Android must not ship its own PIN-to-village database.

Use:

    GET /api/v1/master-data/geography/villages/by-pin-code?pin_code={pin}

The response distinguishes:

- valid postal PIN with LGD village candidates;
- valid postal PIN without LGD rural village candidates;
- PIN not found.

Android must not reject a valid postal PIN only because village candidates are empty.

## Known intentional deferrals

These are documented and not blockers for Android MVP emulator integration:

- live weather/soil provider execution remains approval-gated;
- product catalog rows are demo/reference until manufacturer/regulator verification;
- company-site product scraping continues after Android integration starts;
- broader language QA needs additional local-language seed content beyond core contract support;
- global/non-India geography remains later.

## Company/product source work parked

Company/product discovery tools are ready for later use:

- backend/scripts/build_company_product_scrape_plan.py
- backend/scripts/discover_company_official_websites.py
- backend/scripts/export_company_website_review_checklist.py

Current policy:

- Screener/TNAU are discovery sources only;
- official company sites/regulators/labels are product truth sources;
- no product scraping should start until official websites are reviewed.

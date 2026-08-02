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

## Land intelligence during profile creation

Android may call:

    GET /api/v1/profile/land-intelligence-context

Use this after state/district/PIN is known, and optionally after crop/season selection. The response gives backend-owned climate/agro-ecological context, crop-season suitability warnings, and soil capture guidance.

Android should display this as advisory intelligence during land/profile creation. Android should not hardcode climate zones, ecological zones, or crop suitability rules.

## Android MVP visibility decisions

For MVP emulator integration:

- Finance analytics aggregate page/API remains admin-only. Android should render per-cycle backend-computed stage-cost and P&L summaries only if product UX requires it.
- Company discovery/profile surfaces remain admin-only. Android should not call company discovery/admin endpoints.
- Product catalog demo/reference rows may be visible for emulator/demo flows where backend exposes them, but Android should not present them as manufacturer-verified or regulator-verified.
- Language QA proceeds English-first for emulator integration. Backend contracts support labels/options/localized content, but broader Hindi/local-language seed coverage is a later QA pass.
- Live weather and soil provider execution remains blocked until provider config is explicitly approved. Android should render saved backend snapshots/readiness only.

## Android dynamic profile test context

Dynamic backend-driven profile forms are enabled in a dedicated test context, not on the default tenant.

See:

    docs/android-dynamic-profile-test-context.md

Use:

- `X-Tenant-ID: android-dynamic-test`
- `project_id=0f7e0a6b-8472-5d6d-8a14-a9d000000001`
- test mobile `+919900000002`

Default tenant legacy fallback remains expected.

## Android crop-cycle test fixture

A deterministic crop-cycle creation fixture is available for Maestro tests.

See:

    docs/android-crop-cycle-test-fixture.md

Use this fixture when Android needs an eligible parcel for crop-cycle creation. The eligible-parcels endpoint returns a bare JSON array.

The fixture also has an offline sync crop-cycle replay regression covering dependency failure, ordered replay, idempotent replay, stage start, activity logging, and finance summary updates.


## Android stale-context sync failure test

A controlled stale-context sync failure fixture is available for Maestro Home Sync Status testing. It mutates only the Android dynamic test parcel project after Android queues an offline crop-cycle event, then verifies backend returns `MATERIALIZATION_FAILED` with `PARCEL_PROJECT_MISMATCH` and no manual conflict row.

See:

    docs/android-stale-context-sync-failure-test.md

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

## Next backend richness slice

After Android starts backend-driven profile migration, the next backend priority is crop/climate/geography suitability enrichment.

See:

    docs/crop-climate-suitability-roadmap.md

This covers:

- climatic/agro-ecological region seed sources;
- crop-season-region suitability mapping;
- 45-entry starter crop scenario target;
- Android-facing suitability warning contract;
- provider/source evidence and review policy.

## Backend gap closure tracker

Ongoing backend/demo-readiness gaps are tracked in:

    docs/backend-gap-closure-tracker.md

Use this tracker to mark discussed items as closed, active next, needs research, deferred, or watch during Android integration.

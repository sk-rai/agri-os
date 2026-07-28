# Backend Gap Closure Tracker

Status date: 2026-07-27

This tracker records discussed backend/demo-readiness items so each item is either closed, actively next, or intentionally deferred.

## Status legend

- Closed: implemented, verified, and pushed.
- Active next: next implementation candidate.
- Deferred: intentionally parked.
- Needs research: requires source/API/terms review before implementation.
- Watch during Android: backend should respond to Android integration findings.

## Tracker

| Item | Status | Decision / notes | Evidence |
| --- | --- | --- | --- |
| Android backend profile migration samples | Closed | Android should use backend-driven forms and current `app-config/bootstrap` route. | `docs/samples/android-profile-migration/` |
| Android emulator persona readiness | Closed | Direct farmer, field agent, company/project farmer, independent farmer fixtures are green. | `backend/scripts/audit_android_emulator_persona_readiness.py` |
| Crop climate suitability base tables | Closed | Added region, mapping, suitability rule tables. | Alembic `051` |
| Five-state starter climate mapping | Closed | Maharashtra, Karnataka, Uttar Pradesh, Punjab, West Bengal seeded as starter regions. | `backend/scripts/seed_crop_climate_suitability.py` |
| Effective suitability + tenant/project override | Closed | Default rules remain intact; tenant/project overrides provide effective result. | Alembic `052`, `/api/v1/crop-catalog/suitability` |
| Crop climate admin page | Closed | Dedicated admin page added. | `/crop-climate-suitability` |
| CoRE Stack climate source manifest | Closed | Extracted AEZ/ACZ/Biogeographic GEE asset IDs and class properties. | `backend/scripts/build_core_stack_climate_layer_manifest.py` |
| District fallback climate mappings | Closed | 186 district mappings populated as approximate fallback, not polygon-derived truth. | `backend/scripts/seed_climate_region_district_fallback_mappings.py` |
| Android land intelligence context | Closed | Android can consume climate/suitability as guidance during parcel/soil/crop onboarding; sample payload added. | `/api/v1/profile/land-intelligence-context`, `docs/samples/android/26-land-intelligence-context.json` |
| CoRE class importer | Closed | Imported 45 CoRE AEZ/ACZ/Biogeographic class names into climate region rows without LGD mapping. | `backend/scripts/import_core_stack_climate_regions.py` |
| CoRE polygon export + LGD overlay | Active next | Readiness audit, CoRE GEE export checklist, and LGD boundary source checklist added. CoRE class metadata and district fallback are ready; polygon exports and LGD boundary geometry are missing. | `backend/scripts/audit_climate_polygon_overlay_readiness.py`, `docs/core-stack-gee-export-checklist.md`, `docs/lgd-boundary-source-checklist.md` |
| Village coordinate geocoding | Needs research | Possible only as provider-gated enrichment with source/license/cache rules; store as label point, not centroid. | Provider terms review |
| Live weather/soil providers | Deferred | Readiness audit and live-test runbook added. Current local state: no credentials, no live-enabled providers, not safe for demo live calls yet. Keep approval-gated until credentials, budgets, monitoring, and rate limits are ready. | `backend/scripts/audit_provider_live_readiness.py`, `docs/provider-live-test-readiness-runbook.md` |
| Product source verification | Deferred | Audit and runbook added. Current catalog is demo/reference only: 31 products, 0 source URLs, 0 label URLs, 0 registration numbers, 0 review statuses. Screener/TNAU remain discovery only; official labels/regulators/manufacturer sites needed for verified product data. | `backend/scripts/audit_product_source_verification_readiness.py`, `docs/product-source-verification-runbook.md` |
| Language QA expansion | Deferred | Crop/stage Hindi metadata seed is green for demo QA: crop aliases 30/30, lifecycle template aliases 11/11, missing seeded stage labels 0. Advisory translation remains review-gated; unreviewed dynamic advisory translation is not safe. | `backend/scripts/audit_language_localization_readiness.py`, `backend/scripts/seed_language_labels_crop_stages.py`, `docs/language-localization-advisory-runbook.md` |


## Current next backend priority

After importing CoRE Stack class metadata, the next climate/geography step is polygon/LGD overlay planning:

1. export or obtain CoRE AEZ/ACZ/biogeographic geometries;
2. obtain compatible LGD district/block/village boundaries or use parcel GPS points;
3. generate reviewed mappings into `geography_climate_region_mappings`;
4. keep district fallback mappings marked approximate until replaced or validated.

Provider credentials and product-source verification remain important, but they can proceed separately from this climate metadata path.

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
| Android land intelligence context | Active next | Android should consume climate/suitability as guidance during parcel/soil/crop onboarding. | `/api/v1/profile/land-intelligence-context` |
| CoRE class importer | Active next | Import CoRE AEZ/ACZ/Biogeographic class names into climate region rows without LGD mapping yet. | Manifest JSON |
| CoRE polygon export + LGD overlay | Needs research | Needed for district/block/village precision. State/district fallback remains approximate. | CoRE GEE assets + LGD boundaries |
| Village coordinate geocoding | Needs research | Possible only as provider-gated enrichment with source/license/cache rules; store as label point, not centroid. | Provider terms review |
| Live weather/soil providers | Deferred | Keep approval-gated until credentials, budgets, monitoring, and rate limits are ready. | Provider runbooks |
| Product source verification | Deferred | Screener/TNAU are discovery only; official labels/regulators/manufacturer sites needed for verified product data. | Product source docs |
| Language QA expansion | Deferred | Backend supports labels/localized content; broader Hindi/local-language seed coverage later. | Android handoff docs |

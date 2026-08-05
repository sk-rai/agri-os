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
| Android dynamic profile test context | Watch during Android | Dedicated `android-dynamic-test` tenant/project/mobile/reset flow added for Maestro dynamic profile testing without flipping default tenant. | `backend/scripts/seed_android_dynamic_profile_test_context.py`, `docs/android-dynamic-profile-test-context.md` |
| Android crop-cycle test fixture | Watch during Android | Dedicated repeatable farmer/parcel fixture added for crop-cycle creation, stage/activity logging, and offline sync replay Maestro tests. | `backend/scripts/seed_android_crop_cycle_test_fixture.py`, `backend/scripts/test_android_offline_sync_crop_cycle_activity_flow.py`, `docs/android-crop-cycle-test-fixture.md` |
| Android stale-context sync failure test | Watch during Android | Controlled PARCEL_PROJECT_MISMATCH fixture/verifier and recovery verifier added so Android can validate refresh-local-data Home messaging and local-only stale draft discard. | `backend/scripts/prepare_android_stale_context_sync_failure.py`, `backend/scripts/verify_android_stale_context_sync_failure.py`, `backend/scripts/verify_android_stale_context_recovery_state.py`, `docs/android-stale-context-sync-failure-test.md` |
| Android VERSION_MISMATCH conflict test | Watch during Android | Controlled crop_activity fixture/verifier added so Android can validate manual conflict Home messaging without stale-context refresh guidance. | `backend/scripts/prepare_android_version_mismatch_conflict.py`, `backend/scripts/verify_android_version_mismatch_conflict.py`, `docs/android-version-mismatch-conflict-test.md` |
| Android WORKFLOW_INVALID conflict test | Watch during Android | Controlled crop_stage fixture/verifier added so Android can validate workflow-changed Home messaging without stale-context or version-mismatch guidance. | `backend/scripts/prepare_android_workflow_invalid_conflict.py`, `backend/scripts/verify_android_workflow_invalid_conflict.py`, `docs/android-workflow-invalid-conflict-test.md` |
| Android conflict recovery lifecycle | Watch during Android | Documented VERSION_MISMATCH and WORKFLOW_INVALID recovery/dismiss behavior: refresh context, discard local conflicted row, acknowledge backend conflict with ACCEPT_SERVER, verify durable resolved conflict/audit state. | `docs/android-conflict-recovery-lifecycle.md`, `backend/scripts/verify_android_conflict_recovery_state.py` |
| Android cold-start offline sync persistence | Watch during Android | Added prep/verifier contract for Android local queue persistence across app force-stop/relaunch before backend replay, using random crop_activity event/entity ids under active Rice/NURSERY cycle. | `backend/scripts/prepare_android_cold_start_activity_persistence.py`, `backend/scripts/verify_android_cold_start_activity_persistence.py`, `docs/android-cold-start-sync-persistence-test.md` |
| Android device/emulator restart sync persistence | Watch during Android | Added contract for durable Android local queue persistence across emulator/device restart while preserving app data, reusing cold-start crop_activity baseline/verifier. | `docs/android-device-restart-sync-persistence-test.md`, `backend/scripts/prepare_android_cold_start_activity_persistence.py`, `backend/scripts/verify_android_cold_start_activity_persistence.py` |
| Android uncertain-result sync idempotency | Watch during Android | Added prep/verifier contract for retrying the same crop_activity event after Android loses the first committed response. Backend verifies one processed event, one activity row, and one finance impact. | `backend/scripts/prepare_android_uncertain_result_idempotency.py`, `backend/scripts/verify_android_uncertain_result_idempotency.py`, `docs/android-uncertain-result-idempotency-test.md` |
| Android dependency-ordered offline replay | Watch during Android | Added prep/verifier contract for replaying crop_cycle, crop_stage, and crop_activity queue rows in dependency order after app/device restart. Canonical dependency_ids are sync event IDs. | `backend/scripts/prepare_android_dependency_order_replay.py`, `backend/scripts/verify_android_dependency_order_replay.py`, `docs/android-dependency-order-replay-test.md` |
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


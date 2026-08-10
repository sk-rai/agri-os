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
| Android partial-batch offline replay | Watch during Android | Added prep/verifier contract for mixed sync batches where a valid crop_activity commits while a dependency-missing crop_stage remains retryable, then commits after its crop_cycle dependency exists. | `backend/scripts/prepare_android_partial_batch_replay.py`, `backend/scripts/verify_android_partial_batch_replay.py`, `docs/android-partial-batch-replay-test.md` |
| Android partial-batch success + conflict | Watch during Android | Added prep/verifier contract for mixed sync batches where a valid crop_activity commits while a deterministic WORKFLOW_INVALID crop_stage returns conflicts[] and remains visible through Android pending conflict endpoint. | `backend/scripts/prepare_android_partial_batch_conflict.py`, `backend/scripts/verify_android_partial_batch_conflict.py`, `docs/android-partial-batch-conflict-test.md` |
| Android multi-conflict pending drawer | Watch during Android | Added prep/verifier contract for simultaneous VERSION_MISMATCH and WORKFLOW_INVALID pending conflicts, newest-first Android-safe ordering, event-id dedup, and independent ACK lifecycle. | `backend/scripts/prepare_android_multi_conflict_pending_drawer.py`, `backend/scripts/verify_android_multi_conflict_pending_drawer.py`, `docs/android-multi-conflict-pending-drawer-test.md` |
| Android sync queue pagination/backpressure | Watch during Android | Added prep/verifier contract for N=25 offline crop_activity backlog replay in bounded batches, exact-once materialization, finance delta, and resend idempotency. | `backend/scripts/prepare_android_queue_backpressure.py`, `backend/scripts/verify_android_queue_backpressure.py`, `docs/android-queue-backpressure-test.md` |
| Android interrupted multi-batch replay resume | Watch during Android | Added prep/verifier contract for N=25 offline crop_activity backlog where first 10 commit, sync is interrupted, remaining 15 resume, and full resend stays idempotent. | `backend/scripts/prepare_android_interrupted_multibatch_resume.py`, `backend/scripts/verify_android_interrupted_multibatch_resume.py`, `docs/android-interrupted-multibatch-resume-test.md` |
| Android poison-row backlog sync | Watch during Android | Added prep/verifier contract for 25-row offline backlog where row 10 returns WORKFLOW_INVALID while the other 24 activity rows commit exactly once and later batches continue draining. | `backend/scripts/prepare_android_poison_row_backlog.py`, `backend/scripts/verify_android_poison_row_backlog.py`, `docs/android-poison-row-backlog-test.md` |
| Android persona lifecycle fixture | Watch during Android | Added deterministic tenant/project/mobile fixture plus verifier for independent, project-associated, dual farmer/field-agent, assisted farmer, and independent/project transition flows with duplicate/orphan integrity checks. | `backend/scripts/prepare_android_persona_lifecycle.py`, `backend/scripts/verify_android_persona_lifecycle.py`, `docs/android-persona-lifecycle-test.md` |
| Android persona lifecycle extensions | Watch during Android | Added deterministic extension contract for multiple active project membership/project picker, field-agent reassignment, and duplicate farmer profile detection/archive cleanup without orphan links. | `backend/scripts/prepare_android_persona_lifecycle_extensions.py`, `backend/scripts/verify_android_persona_lifecycle_extensions.py`, `docs/android-persona-lifecycle-extension-tests.md` |
| CoRE class importer | Closed | Imported 45 CoRE AEZ/ACZ/Biogeographic class names into climate region rows without LGD mapping. | `backend/scripts/import_core_stack_climate_regions.py` |
| CoRE polygon export + LGD overlay | Deferred | CoRE/LGD promoted coverage is now sufficient for Android/backend testing: 20 active promoted districts / 60 active mapping rows across Karnataka, Maharashtra, and Punjab. Two Karnataka districts, Chamarajanagar/Chamarajanagara (`29/531`) and Davanagere/Davangere (`29/535`), remain approved but inactive pending manual/map review of near-threshold overlaps. SOI remains an official geometry reference, but the current extracted district shapefile DIST_LGD values are not safe as direct backend LGD keys. | `backend/scripts/build_core_lgd_held_low_margin_review_artifact.py`, `backend/scripts/verify_core_lgd_active_promoted_state.py`, `docs/core-lgd-admin-review-surface.md` |
| Irrigation canal network layer | Deferred | NWIC/CWC Canal Network appears valuable as a water-infrastructure plausibility layer for farmer-reported irrigation source, especially CANAL vs TUBEWELL/RAINFED confirmation prompts. Treat as evidence, not truth; proximity does not prove water availability. | `docs/irrigation-canal-network-layer-analysis.md` |
| Village coordinate geocoding | Needs research | Possible only as provider-gated enrichment with source/license/cache rules; store as label point, not centroid. | Provider terms review |
| Live weather/soil providers | Deferred | Readiness audit and live-test runbook added. Current local state: no credentials, no live-enabled providers, not safe for demo live calls yet. Keep approval-gated until credentials, budgets, monitoring, and rate limits are ready. | `backend/scripts/audit_provider_live_readiness.py`, `docs/provider-live-test-readiness-runbook.md` |
| Product source verification | Deferred | Audit and runbook added. Current catalog is demo/reference only: 31 products, 0 source URLs, 0 label URLs, 0 registration numbers, 0 review statuses. Screener/TNAU remain discovery only; official labels/regulators/manufacturer sites needed for verified product data. | `backend/scripts/audit_product_source_verification_readiness.py`, `docs/product-source-verification-runbook.md` |
| Language QA expansion | Watch during Android | Android multilingual test plan added for Hindi plus Kannada/Marathi/Punjabi state contexts. Current audited form/option labels have complete English fallback and Hindi keys; Kannada, Marathi, and Punjabi are explicit fallback scenarios until native labels are added and reviewed. Advisory translation remains review-gated. | `backend/scripts/audit_android_multilingual_form_labels.py`, `docs/android-multilingual-profile-form-test.md`, `docs/language-localization-advisory-runbook.md` |


## Current next backend priority

After importing CoRE Stack class metadata, the next climate/geography step is polygon/LGD overlay planning:

1. export or obtain CoRE AEZ/ACZ/biogeographic geometries;
2. obtain compatible LGD district/block/village boundaries or use parcel GPS points;
3. generate reviewed mappings into `geography_climate_region_mappings`;
4. keep district fallback mappings marked approximate until replaced or validated.

Provider credentials and product-source verification remain important, but they can proceed separately from this climate metadata path.



- CoRE/LGD review decision workflow added: admins can mark inactive `POLY_REV` candidates as `APPROVED_FOR_PROMOTION`, `REJECTED`, or `MANUAL_REVIEW`. This does not activate rows or change land-intelligence behavior.


- CoRE/LGD approved activation planner added: read-only script reports `APPROVED_FOR_PROMOTION` candidates eligible for a future separate apply workflow. Baseline currently has zero approved rows.


- Bagalkote CoRE/LGD activation pilot promoted: 3 `POLY_APPR` active mappings now replace the previous starter fallback for Karnataka district LGD 524. Verification passed.


- CoRE/LGD reusable activation verifier and next-batch planner added: district-scoped verification now works beyond Bagalkote, and read-only planning recommends safe high-overlap pilot-state candidates before approval/apply.


- Balanced CoRE/LGD activation pilot promoted: Bengaluru Urban, Beed, and Malerkotla now use active `POLY_APPR` CoRE mappings across all 3 region systems. Verifiers passed.


- Second balanced CoRE/LGD activation pilot promoted: Bengaluru Rural, Hingoli, and Sri Muktsar Sahib now use active `POLY_APPR` CoRE mappings across all 3 region systems. Verifiers and land-intelligence checks passed.

- Guarded clean CoRE/LGD activation batch completed for 5 more districts. Active promoted coverage is now 12 districts / 36 rows; active demo fallback rows reduced to 174.

- Expanded active CoRE/LGD promoted coverage to 20 districts / 60 rows; retained Chamarajanagara and Davangere as approved-but-inactive low-margin review items.

- Held two low-margin Karnataka approved candidates, Chamarajanagar and Davanagere, for manual/map review before activation.

| Android stale local conflict card after backend reset | Android follow-up | Fresh sync resilience Maestro pass completed for Flows 14–16 and 20–29. Remaining gap: if backend reset deletes a pending conflict row, Android may retain a stale local conflict card; ACK/refresh `404` should dismiss/mark resolved as already gone server-side. | Android commit `1b7ff1e`; `docs/android-maestro-sync-multilingual-evidence.md` |

- Shared Android sync fixture baseline documented after post-refactor Flow 15/16 smoke evidence survived shutdown. Canonical IDs now live in `backend/scripts/android_dynamic_sync_baseline.py`; Flow 15/16 use that helper, and reset behavior is documented in `docs/android-maestro-sync-multilingual-evidence.md`.

| Admin translation override surface | Deferred/product design | Proposed admin surface for backend-driven form, crop stage, input, and option-set translations: show defaults, allow tenant/project override, preserve English fallback, and keep label overrides separate from workflow semantics. Future demo-language expansion candidates include Tamil, Telugu, and Bengali/Bangla. | `docs/android-multilingual-profile-form-test.md`, `backend/scripts/export_android_multilingual_mvp_translation_backlog.py` |

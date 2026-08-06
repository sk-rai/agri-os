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

## Deterministic persona lifecycle fixture

A dedicated Android persona lifecycle contract is available for Maestro coverage of independent farmers, project-associated farmers, dual farmer/field-agent users, field-agent assisted farmers, and independent/project transition states.

Use:

    backend/scripts/prepare_android_persona_lifecycle.py
    backend/scripts/verify_android_persona_lifecycle.py
    docs/android-persona-lifecycle-test.md

Dedicated tenant/project:

    X-Tenant-ID: android-persona-lifecycle-test
    project_id: 0f7e0a6b-8472-5d6d-8a14-a9d000000201

Verifier coverage includes no duplicate farmer rows per mobile and no orphan parcel, soil profile, enrollment, or agent links.

Extension coverage is also available for multiple active project memberships/project picker, agent reassignment, and duplicate profile cleanup:

    backend/scripts/prepare_android_persona_lifecycle_extensions.py
    backend/scripts/verify_android_persona_lifecycle_extensions.py
    docs/android-persona-lifecycle-extension-tests.md

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
- docs/android-persona-lifecycle-test.md
- docs/android-persona-lifecycle-extension-tests.md
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


## Android poison-row backlog sync

A poison-row backlog contract is available for Android offline sync QA. Android queues 25 rows where row 10 is a deterministic `WORKFLOW_INVALID` crop_stage event, while the other 24 are valid crop_activity rows. Backend verifies later batches continue draining, valid rows commit exactly once, and only the poison row remains visible through pending conflict UI.

See:

    docs/android-poison-row-backlog-test.md

## Android interrupted multi-batch replay resume

An interrupted multi-batch resume contract is available for Android offline sync QA. Android queues 25 `crop_activity` rows, commits the first bounded batch, simulates interruption before the remaining rows are acknowledged, then resumes without duplicating first-batch materialization or finance impact.

See:

    docs/android-interrupted-multibatch-resume-test.md

## Android sync queue pagination/backpressure

A queue backpressure contract is available for Android offline sync QA. Android queues 25 `crop_activity` rows under active Rice/NURSERY, syncs them in bounded batches, and backend verifies exact-once materialization plus a single INR 500.00 finance delta.

See:

    docs/android-queue-backpressure-test.md

## Android multi-conflict pending drawer ordering/dedup

A multi-conflict pending drawer contract is available for Android offline sync QA. Android sends one batch with deterministic `VERSION_MISMATCH` and `WORKFLOW_INVALID` conflicts, verifies newest-first pending ordering, one visible card per unresolved event ID, and independent acknowledgement lifecycle.

See:

    docs/android-multi-conflict-pending-drawer-test.md

## Android partial-batch success + conflict

A partial-batch success + conflict contract is available for Android offline sync QA. Android sends one mixed batch where a valid `crop_activity` commits while a deterministic `WORKFLOW_INVALID` `crop_stage` event returns `conflicts[]`. Android should mark the accepted row synced and route the conflict row to server-authority workflow conflict UI.

See:

    docs/android-partial-batch-conflict-test.md

## Android device/emulator restart sync persistence

A device/emulator restart persistence contract is available for Android offline sync QA. Android queues a `crop_activity` while backend is unavailable, restarts the emulator/device while preserving app data, then replays the same pending event after app/backend relaunch. Backend uses the same baseline/verifier as cold-start persistence.

See:

    docs/android-device-restart-sync-persistence-test.md

## Android partial-batch offline replay resilience

A partial-batch replay contract is available for Android offline sync QA. Android sends one batch with a valid `crop_activity` and a dependency-missing `crop_stage`; backend commits only the valid row, keeps the dependency-missing row retryable, and verifies retry after the missing `crop_cycle` dependency is committed.

See:

    docs/android-partial-batch-replay-test.md

## Android dependency-ordered offline replay

A dependency-ordered replay contract is available for Android offline sync QA. Android queues a `crop_cycle` create, `crop_stage` start, and `crop_activity` create while backend is unavailable, survives app/device restart, then replays the queue in dependency order. Backend verifies one cycle, active NURSERY stage, one activity, and one finance impact.

See:

    docs/android-dependency-order-replay-test.md

## Android uncertain-result sync idempotency

An uncertain-result idempotency contract is available for Android offline sync QA. Android sends a `crop_activity` sync event, simulates app/network loss before marking the local row synced, then retries the exact same `event_id` and `entity_id`. Backend confirms one committed processed event, one activity row, and one finance impact.

See:

    docs/android-uncertain-result-idempotency-test.md

## Android cold-start offline sync persistence

A cold-start persistence contract is available for Android offline sync QA. Android queues a `crop_activity` while backend is unavailable, force-stops/relaunches the app, then replays after backend restart. Backend verifies a new committed NURSERY activity appears after the WSL baseline and finance summaries include the cost.

See:

    docs/android-cold-start-sync-persistence-test.md

## Android conflict recovery lifecycle

For `VERSION_MISMATCH` and `WORKFLOW_INVALID`, Android should refresh context, discard only the local conflicted queue row, and acknowledge the backend conflict with `PATCH /api/v1/sync/conflicts/{conflict_id}` using `ACCEPT_SERVER`. This leaves durable resolved conflict/audit state and avoids stale pending conflict rows.

See:

    docs/android-conflict-recovery-lifecycle.md

## Android WORKFLOW_INVALID conflict test

A controlled WORKFLOW_INVALID fixture is available for Maestro Home Sync Status testing. It ensures the existing Rice NURSERY stage is `ACTIVE`, then Android replays a deterministic invalid `crop_stage` `START` action. Backend returns `conflicts[]` with `WORKFLOW_INVALID` and no `failed[]` row.

See:

    docs/android-workflow-invalid-conflict-test.md

## Android VERSION_MISMATCH conflict test

A controlled VERSION_MISMATCH fixture is available for Maestro Home Sync Status testing. It seeds a committed server sync payload for a fixed `crop_activity` entity, then Android replays a different offline payload for the same entity id/version. Backend returns `conflicts[]` with `VERSION_MISMATCH` and no `failed[]` row.

See:

    docs/android-version-mismatch-conflict-test.md

## Android stale-context recovery lifecycle

Android stale-context recovery is client-side: refresh backend-owned context, discard only the stale local draft queue row, and keep unrelated sync rows intact. Backend keeps durable `FAILED` sync/audit records; no cleanup endpoint is required.

Verifier:

    backend/scripts/verify_android_stale_context_recovery_state.py

See recovery section in:

    docs/android-stale-context-sync-failure-test.md

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

# Android Backend Handoff Packet

Status date: 2026-07-20

Current backend readiness estimate for Android MVP handoff: about 94%.

This packet is not the signal to begin Android rewiring. It is the backend closeout map that will become the Android integration guide after backend testing, provider-worker stubs, permission review, and final regression are complete.

## Handoff principle

Android should become a thin client for profile capture, communication, readiness, and advisory consumption. It should not duplicate backend rules for eligibility, targeting, provider calls, weather logic, soil enrichment grouping, company discovery, or operational queues.

## Backend-ready areas

### 1. Broadcasts and farmer communication

Backend-ready capabilities:

- localized broadcast campaigns, content, media attachments, audience rules, deliveries, and audit trail;
- admin lifecycle: draft, edit, publish, expire, cancel, generate deliveries, retry undelivered, inspect deliveries;
- farmer feed, detail/read, and acknowledgement endpoints;
- targeting by farmer, project, crop, location, language, crop stage, and backend weather snapshot criteria.

Android later consumes:

- broadcast feed;
- broadcast detail;
- read/acknowledgement actions;
- media attachment display;
- backend-provided localized content.

Android should not:

- calculate broadcast audience locally;
- call weather or soil providers;
- decide campaign eligibility locally.

### 2. Backend-owned weather

Backend-ready capabilities:

- weather provider configuration;
- normalized weather snapshots;
- refresh planning and due-provider visibility;
- weather operations health endpoint;
- weather-snapshot-based broadcast targeting.

Important endpoints:

- `GET /api/v1/weather/providers`
- `POST /api/v1/weather/providers`
- `GET /api/v1/weather/snapshots/latest`
- `GET /api/v1/weather/refresh-plan`
- `GET /api/v1/weather/operations/health`

Backend still needs:

- production provider adapter execution;
- scheduled refresh worker;
- real Open-Meteo request/response mapping; adapter normalization is now isolated and regression-tested without network calls;
- weather refresh worker stub is available at `POST /api/v1/weather/refresh-worker/run-due` for backend/admin validation before scheduler wiring;
- Weather refresh worker can now normalize provider `demo_payload` config into a persisted WeatherSnapshot without network calls.
- provider error/retry policy hardening.

Android should not use phone sensors for weather targeting. Weather is backend-only and snapshot-based.

### 3. Farmer, agent, land, and soil profiles

Backend-ready capabilities:

- backend-driven profile forms;
- configurable option sets for seasons, land units, ownership, irrigation, soil, language, and assistance modes;
- farmer create/update;
- parcel create/update;
- soil profile create/update;
- profile readiness and worklists;
- field-agent worklist;
- agent profile support;
- farmer and agent dual-mode support.

Important endpoints:

- `GET /api/v1/auth/mode-bootstrap`
- `GET /api/v1/forms/{form_id}`
- `GET /api/v1/forms/options`
- `GET /api/v1/forms/options/{option_set}`
- `POST /api/v1/farmers`
- `PATCH /api/v1/farmers/{farmer_id}`
- `POST /api/v1/parcels`
- `PATCH /api/v1/parcels/{parcel_id}`
- `POST /api/v1/soil-profiles`
- `PATCH /api/v1/soil-profiles/{profile_id}`
- `GET /api/v1/farmers/profile-readiness`
- `GET /api/v1/field-agent/worklist`

Backend still needs:

- final payload examples captured from regression database;
- tenant/project permission review;
- final sync/offline replay order review with Android team.

Android should not hardcode option lists once backend feature flags are enabled.

### 4. Land parcel assumptions

Backend-ready model decisions:

- most farmers are expected to have one village and one or more parcels;
- parcels support PIN-code/location anchors;
- ownership supports owned, part-owned, leased, shared, sharecrop, family, and configurable variants;
- custom multi-location cases are supported through parcel location fields and location scope;
- FPO/project association can span multiple villages.

Backend still needs:

- final geospatial duplicate/overlap review;
- final village/PIN code normalization strategy during metadata population.

### 5. Soil enrichment

Backend-ready capabilities:

- normalized soil enrichment snapshots;
- SoilGrids-style baseline provider support;
- SHC/SLUSI point-capture source family;
- Open-Meteo soil moisture source family;
- latest and summary endpoints;
- enrichment queue;
- job audit;
- operations health;
- admin soil enrichment queue with manual audit markers.

Important endpoints:

- `POST /api/v1/soil-profiles/enrichments`
- `GET /api/v1/soil-profiles/enrichments/latest`
- `GET /api/v1/soil-profiles/enrichments/summary?farmer_id={farmer_id}`
- `GET /api/v1/soil-profiles/enrichments/queue`
- `POST /api/v1/soil-profiles/enrichments/jobs/audit`
- `GET /api/v1/soil-profiles/enrichments/jobs/audit`
- `GET /api/v1/soil-profiles/enrichments/operations/health`

Backend still needs:

- SoilGrids fetch worker;
- Open-Meteo soil moisture fetch worker;
- controlled SHC/SLUSI adapter/import strategy after source permission/stability review;
- provider retry/backoff policy;
- provider cost/rate-limit guardrails.

Android should consume summaries/readiness only. It should not call SoilGrids, SHC/SLUSI, Open-Meteo, or satellite providers directly.

### 6. Company/customer profile

Backend-ready capabilities:

- backend-only tenant company profile;
- company types including FPO, seed company, fertilizer company, pesticide company, machinery company, input company, buyer, trader, warehouse, financial institution, processor, insurer, NGO, government, cooperative, agri-tech, enterprise, and other;
- source references;
- verification status;
- audit history;
- admin company profile UI.

Important endpoints:

- `GET /api/v1/tenants/{tenant_id}/company-profile`
- `PUT /api/v1/tenants/{tenant_id}/company-profile`
- `GET /api/v1/tenants/{tenant_id}/company-profile/audit`

Android MVP should not render or mutate backend-only company profile data.

### 7. Company discovery and prepopulation

Backend-ready capabilities:

- discovered company candidate staging;
- review queue;
- apply/merge into live company profile;
- CSV template, validation, import;
- admin company discovery page.

Important endpoints:

- `POST /api/v1/company-discovery-candidates`
- `GET /api/v1/company-discovery-candidates`
- `PATCH /api/v1/company-discovery-candidates/{candidate_id}/review`
- `POST /api/v1/company-discovery-candidates/{candidate_id}/apply`
- `GET /api/v1/company-discovery-candidates/template.csv`
- `POST /api/v1/company-discovery-candidates/csv/validate`
- `POST /api/v1/company-discovery-candidates/csv/import`

Backend still needs:

- metadata seeding pipeline;
- public-source citation policy;
- duplicate matching improvements;
- source confidence scoring improvements.

## Final backend engineering checklist before Android starts

### A. Provider-worker stubs

- Weather scheduled refresh worker.
- Open-Meteo weather adapter.
- Open-Meteo soil moisture adapter.
- SoilGrids baseline adapter.
- SHC/SLUSI controlled import or capture adapter.
- Provider retry/backoff/audit policy.
- Soil enrichment queue worker stub is available at `POST /api/v1/soil-profiles/enrichments/worker/run-queue` to create provider-neutral queued audit rows before real provider adapters are connected.
- SoilGrids adapter normalization is isolated and regression-tested without network calls.
- Open-Meteo soil-moisture adapter normalization is isolated and regression-tested without network calls.

### B. Regression sweep

Primary closeout command:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/test_android_backend_closeout.py
```

The runner executes:

- Broadcast API regression.
- Weather snapshot regression.
- Android profile payload regression.
- Profile hydration regression.
- Profile form contract regression.
- Provider worker ops dry-run regression.
- Alembic revision chain validation.

Still run separately where applicable:

- Admin web production build.
- Alembic upgrade from clean database.

### C. Permission and tenancy review

- Tenant isolation for every farmer/profile/soil/weather/company endpoint.
- Admin permission checks for operational endpoints.
- Android-safe read/write scopes.
- Worker-only endpoints separated from Android endpoints.

### D. Payload handoff bundle

- Capture sample bootstrap response.
- Capture sample profile forms/options.
- Capture sample profile readiness payload.
- Capture sample farmer broadcast feed/detail payload.
- Capture sample weather snapshot/health payload.
- Capture sample soil enrichment summary/queue/health payload.
- Capture sample error payloads.

### E. Android rollout order

Recommended later rollout sequence:

1. Bootstrap and feature flags.
2. Backend-driven forms/options.
3. Farmer/parcel/soil create-update payloads.
4. Profile readiness and worklists.
5. Broadcast feed/read/ack/media.
6. Weather and soil enrichment summaries as read-only cards.
7. Agent/farmer dual-mode polish.
8. Offline replay and conflict handling.

## Current decision

Android work should wait until backend provider-worker stubs, full regression, and permission review are complete. Until then this packet should be maintained as the backend closeout checklist and future Android contract map.

- Soil enrichment worker can normalize request-body demo payloads into persisted SoilEnrichmentSnapshot rows without network calls.

- Soil enrichment worker demo-target mode can force no-network snapshot persistence for adapter validation.

## Provider adapter checkpoint - 2026-07-20

Completed since the 84% checkpoint:

- Open-Meteo weather payload normalization is isolated and regression-tested without network calls.
- Weather refresh worker can persist demo payloads as WeatherSnapshot rows.
- SoilGrids baseline payload normalization is isolated and regression-tested without network calls.
- Open-Meteo soil-moisture payload normalization is isolated and regression-tested without network calls.
- Soil enrichment worker can persist demo payloads as SoilEnrichmentSnapshot rows.
- Full Android backend closeout regression runner passes after these changes.

Backend readiness estimate is now about 95%. Remaining backend-heavy work is scheduler/worker invocation strategy, real provider HTTP adapters, rate-limit/error policy, clean Alembic-from-empty validation, permission review, and final Android sample-payload bundle.

Manual provider worker invocation is available through `backend/scripts/run_due_provider_workers.py --tenant-id {tenant_id} --dry-run`. This runs weather and soil enrichment worker stubs from one ops command before scheduler wiring.

Static Alembic chain validation is available through `backend/scripts/check_alembic_revision_chain.py`; it checks duplicate revisions, missing down-revision targets, and single-head status without connecting to the database.

Endpoint permission inventory is available through `backend/scripts/audit_endpoint_permission_inventory.py`. It classifies endpoints as Android/shared, admin/backoffice, worker/ops, or review-needed and flags missing tenant/admin markers for manual hardening review.

Worker/ops endpoints for weather and soil enrichment now require admin permissions: VIEW for operations health/queue/history reads and EDIT for worker execution or job-audit writes.

Weather provider configuration and provider execution endpoints now require admin permissions: VIEW for provider/plan reads and EDIT for provider mutation or execution.

Company profile reads and company discovery CSV template download now require admin VIEW permission; Android MVP should not call these backend-only company administration endpoints.

## Permission hardening checkpoint - 2026-07-20

Completed since the 86% checkpoint:

- Provider worker ops endpoints require admin permissions.
- Weather provider configuration and provider execution endpoints require admin permissions.
- Company profile read and company discovery CSV template download require admin permissions.
- Endpoint permission inventory now shows weather provider/worker ops removed from the flagged list.
- Full Android backend closeout runner passes after permission hardening.

Backend readiness estimate is now about 95%. Remaining backend-heavy work is focused on clean database bootstrap validation, remaining admin/backoffice endpoint review, real provider HTTP adapters/rate-limit policy, final sample payload bundle, and final Android handoff review.

Recovery guidance is documented in `docs/backend-recovery-playbook.md`; use it before risky backend changes, migrations, provider-worker changes, permission hardening, or Android handoff testing.

Backend-side pre-Android handoff checks are available through `backend/scripts/pre_android_handoff_check.py`; run web build separately afterward.

Representative Android payload shapes are documented in `docs/android-sample-payloads.md`; replace examples with captured fixture responses before final Android implementation.

Tenant and project administration endpoints now require admin permissions: MANAGE_USERS for tenant creation, EDIT for project creation, and VIEW for tenant/project reads and project enrollment/edit-policy inspection.

Project-scoped input assignment and workflow configuration read endpoints now require admin VIEW permission.

Permission inventory review is documented in `docs/backend-permission-inventory-review.md`; remaining scanner flags are mostly accepted public/reference or generic template/export review items, not current Android MVP blockers.

## Permission review checkpoint - 2026-07-21

Completed since the 87% checkpoint:

- Morning pre-Android backend handoff checker passed.
- Web production build passed.
- Tenant/project admin endpoints require admin permissions.
- Project-scoped input assignment and workflow configuration read endpoints require admin VIEW permission.
- Permission inventory review artifact was created and remaining scanner noise was categorized.
- Full Android backend closeout runner passes after this hardening.

Backend readiness estimate is now about 95%. Remaining backend-heavy work is clean database bootstrap validation, real provider HTTP adapters/rate-limit policy, final captured sample payload bundle, and final Android handoff review.

Clean database bootstrap preflight is available through `backend/scripts/check_clean_db_bootstrap_preflight.py`; true temp database bootstrap execution remains gated behind a separate reviewed script/command.

The pre-Android handoff checker now includes clean database bootstrap preflight; a NOT_READY result is acceptable when `DATABASE_URL` is not configured in the shell, but true clean-bootstrap execution remains a release gate.

## Clean database bootstrap checkpoint - 2026-07-21

Completed:

- Alembic current/head check passes.
- Static Alembic revision chain validation passes.
- Clean database bootstrap preflight script exists and is included in the pre-Android handoff checker.
- Preflight currently reports `DATABASE_URL_present=False` in the local shell, so true temporary database bootstrap execution is not attempted.

Remaining release gate:

- Provide a safe PostgreSQL `DATABASE_URL` or temp database credentials.
- Add/run the execute-mode clean bootstrap script against an isolated temporary database.
- Confirm `alembic upgrade head` succeeds from empty database.

Android endpoint boundaries are documented in `docs/android-endpoint-allowlist.md`; Android MVP should call only allowlisted endpoints and avoid backend/admin-only operations surfaces.

Repeatable Android sample payload capture is available through `backend/scripts/capture_android_sample_payloads.py`; generated files live under `docs/samples/android/`.

## Sample payload checkpoint - 2026-07-21

Completed since the 88% checkpoint:

- Android endpoint allowlist documented.
- Repeatable Android sample payload capture script added.
- Redacted generated sample payloads committed under `docs/samples/android/`.
- Pre-Android backend handoff checker remains read-only; sample capture remains manual because it writes documentation artifacts.

Backend readiness estimate is now about 95%. Remaining backend-heavy work is true clean temporary database bootstrap execution, real provider HTTP adapters/rate-limit policy, and final Android handoff review.

## Farmer and parcel location checkpoint - 2026-07-21

Enrollment should distinguish farmer home GPS from land/parcel location. Farmer home should capture precise GPS plus admin hierarchy/manual village fallback. Land enrollment should ask for parcel PIN code, then show backend-provided candidate villages for that PIN code because one PIN can map to multiple villages. Parcel GPS centroid/polygon remains recommended for precision, with override support for parcels spanning multiple villages or PIN codes.

Clean temporary database bootstrap execution script is available at `backend/scripts/check_clean_db_bootstrap.py --execute`; run it only with a safe local/staging PostgreSQL `DATABASE_URL`.

### Farmer home and parcel land location flow

Android should treat farmer home location and parcel land location as separate concepts. During farmer registration, capture home PIN/village and optionally a precise home GPS point. During parcel registration, first ask whether all parcels are in the same PIN code/village as the farmer home. If yes, Android can copy farmer `pin_code`, `village_id`, and `village_name_manual` into parcel defaults while storing the confirmation in `location_scope`. If no, Android should ask parcel PIN code and call `GET /api/v1/master-data/geography/villages/by-pin-code?pin_code={pin_code}` to display candidate villages because one PIN code can map to multiple villages. GPS point/polygon remains optional precision capture and does not replace PIN/village selection.

## Parcel location sample checkpoint

The Android sample bundle includes a PIN-code village candidate response plus parcel create payloads that demonstrate location_scope.type=SAME_AS_HOME. This confirms the intended Android flow: home GPS/PIN/village is captured separately, parcel land location can default from home only after farmer confirmation, and GPS point/polygon remains optional precision capture.

## Parcel location validation guardrails

Backend validates parcel location semantics without requiring GPS. If a parcel is marked same_as_home_location=true, supplied parcel PIN/village fields must not conflict with the farmer home PIN/village. If same_as_home_location=false, parcel PIN and village are required. GPS point/polygon remains optional precision data and is not used as a replacement for PIN/village selection.

## Provider retry/error policy

Weather and soil provider adapters normalize HTTP failures into retryable and non-retryable classes. Retryable statuses are 408, 425, 429, 500, 502, 503, and 504. Non-retryable statuses are 400, 401, 403, 404, and 422. Workers should record retryable failures as audit/job events suitable for later retry, while non-retryable failures should be surfaced for configuration or source-data review.

## Backend hardening checkpoint - 2026-07-21

Backend readiness estimate is now about 94% for Android MVP handoff.

Completed since the previous checkpoint:

- clean temporary database bootstrap validation now runs end-to-end against a fresh PostgreSQL database and reaches Alembic head;
- farmer home vs parcel land location is now a backend contract with PIN-code village candidate lookup, Android form hints, sample payloads, and validation guardrails;
- Android samples include PIN-code village candidates and same-as-home parcel location examples;
- provider adapter HTTP error policy is normalized for weather and soil enrichment adapters with retryable/non-retryable classification and regression coverage;
- full backend closeout gate and web build continue to pass.

Remaining backend-heavy work is now concentrated on real external HTTP adapters and scheduling/deployment operations: live provider credentials, rate-limit budgets, production scheduler wiring, final permission-inventory cleanup, and final Android implementation review.

## Provider runtime policy

Provider workers now have a shared runtime policy contract covering timeout_seconds, max_retries, backoff_seconds, rate_limit_window_seconds, max_requests_per_window, and demo_mode. Runtime policy is serialized into provider failure metadata so retries and production incidents can be audited without guessing which operational limits were active.

## Provider runtime policy in worker output

Weather and soil enrichment worker outputs now expose the runtime policy used for provider processing. This makes dry-run and execution responses auditable: operators can see timeout, retry, backoff, rate-limit, and demo-mode settings alongside worker results.

## Provider worker auditability checkpoint - 2026-07-22

Backend readiness estimate is now about 94% for Android MVP handoff.

Completed since the previous checkpoint:

- shared provider runtime policy is defined for timeout, retry, backoff, rate-limit, and demo-mode settings;
- weather and soil enrichment workers now expose runtime policy in worker output;
- provider worker responses are more auditable for dry-run, demo execution, and production incident review;
- targeted provider runtime regressions, full backend closeout gate, and web build passed.

Remaining backend-heavy work is now mostly production operations wiring: scheduler invocation, live provider credentials, real external HTTP calls, rate-limit budget enforcement, final permission-inventory cleanup, and final Android implementation review.

## Provider worker scheduler runbook

See `docs/provider-worker-scheduler-runbook.md` for dry-run-first provider worker scheduling guidance, cron/systemd examples, execution-mode gates, failure review, and recovery links.

## Permission inventory checkpoint

Endpoint permission inventory is currently at flagged_count=38. Remaining flags are mostly Android/shared-read tenant-scope review items and template/export tenant-scope checks. Mutation/provider-worker/admin surfaces have already been hardened more aggressively; do not lock down Android-required master-data reads without revising the endpoint allowlist and handoff contract.

## Provider live execution safety policy

Live external provider execution is blocked by default. Provider config must explicitly set `live_execution_enabled=true` before live HTTP calls are allowed. Worker output exposes `live_execution.live_execution_status` so operators can distinguish demo/stub runs from approved live-provider runs.

## Provider live-execution safety checkpoint - 2026-07-22

Backend readiness estimate is now about 94% for Android MVP handoff.

Completed since the previous checkpoint:

- provider live execution is explicitly blocked by default;
- provider config must set `live_execution_enabled=true` before live external HTTP provider execution is allowed;
- weather and soil enrichment worker outputs expose live execution status;
- provider scheduler/runbook, runtime policy, retry/error policy, and worker auditability are now documented and regression-covered;
- full backend closeout gate and web build passed.

Remaining backend-heavy work is now mostly live provider implementation and final release review: real external HTTP adapters, production credentials/secrets, rate-limit budget enforcement, monitoring/alerts, final Android implementation review, and final production permission/audit signoff.

## Provider HTTP client boundary

External provider HTTP calls must go through `app.modules.media.provider_http_client`. The boundary blocks live execution unless provider config explicitly enables it, and it is the future insertion point for timeout, retry, rate-limit, and response/error normalization. Raw HTTP calls should not be scattered across weather or soil modules.

## Provider HTTP boundary checkpoint - 2026-07-22

Backend readiness estimate is now about 94% for Android MVP handoff.

Completed since the previous checkpoint:

- a controlled provider HTTP boundary was added;
- live external provider calls remain blocked unless explicitly enabled;
- future weather/soil provider HTTP integrations now have one approved insertion point for timeout, retry, rate-limit, error normalization, and live-execution guardrails;
- full backend closeout gate and web build passed.

Remaining backend-heavy work is now mostly final live-provider implementation and production operations: actual external HTTP clients inside the approved boundary, credentials/secrets, rate-limit budget enforcement, monitoring/alerts, final Android implementation review, and production permission/audit signoff.

## Provider credentials contract

See `docs/provider-credentials-contract.md` for provider credential environment variables, live-execution gates, non-secret provider config fields, and Android/provider boundary rules.

## Backend metadata readiness roadmap

See `docs/backend-metadata-readiness-roadmap.md` for the pre-Android metadata and scenario-readiness plan covering all-India geography, crop scenario packs, configurable seasons/local units, input/provider prepopulation, branching crop workflows, perennial/orchard onboarding, stage cost/P&L summaries, advisory seed content, multimedia broadcasts, and web UI screenshot testing.

## Metadata readiness audit script

Run `backend/scripts/audit_metadata_readiness.py` to inspect current geography, crop, input/provider, and workflow metadata coverage before expanding Android scenario testing.

Metadata readiness current-state checkpoint
The repository now includes `docs/backend-metadata-readiness-current-state.md`, summarizing the first metadata audit baseline: crops/workflows are already rich enough for Android MVP testing, while all-India geography expansion and agricultural product seeding remain the next backend metadata priorities.

Product catalog readiness audit checkpoint
Added `backend/scripts/audit_product_catalog_readiness.py` as a read-only audit for manufacturer/input/product coverage before seeding Android product scenarios.

Product catalog Android scenario checkpoint
Added `backend/scripts/seed_android_product_catalog.py` and verified the product catalog audit now reports 9 seeded agricultural products/packages for Android metadata testing.

Season and land-unit readiness audit checkpoint
Added `backend/scripts/audit_season_land_unit_readiness.py` to measure backend season metadata, parcel unit usage, and readiness for normalized acre/hectare calculations with local-unit display.

## Metadata governance rule

All metadata mutations must be admin/backoffice controlled and audit logged. This applies to geography aliases/imports, crop taxonomy, crop seasons, local unit conversions, input/product catalog rows, workflow templates, advisory seed content, and broadcast templates. The preferred mutation model is append/update/expire rather than physical delete: rows should keep `created_at`, `updated_at`, actor metadata, reason, and where relevant `effective_from`, `expires_at`, `status`, or `is_active`. Runtime consumers should decide visibility/validity from status plus effective/expiry windows. Physical deletion should be reserved for failed imports, temporary staging rows, or explicit maintenance tasks with audit trail.

## Geography canonical-data guardrail

Geography records sourced from Local Government Directory, Census, or other government reference datasets must be treated as canonical reference data. Admin UI/API edits must not allow changing LGD codes, government names, hierarchy parentage, or other canonical fields in a way that contradicts the source dataset. Allowed admin actions should be limited to adding local aliases, display labels, translations, PIN-code associations, operational grouping, temporary deactivation/expiry, or import-batch corrections with source evidence. Corrections to canonical geography should flow through a verified import/versioning process with source URL/file, import batch ID, actor, timestamp, and reason. Runtime Android search should use canonical records plus approved aliases, while preserving the government-backed identifiers for audit and interoperability.

Season and land-unit registry checkpoint
Added a config-backed season and land-unit registry with Kharif/Rabi/Zaid/Perennial support, canonical acre/hectare conversion, and explicit unsafe placeholders for variable local units such as Bigha/Biswa until geography-scoped conversion is known.

Season and land-unit Android exposure checkpoint
The profile forms/options API now exposes backend-configured season and land-unit registry metadata. Android can keep displaying familiar values such as BIGHA/BISWA/KATHA/GUNTHA, while backend metadata marks variable local units as requiring geography-scoped conversion before normalized acre/hectare calculations and P&L summaries.

Area normalization contract checkpoint
The season/land-unit registry now includes an area normalization result contract. Safe units convert to acres/hectares, while unsupported or geography-variable local units return explicit statuses instead of silently producing unsafe financial/P&L calculations.

Season and land-unit metadata endpoint checkpoint
Android can now call `GET /api/v1/forms/metadata/season-land-units` to retrieve backend-owned seasons, land-unit registry rows, and warnings for variable local units such as Bigha/Biswa/Katha/Guntha before P&L calculations.

Perennial and long-duration crop onboarding checkpoint
Added a backend policy contract for annual crops, perennial orchards, plantation crops, perennial spices, and agroforestry/timber systems. Android should allow existing orchards/plantations/agroforestry parcels to start at their current stage, while showing backend-configured warnings for missing establishment year, unusual stage, season/calendar mismatch, or geography mismatch.

Workflow BBCH and crop-system customization checkpoint
Added `docs/workflow-crop-system-bbch-customization.md`. BBCH remains the baseline crop-stage classification spine, while client/project workflow customizations layer labels, stage durations, decision nodes, recommendations, costs, and crop-system onboarding metadata on top through workflow templates/versions/overrides.

Workflow BBCH/crop-system audit checkpoint
Added `backend/scripts/audit_workflow_bbch_crop_system_readiness.py` to measure BBCH range coverage, propagation-step stages, recommendation cost coverage, decision-like recommendations, and missing crop-system metadata on workflow templates.

Workflow crop-system metadata backfill checkpoint
Added `backend/scripts/backfill_workflow_crop_system_metadata.py` to backfill crop-system, BBCH baseline, allowed start stages, warning rules, and decision-node metadata on existing Rice/Sugarcane workflow templates and versions without changing stage rows.

Pre-Android metadata audit checkpoint
`backend/scripts/pre_android_handoff_check.py` now runs metadata, product catalog, season/land-unit, and workflow BBCH/crop-system readiness audits as part of the backend handoff gate.

Metadata hardening readiness checkpoint
Backend readiness is now approximately 95% for Android MVP handoff. The pre-Android handoff checker now includes metadata, product catalog, season/land-unit, and workflow BBCH/crop-system audits. The latest backend handoff checker and separate web build both passed. Remaining backend-heavy work is now concentrated around all-India geography import expansion, richer product/advisory seed packs, formal admin UI surfacing for crop-system/decision-node metadata, and final Android/web exploratory UI test sweep with screenshots.

Global geography model checkpoint
Added `docs/global-geography-model-roadmap.md`. Geography should evolve from India-specific state/district/block/village tables toward a generic country/profile/entity model that supports each country's administrative hierarchy, while preserving stable India APIs for Android MVP.

Geography hierarchy profile checkpoint
Android can now call `GET /api/v1/master-data/geography/hierarchy-profile` to discover country/geography level metadata. For MVP it describes India compatibility mode; future country profiles can expose different administrative structures without hardcoding client changes.

Global geography readiness audit checkpoint
Added `backend/scripts/audit_global_geography_readiness.py` to verify the geography hierarchy profile endpoint, current India compatibility counts, and explicit remaining gaps before all-India/global rollout.

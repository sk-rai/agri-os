# Android Backend Handoff Packet

Status date: 2026-07-20

Current backend readiness estimate for Android MVP handoff: about 86%.

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

Backend readiness estimate is now about 86%. Remaining backend-heavy work is scheduler/worker invocation strategy, real provider HTTP adapters, rate-limit/error policy, clean Alembic-from-empty validation, permission review, and final Android sample-payload bundle.

Manual provider worker invocation is available through `backend/scripts/run_due_provider_workers.py --tenant-id {tenant_id} --dry-run`. This runs weather and soil enrichment worker stubs from one ops command before scheduler wiring.

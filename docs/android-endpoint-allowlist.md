# Android Endpoint Allowlist

Status date: 2026-07-24

This document defines which backend endpoints Android may call for MVP and which endpoints must remain admin/backend-only. It is a security and integration boundary, not just an API list.

## Rule

Android may call only endpoints in the allowed sections below. If Android needs data from a backend/admin-only endpoint, add a dedicated Android-safe read endpoint instead of calling operational/admin APIs directly.

## Allowed for Android MVP

### Bootstrap and auth

- `GET /api/v1/auth/mode-bootstrap`
- OTP/login endpoints used by the existing auth flow.

### Backend-driven forms/options

- `GET /api/v1/forms/{form_id}`
- `GET /api/v1/forms/options`
- `GET /api/v1/forms/options/{option_set}`
- `GET /api/v1/forms/profile-contract`

### Farmer/profile write paths

- `POST /api/v1/farmers`
- `PATCH /api/v1/farmers/{farmer_id}`
- `POST /api/v1/parcels`
- `PATCH /api/v1/parcels/{parcel_id}`
- `POST /api/v1/soil-profiles`
- `PATCH /api/v1/soil-profiles/{profile_id}`

### Farmer/profile read paths

- `GET /api/v1/farmers/profile-readiness`
- farmer/profile hydration endpoints already used by Android mode bootstrap/profile loading.
- `GET /api/v1/field-agent/worklist` when the user is acting as a field agent.

### Broadcast consumption

- `GET /api/v1/broadcasts/farmers/{farmer_id}/broadcasts`
- `GET /api/v1/broadcasts/{campaign_id}` for assigned/visible campaign detail only.
- `POST /api/v1/broadcasts/deliveries/{delivery_id}/read`
- `POST /api/v1/broadcasts/deliveries/{delivery_id}/acknowledge`

### Read-only enrichment/advisory cards

- `GET /api/v1/weather/snapshots/latest`
- `GET /api/v1/soil-profiles/enrichments/latest`
- `GET /api/v1/soil-profiles/enrichments/summary`

### Reference/catalog reads

- geography reference reads required for forms/search;
- crop catalog reference reads required for forms/search;
- input/product reference reads only where needed for farmer-facing activity capture.

## Backend/admin-only: Android must not call

### Weather operations

- weather provider create/list/update endpoints;
- weather refresh plan;
- weather provider run-due/run-adapter/refresh endpoints;
- weather refresh worker;
- weather operations health.

### Soil enrichment operations

- soil enrichment queue;
- soil enrichment worker;
- soil enrichment job audit create/list;
- soil enrichment operations health;
- direct provider source contracts unless explicitly wrapped for Android.

### Company/customer administration

- tenant company profile read/write/audit;
- company discovery candidates;
- company discovery CSV template/validate/import;
- candidate review/apply endpoints.

### Tenant/project/admin configuration

- tenant create/list;
- project create/list/edit-policy;
- project farmer enrollment admin listings;
- project input assignment admin views;
- workflow override/enablement admin views;
- workflow/template/catalog CSV import/export admin endpoints;
- user/admin access management.

### Operational reports and traces

- admin dashboards;
- sync health/conflict operations;
- traceability reports not explicitly designed for Android farmer/agent UX.

## Android implementation guidance

- Prefer backend-provided forms, option sets, readiness fields, and feature flags.
- Do not duplicate targeting, readiness, provider, worker, or operations logic locally.
- Treat weather and soil enrichment as saved backend snapshots.
- Treat company/customer profile and discovery as admin-only.
- If a needed field is missing from an allowed endpoint, request a backend contract update rather than calling admin-only endpoints.

## Review before Android handoff

- Run `backend/scripts/pre_android_handoff_check.py`.
- Run web build.
- Confirm this allowlist against Android API client interfaces.
- Confirm `docs/samples/android/` contains the current 22-file redacted payload bundle.

## Location lookup requirement

Android may call backend-safe geography/PIN lookup endpoints for enrollment. The intended flow is:

1. Farmer home: capture GPS plus state/district/block/village fields.
2. Parcel land: enter PIN code.
3. Backend returns villages associated with that PIN code.
4. Android shows the village list for confirmation.
5. Android saves selected village/PIN/GPS fields on the parcel.

Android should not ship or maintain its own PIN-to-village database.

## Season and land-unit metadata

- `GET /api/v1/forms/metadata/season-land-units` — returns backend-configured seasons, land units, conversion metadata, and Android warning guidance for local units that require geography-scoped conversion before financial/P&L calculations.

## Geography hierarchy profile

- `GET /api/v1/master-data/geography/hierarchy-profile` — returns backend-owned geography cascade metadata. Android should render levels from this profile instead of hardcoding a fixed state/district/block/village structure, while India compatibility endpoints remain stable for MVP.

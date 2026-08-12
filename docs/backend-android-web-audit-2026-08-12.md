# Backend, Android, and Web implementation audit

Status date: 2026-08-12

This audit summarizes the implemented Agri-OS backend/web surface, Android-consumable contracts, Android-tested areas, and remaining pending items after the Android land-summary and DigiPin V1 closures.

## Current implementation inventory

- Backend API surface: 296 FastAPI routes.
- Web admin surface: 42 Next.js pages.
- Relevant backend Android/audit/fixture/verifier scripts: 72.
- Web Playwright smoke scripts currently present:
  - web/smoke/core_lgd_review_smoke.mjs
  - web/smoke/localization_admin_smoke.mjs
  - web/smoke/land_intelligence_summary_admin_smoke.mjs

## Implemented backend domains

- Auth, OTP/device login, mode bootstrap, and runtime app bootstrap.
- Farmer profile, parcel, soil profile, profile hydration, profile readiness, duplicate cleanup, project enrollment, and launch context.
- Field-agent mode, assigned worklist, dual farmer/agent personas, project-agent assignment, and assigned-agent mutation authorization.
- Backend-driven profile forms, option sets, localized labels, and profile form contracts.
- Multi-tenant/project configuration, runtime branding/config, and project effective app config.
- Crop catalog, crop taxonomy, crop workflows, workflow draft/publish/versioning, project workflow enablement, crop cycles, stages, activities, and backend-computed finance summaries.
- Input catalog, project input assignments, product catalog, product approval, CSV import/export/validation surfaces.
- Offline sync event replay, dependency handling, idempotency, conflict generation, Android-safe pending conflicts, and conflict acknowledgement.
- Broadcast/advisory campaigns, deliveries, read/ack lifecycle, farmer query threads, media assets/attachments, and field event reporting.
- Weather snapshots/provider framework and soil enrichment snapshot/provider framework, with live provider execution intentionally gated.
- Land intelligence context and land intelligence summary cards, including admin overrides and Android-facing runtime summary.
- DigiPin utility/runtime materialization for farmer home GPS and parcel centroid/geometry.
- Admin reports, dashboards, trace pages, sync health, activity usage, finance analytics, profile readiness, project enrollments, and operational admin pages.

## Android-tested or closed items

- Android agent-assisted farmer management: closed via Flow 38. Assigned agent updates pass; unassigned active agent receives 403 FARMER_ASSIGNMENT_REQUIRED; multi-assigned worklist is covered.
- Android land-intelligence summary screen: closed via Flow 39. Android renders backend summary schema, PIN scope, informational-only flags, card count, main crops, and alternate crops.
- Android DigiPin GPS materialization: closed via Flow 39. Android sends deterministic lat/lng, backend computes 4P3JK852C9, Android displays backend-returned farmer home and parcel centroid DigiPin, null-without-GPS is verified, and Android emits no-local-computation evidence.
- Sync resilience flows: fresh evidence exists for stale-context, VERSION_MISMATCH, WORKFLOW_INVALID, and queue/backpressure hardening flows; see docs/android-maestro-sync-multilingual-evidence.md.

## Main pending Android items

1. Stale local conflict card after backend reset
   - If backend reset deletes a pending conflict row while Android still has a local conflict card, Android ACK/refresh may receive 404.
   - Android should treat this as already gone/resolved server-side and dismiss or resolve the local stale card.

2. Persona lifecycle extension closure
   - Backend fixtures/verifiers exist for project picker, membership transition, agent reassignment, and duplicate farmer cleanup.
   - Android evidence should close project picker, project membership transition, duplicate farmer cleanup UI, and agent reassignment UI flows.

3. Dynamic profile and crop-cycle closure
   - Backend fixtures/tests exist for dynamic profile submit, crop-cycle create, stage/activity logging, and offline replay.
   - Android should confirm online crop-cycle create, stage timeline/activity logging, and backend workflow rendering separately from offline sync resilience.

4. Multilingual QA expansion
   - Backend English fallback and Hindi keys are present; native Kannada/Marathi/Punjabi coverage remains incomplete.
   - Android should verify no blank labels, no raw label-map JSON, no hardcoded Android translations for backend-driven labels, and clean fallback behavior.

5. Android endpoint allowlist refresh
   - The allowlist audit reports no stale backend routes and no missing backend route references, but many Android docs mention admin/deferred endpoints.
   - Update docs/android-endpoint-allowlist.md for newer Android-safe surfaces including land-intelligence summary and DigiPin response fields, and clarify admin-only references.

## Main pending admin/web items

- Web admin smoke coverage is still thin compared with 42 pages.
- High-value Playwright smoke candidates:
  - dashboard
  - projects
  - project workflows
  - profile forms
  - crop taxonomy
  - inputs
  - products
  - project enrollments
  - field events
  - query inbox
  - broadcasts
  - sync health/conflicts
  - weather
  - soil enrichment
  - finance analytics
  - agent profiles/worklist
- Localization depth remains pending for workflow-stage/detail views, input-rule detail copy, crop-stage recommendations, advisory/broadcast copy review, and bulk translation import/export.

## Deferred or provider-gated items

- Live weather providers are not enabled for demo/live execution until credentials, retry policy, rate limits, and cost guardrails are approved.
- Live soil providers and enrichment workers remain backend-controlled and approval-gated.
- Product source verification remains deferred; current catalog is demo/reference quality and not production regulatory truth.
- Irrigation canal network layer, village coordinate geocoding, and remaining CoRE/LGD low-margin district decisions remain data/product hardening tasks.

## Audit finding fixed next

The audit found a real backend regression in project app-config effective payload generation:

    NameError: name 'db' is not defined

Affected helper:

    backend/app/modules/app_config/api.py::_effective_config_payload

Cause:

- localization-aware _profile_form_contracts(...) and _form_versions(...) require db;
- _effective_config_payload(...) referenced db without receiving it.

Resolution:

- pass db into _effective_config_payload(...);
- update both effective-config and project-config patch callers.

## Recommended next execution order

1. Fix and verify app-config regression.
2. Refresh Android endpoint allowlist for land summary and DigiPin.
3. Ask Android to close stale conflict 404 dismissal.
4. Close persona lifecycle extension flows.
5. Expand Playwright smoke coverage for the highest-value admin pages.
6. Continue localization depth for workflow/input/advisory content.

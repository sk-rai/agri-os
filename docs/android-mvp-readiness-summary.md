# Android MVP Readiness Summary

Status date: 2026-08-17

## Executive summary

Android MVP integration is closed across profile, persona, FPO/project workflows, crop-cycle/activity capture, offline sync/conflict recovery, broadcasts/advisories/media, field-event advisory loop, localization fallback, and backend-owned land-intelligence display.

The backend gap tracker currently has no Open, Watch, Pending, Blocked, Ready, or In progress rows.

## MVP-ready Android capabilities

- Farmer mode, independent farmer mode, and project-associated farmer mode.
- Field-agent assisted farmer workflows.
- FPO/project enrollment, launch context, project trace, and project closure continuation.
- Dynamic profile forms and backend-owned labels/options.
- PIN/geography guardrails and DIGIPIN/plot-resolution friendly parcel capture.
- Crop cycles, stages, activity logging, cost summaries, and traceability.
- Offline sync queue persistence and replay.
- Conflict recovery for VERSION_MISMATCH, WORKFLOW_INVALID, stale context materialization failure, partial batch conflict, and multi-conflict drawer cases.
- Queue resilience for cold start, device restart, uncertain results, dependency ordering, partial batches, backpressure, interrupted multibatch replay, and poison-row backlog draining.
- Broadcast/advisory lifecycle including read/ack, admin analytics, pending follow-up, terminal visibility, media attachments, language fallback, and audience targeting.
- Field event to advisory loop with media reuse and crop-targeted delivery.
- Admin-published localization overrides.
- Multilingual label fallback rendering.
- Backend-owned land-intelligence override rendering as informational, non-blocking guidance.

## Reusable deterministic fixtures

- `android-dynamic-test` tenant and sync/offline replay fixtures.
- Crop-cycle farmer/parcel/stage/activity fixtures.
- Persona lifecycle fixtures.
- FPO multi-village/project closure/broadcast fixtures.
- Localization override and land-intelligence override fixtures.

These are closed as MVP blockers but remain useful for reruns, demos, and regression checks.

## Deferred / not demo-live-safe

- Live weather/soil provider calls remain approval-gated until credentials, budgets, monitoring, retries, and rate limits are configured.
- Product source verification remains deferred; demo/reference product rows should not be positioned as regulator/manufacturer-verified.
- Village coordinate geocoding remains research/provider-gated.
- Native Kannada, Marathi, and Punjabi labels are not complete; Android currently proves safe English fallback.
- Advisory translation review remains content/governance work.
- Global/non-India geography migration remains future architecture work.
- Formal decision-node/perennial/orchard current-stage onboarding remains future workflow hardening.
- Materialized finance aggregate tables remain deferred.
- Insurance fraud/waste/abuse risk scoring is a roadmap concept, not yet an operational scoring engine.

## Demo-safe positioning

The system is demo-safe for deterministic Android and admin workflows using seeded local/demo data, backend-owned contracts, saved snapshots, and controlled fixtures.

Do not claim live provider execution, verified product-label compliance, native regional translation completeness, or operational insurance fraud scoring until those buckets are separately implemented, verified, and governed.

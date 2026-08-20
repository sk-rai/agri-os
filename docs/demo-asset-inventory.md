# AgriFabric demo asset inventory

## Available static SVG assets

These assets are now available for landing-page sections, explainer slides, and demo-video overlays.

| Asset pack | Files | Use |
| --- | --- | --- |
| Relationship graph | `docs/assets/relationship-graph.svg`, `docs/assets/relationship-graph-overview.svg`, `docs/assets/relationship-graph-roadmap-layer.svg` | Explain AgriFabric as a connected evidence graph across farmers, agents, projects, parcels, advisories, sync, and audit. |
| Geography and DigiPin | `docs/assets/geography-digipin-overview.svg`, `docs/assets/geography-digipin-layered-model.svg`, `docs/assets/geography-global-extension-layer.svg` | Explain PIN context, GPS/parcel precision, backend-generated DigiPin, land intelligence, and global geography roadmap boundaries. |
| Field evidence pipeline | `docs/assets/field-evidence-pipeline.svg`, `docs/assets/field-evidence-pipeline-compact.svg` | Explain Android capture, offline sync, backend contracts, admin operations, and bounded roadmap intelligence. |
| Insurance and subsidy integrity roadmap | `docs/assets/insurance-risk-roadmap.svg`, `docs/assets/insurance-risk-roadmap-compact.svg` | Claim-safe roadmap graphic for future risk flags, duplicate parcel review, evidence bundles, NDVI/provider context, and human review queues. |
| Product pillar icons | `docs/assets/product-pillars.svg`, `docs/assets/product-pillar-*.svg` | Six-pillar visual vocabulary for Capture, Coordinate, Sync, Advise, Govern, and Extend. |


Status date: 2026-08-17

This inventory maps landing-page and demo-pack claims to concrete clips, screenshots, fixture commands, and proof docs. It is meant to keep the future landing page honest: every visible claim should either point to an implemented proof asset or be clearly marked as roadmap.

Use this alongside:

- `docs/demo-script-pack.md`
- `docs/demo-capture-checklist.md`
- `docs/demo-capture-operations-runbook.md`
- `docs/landing-page-content-brief.md`
- `docs/landing-page-wireframe.md`

## Asset naming convention

Use short, sortable names:

```text
01-farmer-onboarding-android.mp4
02-fpo-project-ops-web-android.mp4
03-crop-activity-ledger-android.mp4
04-offline-sync-resilience-android.mp4
05-advisory-lifecycle-web-android.mp4
06-field-event-to-advisory-mixed.mp4
07-localization-land-intelligence-mixed.mp4
08-geography-digipin-android-concept.mp4
09-relationship-graph-agent-performance-concept.mp4
10-insurance-integrity-roadmap-concept.mp4
```

For landing-page thumbnails:

```text
hero-field-evidence-graph.png
proof-fpo-project-ops.png
proof-offline-sync.png
proof-broadcast-analytics.png
proof-field-event-advisory.png
proof-localization-land-intelligence.png
proof-geography-digipin.png
roadmap-insurance-risk-review.png
```

## Landing-page proof map

| Landing-page area | Claim to support | Asset type | Natural capture mode | Proof boundary |
| --- | --- | --- | --- | --- |
| Hero | AgriFabric is an offline-first field evidence and operations fabric. | 20-30 second montage plus graph visual | Mixed Android + web + concept overlay | Implemented foundation; avoid risk-scoring claims in hero. |
| Capture pillar | Farmer, parcel, crop, activity, media, and event capture. | Android clip | Android-only | Implemented MVP. |
| Coordinate pillar | FPO/project operations across farmers, villages, crops, and stages. | Web/admin clip with Android confirmation | Mixed, web-first | Implemented deterministic FPO fixture, not load-test claim. |
| Sync pillar | Offline replay, conflict recovery, exact-once materialization. | Android clip plus technical overlay | Android-only, optional backend proof overlay | Implemented deterministic sync/conflict smokes. |
| Advise pillar | Targeted advisories with media, language fallback, read/ack analytics. | Web + Android clip | Mixed | Implemented deterministic broadcast smokes. |
| Govern pillar | Backend-owned labels, localization overrides, land intelligence summaries. | Web/admin + Android clip | Mixed | Implemented for MVP/fallback; native translation completeness remains future content work. |
| Extend pillar | Insurance, subsidy, credit, weather, soil, satellite evidence. | Concept graphic with implemented evidence snippets | Narrated concept | Roadmap/foundation only. |
| Relationship graph section | Typed relationships connect farmers, agents, companies, projects, parcels, crop cycles, media, advisories, and audit. | Graph illustration plus short proof snippets | Concept visual with web snippets | Graph foundation is implemented through relational data/audit; analytics dashboards are roadmap unless separately built. |

## Clip inventory

### 01 — Farmer onboarding and profile capture

Primary claim:

Android is a field surface for backend-owned farmer/profile/parcel capture.

Must capture:

- Android farmer mode or field-agent-assisted mode.
- Backend-driven profile form labels/options.
- PIN/village or geography guardrail field.
- Parcel/location evidence.
- DigiPin/GPS display if visible in the selected flow.

Useful proof docs:

- `docs/android-mvp-readiness-summary.md`
- `docs/android-persona-lifecycle-test.md`
- `docs/android-endpoint-allowlist.md`
- `docs/digipin-location-architecture.md`

Useful fixture commands:

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_persona_lifecycle.py --reset --apply \
  > /tmp/demo-persona-lifecycle-prepare.json \
  2>&1

tail -160 /tmp/demo-persona-lifecycle-prepare.json
```

Landing-page badge:

`Verified MVP`

Do not say:

- “Global geography is complete.”
- “Android computes DigiPin.”

### 02 — FPO/project operations

Primary claim:

FPOs and enterprises can coordinate farmer cohorts by village, crop, mobile, project, and crop-stage context.

Must capture:

- Web admin project enrollment/search page.
- Village/crop/mobile search.
- Farmer drilldown.
- Project trace or crop/status distribution.
- Android project context for the selected farmer.
- Optional closure continuation flow.

Useful proof docs:

- `docs/android-fpo-multi-village-workflow-test.md`
- `docs/android-fpo-project-closure-migration-notice-test.md`
- `docs/android-broadcast-terminal-visibility-test.md`
- `docs/broadcast-admin-delivery-analytics-web-smoke.md`

Useful fixture commands:

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_fpo_multi_village_workflow.py --reset --apply \
  > /tmp/demo-fpo-project-ops-prepare.json \
  2>&1

../venv/bin/python scripts/verify_android_fpo_multi_village_workflow.py \
  > /tmp/demo-fpo-project-ops-verify.raw \
  2>&1

tail -180 /tmp/demo-fpo-project-ops-verify.raw
```

Useful web smoke:

```bash
cd ~/projects/farmint

set -a
source /tmp/web-smoke-env.sh
set +a

WEB_BASE_URL=http://localhost:3000 \
NEXT_PUBLIC_API_URL=http://localhost:8000 \
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 \
node web/smoke/fpo_project_enrollment_search_smoke.mjs \
  > /tmp/demo-fpo-project-enrollment-search-web-smoke.json \
  2>&1

cat /tmp/demo-fpo-project-enrollment-search-web-smoke.json
```

Landing-page badge:

`Verified MVP`

Do not say:

- “This is a production thousand-farmer load test.”

### 03 — Crop activity ledger

Primary claim:

Crop activities become a structured, stage-aware evidence ledger.

Must capture:

- Android crop cycle screen.
- Stage timeline.
- Activity logging.
- Activity saved/synced state.
- Cost/summary card if visible.

Useful proof docs:

- `docs/android-crop-cycle-test-fixture.md`
- `docs/android-cold-start-sync-persistence-test.md`
- `docs/android-dependency-order-replay-test.md`
- `docs/android-partial-batch-replay-test.md`

Useful fixture commands:

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/seed_android_crop_cycle_test_fixture.py --reset --apply \
  > /tmp/demo-crop-cycle-fixture.json \
  2>&1

tail -160 /tmp/demo-crop-cycle-fixture.json
```

Landing-page badge:

`Verified MVP`

Do not say:

- “Full harvest P&L is implemented.”
- “Materialized finance aggregate tables are complete.”

### 04 — Offline sync resilience

Primary claim:

Offline work survives restarts, replays safely, isolates conflicts, and avoids duplicate backend materialization.

Must capture:

- Pending queue state.
- Offline/new activity capture.
- Restart or reconnect.
- Replay success.
- Conflict card or drawer.
- Resolved state.

Useful proof docs:

- `docs/android-version-mismatch-conflict-test.md`
- `docs/android-workflow-invalid-conflict-test.md`
- `docs/android-stale-context-sync-failure-test.md`
- `docs/android-cold-start-sync-persistence-test.md`
- `docs/android-device-restart-sync-persistence-test.md`
- `docs/android-uncertain-result-idempotency-test.md`
- `docs/android-dependency-order-replay-test.md`
- `docs/android-partial-batch-replay-test.md`
- `docs/android-partial-batch-conflict-test.md`
- `docs/android-multi-conflict-pending-drawer-test.md`
- `docs/android-queue-backpressure-test.md`
- `docs/android-interrupted-multibatch-resume-test.md`
- `docs/android-poison-row-backlog-test.md`

Useful fixture commands:

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_cold_start_activity_persistence.py --apply \
  > /tmp/demo-offline-sync-prepare.json \
  2>&1

tail -180 /tmp/demo-offline-sync-prepare.json
```

Conflict variants:

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_version_mismatch_conflict.py --reset --apply \
  > /tmp/demo-version-mismatch-conflict-prepare.json \
  2>&1

../venv/bin/python scripts/prepare_android_workflow_invalid_conflict.py --reset --apply \
  > /tmp/demo-workflow-invalid-conflict-prepare.json \
  2>&1
```

Landing-page badge:

`Verified MVP`

Do not say:

- “Production fleet-scale sync metrics are already measured.”

### 05 — Broadcast/advisory lifecycle

Primary claim:

Admins can target advisories, Android can receive/read/ack them, and web admin can inspect delivery analytics and audit history.

Must capture:

- Web Broadcasts list/detail.
- Campaign content.
- Audience rule.
- Delivery lifecycle counts.
- Android farmer advisory card.
- Read/ack action.
- Web audit history.

Useful proof docs:

- `docs/android-broadcast-read-ack-lifecycle-test.md`
- `docs/broadcast-admin-delivery-analytics-web-smoke.md`
- `docs/broadcast-pending-followup-web-smoke.md`
- `docs/broadcast-terminal-lifecycle-smoke.md`
- `docs/broadcast-media-attachment-smoke.md`
- `docs/broadcast-language-fallback-smoke.md`
- `docs/android-broadcast-audience-targeting-test.md`

Useful fixture commands:

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_fpo_multi_village_workflow.py --reset --apply \
  > /tmp/demo-fpo-prepare-for-broadcast.json \
  2>&1

../venv/bin/python scripts/prepare_android_fpo_project_closure_migration_notice.py --reset --apply \
  > /tmp/demo-closure-notice-prepare.json \
  2>&1

../venv/bin/python scripts/verify_android_broadcast_read_ack_lifecycle.py \
  > /tmp/demo-broadcast-read-ack-verify.raw \
  2>&1

tail -180 /tmp/demo-broadcast-read-ack-verify.raw
```

Useful web smoke:

```bash
cd ~/projects/farmint

set -a
source /tmp/web-smoke-env.sh
set +a

WEB_BASE_URL=http://localhost:3000 \
NEXT_PUBLIC_API_URL=http://localhost:8000 \
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 \
node web/smoke/broadcast_admin_delivery_analytics_smoke.mjs \
  > /tmp/demo-broadcast-admin-delivery-analytics.json \
  2>&1

cat /tmp/demo-broadcast-admin-delivery-analytics.json
```

Cleanup:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_fpo_project_closure_migration_notice.py --restore
```

Landing-page badge:

`Verified MVP`

Do not say:

- “Android selects the audience locally.”
- “Native translation quality review is complete.”

### 06 — Field event to targeted advisory

Primary claim:

A field event with media can become a crop-targeted advisory while preserving the evidence chain.

Must capture:

- Android/field event photo capture or narrated event setup.
- Web Field Events detail.
- Web Broadcast detail.
- Media asset reused.
- Target farmer receives advisory.
- Excluded farmer does not receive it.

Useful proof docs:

- `docs/android-field-event-advisory-loop-test.md`
- `docs/broadcast-media-attachment-smoke.md`
- `docs/android-broadcast-audience-targeting-test.md`

Useful fixture commands:

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_fpo_multi_village_workflow.py --reset --apply \
  > /tmp/demo-fpo-prepare-for-field-event.json \
  2>&1

../venv/bin/python scripts/prepare_android_field_event_advisory_loop.py --reset --apply \
  > /tmp/demo-field-event-advisory-loop.raw \
  2>&1

tail -220 /tmp/demo-field-event-advisory-loop.raw
```

Useful web smoke:

```bash
cd ~/projects/farmint

set -a
source /tmp/web-smoke-env.sh
set +a

WEB_BASE_URL=http://localhost:3000 \
NEXT_PUBLIC_API_URL=http://localhost:8000 \
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 \
node web/smoke/field_event_advisory_loop_smoke.mjs \
  > /tmp/demo-field-event-advisory-loop-web.json \
  2>&1

cat /tmp/demo-field-event-advisory-loop-web.json
```

Cleanup:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_field_event_advisory_loop.py --cleanup
```

Landing-page badge:

`Verified MVP`

Do not say:

- “The system automatically diagnoses pest/disease from the image.”

### 07 — Localization and land intelligence

Primary claim:

Backend-published labels, fallbacks, and land-intelligence summaries render safely on Android without hardcoded local logic.

Must capture:

- Web localization override if used.
- Android Kannada override or fallback screen.
- Android land-intelligence summary card.
- Informational-only/do-not-block boundary.

Useful proof docs:

- `docs/android-localization-override-delivery-test.md`
- `docs/android-multilingual-profile-form-test.md`
- `docs/android-land-intelligence-override-delivery-test.md`
- `docs/language-localization-advisory-runbook.md`

Useful fixture commands:

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_localization_override_delivery.py --reset --apply \
  > /tmp/demo-localization-override-prepare.raw \
  2>&1

../venv/bin/python scripts/prepare_android_land_intelligence_override_delivery.py --reset --apply \
  > /tmp/demo-land-intelligence-override-prepare.raw \
  2>&1

tail -180 /tmp/demo-land-intelligence-override-prepare.raw
```

Optional web smokes:

```bash
cd ~/projects/farmint

set -a
source /tmp/web-smoke-env.sh
set +a

WEB_BASE_URL=http://localhost:3000 \
NEXT_PUBLIC_API_URL=http://localhost:8000 \
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 \
node web/smoke/localization_admin_smoke.mjs \
  > /tmp/demo-localization-admin-web.json \
  2>&1

WEB_BASE_URL=http://localhost:3000 \
NEXT_PUBLIC_API_URL=http://localhost:8000 \
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 \
node web/smoke/land_intelligence_summary_admin_smoke.mjs \
  > /tmp/demo-land-intelligence-admin-web.json \
  2>&1
```

Cleanup:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_localization_override_delivery.py --cleanup
../venv/bin/python scripts/prepare_android_land_intelligence_override_delivery.py --cleanup
```

Landing-page badge:

`Verified MVP`

Do not say:

- “Kannada/Marathi/Punjabi native translation is complete.”
- “Live weather/soil provider calls are demo-safe.”

### 08 — Geography, DigiPin, and plot resolution

Primary claim:

The system separates administrative hierarchy, postal PIN context, GPS/parcel evidence, DigiPin precision, and land-intelligence guidance.

Must capture:

- PIN/village entry or display.
- Parcel point/polygon-related screen.
- DigiPin field where available.
- Concept overlay showing layers: LGD admin geography, PIN, GPS, DigiPin, parcel, land intelligence.

Useful proof docs:

- `docs/digipin-location-architecture.md`
- `docs/geography-enrichment-analytics-model.md`
- `docs/android-digipin-gps-materialization-test.md`
- `docs/android-land-intelligence-summary-screen-test.md`

Useful checks:

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/test_digipin_utility.py
../venv/bin/python scripts/test_digipin_farmer_parcel_fields.py
../venv/bin/python scripts/test_sync_digipin_materialization.py
```

Landing-page badge:

`Verified foundation`

Do not say:

- “Village geocoding is live.”
- “Global geography coverage is complete.”

### 09 — Relationship graph and field-agent performance concept

Primary claim:

AgriFabric is a typed relationship graph, not just mobile forms: farmers, agents, companies, projects, parcels, crop cycles, media, advisories, and audit trails create a basis for traceability and future analytics.

Must capture:

- Graph illustration.
- Web field-agent worklist or assignment evidence if available.
- FPO/project farmer search.
- Advisory analytics.
- Field-event/media evidence.

Useful proof docs:

- `docs/agrifabric-relationship-graph-and-agent-performance.md`
- `docs/android-persona-lifecycle-extension-tests.md`
- `docs/android-agent-assisted-farmer-management-test.md`
- `docs/android-fpo-multi-village-workflow-test.md`

Useful fixture commands:

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_persona_lifecycle_extensions.py --reset --apply \
  > /tmp/demo-persona-extensions-prepare.json \
  2>&1

../venv/bin/python scripts/verify_android_persona_lifecycle_extensions.py --perform-reassignment \
  > /tmp/demo-persona-extensions-verify.raw \
  2>&1

tail -180 /tmp/demo-persona-extensions-verify.raw
```

Landing-page badge:

`Roadmap analytics on verified graph foundation`

Do not say:

- “Agent scoring dashboard is implemented.”
- “The marketplace is live.”

### 10 — Insurance, subsidy, credit, weather, soil, and satellite integrity concept

Primary claim:

The implemented evidence fabric can become the basis for future risk-review and claim-evidence workflows.

Must capture:

- Short clips reused from farmer identity, parcel/GPS/DigiPin, crop cycle, activity, field-event media, advisory audit, and sync audit.
- Concept visual for risk flags:
  - duplicate parcel claims;
  - crop mismatch;
  - suspicious media reuse;
  - geography/time plausibility;
  - NDVI/EVI time-series mismatch;
  - field-agent activity anomalies.

Useful proof docs:

- `docs/agrifabric-insurance-fraud-risk-scoring.md`
- `docs/digipin-location-architecture.md`
- `docs/geography-enrichment-analytics-model.md`
- `docs/provider-live-test-readiness-runbook.md`
- `docs/product-source-verification-runbook.md`

Landing-page badge:

`Roadmap / future risk review`

Do not say:

- “Operational fraud detection is live.”
- “The system approves or denies claims.”
- “NDVI analysis is implemented.”
- “Live provider execution is demo-safe.”

## Required hero/landing visuals

### Hero montage

Use 4-6 fast cuts:

1. Android farmer/profile capture.
2. Admin FPO farmer search.
3. Android offline queue/conflict card.
4. Admin broadcast analytics.
5. Field event/advisory evidence.
6. Graph overlay.

Text overlay:

```text
Capture → Coordinate → Sync → Advise → Govern → Extend
```

### Relationship graph visual

Recommended nodes:

- Farmer
- Field agent
- Company/FPO
- Project
- Parcel
- Crop cycle
- Stage/activity
- Media asset
- Field event
- Advisory
- Delivery/read/ack
- Sync/audit event

Recommended highlighted paths:

- FPO → Project → Farmer cohort
- Agent → Assigned farmers → Completed work
- Parcel → Crop cycle → Activity/media
- Field event → Advisory → Read/ack audit

Claim boundary overlay:

```text
Traceability today. Advanced scoring and commercial matching are roadmap modules.
```

### Geography visual

Recommended layer stack:

```text
State / district / tehsil / block / village
  + PIN postal context
  + GPS / parcel point or polygon
  + DigiPin derived from coordinates
  + climate / soil / land-intelligence enrichment
```

Claim boundary overlay:

```text
India-compatible MVP now. Global geography extension is a documented future architecture path.
```

### Insurance/risk visual

Recommended visual:

```text
Evidence bundle
  = farmer identity
  + parcel/GPS/DigiPin
  + crop cycle/activity
  + media/field event
  + advisory/audit
  + future satellite/weather/soil signals
```

Claim boundary overlay:

```text
Future review-assistive risk flags, not automated claim decisions.
```

## Asset readiness checklist

Before placing any asset on the landing page:

- The clip or screenshot has a clear implemented/roadmap badge.
- The supporting doc is listed in this inventory.
- The fixture or smoke source is known.
- The screen contains no private production data.
- The clip does not show raw technical logs unless it is for a technical audience.
- Any roadmap concept is visibly marked as roadmap.
- Any provider, product, NDVI, scoring, or global geography claim has a boundary note.
- Cleanup/restore commands have been run after stateful capture.


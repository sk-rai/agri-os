# AgriFabric demo script pack

Status date: 2026-08-17

This pack turns the implemented Android, backend, and admin capabilities into short demo narratives. It is intentionally claim-safe: each script separates what is already implemented and verified from what belongs on the roadmap or landing-page “future vision”.

Primary evidence sources:

- `docs/android-mvp-readiness-summary.md`
- `docs/backend-gap-closure-tracker.md`
- `docs/android-fpo-multi-village-workflow-test.md`
- `docs/android-fpo-project-closure-migration-notice-test.md`
- `docs/android-field-event-advisory-loop-test.md`
- `docs/agrifabric-insurance-fraud-risk-scoring.md`
- `docs/digipin-location-architecture.md`
- `docs/geography-enrichment-analytics-model.md`

## Demo positioning principles

- Show AgriFabric as a backend-owned evidence and workflow fabric, not just a mobile form app.
- Keep Android simple: Android captures, syncs, displays, and acknowledges; backend owns contracts, labels, targeting, conflict interpretation, summaries, and audit history.
- Make “offline-first but auditable” a recurring theme.
- Do not overclaim live provider execution, verified product labels, native regional translations, or insurance risk scoring. Those are roadmap or approval-gated items.
- Every landing-page claim should map to one of: implemented MVP, deterministic demo fixture, deferred/approval-gated, or future product roadmap.

## Script 1: Farmer registration and backend-owned profile capture

### Audience promise

“A farmer or field agent can onboard a farmer with backend-owned forms, geography guardrails, parcel data, and precise location evidence without hardcoding local rules in the app.”

### 60-90 second demo flow

1. Open Android as a farmer or field agent.
2. Show mode bootstrap: independent farmer, project-associated farmer, or field-agent assisted mode.
3. Open profile/registration.
4. Show backend-driven labels/options instead of app-hardcoded forms.
5. Enter farmer profile, PIN/village details, and parcel information.
6. Capture GPS point or parcel location evidence.
7. Show backend-returned profile readiness and parcel/home DigiPin where coordinates exist.

### What this proves

- Backend owns profile form structure, labels, option sets, readiness, and project context.
- Android can support independent and project-associated farmers without separate apps.
- DigiPin is backend-generated from coordinates and displayed by Android; Android does not infer it from PIN or compute it locally.
- PIN/village/geography are reference/guardrail layers; DigiPin/GPS is precision location evidence.

### Evidence hooks

- Android MVP readiness summary: dynamic profile forms, backend-owned labels/options, PIN/geography guardrails, DigiPin/plot-resolution friendly parcel capture.
- `docs/android-endpoint-allowlist.md`: Android should render backend-provided forms/options/readiness and must not compute DigiPin locally.
- `docs/digipin-location-architecture.md`: DigiPin is generated only from actual coordinates, not preloaded for PINs.

### Landing-page claim candidate

“Backend-driven farmer onboarding with precise GPS/DigiPin evidence and no hardcoded local form logic.”

### Claim boundary

Do not claim all countries/geographies are live. Current MVP is India-compatible, with a documented path to generalized geography.

## Script 2: FPO/project operating system across villages and crops

### Audience promise

“An FPO, enterprise, or program operator can manage many affiliated farmers across villages, crops, stages, and project membership states.”

### 90 second demo flow

1. Start on the admin project enrollments or Android project context.
2. Show the FPO project with 12 farmers across 4 villages.
3. Search by village, crop, or mobile number.
4. Drill into a Maize/Rice/Wheat/Sugarcane farmer.
5. Open crop cycles and workflow stages.
6. Show project trace counts and crop/status distribution.
7. Show project closure notice path: farmer receives continuation message and can return to self-service context after enrollment completion.

### What this proves

- One project/FPO can coordinate multiple affiliated farmers.
- Farmers remain individually traceable by mobile, village, crop, parcel, and cycle.
- Project closure does not delete the farmer identity or parcel/crop history.
- Farmer identity is independent from project participation.

### Evidence hooks

- FPO fixture: 12 affiliated farmers, 4 villages, 4 crops, mixed stage statuses.
- Android Flow 42: project enrollment search by village/crop/mobile and drill-down.
- Android Flow 43: backend-triggered project closure notice and SELF_SERVICE continuation.

### Landing-page claim candidate

“Run FPO and enterprise crop programs with farmer-level traceability, search, project context, and graceful exit to independent farmer mode.”

### Claim boundary

The current fixture is a compact demo/regression proof, not a load test for thousands of farmers.

## Script 3: Crop cycle, stage, activity, and cost trail

### Audience promise

“A crop season becomes a structured operational record: crop cycle, stage timeline, activity logs, and backend-computed cost summaries.”

### 60-90 second demo flow

1. Open a farmer with an active crop cycle.
2. Show crop, season, parcel, and workflow stage timeline.
3. Log an activity such as fertilizer, pesticide, irrigation, labor, or machinery.
4. Show stage/cost summary update.
5. Show traceability from project or farmer drill-down.

### What this proves

- Crop-cycle and activity capture are tied to farmer, parcel, project, crop, season, and workflow stage.
- Backend owns workflow/stage semantics and cost summaries.
- Android does not calculate core P&L locally.

### Evidence hooks

- Android MVP readiness summary: crop cycles, stages, activity logging, cost summaries, traceability.
- Offline sync flows prove activity materialization exactly once under retry/interruption conditions.

### Landing-page claim candidate

“Convert farm activity into a structured crop-season ledger with stage-aware traceability and cost evidence.”

### Claim boundary

Harvest P&L and materialized finance aggregate tables remain roadmap/deferred, while current stage/activity cost summaries are MVP-ready.

## Script 4: Offline-first sync that survives real field conditions

### Audience promise

“The app keeps working in low-connectivity field conditions, then syncs safely with backend audit and conflict handling.”

### 90-120 second demo flow

1. Put Android into an offline or backend-unavailable condition.
2. Queue one or more crop activities.
3. Restart the app or device/emulator.
4. Restore backend/network.
5. Show queued work syncs exactly once.
6. Show a conflict case: VERSION_MISMATCH or WORKFLOW_INVALID appears as a human-readable conflict card.
7. Accept server guidance and show conflict cleared without corrupting accepted rows.

### What this proves

- Queue persistence survives cold start and device restart.
- Idempotency prevents duplicate rows when result certainty is unclear.
- Dependency ordering and partial batches are handled.
- Poison rows do not block the rest of the backlog.
- Android distinguishes retryable stale context/failure from manual/server-authority conflict.

### Evidence hooks

- Flows 52-64 cover VERSION_MISMATCH, WORKFLOW_INVALID, stale context failure, cold start, device restart, uncertain result idempotency, dependency ordering, partial batch replay/conflict, multi-conflict drawer, backpressure, interrupted multibatch resume, and poison-row backlog.

### Landing-page claim candidate

“Offline-first capture with auditable replay, conflict recovery, and exact-once backend materialization.”

### Claim boundary

This is deterministic MVP/regression evidence. Production scale and real-device fleet metrics should be measured separately.

## Script 5: Broadcasts and advisories as operational communication

### Audience promise

“Admins can send targeted, auditable advisories to farmers, including media, language fallback, read/ack status, and lifecycle controls.”

### 90 second demo flow

1. Open admin Broadcasts.
2. Show a project/FPO advisory campaign.
3. Show audience rules: project, crop, stage, location, or farmer.
4. Generate deliveries.
5. Open Android farmer feed and show advisory card.
6. Mark read and acknowledge.
7. Return to admin analytics and show read/ack counts and audit history.
8. Optionally show terminal campaign behavior: expired/cancelled campaigns leave admin history but disappear from farmer feed.

### What this proves

- Backend owns targeting, campaign content, delivery generation, lifecycle, and audit trail.
- Android consumes assigned farmer feed; it does not perform local audience matching.
- Media URLs, thumbnails, captions, and fallback text come from backend.
- Unsupported language requests fall back to backend-selected English content.

### Evidence hooks

- Android Flow 44: read/ack lifecycle.
- Web smoke: admin delivery analytics.
- Broadcast pending follow-up and retry safety.
- Terminal lifecycle and terminal visibility.
- Media attachment delivery.
- Language fallback delivery.
- Audience targeting.

### Landing-page claim candidate

“Targeted farmer advisories with media, language fallback, delivery analytics, and full audit history.”

### Claim boundary

Native language quality review is separate; current verified behavior includes Hindi/fallback mechanics and backend-owned content selection.

## Script 6: Field event to targeted advisory loop

### Audience promise

“A field observation can become a targeted advisory without losing evidence: photo, event, crop, farmer, and delivery all stay linked.”

### 60-90 second demo flow

1. Android/field workflow captures a pest field event with photo.
2. Admin/backend marks the event under review and sends an advisory.
3. Show advisory reuses the original media asset.
4. Show delivery targets active Maize farmers and excludes non-target Rice farmers.
5. Open Android farmer feed and show the advisory with media and text fallback.

### What this proves

- Field events are not isolated notes; they can trigger backend-owned advisory workflows.
- Media evidence is reused rather than reconstructed locally.
- Targeting can be crop-aware and excludes non-matching farmers.

### Evidence hooks

- Android Flow 49: pest field event photo -> ADVISORY_SENT -> backend-owned FPO advisory -> same media asset reused -> Maize-only targeting.

### Landing-page claim candidate

“Close the loop from field evidence to targeted farmer action.”

### Claim boundary

Automated pest diagnosis is not implemented here. The implemented proof is workflow linkage, media reuse, targeting, and delivery visibility.

## Script 7: Localization and land-intelligence as backend-owned experience

### Audience promise

“Tenants/projects can adapt labels and land guidance from the backend without shipping a new Android build.”

### 90 second demo flow

1. Open admin localization override.
2. Publish a Kannada override for an activity-log title or language option.
3. Open Android and show the backend-published label.
4. Switch to Hindi/Kannada/Marathi/Punjabi fallback contexts and show readable labels without raw JSON or blanks.
5. Open land-intelligence summary for PIN 560003 / KHARIF / MAIZE.
6. Show informational cards, main/alternate crops, and do-not-block onboarding flag.

### What this proves

- Backend label maps drive Android UI text.
- Tenant/admin override can update Android-visible labels without hardcoded client translation.
- English fallback is safe when regional native labels are not reviewed.
- Land intelligence is backend-owned and informational, not a local blocking rule.

### Evidence hooks

- Android Flow 50: localization override delivery.
- Android Flow 51: land-intelligence PROJECT_OVERRIDE delivery.
- Android Flow 65: multilingual fallback smoke.

### Landing-page claim candidate

“Configurable multilingual farmer experience and advisory intelligence governed from the backend.”

### Claim boundary

Do not claim native Kannada/Marathi/Punjabi translation completeness. Current claim is backend override and safe fallback.

## Script 8: Geography, DigiPin, and land intelligence foundation

### Audience promise

“The system separates administrative geography, postal reference, precise GPS/DigiPin, and climate/land-intelligence evidence instead of mixing them into one fragile location field.”

### 90 second demo flow

1. Show PIN/village guardrail during onboarding.
2. Show parcel/home GPS capture and backend-returned DigiPin.
3. Explain that PIN is broad postal context, LGD is administrative identity, and DigiPin/GPS is precise location evidence.
4. Show land-intelligence informational card for a project/PIN/crop scenario.
5. Explain current saved snapshot/provider-deferred posture for weather/soil.

### What this proves

- Android uses backend hierarchy/profile contracts and does not ship its own geography database.
- DigiPin is calculated from coordinates by backend.
- Land-intelligence summaries can be project-overridden and displayed as non-blocking context.

### Evidence hooks

- DigiPin architecture and Android DigiPin GPS materialization closure.
- Geography data-source contract.
- Land-intelligence summary cards and override delivery.

### Landing-page claim candidate

“Location intelligence built from the right layers: LGD/PIN for reference, GPS/DigiPin for precision, and backend land intelligence for advisory context.”

### Claim boundary

Village coordinate geocoding and global/non-India hierarchy migration are future work.

## Script 9: Insurance and subsidy integrity vision

### Audience promise

“The same field evidence fabric can become a fraud/waste/abuse risk layer for insurance, credit, subsidy, and relief programs.”

### 90 second concept demo

1. Start with an implemented parcel/crop-cycle/activity trail.
2. Show GPS/DigiPin and media evidence.
3. Show a field event and advisory audit trail.
4. Explain future claim-risk scoring:
   - same parcel claimed by multiple farmers;
   - crop declaration mismatch;
   - duplicate/recycled damage photos;
   - geo/time plausibility;
   - sparse cultivation trail;
   - agent/intermediary anomaly;
   - NDVI/time-series crop plausibility from GPS parcel polygons.

### What this proves today

- The foundation exists: farmer/project identity, parcel mapping, crop cycles, activity logs, field events, media, DigiPin/GPS, broadcasts, and sync/audit trails.
- These are the ingredients required for claim evidence bundles.

### What remains future work

- Operational insurance claim workflow.
- Risk score model and review queue.
- NDVI/EVI satellite integration.
- Policy/program integration with insurers or government systems.
- Governance for false positives, appeals, and human review.

### Landing-page claim candidate

“A field evidence layer that can power future insurance, subsidy, and credit risk review.”

### Claim boundary

Say “can support” or “roadmap”, not “currently detects fraud”. The current implemented product captures evidence; the risk scoring engine is not yet operational.

## Recommended short-video set

| Video | Duration | Title | Primary viewer | Core claim |
| --- | ---: | --- | --- | --- |
| 1 | 60-90s | Farmer onboarding without hardcoded forms | Farmer ops / product | Backend-owned profile, geography, DigiPin |
| 2 | 90s | FPO project across villages and crops | FPO / enterprise | Multi-farmer project traceability |
| 3 | 60-90s | Crop activity and cost trail | Agronomy / finance | Crop-season operational ledger |
| 4 | 90-120s | Offline sync under real field conditions | Technical / ops | Offline-first, conflict-safe replay |
| 5 | 90s | Targeted advisories with read/ack analytics | Admin / program manager | Communication + audit loop |
| 6 | 60-90s | Pest photo to targeted advisory | Agronomy / FPO | Field evidence to action |
| 7 | 90s | Localization and land intelligence | Product / rollout | Backend-configurable farmer experience |
| 8 | 90s | Geography and DigiPin foundation | Data / platform | Location intelligence layers |
| 9 | 90s | Insurance integrity roadmap | Insurer / investor | Evidence fabric for risk review |

## Landing-page message architecture

### Hero

AgriFabric is an offline-first field evidence and operations fabric for agriculture programs.

### Proof pillars

1. Capture: farmer, parcel, crop, activity, media, and field events.
2. Coordinate: FPO/project enrollment, workflows, advisories, and project closure.
3. Sync: resilient offline replay, conflict recovery, and exact-once materialization.
4. Govern: backend-owned labels, targeting, land intelligence, audit, and admin overrides.
5. Extend: foundation for insurance, subsidy, credit, weather, soil, and satellite evidence.

### Safe language for the landing page

- Use “implemented and verified” for Android MVP flows listed in `docs/android-mvp-readiness-summary.md`.
- Use “approval-gated” for live weather/soil providers and product-source verification.
- Use “roadmap” for insurance risk scoring, NDVI time-series, global geography, and native regional translation expansion.


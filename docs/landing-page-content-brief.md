# AgriFabric landing page content brief

Status date: 2026-08-17

This brief converts the implemented MVP evidence and demo-script pack into landing-page-ready positioning. It is not the landing page implementation. It defines the claims, proof pillars, audience framing, and claim boundaries the eventual page should respect.

Primary source docs:

- `docs/android-mvp-readiness-summary.md`
- `docs/demo-script-pack.md`
- `docs/backend-gap-closure-tracker.md`
- `docs/agrifabric-insurance-fraud-risk-scoring.md`
- `docs/digipin-location-architecture.md`
- `docs/geography-enrichment-analytics-model.md`

## Core positioning

AgriFabric is an offline-first field evidence and operations fabric for agriculture programs.

It helps farmers, field agents, FPOs, enterprises, and program administrators capture trusted field data, coordinate project workflows, send targeted advisories, recover from offline sync conflicts, and build an auditable operational record that can later support insurance, subsidy, credit, and risk-review use cases.

The deeper platform idea is a relationship graph: farmers, agents, companies, FPOs, projects, parcels, crop cycles, activities, field events, media, advisories, and audit trails are connected through typed relationships. This graph is what makes operational analytics, commercial matching, agent benchmarking, and future risk review possible.

## Hero headline options

1. Agriculture operations, evidence, and advisories — built for the field.
2. Offline-first field intelligence for farmers, FPOs, and agriculture programs.
3. Turn farm activity into trusted evidence, workflows, and targeted action.
4. The field evidence fabric for modern agriculture programs.
5. From farmer onboarding to advisory delivery — one auditable agriculture workflow fabric.

## Hero subheadline options

1. AgriFabric connects Android field capture, backend-owned workflows, FPO/project operations, advisories, localization, location intelligence, and resilient offline sync into one auditable platform.
2. Capture farmer, parcel, crop, activity, media, and field-event data in low-connectivity environments, then sync safely with backend audit, conflict recovery, and project traceability.
3. Coordinate FPO programs, crop cycles, field advisories, and farmer communication from a backend-governed system designed for real field conditions.

## Primary call-to-action options

- Watch demo flows
- Explore platform capabilities
- Review MVP evidence
- Talk to us about a pilot

## Problem statement

Agriculture programs often operate across fragmented records: farmer lists, parcel maps, crop declarations, field notes, advisory messages, and claim documents live in separate systems or paper workflows.

This creates recurring problems:

- field data is hard to verify;
- mobile apps fail or duplicate records when connectivity is weak;
- FPO/project teams cannot easily search and drill into the right farmer/crop context;
- advisories lack targeted delivery and audit history;
- location data mixes postal, administrative, and GPS concepts;
- insurance/subsidy programs lack a continuous evidence trail across the crop season.

AgriFabric addresses this by making the backend the source of truth for forms, labels, workflows, targeting, conflict interpretation, audit trails, and summaries while Android remains the field capture and display surface.

## Product pillars

### 1. Capture

Field teams can capture farmer profiles, parcels, crop cycles, activities, media, and field events through Android.

Implemented proof:

- farmer, independent farmer, project-associated farmer, and field-agent modes;
- backend-driven profile forms, option sets, and labels;
- parcel capture with GPS/DigiPin-friendly location evidence;
- crop cycles, stages, activity logging, and cost summaries;
- field-event photo capture feeding advisory workflows.

Landing-page copy:

“Capture the season as it happens: farmer identity, parcel evidence, crop lifecycle, activity logs, media, and field observations.”

### 2. Coordinate

FPOs, enterprises, and program administrators can coordinate farmers across projects, villages, crops, workflows, and advisories.

Implemented proof:

- FPO multi-village fixture with 12 farmers, 4 villages, 4 crops, and mixed workflow stages;
- project enrollment search by village/crop/mobile;
- project trace and farmer/crop drill-down;
- project closure notice with self-service continuation;
- backend-owned project context and launch routing.

Landing-page copy:

“Run project and FPO operations with farmer-level search, crop-stage context, project traceability, and graceful transitions when programs end.”

### 3. Sync

Android can work in real field conditions and recover safely when network state, backend state, or user workflow changes.

Implemented proof:

- cold-start and device-restart queue persistence;
- uncertain-result idempotency;
- dependency-ordered replay;
- partial-batch success and retry behavior;
- VERSION_MISMATCH and WORKFLOW_INVALID conflict recovery;
- multi-conflict drawer;
- queue backpressure;
- interrupted multibatch resume;
- poison-row backlog draining.

Landing-page copy:

“Offline-first capture with auditable replay, conflict recovery, and exact-once backend materialization.”

### 4. Advise

Admins can send targeted, auditable advisories to farmers and inspect delivery/read/ack state.

Implemented proof:

- broadcast delivery generation;
- read and acknowledgement lifecycle;
- admin delivery analytics;
- pending follow-up and retry safety;
- terminal campaign visibility;
- media attachments with backend-provided URLs/captions;
- language fallback;
- crop/location/stage/farmer targeting;
- field event to targeted advisory loop.

Landing-page copy:

“Turn field observations and program rules into targeted advisories with media, language fallback, delivery analytics, and audit history.”

### 5. Govern

The backend governs labels, language fallback, land-intelligence summaries, targeting, project context, and audit trails.

Implemented proof:

- admin-published localization overrides;
- Android multilingual fallback rendering;
- backend-owned land-intelligence summary cards;
- informational-only/do-not-block flags;
- Android endpoint allowlist and no-local-computation boundaries.

Landing-page copy:

“Update labels, content, targeting, and land-intelligence guidance from the backend without hardcoding local logic into Android.”

### 6. Extend

The same field evidence trail can support future insurance, subsidy, credit, weather, soil, and satellite risk-review use cases.

Implemented foundation:

- farmer/project identity;
- parcel and DigiPin/GPS evidence;
- crop-cycle and activity trails;
- media evidence;
- field-event and advisory audit;
- sync and conflict audit trails.

Roadmap:

- insurance fraud/waste/abuse risk scoring;
- NDVI/EVI time-series evidence from parcel polygons;
- live weather/soil provider execution;
- verified product-source catalog;
- global geography model;
- native regional translation expansion.

Landing-page copy:

“Build the evidence fabric today; extend it tomorrow into insurance, credit, subsidy, weather, soil, and satellite intelligence.”

## Use-case cards

### Farmer onboarding

Backend-owned forms, labels, options, geography guardrails, and DigiPin/GPS location evidence.

Proof status: implemented and verified.

### FPO/project operations

Manage many affiliated farmers across villages, crops, stages, and project lifecycle transitions.

Proof status: implemented and verified through deterministic FPO flows.

### Crop activity ledger

Capture crop cycles, stage timelines, activity logs, and backend-computed cost evidence.

Proof status: implemented and verified for MVP activity/cost summaries.

### Offline sync resilience

Recover from no network, restarts, partial batches, conflicts, and poison rows without duplicate backend records.

Proof status: implemented and verified across Android sync/conflict flows.

### Targeted advisory delivery

Send crop/location/stage/farmer-targeted messages with media, language fallback, read/ack analytics, and audit history.

Proof status: implemented and verified.

### Field event to action

Convert a pest/damage field-event photo into a targeted advisory while preserving source media evidence.

Proof status: implemented and verified.

### Localization and land intelligence

Backend-published labels, fallback behavior, and project-specific land-intelligence cards.

Proof status: implemented and verified for MVP/fallback behavior.

### Geography and DigiPin foundation

Separate LGD administrative hierarchy, PIN postal reference, GPS/DigiPin precision, and land-intelligence context.

Proof status: implemented for MVP India-compatible flows; global generalization remains roadmap.

### Insurance and subsidy integrity

Use the field evidence trail to support future risk flags for duplicate parcel claims, crop mismatch, media reuse, geo/time plausibility, and NDVI time-series evidence.

Proof status: roadmap. Implemented foundation exists, but operational scoring is not yet implemented.

## Buyer/persona framing

### FPO and project operators

Need to coordinate many farmers, crop cycles, advisories, and project transitions.

Relevant claims:

- multi-village project traceability;
- farmer search and drill-down;
- targeted advisories;
- project closure continuation.

### Agri-enterprises and input/advisory programs

Need field execution, crop-stage visibility, farmer communication, and evidence of adoption/activity.

Relevant claims:

- crop activity ledger;
- stage-aware workflows;
- media advisories;
- read/ack analytics.

### Field-agent networks

Need assisted capture, worklists, low-connectivity operation, and conflict-safe sync.

Relevant claims:

- field-agent assisted mode;
- offline-first capture;
- queue recovery;
- backend-owned forms.

### Insurers, lenders, and subsidy programs

Need trustworthy evidence trails and future risk-review signals.

Relevant claims:

- parcel/crop/activity/media evidence;
- DigiPin/GPS location evidence;
- field-event audit trail;
- future insurance/subsidy risk scoring roadmap.

## Demo-safe proof points

- Android MVP readiness is closed and documented.
- Backend tracker has no active MVP Android watch rows.
- FPO/project flows are verified across backend, web, and Android.
- Sync/conflict/offline resilience is verified through deterministic Android flows.
- Broadcast/advisory/media/language/targeting lifecycle is verified.
- Field-event advisory loop is verified.
- Localization override, multilingual fallback, DigiPin, and land-intelligence display are verified.

## Roadmap / vision section

Use this section for aspirational but bounded claims.

Possible copy:

“AgriFabric is designed to become a field evidence layer for insurance, subsidy, credit, weather, soil, and satellite intelligence. The current MVP captures the operational evidence trail. Future modules can add NDVI time-series analysis, insurer claim packets, product-source verification, live provider workers, and transparent risk scoring with human review.”

## Claims to avoid for now

- Do not say AgriFabric currently detects crop insurance fraud automatically.
- Do not say risk scores are operational.
- Do not say NDVI/EVI analysis is implemented.
- Do not say live weather/soil providers are active in demo.
- Do not say product catalog rows are regulator/manufacturer verified.
- Do not say Kannada/Marathi/Punjabi native translations are complete.
- Do not say the platform is fully global/multi-country today.
- Do not imply automated claim denial. Future risk scoring should be review-assistive and explainable.

## Recommended landing-page structure

1. Hero: offline-first field evidence fabric.
2. Problem: agriculture data is fragmented and hard to verify.
3. Product pillars: Capture, Coordinate, Sync, Advise, Govern, Extend.
4. Use-case cards: onboarding, FPO ops, crop ledger, offline sync, advisories, field events, localization, geography, insurance roadmap.
5. Evidence strip: Android MVP closed, backend tracker clean, verified flows.
6. Demo video grid: 9 short demos from `docs/demo-script-pack.md`.
7. Roadmap with boundaries: insurance risk, satellite, live providers, global geography.
8. CTA: pilot conversation or demo request.


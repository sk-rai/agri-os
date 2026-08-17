# AgriFabric landing page wireframe

Status date: 2026-08-17

This wireframe translates `docs/landing-page-content-brief.md` into a section-by-section landing page blueprint. It is still not an implementation. It defines page order, copy intent, visual placement, proof placement, and claim boundaries for a future website build.

## Page goal

Convert a visitor from “this is another agri app” to “this is an offline-first field evidence and operations fabric with verified Android/admin workflows and a credible roadmap into insurance, subsidy, credit, weather, soil, and satellite intelligence.”

Primary CTA:

- Talk to us about a pilot

Secondary CTA:

- Watch demo flows

## Visual tone

- Practical, field-ready, trustworthy.
- More operating system than glossy marketplace.
- Use grounded visuals: Android screens, admin dashboards, maps/parcels, advisory cards, sync/conflict evidence, and audit trails.
- Avoid over-polished “AI magic” visuals unless clearly marked as roadmap.

## Section 1: Hero

### Purpose

State the platform category quickly and separate AgriFabric from a simple mobile data-entry app.

### Layout

```text
┌──────────────────────────────────────────────────────────────┐
│ Nav: AgriFabric | Product | Use cases | Demo | Roadmap | CTA │
├──────────────────────────────┬───────────────────────────────┤
│ Headline                     │ Hero visual                    │
│ Subheadline                  │ Android + admin composite      │
│ CTA primary / CTA secondary  │ Offline sync / advisory / map  │
│ Proof badges                 │                               │
└──────────────────────────────┴───────────────────────────────┘
```

### Recommended headline

Offline-first field intelligence for farmers, FPOs, and agriculture programs.

### Recommended subheadline

Capture farmer, parcel, crop, activity, media, and field-event data in low-connectivity environments, then sync safely with backend audit, conflict recovery, project traceability, and targeted advisories.

### Proof badges

- Android MVP closed
- Offline sync verified
- FPO/project workflows verified
- Backend-owned advisories and localization

### Visual slot

Composite image or short silent loop:

- Android farmer profile/crop screen;
- admin broadcast/project screen;
- small map/DigiPin/parcel callout;
- sync status card.

### Claim boundary

Do not mention operational insurance fraud detection in the hero. Keep hero focused on implemented platform capability.

## Section 2: Problem

### Purpose

Show the operational pain that the product organizes.

### Layout

```text
┌──────────────────────────────────────────────────────────────┐
│ Agriculture programs run on fragmented field evidence.        │
├──────────────┬──────────────┬──────────────┬────────────────┤
│ Paper/forms  │ Weak offline │ No audit     │ Poor targeting │
│ Parcel gaps  │ Crop mismatch│ Language gaps│ Siloed systems │
└──────────────┴──────────────┴──────────────┴────────────────┘
```

### Copy intent

Agriculture programs need more than farmer lists and advisory messages. They need a continuous evidence trail across identity, parcel, crop, field activity, media, location, communication, and audit history.

### Visual slot

Fragmented cards flowing into a single AgriFabric evidence timeline.

## Section 3: Product pillars

### Purpose

Introduce the platform model in six verbs: Capture, Coordinate, Sync, Advise, Govern, Extend.

### Layout

```text
┌──────────────────────────────────────────────────────────────┐
│ Six pillars                                                   │
├──────────┬──────────┬──────────┐                            │
│ Capture  │ Coordinate│ Sync     │                            │
├──────────┼──────────┼──────────┤                            │
│ Advise   │ Govern   │ Extend   │                            │
└──────────┴──────────┴──────────┘
```

### Card copy

Capture:

Farmer profiles, parcels, crop cycles, activities, media, and field events from Android.

Coordinate:

FPO/project enrollment, search, project trace, workflow stages, and closure continuation.

Sync:

Offline-first queue persistence, replay ordering, conflict recovery, and exact-once materialization.

Advise:

Targeted advisories with media, language fallback, read/ack lifecycle, analytics, and audit.

Govern:

Backend-owned forms, labels, localization overrides, targeting rules, land intelligence, and audit trails.

Extend:

Foundation for insurance, subsidy, credit, weather, soil, and satellite evidence.

### Visual slot

Icon grid with one proof screenshot per pillar available on hover/click in later implementation.

## Section 4: How the field evidence fabric works

### Purpose

Explain the system architecture at a product level without diving into implementation details.

### Layout

```text
Android field app
  ↓ captures
Farmer + parcel + crop + activity + media + event
  ↓ syncs
Backend contracts + validation + conflict handling
  ↓ powers
Admin operations + project trace + advisories + audit
  ↓ extends into
Insurance / subsidy / credit / weather / soil / satellite roadmap
```

### Copy intent

Android captures and displays. Backend owns contracts, labels, workflow rules, targeting, conflict interpretation, summaries, and audit history.

### Visual slot

Simple horizontal pipeline with icons:

Android → Sync Queue → Backend Evidence Graph → Admin/FPO Operations → Future Risk Intelligence.

### Claim boundary

“Future Risk Intelligence” should be visually marked as roadmap/future, not current operational scoring.

## Section 5: Use-case grid

### Purpose

Let different buyer personas find themselves quickly.

### Layout

```text
┌──────────────┬──────────────┬──────────────┐
│ Onboarding   │ FPO Ops      │ Crop Ledger  │
├──────────────┼──────────────┼──────────────┤
│ Offline Sync │ Advisories   │ Field Events │
├──────────────┼──────────────┼──────────────┤
│ Localization │ Geography    │ Insurance*   │
└──────────────┴──────────────┴──────────────┘
```

Insurance card label:

- “Roadmap: Insurance & subsidy integrity”

### Card details

Farmer onboarding:

Backend-owned forms, labels, options, geography guardrails, GPS/DigiPin evidence.

FPO/project operations:

Multi-village farmer management, project trace, search, crop-stage visibility, closure continuation.

Crop activity ledger:

Crop cycles, stage timeline, activity logs, cost evidence, and traceability.

Offline sync resilience:

No-network capture, queue persistence, replay, idempotency, conflict cards, backlog draining.

Targeted advisories:

Campaigns, media, language fallback, read/ack analytics, terminal lifecycle, audit history.

Field event to action:

Pest/photo field event becomes targeted advisory with source media reuse.

Localization and land intelligence:

Backend-published labels, safe language fallback, project land-intelligence summaries.

Geography and DigiPin:

LGD/PIN reference, GPS/DigiPin precision, parcel-friendly location evidence.

Insurance and subsidy integrity:

Future risk review from parcel, crop, media, sync, weather, and satellite evidence.

## Section 6: Demo video strip

### Purpose

Convert the demo script pack into visible proof assets.

### Layout

```text
┌──────────────────────────────────────────────────────────────┐
│ Watch the system in short flows                               │
├──────────┬──────────┬──────────┬──────────┬──────────┐       │
│ 1 Onboard│ 2 FPO    │ 3 Crop   │ 4 Offline│ 5 Advise │       │
├──────────┼──────────┼──────────┼──────────┼──────────┤       │
│ 6 Event  │ 7 Local  │ 8 Geo    │ 9 Risk*  │          │       │
└──────────┴──────────┴──────────┴──────────┴──────────┘
```

### Video cards

Use the 9 scripts from `docs/demo-script-pack.md`.

Each card should include:

- title;
- duration;
- implemented/roadmap badge;
- one sentence;
- thumbnail from Android/admin screen recording.

### Claim boundary

Risk/insurance video must be marked “roadmap concept built on implemented evidence foundation.”

## Section 7: Proof strip

### Purpose

Give confidence that the platform is not speculative.

### Layout

```text
┌──────────────┬──────────────┬──────────────┬──────────────┐
│ Android MVP  │ Sync flows   │ FPO flows    │ Advisory loop│
│ closed       │ verified     │ verified     │ verified     │
└──────────────┴──────────────┴──────────────┴──────────────┘
```

### Suggested proof metrics

- Android MVP readiness documented.
- Backend tracker has no active MVP Android rows.
- Sync/conflict/offline flows verified through Flow 64.
- Multilingual fallback verified through Flow 65.
- FPO search/drill-down, project closure, broadcast lifecycle, and field-event advisory loop verified.

### Visual slot

Small “evidence cards” with links to docs or eventual demo clips.

## Section 8: Buyer/persona sections

### Purpose

Translate platform features into buyer-specific language.

### Layout

```text
Tabs or stacked cards:
FPOs | Agri-enterprises | Field-agent networks | Insurers/lenders/programs
```

### FPOs

Run multi-village crop programs, search farmers by project/crop/village, track crop stages, and send targeted advisories.

### Agri-enterprises

Coordinate field execution, crop-stage workflows, product/advisory programs, media guidance, and adoption evidence.

### Field-agent networks

Capture data offline, assist farmers, recover sync safely, and keep work traceable to backend rules.

### Insurers/lenders/programs

Use the field evidence foundation for future review-assistive risk flags and claim evidence bundles.

### Claim boundary

Insurance/lender/program section must say “future risk-review modules” or “foundation for”, not operational underwriting/claim decisioning.

## Section 9: Geography and location intelligence

### Purpose

Make DigiPin/geography a differentiator without drowning visitors in data-model details.

### Layout

```text
PIN / LGD / GPS / DigiPin / Parcel / Land Intelligence
```

### Copy

AgriFabric keeps location layers separate:

- LGD for administrative hierarchy;
- PIN for postal/reference context;
- GPS and parcel geometry for physical evidence;
- DigiPin for precise coordinate-derived addressing;
- land-intelligence cards for backend-owned, non-blocking guidance.

### Visual slot

Layered map card:

Village/PIN → parcel point/polygon → DigiPin → land-intelligence card.

### Claim boundary

Do not claim live village geocoding or global geography coverage yet.

## Section 10: Roadmap with boundaries

### Purpose

Show ambitious direction while preserving trust.

### Layout

```text
Implemented foundation | Approval-gated | Roadmap
```

Implemented foundation:

- field capture;
- crop cycle/activity evidence;
- media and field events;
- FPO/project traceability;
- sync/audit trail;
- DigiPin/GPS evidence.

Approval-gated:

- live weather/soil providers;
- product-source verification;
- provider worker live execution.

Roadmap:

- insurance risk scoring;
- NDVI/EVI satellite time series;
- global geography model;
- native regional translations;
- decision-node/perennial workflow hardening.

### Claim boundary

This section should be explicit and confidence-building: “We know what is implemented, what is gated, and what is roadmap.”

## Section 11: Final CTA

### Purpose

Close with a pilot/demo invitation.

### Layout

```text
Ready to pilot a field evidence fabric for your agriculture program?
[Talk to us about a pilot] [Watch demo flows]
```

### Copy

Start with a focused pilot: farmer onboarding, FPO project operations, offline crop activity capture, or targeted advisory delivery.

## Mobile page order

For mobile, collapse to:

1. Hero
2. Proof badges
3. Product pillars
4. Use-case cards
5. Demo videos
6. Buyer cards
7. Roadmap boundaries
8. CTA

## Implementation notes for later

- Use screenshots/videos from Playwright and Maestro once final demo captures are curated.
- Keep roadmap badges visually distinct from implemented proof badges.
- Link evidence cards to docs or demo clips, not raw verifier logs.
- Avoid naming exact fixture counts in the hero. Use them in proof/evidence sections only.
- Add a “claim safety” checklist before publishing.

## Claim safety checklist

Before publishing, confirm the page does not claim:

- automatic fraud detection;
- operational risk scoring;
- implemented NDVI/EVI analysis;
- live weather/soil provider execution;
- verified regulator/manufacturer product labels;
- complete native Kannada/Marathi/Punjabi translations;
- full global geography rollout;
- automated insurance claim denial or approval.


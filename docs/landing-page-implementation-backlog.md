# AgriFabric landing page implementation backlog

Status date: 2026-08-17

This backlog turns the landing-page content brief, wireframe, demo scripts, and demo asset inventory into a build plan. It is not the landing page implementation. It defines what should be built, what content each section needs, which proof assets it depends on, and which claims must remain bounded.

Source docs:

- `docs/landing-page-content-brief.md`
- `docs/landing-page-wireframe.md`
- `docs/demo-script-pack.md`
- `docs/demo-capture-checklist.md`
- `docs/demo-capture-operations-runbook.md`
- `docs/demo-asset-inventory.md`
- `docs/android-mvp-readiness-summary.md`
- `docs/agrifabric-relationship-graph-and-agent-performance.md`
- `docs/agrifabric-insurance-fraud-risk-scoring.md`

## Build principle

The page should feel like an evidence-backed product, not a speculative concept deck.

Every major section should answer three questions:

1. What operational problem does this solve?
2. What implemented proof can we show?
3. What is clearly roadmap or approval-gated?

## Page-level requirements

- Mobile-first responsive design.
- Clear top navigation: Product, Use cases, Demo, Geography, Roadmap, Pilot CTA.
- Fast-loading static content first; videos can lazy-load.
- Roadmap badges must be visually distinct from verified-MVP badges.
- No production/private data in screenshots or videos.
- No claims of live provider execution, operational fraud scoring, NDVI analysis, complete global geography, or verified product labels.
- Evidence links should point to curated docs/demo clips, not raw logs.

## Content model

The landing page can be implemented with a small static content model before a CMS exists.

Suggested content groups:

```text
hero
proofBadges[]
problemCards[]
pillars[]
relationshipGraph
fieldEvidencePipeline
useCases[]
demoVideos[]
proofCards[]
buyerPersonas[]
geographyLayers[]
roadmapColumns[]
finalCta
```

This keeps the page easy to port later into a CMS, Airtable, Notion, or admin-managed content source if needed.

## Implementation backlog

### LP-01 — Landing page shell

Goal:

Create the base route/page shell for the future AgriFabric landing page.

Recommended route:

```text
/agrifabric
```

Components:

- Header/nav.
- Footer.
- Section wrapper.
- CTA button variants.
- Badge component.
- Video/card placeholder component.

Acceptance criteria:

- Page renders without demo videos.
- Mobile and desktop layouts are usable.
- No backend dependency required for static page render.

Dependencies:

- None beyond existing web stack.

Claim boundary:

- Do not add unsupported marketing copy during implementation.

### LP-02 — Hero section

Goal:

Communicate the category: offline-first field evidence and operations fabric.

Required content:

- Headline: “Offline-first field intelligence for farmers, FPOs, and agriculture programs.”
- Subheadline from `docs/landing-page-wireframe.md`.
- Primary CTA: “Talk to us about a pilot.”
- Secondary CTA: “Watch demo flows.”
- Proof badges:
  - Android MVP closed.
  - Offline sync verified.
  - FPO/project workflows verified.
  - Backend-owned advisories and localization.

Required assets:

- `hero-field-evidence-graph.png` or a temporary CSS/SVG composite.
- Optional short silent hero loop later.

Acceptance criteria:

- Hero does not mention operational insurance fraud detection.
- Hero visual shows Android + admin + graph/evidence theme.
- CTA anchors work.

### LP-03 — Problem section

Goal:

Explain why fragmented agriculture operations need an evidence fabric.

Problem cards:

- Paper/forms.
- Weak offline.
- No audit.
- Poor targeting.
- Parcel gaps.
- Crop mismatch.
- Language gaps.
- Siloed systems.

Acceptance criteria:

- The problem is framed operationally, not as generic “AI for agriculture.”
- Copy sets up the graph/evidence solution.

### LP-04 — Product pillars

Goal:

Introduce the six product verbs.

Pillars:

1. Capture.
2. Coordinate.
3. Sync.
4. Advise.
5. Govern.
6. Extend.

Required behavior:

- Each pillar has a short one-line description.
- Each pillar has a proof badge:
  - Capture, Coordinate, Sync, Advise, Govern = verified MVP.
  - Extend = foundation/roadmap.

Required assets:

- One small image/icon per pillar.
- Later: hover/click proof screenshot.

Acceptance criteria:

- Extend does not imply live insurance/scoring/provider modules.
- Sync copy includes conflict recovery and exact-once materialization.

### LP-05 — Relationship graph section

Goal:

Explain that AgriFabric is a typed relationship graph across farmers, agents, companies/FPOs, projects, parcels, crop cycles, media, advisories, and audit events.

Graph nodes:

- Farmer.
- Field agent.
- Company/FPO.
- Project.
- Parcel.
- Crop cycle.
- Stage/activity.
- Media asset.
- Field event.
- Advisory.
- Delivery/read/ack.
- Sync/audit event.

Highlighted paths:

- FPO → Project → Farmer cohort.
- Agent → Assigned farmers → Completed work.
- Parcel → Crop cycle → Activity/media.
- Field event → Advisory → Read/ack audit.

Acceptance criteria:

- Uses a real graph-style visual, not only text.
- Mentions current traceability and future analytics separately.
- Field-agent performance, commercial matching, and fraud/risk scoring are marked as roadmap modules unless implemented later.

Suggested visual implementation:

- First version: SVG/HTML node-link diagram.
- Later version: interactive graph with highlighted paths.

### LP-06 — Field evidence pipeline

Goal:

Show the product architecture at a non-technical level.

Pipeline:

```text
Android field app
  → captures farmer/parcel/crop/activity/media/event
  → syncs through backend contracts/validation/conflict handling
  → powers admin operations/project trace/advisories/audit
  → extends into future risk intelligence
```

Acceptance criteria:

- Android is described as capture/display surface.
- Backend is described as owner of contracts, labels, workflow rules, targeting, conflict interpretation, summaries, and audit.
- Future Risk Intelligence is visually marked roadmap.

### LP-07 — Use-case grid

Goal:

Help buyers quickly find relevant outcomes.

Use-case cards:

- Farmer onboarding.
- FPO/project operations.
- Crop activity ledger.
- Offline sync resilience.
- Targeted advisories.
- Field event to action.
- Localization and land intelligence.
- Geography and DigiPin.
- Insurance and subsidy integrity.

Acceptance criteria:

- Eight implemented/foundation cards can use verified/foundation badges.
- Insurance/subsidy card must use “Roadmap: Insurance & subsidy integrity.”

### LP-08 — Demo video strip

Goal:

Surface the short clips from `docs/demo-asset-inventory.md`.

Video cards:

1. Farmer onboarding.
2. FPO/project operations.
3. Crop activity ledger.
4. Offline sync resilience.
5. Advisory lifecycle.
6. Field event to advisory.
7. Localization and land intelligence.
8. Geography and DigiPin.
9. Relationship graph and agent performance.
10. Insurance integrity roadmap.

Fields:

- Title.
- Duration.
- Capture mode badge: Android, Web, Mixed, Concept.
- Proof status badge.
- Thumbnail.
- Short summary.
- Link to video asset or placeholder.

Acceptance criteria:

- Page works with placeholder cards before videos exist.
- Roadmap concept videos are visually distinct.

### LP-09 — Proof strip

Goal:

Give immediate confidence that the MVP was verified.

Proof cards:

- Android MVP readiness documented.
- Backend tracker has no active MVP Android rows.
- Sync/conflict/offline flows verified through Flow 64.
- Multilingual fallback verified through Flow 65.
- FPO search/drill-down verified.
- Broadcast/advisory lifecycle verified.
- Field-event advisory loop verified.
- Land intelligence/localization override verified.

Acceptance criteria:

- Proof cards link to curated docs.
- Do not link to raw `/tmp` outputs.

### LP-10 — Buyer/persona sections

Goal:

Translate features into buyer language.

Personas:

- FPOs and project operators.
- Agri-enterprises and input/advisory programs.
- Field-agent networks.
- Insurers, lenders, and public programs.

Acceptance criteria:

- Insurer/lender/program section says “future risk-review modules” or “foundation for claim evidence bundles.”
- It does not claim operational underwriting, claim approval, or claim denial.

### LP-11 — Geography and location intelligence section

Goal:

Make the location model understandable and useful.

Layers:

- LGD administrative hierarchy.
- PIN postal/reference context.
- GPS and parcel geometry.
- DigiPin derived from coordinates.
- Land-intelligence summaries.
- Future provider/geocoding/global geography extensions.

Acceptance criteria:

- DigiPin is described as coordinate-derived precision evidence.
- PIN is not described as precision location.
- Village geocoding and global geography coverage remain future/provider-gated.

### LP-12 — Roadmap boundaries section

Goal:

Build trust by explicitly separating implemented, approval-gated, and roadmap capabilities.

Columns:

Implemented foundation:

- Android field capture.
- Crop cycle/activity evidence.
- Media and field events.
- FPO/project traceability.
- Sync/audit trail.
- DigiPin/GPS evidence.
- Broadcast/advisory lifecycle.
- Localization fallback.

Approval-gated:

- Live weather/soil providers.
- Product-source verification.
- Provider worker live execution.

Roadmap:

- Insurance risk scoring.
- NDVI/EVI satellite time series.
- Global geography model.
- Native regional translations.
- Decision-node/perennial workflow hardening.
- Field-agent scorecards and commercial matching.

Acceptance criteria:

- This section is visible, not hidden in footnotes.
- It reassures buyers that the system has disciplined claim boundaries.

### LP-13 — Final CTA

Goal:

Close with a focused pilot offer.

Suggested copy:

```text
Ready to pilot a field evidence fabric for your agriculture program?
Start with farmer onboarding, FPO project operations, offline crop activity capture, or targeted advisory delivery.
```

Buttons:

- Talk to us about a pilot.
- Watch demo flows.

Acceptance criteria:

- CTA does not promise unsupported modules.

## Asset dependencies

| Asset | Required for | Status |
| --- | --- | --- |
| Hero composite | Hero | Available: `docs/assets/hero-composite.svg`, `docs/assets/hero-composite-compact.svg` |
| Product pillar icons | Product pillars | Available: `docs/assets/product-pillars.svg` plus individual `docs/assets/product-pillar-*.svg` icons |
| Relationship graph SVG | Relationship graph | Available: `docs/assets/relationship-graph.svg`, `docs/assets/relationship-graph-overview.svg`, `docs/assets/relationship-graph-roadmap-layer.svg` |
| Field evidence pipeline visual | Pipeline | Available: `docs/assets/field-evidence-pipeline.svg`, `docs/assets/field-evidence-pipeline-compact.svg` |
| Demo video thumbnails | Demo strip | Needed after capture |
| Android onboarding clip | Demo strip / Capture pillar | Needed |
| FPO web/admin clip | Demo strip / Coordinate pillar | Needed |
| Offline sync clip | Demo strip / Sync pillar | Needed |
| Broadcast analytics clip | Demo strip / Advise pillar | Needed |
| Field-event advisory clip | Demo strip / Advise/graph | Needed |
| Localization/land-intelligence clip | Demo strip / Govern pillar | Needed |
| Geography/DigiPin visual | Geography section | Available: `docs/assets/geography-digipin-overview.svg`, `docs/assets/geography-digipin-layered-model.svg`, `docs/assets/geography-global-extension-layer.svg` |
| Insurance roadmap graphic | Extend/Roadmap | Available: `docs/assets/insurance-risk-roadmap.svg`, `docs/assets/insurance-risk-roadmap-compact.svg` |

## Landing page draft checkpoint

Status date: 2026-08-20

The first public AgriFabric landing-page draft is implemented at `/agrifabric`.

Implemented:

- tabbed story structure: Overview, Product, Evidence graph, Operations, Geography, Roadmap;
- committed static SVG assets copied into `web/public/landing-assets`;
- claim-bounded roadmap sections for insurance/risk, NDVI, live providers, and global geography;
- admin root behavior remains unchanged because `/` still redirects to `/login`;
- Playwright smoke `web/smoke/agrifabric_landing_smoke.mjs` verifies page load, all six tabs, landing assets, mobile rendering, and roadmap claim boundary.

Current next work:

- visual/copy polish as needed;
- demo capture planning and eventual video/thumbnails;
- future landing-page hosting/deployment decision when ready.

## README and discoverability checkpoint

Status date: 2026-08-20

Repository entry-point documentation now points reviewers to the AgriFabric landing route, smoke test, capture helper, demo planning docs, and claim boundaries.

Implemented:

- root `README.md` explains repo structure, backend/web startup, landing route, useful checks, and claim boundaries;
- `web/README.md` documents `/agrifabric`, local web startup, build, smoke test, and capture helper;
- `docs/README.md` links the static demo capture runbook and landing capture helper.

Current remaining landing work:

- visual and copy refinement as needed;
- demo video and thumbnail production;
- future hosting/deployment decision;
- optional performance polish for landing SVG rendering if needed.

## Demo capture planning checkpoint

Status date: 2026-08-20

Demo-video planning is now captured in `docs/agrifabric-demo-video-capture-matrix.md`.

The matrix maps videos to landing tabs and separates Web/static-only, Android-only, and mixed Android+web capture modes. Actual video assets and thumbnails remain future production work.

## Suggested implementation phases

### Phase 1 — Static landing page without final video assets

- Build route/page shell.
- Add all sections with copy.
- Use simple CSS/SVG placeholders for visuals.
- Use badges and claim boundaries.
- Link docs where video assets are not yet available.

### Phase 2 — Proof assets

- Capture videos according to `docs/demo-capture-operations-runbook.md`.
- Export thumbnails.
- Add demo video strip assets.
- Replace placeholders in hero/proof sections.

### Phase 3 — Polish and conversion

- Add stronger CTA handling.
- Add inquiry/pilot form when product/CRM decision is made.
- Add analytics only after privacy/consent decision.
- Tighten mobile animations and lazy-loading.

## Pre-publish claim review

Before publishing, search the page copy for these terms and verify badges/boundaries:

- fraud
- risk
- scoring
- insurance
- claim
- NDVI
- satellite
- live weather
- live soil
- verified product
- global
- Kannada
- Marathi
- Punjabi

Any use of these terms must be either:

- implemented and linked to proof; or
- marked as foundation, approval-gated, or roadmap.


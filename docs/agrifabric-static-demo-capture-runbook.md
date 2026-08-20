# AgriFabric static/web demo capture runbook

Status date: 2026-08-20

This runbook defines the first low-risk demo capture batch for `/agrifabric`. These clips are web/static-led and should be captured before fragile Android/Maestro videos.

Source matrix: `docs/agrifabric-demo-video-capture-matrix.md`

## Capture setup

Frontend:

- start command: `cd web && npm run dev -- --port 3000`
- URL: `http://localhost:3000/agrifabric`

Recommended viewport:

- desktop capture: 1440x1100
- thumbnail capture: 1280x720
- social/carousel crop: 1080x1080 from source frame if needed

Recommended capture style:

- dark background retained;
- pointer movement minimal;
- one tab per clip;
- no raw dev tools unless capturing proof for internal docs;
- overlays added in editing, not in the app, unless later implemented.

## V02 — Six pillars of AgriFabric

Landing tab: Product

Capture mode: Web/static only

Purpose:
Explain the product in six verbs: Capture, Coordinate, Sync, Advise, Govern, Extend.

Open:

- `/agrifabric`
- click Product tab

Primary visual:

- product pillar cards
- `docs/assets/product-pillars.svg`

Narration beats:

1. AgriFabric is not just an Android app; it is a field evidence fabric.
2. Capture records farmer, parcel, crop, activity, media, and field events.
3. Coordinate supports FPO/project operations and field-agent work.
4. Sync handles offline replay, idempotency, conflicts, and backlog draining.
5. Advise and Govern cover backend-owned advisories, labels, localization, land intelligence, and audit.
6. Extend is a roadmap foundation, not a live risk engine.

Overlay badges:

- Verified MVP for Capture/Coordinate/Sync/Advise/Govern.
- Roadmap foundation for Extend.

Do not claim:

- live fraud scoring;
- live weather/soil execution;
- automated insurance decisions.

## V08 — PIN, GPS, DigiPin, and land intelligence

Landing tab: Geography

Capture mode: Web/static only, optional later Android insert

Purpose:
Explain why geography is modeled in layers.

Open:

- `/agrifabric`
- click Geography tab

Primary visuals:

- `docs/assets/geography-digipin-overview.svg`
- `docs/assets/geography-digipin-layered-model.svg`
- `docs/assets/geography-global-extension-layer.svg`

Narration beats:

1. PIN is useful context, but it is not parcel precision.
2. GPS/parcel capture provides the field evidence layer.
3. DigiPin is backend-generated from coordinates.
4. Land intelligence is displayed as informational, non-blocking guidance.
5. Global geography is an architecture path, not completed rollout.

Overlay badges:

- Backend-owned
- Informational only
- Roadmap: global extension

Do not claim:

- Android computes canonical DigiPin locally;
- PIN resolves exact plot identity;
- global geography is implemented;
- live provider/geocoding is demo-live-safe.

## V10 — Relationship graph and commercial analytics

Landing tab: Evidence graph

Capture mode: Web/static only

Purpose:
Explain the core platform concept: entities are connected through typed relationships.

Open:

- `/agrifabric`
- click Evidence graph tab

Primary visuals:

- `docs/assets/relationship-graph-overview.svg`
- optionally `docs/assets/relationship-graph-roadmap-layer.svg`

Narration beats:

1. Farmers, agents, companies/FPOs, projects, parcels, crop cycles, advisories, sync events, and audit trails are connected.
2. These relationships enable project traceability today.
3. The same graph can later support agent benchmarking, assignment planning, risk review, and claim evidence bundles.
4. Roadmap analytics are deliberately separated from verified MVP capabilities.

Overlay badges:

- Implemented traceability
- Evidence graph
- Roadmap analytics bounded

Do not claim:

- current automated agent scoring;
- current operational fraud score;
- current claim decisioning.

## V11 — Insurance and subsidy integrity foundation

Landing tab: Roadmap

Capture mode: Web/static only

Purpose:
Explain the fraud/waste/abuse and claim-evidence direction without overclaiming.

Open:

- `/agrifabric`
- click Roadmap tab

Primary visuals:

- `docs/assets/insurance-risk-roadmap.svg`
- `docs/assets/insurance-risk-roadmap-compact.svg`

Narration beats:

1. AgriFabric already creates a field evidence foundation: identity, parcel, crop ledger, media, sync, advisories, and audit.
2. Future insurance/subsidy review can use this evidence to assemble claim bundles and flag inconsistencies.
3. Duplicate parcel cultivation claims, missing field activity, suspicious media patterns, or agent-task gaps can become review signals.
4. NDVI/time-series and live weather/soil context are future/approval-gated enrichments.
5. Human review remains explicit; this is not automated approval/rejection.

Overlay badges:

- Roadmap
- Human review
- Not automated decisioning

Do not claim:

- detects fraud today;
- automated claim decisions;
- live NDVI scoring;
- insurer-integrated production scoring.

## Suggested capture order

1. V02 Product pillars
2. V10 Relationship graph
3. V08 Geography/DigiPin
4. V11 Insurance/subsidy roadmap

Reason:
This order moves from product overview to graph concept to location evidence to roadmap/risk. It tells a coherent story without requiring Android emulator capture.

## Output naming

Suggested raw capture filenames:

- `agrifabric-v02-product-pillars-raw.mp4`
- `agrifabric-v10-relationship-graph-raw.mp4`
- `agrifabric-v08-geography-digipin-raw.mp4`
- `agrifabric-v11-insurance-roadmap-raw.mp4`

Suggested thumbnail filenames:

- `agrifabric-v02-product-pillars-thumb.png`
- `agrifabric-v10-relationship-graph-thumb.png`
- `agrifabric-v08-geography-digipin-thumb.png`
- `agrifabric-v11-insurance-roadmap-thumb.png`

## Acceptance checklist

- Clip is 30-90 seconds.
- One clear promise per clip.
- Roadmap/future modules are visually marked.
- No unsupported claims are spoken or shown.
- Text remains readable at 720p.
- If exported for LinkedIn/social, subtitles or captions are added.

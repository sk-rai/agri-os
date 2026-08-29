# AgriFabric demo video production manifest

Status date: 2026-08-29

This manifest records where the AgriFabric demo-video effort paused and where production should resume. It is intentionally scoped to static/web-first work so it can run safely while long NWDP read-only overlay jobs are still using CPU.

## Current state

The /agrifabric landing draft is implemented and tracked.

Tracked implementation:

- web/src/app/agrifabric/page.tsx
- web/src/app/agrifabric/AgriFabricLandingClient.tsx
- web/smoke/agrifabric_landing_smoke.mjs
- web/smoke/agrifabric_landing_capture_helper.mjs
- web/public/landing-assets/*.svg

Tracked planning docs:

- docs/demo-script-pack.md
- docs/demo-capture-checklist.md
- docs/demo-capture-operations-runbook.md
- docs/demo-asset-inventory.md
- docs/agrifabric-demo-video-capture-matrix.md
- docs/agrifabric-static-demo-capture-runbook.md

Already generated but still untracked:

- web/smoke/screenshots/agrifabric/agrifabric-v02-product-pillars-thumb.png
- web/smoke/screenshots/agrifabric/agrifabric-v02-product-pillars-full.png
- web/smoke/screenshots/agrifabric/agrifabric-v08-geography-digipin-thumb.png
- web/smoke/screenshots/agrifabric/agrifabric-v08-geography-digipin-full.png
- web/smoke/screenshots/agrifabric/agrifabric-v10-relationship-graph-thumb.png
- web/smoke/screenshots/agrifabric/agrifabric-v10-relationship-graph-full.png
- web/smoke/screenshots/agrifabric/agrifabric-v11-insurance-roadmap-thumb.png
- web/smoke/screenshots/agrifabric/agrifabric-v11-insurance-roadmap-full.png

These screenshots are useful review artifacts, but they should remain untracked until final thumbnail selection is made.

## Safe next production batch

Start with the static/web-led clips. These avoid Android emulator load, backend fixture mutation, and database writes.

| Video | Title | Source tab | Status | Why first |
| --- | --- | --- | --- | --- |
| V02 | Six pillars of AgriFabric | Product | Thumbnail/full screenshot already generated | Pure landing/SVG capture, low risk |
| V10 | Relationship graph and commercial analytics | Evidence graph | Thumbnail/full screenshot already generated | Claim-safe graph narrative |
| V08 | PIN, GPS, DigiPin, and land intelligence | Geography | Thumbnail/full screenshot already generated | Supports current geography story without touching NWDP job |
| V11 | Insurance and subsidy integrity foundation | Roadmap | Thumbnail/full screenshot already generated | Roadmap narrative with explicit boundaries |

Hold Android-heavy clips until the NWDP overlay job completes:

- V03 Farmer onboarding and parcel evidence
- V04 Offline sync survives the field
- V05 FPO project operations
- V06 Field event to targeted advisory
- V07 Broadcast lifecycle and analytics
- V09 Backend-owned localization and labels

## Guardrails

- Use deterministic local/demo data only.
- Do not show private production data.
- Do not run Android emulator capture while the full NWDP overlay worker is CPU-bound unless explicitly approved.
- Do not enable runtime lookup, live providers, risk scoring, or Android behavior changes as part of demo capture.
- Roadmap clips must remain clearly marked as roadmap, review-assistive, human-review, or approval-gated.
- Do not claim live weather/soil execution, live NDVI scoring, automated fraud detection, automated claim approval, or automated claim rejection.

## Validation commands

Run these from WSL.

```bash
cd ~/projects/farmint

git status --short --branch

find web/smoke/screenshots/agrifabric -maxdepth 1 -type f \
  -printf '%s %f\n' 2>/dev/null | sort -k2

find web/public/landing-assets -maxdepth 1 -type f \
  -printf '%f\n' 2>/dev/null | sort
```

If the frontend is already running on port 3000, run:

```bash
cd ~/projects/farmint/web

WEB_BASE_URL=http://localhost:3000 \
node smoke/agrifabric_landing_smoke.mjs
```

If the frontend is not running, start it in a separate terminal:

```bash
cd ~/projects/farmint/web

NEXT_PUBLIC_API_URL=http://localhost:8000 \
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 \
npm run dev -- --port 3000
```

## Static thumbnail refresh commands

Use these only if the existing screenshots need to be refreshed.

```bash
cd ~/projects/farmint/web

WEB_BASE_URL=http://localhost:3000 \
AGRIFABRIC_TAB=product \
AGRIFABRIC_VIEWPORT=thumbnail \
AGRIFABRIC_OUTPUT=agrifabric-v02-product-pillars-thumb.png \
node smoke/agrifabric_landing_capture_helper.mjs

WEB_BASE_URL=http://localhost:3000 \
AGRIFABRIC_TAB=graph \
AGRIFABRIC_VIEWPORT=thumbnail \
AGRIFABRIC_OUTPUT=agrifabric-v10-relationship-graph-thumb.png \
node smoke/agrifabric_landing_capture_helper.mjs

WEB_BASE_URL=http://localhost:3000 \
AGRIFABRIC_TAB=geography \
AGRIFABRIC_VIEWPORT=thumbnail \
AGRIFABRIC_OUTPUT=agrifabric-v08-geography-digipin-thumb.png \
node smoke/agrifabric_landing_capture_helper.mjs

WEB_BASE_URL=http://localhost:3000 \
AGRIFABRIC_TAB=roadmap \
AGRIFABRIC_VIEWPORT=thumbnail \
AGRIFABRIC_OUTPUT=agrifabric-v11-insurance-roadmap-thumb.png \
node smoke/agrifabric_landing_capture_helper.mjs
```

## Recommended immediate next step

Review the four existing static thumbnails and choose one of two paths:

1. If they are good enough, copy selected final thumbnails into a tracked asset directory such as web/public/demo-assets/.
2. If they need polish, adjust /agrifabric copy/layout first, then refresh the screenshots using the commands above.

After thumbnail selection, produce short narrated static clips for V02, V10, V08, and V11 using the script beats in docs/agrifabric-static-demo-capture-runbook.md.

## Demo thumbnail strip integration checkpoint - 2026-08-29

The first static demo thumbnail strip has been wired into the AgriFabric landing page using promoted public assets under web/public/demo-assets/.

Promoted thumbnails:

- web/public/demo-assets/agrifabric-v02-product-pillars-thumb.png
- web/public/demo-assets/agrifabric-v10-relationship-graph-thumb.png
- web/public/demo-assets/agrifabric-v08-geography-digipin-thumb.png
- web/public/demo-assets/agrifabric-v11-insurance-roadmap-thumb.png

The Operations tab now distinguishes static/web-ready demo cards from Android-heavy clips that should wait until the long NWDP overlay job is complete.

Validation command used from web/:

WEB_BASE_URL=http://localhost:3000 node smoke/agrifabric_landing_smoke.mjs

Validation result:

- status: PASSED
- landing loaded: true
- tab count: 6
- overview/product/graph/operations/geography/roadmap rendered: true
- claim boundary visible: true
- landing asset count: 10
- missing assets: none
- mobile rendered: true

Current next step: create static narrated clips for V02, V10, V08, and V11, or refresh thumbnails if visual polish is required.

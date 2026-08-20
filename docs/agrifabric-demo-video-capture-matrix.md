# AgriFabric demo video capture matrix

Status date: 2026-08-20

This matrix maps demo videos to the `/agrifabric` landing-page tabs. It should guide future Playwright/Maestro capture work so videos support the landing narrative instead of becoming disconnected screen recordings.

## Capture principles

- Keep clips short: 30-90 seconds each.
- Prefer one promise per clip.
- Use deterministic demo fixtures only.
- Use overlays for: Android, Admin web, Backend-owned, Verified MVP, Roadmap.
- Do not show roadmap modules as operational product.
- Do not claim live weather/soil, NDVI, insurance scoring, or automated claim decisions.
- Capture videos after the landing page visual style is stable enough to avoid rework.

## Video set

| ID | Landing tab | Working title | Capture mode | Purpose | Current evidence/source |
| --- | --- | --- | --- | --- | --- |
| V01 | Overview | AgriFabric in 60 seconds | Mixed + static assets | Introductory product story using hero, pillars, and short Android/admin flashes. | `/agrifabric`, `docs/assets/hero-composite.svg`, `docs/demo-script-pack.md` |
| V02 | Product | Six pillars of AgriFabric | Web/static only | Explain Capture, Coordinate, Sync, Advise, Govern, Extend using pillar icons and concise overlays. | `docs/assets/product-pillars.svg`, `/agrifabric` Product tab |
| V03 | Operations | Farmer onboarding and parcel evidence | Android only | Show field capture: farmer/profile/parcel/GPS/DigiPin-friendly evidence. | Android MVP flows, DigiPin/land summary docs |
| V04 | Operations | Offline sync survives the field | Android only | Show offline queue, replay, conflict recovery, and backlog draining. | Android Flows 52-64 sync/conflict suite |
| V05 | Product / Operations | FPO project operations | Web + Android | Show FPO/project enrollment, farmer search, project trace, crop-stage context. | FPO multi-village and project workflows |
| V06 | Operations / Roadmap | Field event to targeted advisory | Mixed | Show Android pest/media event becoming backend-owned targeted advisory with read/ack visibility. | Android Flow 49, field-event advisory loop fixture |
| V07 | Product / Operations | Broadcast lifecycle and analytics | Web first, optional Android | Show campaign, delivery/read/ack analytics, pending follow-up, targeting, terminal visibility. | Broadcast admin smokes + Android Flows 44-48 |
| V08 | Geography | PIN, GPS, DigiPin, and land intelligence | Web/static + Android | Explain PIN context vs parcel precision, backend-generated DigiPin, land-intelligence display. | Geography/DigiPin SVGs, Android Flow 39/51 |
| V09 | Product / Geography | Backend-owned localization and labels | Mixed | Show admin-published override and Android fallback/no raw JSON labels. | Android Flow 50/65, localization admin |
| V10 | Evidence graph | Relationship graph and commercial analytics | Static/web only | Explain farmers/agents/projects/parcels/advisories/audit as a graph; mark agent performance/risk as roadmap. | Relationship graph assets and concept docs |
| V11 | Roadmap | Insurance and subsidy integrity foundation | Static/web only | Explain evidence bundle and human-review roadmap without operational scoring claims. | Insurance roadmap SVG and `docs/agrifabric-insurance-fraud-risk-scoring.md` |

## Recommended first capture batch

Start with these because they align tightly with the current landing tabs and do not require complex live coordination:

1. V02 — Six pillars of AgriFabric
2. V08 — PIN, GPS, DigiPin, and land intelligence
3. V10 — Relationship graph and commercial analytics
4. V11 — Insurance and subsidy integrity foundation

These can be produced mostly from the landing page and SVG assets before recording fragile Android flows.

## Recommended second capture batch

Then capture operational proof clips:

1. V03 — Farmer onboarding and parcel evidence
2. V04 — Offline sync survives the field
3. V05 — FPO project operations
4. V06 — Field event to targeted advisory
5. V07 — Broadcast lifecycle and analytics
6. V09 — Backend-owned localization and labels

## Capture mode definitions

Web/static only:
Use `/agrifabric`, SVGs, and admin web UI screens. No Android emulator required.

Android only:
Use Maestro/emulator capture. Add overlays later.

Mixed:
Capture Android and web/admin clips separately, then stitch in editing.

## Landing page integration

The `/agrifabric` Demo/Operations tab should eventually replace placeholder demo slots with:

- thumbnail;
- title;
- capture mode badge;
- 1-line promise;
- claim boundary where relevant;
- link or modal for video playback.

## Thumbnail requirements

Each thumbnail should include:

- one short title;
- one visual anchor;
- one badge: Android / Admin web / Mixed / Roadmap;
- no small unreadable text;
- consistent dark AgriFabric palette.

## Claim boundary reminders

Roadmap videos must use phrases like:

- “foundation for”
- “future review-assistive module”
- “human review queue”
- “approval-gated”
- “not automated claim decisioning”

Avoid:

- “detects fraud today”
- “approves claims”
- “rejects claims”
- “live NDVI scoring”
- “real-time insurance risk engine”

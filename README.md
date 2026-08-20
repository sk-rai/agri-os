# Agri-OS / AgriFabric

Agri-OS is an offline-first agricultural operations platform. AgriFabric is the field evidence fabric inside it: farmer and parcel capture, FPO/project workflows, crop activity trails, field events, targeted advisories, localization, geography/DigiPin evidence, sync resilience, and audit-backed admin operations.

## Repository map

- `backend/` — FastAPI backend, database models, APIs, seed/verification scripts.
- `web/` — Next.js admin web app plus the public AgriFabric landing-page draft at `/agrifabric`.
- `app/` — Android client code and Maestro flow coverage.
- `docs/` — architecture notes, readiness summaries, demo scripts, visual specs, and runbooks.
- `web/smoke/` — Playwright smoke and capture helpers.

## Local backend

From repo root:

- `cd backend`
- `source ../venv/bin/activate`
- `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`

Backend API base:

- `http://localhost:8000`

## Local web app

From repo root:

- `cd web`
- `NEXT_PUBLIC_API_URL=http://localhost:8000 NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev -- --port 3000`

Open:

- Admin app: `http://localhost:3000/login`
- AgriFabric landing draft: `http://localhost:3000/agrifabric`

Note: `/` intentionally still redirects to `/login`.

## Useful checks

From repo root:

- Landing smoke: `WEB_BASE_URL=http://localhost:3000 node web/smoke/agrifabric_landing_smoke.mjs`
- Landing capture helper: `WEB_BASE_URL=http://localhost:3000 AGRIFABRIC_TAB=product AGRIFABRIC_VIEWPORT=thumbnail node web/smoke/agrifabric_landing_capture_helper.mjs`
- Web production build: `cd web && npm run build`

## Key AgriFabric docs

- `docs/android-mvp-readiness-summary.md`
- `docs/demo-script-pack.md`
- `docs/landing-page-content-brief.md`
- `docs/landing-page-wireframe.md`
- `docs/landing-page-implementation-backlog.md`
- `docs/demo-asset-inventory.md`
- `docs/agrifabric-demo-video-capture-matrix.md`
- `docs/agrifabric-static-demo-capture-runbook.md`

## Claim boundaries

The deterministic Android/admin workflows are demo-ready with local seeded data and committed smoke coverage.

Do not claim these as live/operational until separately implemented, verified, and governed:

- live weather/soil provider execution;
- operational insurance fraud scoring or automated claim decisions;
- live NDVI/satellite scoring;
- verified product-label compliance;
- native regional translation completeness;
- global/non-India geography rollout.

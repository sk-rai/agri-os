# Agri-OS: Agricultural Operations Intelligence Platform

Offline-first, workflow-driven agricultural operations platform for India.

## Tech Stack
- Backend: FastAPI + PostgreSQL + PostGIS
- Mobile: Kotlin (Android native)
- Web: TypeScript (Next.js)
- Deploy: Render.com

## Quick Start
cd backend
source ../venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload

## AgriFabric landing draft

A public, claim-bounded AgriFabric landing-page draft is available in the web app at `/agrifabric`.

Local URL: http://localhost:3000/agrifabric

The current root route still redirects to `/login`, so existing admin behavior is unchanged.

Related planning and proof docs:

- `docs/landing-page-content-brief.md`
- `docs/landing-page-wireframe.md`
- `docs/landing-page-implementation-backlog.md`
- `docs/agrifabric-demo-video-capture-matrix.md`
- `web/smoke/agrifabric_landing_smoke.mjs`

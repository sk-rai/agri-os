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

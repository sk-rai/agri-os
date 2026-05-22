"""Agri-OS: Agricultural Operations Intelligence Platform.

FastAPI application entry point.
Modular monolith with in-process events (ADR-001).
Tenant-scoped via X-Tenant-ID header (ADR-002).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.middleware import TenantMiddleware
from app.modules.master_data.api import master_data_router
from app.modules.auth import auth_router
from app.modules.sync import sync_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Offline-first agricultural operations intelligence platform",
    docs_url="/docs",
    redoc_url="/redoc",
)

# --- Middleware ---
app.add_middleware(TenantMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Routers ---
app.include_router(master_data_router)
app.include_router(auth_router)
app.include_router(sync_router)


# --- Health Check ---
@app.get("/health", tags=["system"])
def health_check():
    """System health check endpoint."""
    return {
        "status": "ok",
        "version": settings.VERSION,
        "service": settings.PROJECT_NAME,
    }

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
from app.modules.auth.api import router as auth_router
from app.modules.auth.admin_api import router as admin_user_router
from app.modules.sync import sync_router, dashboard_router, conflicts_router
from app.modules.farmer import farmer_router
from app.modules.farmer.soil_profile import router as soil_profile_router
from app.modules.workflow import workflow_router
from app.modules.workflow.forms import router as forms_router
from app.modules.workflow.config import router as workflow_config_router
from app.modules.workflow.catalog_api import router as workflow_catalog_router
from app.modules.workflow.reports_api import router as workflow_reports_router
from app.modules.master_data.api.crop_catalog import router as crop_catalog_router
from app.modules.master_data.api.crop_catalog_csv import router as crop_catalog_csv_router
from app.modules.master_data.api.input_catalog import router as input_catalog_router
from app.modules.master_data.api.input_catalog_csv import router as input_catalog_csv_router
from app.modules.master_data.api.product_catalog import router as product_catalog_router
from app.modules.app_config import router as app_config_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Offline-first agricultural operations intelligence platform",
    docs_url="/docs",
    redoc_url="/redoc",
)

# --- Middleware ---
# Order: last-added = outermost. CORS must be outermost for preflight OPTIONS.
app.add_middleware(TenantMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Next.js dev
        "http://127.0.0.1:3000",
        "http://localhost:8000",  # Swagger UI
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Dev-OTP"],
)

# --- Routers ---
app.include_router(master_data_router)
app.include_router(auth_router)
app.include_router(admin_user_router)
app.include_router(sync_router)
app.include_router(dashboard_router)
app.include_router(conflicts_router)
app.include_router(farmer_router)
app.include_router(soil_profile_router)
app.include_router(workflow_router)
app.include_router(forms_router)
app.include_router(workflow_config_router)
app.include_router(workflow_catalog_router)
app.include_router(workflow_reports_router)
app.include_router(crop_catalog_router)
app.include_router(crop_catalog_csv_router)
app.include_router(input_catalog_router)
app.include_router(input_catalog_csv_router)
app.include_router(product_catalog_router)
app.include_router(app_config_router)


# --- Health Check ---
@app.get("/health", tags=["system"])
def health_check():
    """System health check endpoint."""
    return {
        "status": "ok",
        "version": settings.VERSION,
        "service": settings.PROJECT_NAME,
    }

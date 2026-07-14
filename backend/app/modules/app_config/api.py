"""Runtime app/bootstrap configuration API.

This endpoint is intentionally read-only and additive. It lets Android and web
discover branding, feature flags, locale/unit defaults, and currently available
form versions without hardcoding client/project behavior into the app.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Optional
import uuid

from fastapi import APIRouter, Header, HTTPException, Query
from sqlalchemy.orm import Session
from fastapi import Depends

from app.core.config import settings
from app.core.database import get_db
from app.modules.farmer.models import Project, Tenant
from app.modules.workflow.forms import FORM_REGISTRY


router = APIRouter(prefix="/api/v1/app-config", tags=["app-config"])


PROFILE_FORM_FLAG_MAP = {
    "farmer_registration": "backend_driven_farmer_forms",
    "parcel_registration": "backend_driven_parcel_forms",
    "soil_profile": "backend_driven_soil_forms",
}


DEFAULT_BOOTSTRAP_CONFIG = {
    "branding": {
        "app_name": "Agri-OS",
        "logo_url": None,
        "primary_color": "#2563EB",
        "secondary_color": "#16A34A",
        "accent_color": "#F59E0B",
        "support_email": None,
        "support_phone": None,
    },
    "localization": {
        "default_language": "en",
        "supported_languages": ["en", "hi"],
        "country_code": "IN",
        "timezone": "Asia/Kolkata",
    },
    "units": {
        "area_units": ["ACRE", "HECTARE", "BIGHA", "BISWA", "KATHA", "GUNTHA"],
        "default_area_unit": "BIGHA",
        "currency": "INR",
        "measurement_system": "METRIC",
    },
    "enabled_modules": [
        "FARMER_PROFILE",
        "LAND_PARCELS",
        "SOIL_PROFILE",
        "CROP_CYCLES",
        "ACTIVITY_LOGGING",
        "GPS_GEOMETRY",
    ],
    "feature_flags": {
        "backend_driven_farmer_forms": False,
        "backend_driven_parcel_forms": False,
        "backend_driven_soil_forms": False,
        "white_label_runtime_branding": True,
        "project_memberships": False,
        "media_attachments": False,
        "broadcast_advisories": False,
        "farmer_queries": False,
        "field_event_reporting": False,
        "economics_summary": False,
    },
    "self_service": {
        "allow_direct_farmer_registration": True,
        "default_tenant_id": "default",
        "requires_project_invite": False,
    },
}


def _deep_merge(base: dict, override: Optional[dict]) -> dict:
    """Merge JSON config dictionaries without mutating either side."""
    result = deepcopy(base)
    if not isinstance(override, dict):
        return result
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _form_versions() -> list[dict]:
    return [
        {
            "form_id": form_id,
            "version": schema.version,
            "title": schema.title,
            "endpoint": f"/api/v1/forms/{form_id}",
        }
        for form_id, schema in sorted(FORM_REGISTRY.items())
    ]


def _profile_form_contracts(feature_flags: dict) -> dict:
    contracts = {}
    for form_id, flag_name in PROFILE_FORM_FLAG_MAP.items():
        schema = FORM_REGISTRY.get(form_id)
        if not schema:
            continue
        contracts[form_id] = {
            "form_id": form_id,
            "version": schema.version,
            "endpoint": f"/api/v1/forms/{form_id}",
            "enabled": bool(feature_flags.get(flag_name)),
            "feature_flag": flag_name,
            "title": schema.title,
        }
    return contracts


@router.get("/bootstrap")
def get_app_bootstrap_config(
    project_id: Optional[uuid.UUID] = Query(None),
    db: Session = Depends(get_db),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
):
    """Return runtime app configuration for Android/web clients.

    This endpoint is safe to call before or after login. If no tenant header is
    provided, the default self-service tenant context is returned. Tenant and
    project JSON config can override the stable defaults using matching keys.
    """
    tenant_id = x_tenant_id or DEFAULT_BOOTSTRAP_CONFIG["self_service"]["default_tenant_id"]
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.is_active == True).first()

    project = None
    if project_id:
        project = (
            db.query(Project)
            .filter(Project.id == project_id, Project.tenant_id == tenant_id, Project.is_active == True)
            .first()
        )
        if not project:
            raise HTTPException(404, "Project not found")

    config = _deep_merge(DEFAULT_BOOTSTRAP_CONFIG, tenant.config if tenant else None)
    if project:
        config = _deep_merge(config, project.config)

    return {
        "schema_version": "app_bootstrap.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "service": {
            "name": settings.PROJECT_NAME,
            "version": settings.VERSION,
        },
        "tenant": {
            "id": tenant_id,
            "exists": tenant is not None,
            "name": tenant.name if tenant else "Default",
            "type": tenant.type if tenant else "SELF_SERVICE",
        },
        "project": None if not project else {
            "id": str(project.id),
            "name": project.name,
            "status": project.status,
            "start_date": project.start_date.isoformat() if project.start_date else None,
            "end_date": project.end_date.isoformat() if project.end_date else None,
            "crop_scope": project.crop_scope or [],
            "geography_scope": project.geography_scope or {},
        },
        "branding": config["branding"],
        "localization": config["localization"],
        "units": config["units"],
        "enabled_modules": config["enabled_modules"],
        "feature_flags": config["feature_flags"],
        "self_service": config["self_service"],
        "forms": _form_versions(),
        "profile_forms": _profile_form_contracts(config["feature_flags"]),
        "contracts": {
            "profile_hydration": {
                "schema_version": "profile_hydration.v1",
                "by_mobile_endpoint": "/api/v1/farmers/by-mobile/{mobile}",
                "me_endpoint": "/api/v1/farmers/me/profile",
            },
            "parcel_geometry": {
                "endpoint": "/api/v1/parcels/{parcel_id}/geometry",
                "pin_drop": "PIN_DROP returns centroid_lat/centroid_lng and no GeoJSON for MVP.",
                "gps_walk": "GPS_WALK returns Polygon GeoJSON, centroid_lat/centroid_lng, and computed_area_hectares.",
            },
        },
    }

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
from pydantic import BaseModel, Field

from app.core.admin_auth import AdminPermission, AdminPrincipal, require_admin_permission
from app.core.config import settings
from app.core.database import get_db
from app.modules.farmer.models import Project, ProjectAppConfigAuditEvent, Tenant
from app.modules.workflow.forms import FORM_REGISTRY, PROFILE_OPTION_REGISTRY


router = APIRouter(prefix="/api/v1/app-config", tags=["app-config"])


PROFILE_FORM_FLAG_MAP = {
    "farmer_registration": "backend_driven_farmer_forms",
    "parcel_registration": "backend_driven_parcel_forms",
    "soil_profile": "backend_driven_soil_forms",
}




class AppConfigPatchRequest(BaseModel):
    config_patch: dict = Field(default_factory=dict)
    reason: str = Field(..., min_length=3, max_length=500)

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


def _validate_profile_option_overrides(config_patch: dict) -> list[dict]:
    """Validate tenant/project profile option override shape before storing JSON config."""
    errors: list[dict] = []
    profile_options = config_patch.get("profile_options") if isinstance(config_patch, dict) else None
    if profile_options is None:
        return errors
    if not isinstance(profile_options, dict):
        return [{"code": "PROFILE_OPTIONS_NOT_OBJECT", "path": "profile_options", "message": "profile_options must be an object."}]

    overrides = profile_options.get("overrides")
    if overrides is None:
        return errors
    if not isinstance(overrides, dict):
        return [{"code": "PROFILE_OPTION_OVERRIDES_NOT_OBJECT", "path": "profile_options.overrides", "message": "profile_options.overrides must be an object."}]

    for option_set, payload in sorted(overrides.items()):
        path = f"profile_options.overrides.{option_set}"
        if option_set not in PROFILE_OPTION_REGISTRY:
            errors.append({"code": "UNKNOWN_PROFILE_OPTION_SET", "path": path, "message": f"Unknown profile option set {option_set}."})
            continue
        if not isinstance(payload, dict):
            errors.append({"code": "PROFILE_OPTION_SET_NOT_OBJECT", "path": path, "message": "Option set override must be an object."})
            continue
        if "title" in payload and (not isinstance(payload["title"], dict) or not payload["title"].get("en")):
            errors.append({"code": "PROFILE_OPTION_TITLE_INVALID", "path": f"{path}.title", "message": "Option set title must include an English label."})
        if "version" in payload and not str(payload["version"]).strip():
            errors.append({"code": "PROFILE_OPTION_VERSION_INVALID", "path": f"{path}.version", "message": "Option set version cannot be blank."})
        options = payload.get("options")
        if not isinstance(options, list) or not options:
            errors.append({"code": "PROFILE_OPTION_OPTIONS_EMPTY", "path": f"{path}.options", "message": "Option set override must include at least one option."})
            continue
        seen_values: set[str] = set()
        for index, option in enumerate(options):
            option_path = f"{path}.options[{index}]"
            if not isinstance(option, dict):
                errors.append({"code": "PROFILE_OPTION_NOT_OBJECT", "path": option_path, "message": "Each option must be an object."})
                continue
            value = str(option.get("value") or "").strip()
            label = option.get("label")
            if not value:
                errors.append({"code": "PROFILE_OPTION_VALUE_REQUIRED", "path": f"{option_path}.value", "message": "Option value is required."})
            elif value in seen_values:
                errors.append({"code": "PROFILE_OPTION_VALUE_DUPLICATE", "path": f"{option_path}.value", "message": f"Duplicate option value {value}."})
            else:
                seen_values.add(value)
            if not isinstance(label, dict) or not str(label.get("en") or "").strip():
                errors.append({"code": "PROFILE_OPTION_LABEL_EN_REQUIRED", "path": f"{option_path}.label", "message": "Option label must include an English fallback."})
    return errors


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


def _section_sources(tenant_config: Optional[dict], project_config: Optional[dict]) -> dict:
    sources = {}
    all_sections = set(DEFAULT_BOOTSTRAP_CONFIG.keys())
    if isinstance(tenant_config, dict):
        all_sections.update(tenant_config.keys())
    if isinstance(project_config, dict):
        all_sections.update(project_config.keys())
    for section in sorted(all_sections):
        if isinstance(project_config, dict) and section in project_config:
            sources[section] = "project"
        elif isinstance(tenant_config, dict) and section in tenant_config:
            sources[section] = "tenant"
        elif section in DEFAULT_BOOTSTRAP_CONFIG:
            sources[section] = "default"
        else:
            sources[section] = "unknown"
    return sources


def _project_payload(project: Project) -> dict:
    return {
        "id": str(project.id),
        "name": project.name,
        "status": project.status,
        "start_date": project.start_date.isoformat() if project.start_date else None,
        "end_date": project.end_date.isoformat() if project.end_date else None,
        "crop_scope": project.crop_scope or [],
        "geography_scope": project.geography_scope or {},
    }


def _app_config_audit_payload(event: ProjectAppConfigAuditEvent) -> dict:
    return {
        "id": str(event.id),
        "tenant_id": event.tenant_id,
        "project_id": str(event.project_id),
        "actor_id": str(event.actor_id),
        "action": event.action,
        "patched_sections": event.patched_sections or [],
        "before_config": event.before_config or {},
        "after_config": event.after_config or {},
        "config_patch": event.config_patch or {},
        "reason": event.reason,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


def _effective_config_payload(tenant: Tenant, project: Project) -> dict:
    tenant_config = tenant.config or {}
    project_config = project.config or {}
    effective_config = _deep_merge(DEFAULT_BOOTSTRAP_CONFIG, tenant_config)
    effective_config = _deep_merge(effective_config, project_config)
    return {
        "schema_version": "effective_app_config.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tenant": {
            "id": tenant.id,
            "name": tenant.name,
            "type": tenant.type,
        },
        "project": _project_payload(project),
        "layers": {
            "default": DEFAULT_BOOTSTRAP_CONFIG,
            "tenant": tenant_config,
            "project": project_config,
        },
        "effective_config": effective_config,
        "section_sources": _section_sources(tenant_config, project_config),
        "profile_forms": _profile_form_contracts(effective_config["feature_flags"]),
        "forms": _form_versions(),
    }


def _validate_profile_forms(feature_flags: dict) -> dict:
    errors: list[dict] = []
    warnings: list[dict] = []
    form_reports: list[dict] = []
    required_form_ids = set(PROFILE_FORM_FLAG_MAP.keys())

    for form_id in sorted(required_form_ids):
        schema = FORM_REGISTRY.get(form_id)
        flag_name = PROFILE_FORM_FLAG_MAP[form_id]
        enabled = bool(feature_flags.get(flag_name))
        if not schema:
            errors.append({
                "form_id": form_id,
                "field_id": None,
                "code": "MISSING_FORM",
                "message": f"Required profile form {form_id} is missing from FORM_REGISTRY.",
            })
            form_reports.append({
                "form_id": form_id,
                "enabled": enabled,
                "ready": False,
                "field_count": 0,
                "required_field_count": 0,
                "gps_field_count": 0,
                "error_count": 1,
                "warning_count": 0,
            })
            continue

        field_ids = {field.id for field in schema.fields}
        option_values_by_field = {
            field.id: {option.value for option in field.options or []}
            for field in schema.fields
            if field.options
        }
        form_error_start = len(errors)
        form_warning_start = len(warnings)

        if not schema.submit_endpoint:
            errors.append({"form_id": form_id, "field_id": None, "code": "MISSING_SUBMIT_ENDPOINT", "message": "Form submit_endpoint is required."})
        if schema.submit_method not in {"POST", "PUT", "PATCH"}:
            errors.append({"form_id": form_id, "field_id": None, "code": "UNSUPPORTED_SUBMIT_METHOD", "message": f"Unsupported submit_method {schema.submit_method}."})
        if not schema.fields:
            errors.append({"form_id": form_id, "field_id": None, "code": "NO_FIELDS", "message": "Form must contain at least one field."})

        for field in schema.fields:
            if not field.id:
                errors.append({"form_id": form_id, "field_id": None, "code": "MISSING_FIELD_ID", "message": "Field id is required."})
            if not field.type:
                errors.append({"form_id": form_id, "field_id": field.id, "code": "MISSING_FIELD_TYPE", "message": "Field type is required."})
            if not field.label or not field.label.get("en"):
                warnings.append({"form_id": form_id, "field_id": field.id, "code": "MISSING_EN_LABEL", "message": "Field should include an English label fallback."})
            if field.depends_on:
                if field.depends_on not in field_ids:
                    errors.append({"form_id": form_id, "field_id": field.id, "code": "UNKNOWN_DEPENDENCY", "message": f"depends_on references unknown field {field.depends_on}."})
                elif field.depends_on_value and field.depends_on in option_values_by_field and field.depends_on_value not in option_values_by_field[field.depends_on]:
                    errors.append({"form_id": form_id, "field_id": field.id, "code": "INVALID_DEPENDS_ON_VALUE", "message": f"depends_on_value {field.depends_on_value} is not an option for {field.depends_on}."})
            if field.source and field.source.startswith("profile_options."):
                option_set = field.source.split(".", 1)[1]
                if option_set not in PROFILE_OPTION_REGISTRY:
                    errors.append({"form_id": form_id, "field_id": field.id, "code": "UNKNOWN_PROFILE_OPTION_SET", "message": f"source references unknown profile option set {option_set}."})
            if field.type == "GPS_POINT":
                if field.output_format not in {"centroid_lat_lng", "geojson_point", "lat_lng"}:
                    warnings.append({"form_id": form_id, "field_id": field.id, "code": "GPS_POINT_OUTPUT_FORMAT", "message": "GPS_POINT should declare a centroid/point output_format."})
                if not field.capture_modes:
                    warnings.append({"form_id": form_id, "field_id": field.id, "code": "GPS_CAPTURE_MODES_MISSING", "message": "GPS_POINT should declare capture_modes."})
            if field.type == "GPS_POLYGON":
                if field.output_format != "geojson_polygon":
                    errors.append({"form_id": form_id, "field_id": field.id, "code": "GPS_POLYGON_OUTPUT_FORMAT", "message": "GPS_POLYGON must use geojson_polygon output_format."})
                if not field.min_points or field.min_points < 3:
                    errors.append({"form_id": form_id, "field_id": field.id, "code": "GPS_POLYGON_MIN_POINTS", "message": "GPS_POLYGON must require at least 3 points."})
                if not field.capture_modes:
                    warnings.append({"form_id": form_id, "field_id": field.id, "code": "GPS_CAPTURE_MODES_MISSING", "message": "GPS_POLYGON should declare capture_modes."})

        form_error_count = len(errors) - form_error_start
        form_warning_count = len(warnings) - form_warning_start
        form_reports.append({
            "form_id": form_id,
            "title": schema.title,
            "version": schema.version,
            "enabled": enabled,
            "ready": form_error_count == 0,
            "field_count": len(schema.fields),
            "required_field_count": sum(1 for field in schema.fields if field.required),
            "gps_field_count": sum(1 for field in schema.fields if field.type.startswith("GPS")),
            "error_count": form_error_count,
            "warning_count": form_warning_count,
        })

    enabled_count = sum(1 for form in form_reports if form.get("enabled"))
    return {
        "ready": len(errors) == 0,
        "summary": {
            "form_count": len(form_reports),
            "enabled_count": enabled_count,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "field_count": sum(form.get("field_count", 0) for form in form_reports),
            "gps_field_count": sum(form.get("gps_field_count", 0) for form in form_reports),
        },
        "forms": form_reports,
        "errors": errors,
        "warnings": warnings,
    }


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
        "project": None if not project else _project_payload(project),
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




@router.get("/profile-forms/validation")
def validate_profile_form_contracts(
    project_id: Optional[uuid.UUID] = Query(None),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    _principal=Depends(require_admin_permission(AdminPermission.VIEW)),
):
    """Validate effective backend-driven profile form contracts for Android rendering."""
    tenant = db.query(Tenant).filter(Tenant.id == x_tenant_id, Tenant.is_active == True).first()
    if not tenant:
        raise HTTPException(404, "Tenant not found")

    project = None
    if project_id:
        project = (
            db.query(Project)
            .filter(Project.id == project_id, Project.tenant_id == x_tenant_id, Project.is_active == True)
            .first()
        )
        if not project:
            raise HTTPException(404, "Project not found")

    config = _deep_merge(DEFAULT_BOOTSTRAP_CONFIG, tenant.config or {})
    if project:
        config = _deep_merge(config, project.config or {})

    validation = _validate_profile_forms(config.get("feature_flags", {}))
    return {
        "schema_version": "profile_form_validation.v1",
        "tenant": {"id": tenant.id, "name": tenant.name, "type": tenant.type},
        "project": None if not project else _project_payload(project),
        "filters": {"project_id": str(project_id) if project_id else None},
        "ready": validation["ready"],
        "summary": validation["summary"],
        "forms": validation["forms"],
        "errors": validation["errors"],
        "warnings": validation["warnings"],
    }


@router.get("/projects/{project_id}/effective-app-config")
def get_project_effective_app_config(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    _principal=Depends(require_admin_permission(AdminPermission.VIEW, project_scoped=True)),
):
    """Inspect effective app-config after default + tenant + project merge."""
    tenant = db.query(Tenant).filter(Tenant.id == x_tenant_id, Tenant.is_active == True).first()
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.tenant_id == x_tenant_id, Project.is_active == True)
        .first()
    )
    if not project:
        raise HTTPException(404, "Project not found")

    return _effective_config_payload(tenant, project)


@router.patch("/projects/{project_id}/config")
def update_project_app_config(
    project_id: uuid.UUID,
    request: AppConfigPatchRequest,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT, project_scoped=True)),
):
    """Patch project-level runtime app config and return effective config."""
    tenant = db.query(Tenant).filter(Tenant.id == x_tenant_id, Tenant.is_active == True).first()
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.tenant_id == x_tenant_id, Project.is_active == True)
        .first()
    )
    if not project:
        raise HTTPException(404, "Project not found")
    if not isinstance(request.config_patch, dict) or not request.config_patch:
        raise HTTPException(400, "config_patch is required")
    option_override_errors = _validate_profile_option_overrides(request.config_patch)
    if option_override_errors:
        raise HTTPException(status_code=400, detail={"error": "INVALID_PROFILE_OPTION_OVERRIDES", "errors": option_override_errors})

    current_config = deepcopy(project.config or {})
    updated_config = _deep_merge(current_config, request.config_patch)
    project.config = updated_config
    project.updated_at = datetime.now(timezone.utc)
    audit_event = ProjectAppConfigAuditEvent(
        id=uuid.uuid4(),
        tenant_id=x_tenant_id,
        project_id=project.id,
        actor_id=principal.user_id,
        action="UPDATE_PROJECT_APP_CONFIG",
        patched_sections=sorted(request.config_patch.keys()),
        before_config=current_config,
        after_config=updated_config,
        config_patch=request.config_patch,
        reason=request.reason,
        created_at=datetime.now(timezone.utc),
    )
    db.add(project)
    db.add(audit_event)
    db.commit()
    db.refresh(project)

    payload = _effective_config_payload(tenant, project)
    payload["update"] = {
        "reason": request.reason,
        "patched_sections": sorted(request.config_patch.keys()),
        "audit_event": _app_config_audit_payload(audit_event),
    }
    return payload


@router.get("/projects/{project_id}/config/audit")
def list_project_app_config_audit(
    project_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    _principal=Depends(require_admin_permission(AdminPermission.VIEW, project_scoped=True)),
):
    """Return recent project runtime app-config audit events."""
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.tenant_id == x_tenant_id, Project.is_active == True)
        .first()
    )
    if not project:
        raise HTTPException(404, "Project not found")
    events = (
        db.query(ProjectAppConfigAuditEvent)
        .filter(
            ProjectAppConfigAuditEvent.tenant_id == x_tenant_id,
            ProjectAppConfigAuditEvent.project_id == project_id,
        )
        .order_by(ProjectAppConfigAuditEvent.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "schema_version": "project_app_config_audit.v1",
        "tenant_id": x_tenant_id,
        "project": _project_payload(project),
        "count": len(events),
        "events": [_app_config_audit_payload(event) for event in events],
    }

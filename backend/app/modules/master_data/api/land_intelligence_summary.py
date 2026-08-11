"""Land-intelligence summary API for Android and admin override management."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.admin_auth import AdminPermission, AdminPrincipal, require_admin_permission
from app.core.database import get_db
from app.modules.farmer.models import Project, Tenant
from app.modules.master_data.models import LandIntelligenceSummaryOverride


router = APIRouter(prefix="/api/v1", tags=["land-intelligence-summary"])

PUBLISHED_STATUSES = {"PUBLISHED", "APPROVED", "ACTIVE"}
SCOPE_TYPES = {"PIN", "DISTRICT", "STATE"}


class LandIntelligenceSummaryOverrideUpsert(BaseModel):
    tenant_id: Optional[str] = None
    project_id: Optional[uuid.UUID] = None
    scope_type: str = Field(..., min_length=2, max_length=40)
    scope_code: str = Field(..., min_length=1, max_length=120)
    language_code: str = Field("en", min_length=2, max_length=12)
    summary_payload: dict = Field(default_factory=dict)
    review_status: str = Field("PUBLISHED", min_length=2, max_length=40)
    review_notes: Optional[str] = None
    reason: Optional[str] = None


class LandIntelligenceSummaryOverrideDeactivate(BaseModel):
    reason: Optional[str] = None


def _now():
    return datetime.now(timezone.utc)


def _normalize_language(value: str) -> str:
    return str(value or "en").strip().lower()


def _normalize_scope(scope_type: str, scope_code: str) -> tuple[str, str]:
    normalized_type = str(scope_type or "").strip().upper()
    normalized_code = str(scope_code or "").strip()
    if normalized_type not in SCOPE_TYPES:
        raise HTTPException(400, {"error": "INVALID_SCOPE_TYPE", "allowed": sorted(SCOPE_TYPES)})
    if not normalized_code:
        raise HTTPException(400, {"error": "SCOPE_CODE_REQUIRED"})
    return normalized_type, normalized_code


def _scope_from_query(
    pin_code: Optional[str],
    district_lgd_code: Optional[str],
    state_lgd_code: Optional[str],
    scope_type: Optional[str] = None,
    scope_code: Optional[str] = None,
) -> tuple[str, str]:
    if pin_code:
        return "PIN", str(pin_code).strip()
    if district_lgd_code:
        return "DISTRICT", str(district_lgd_code).strip()
    if state_lgd_code:
        return "STATE", str(state_lgd_code).strip()
    if scope_type and scope_code:
        return _normalize_scope(scope_type, scope_code)
    raise HTTPException(400, "Provide pin_code, district_lgd_code, state_lgd_code, or scope_type/scope_code")


def _default_summary_payload(
    *,
    scope_type: str,
    scope_code: str,
    language_code: str,
    season_code: Optional[str],
    crop_code: Optional[str],
) -> dict:
    season = str(season_code or "current season").upper()
    crop = str(crop_code or "").upper() or None
    scope_label = f"{scope_type} {scope_code}"

    main_crops = [
        {"crop_code": "RICE", "label": {"en": "Rice"}, "reason": {"en": "Common irrigated-season option where water is available."}},
        {"crop_code": "WHEAT", "label": {"en": "Wheat"}, "reason": {"en": "Common Rabi option where winter conditions and irrigation support it."}},
    ]
    alternate_crops = [
        {"crop_code": "MAIZE", "label": {"en": "Maize"}, "reason": {"en": "Useful alternate where water or crop-duration risk needs diversification."}},
        {"crop_code": "PULSES", "label": {"en": "Pulses"}, "reason": {"en": "Lower-input alternate that can support soil health and risk spread."}},
    ]
    if crop:
        main_crops = [row for row in main_crops if row.get("crop_code") != crop]
        main_crops.insert(0, {"crop_code": crop, "label": {"en": crop.replace("_", " ").title()}, "reason": {"en": "Selected crop for this land-intelligence check."}})

    return {
        "title": {"en": "Land intelligence summary"},
        "subtitle": {"en": f"Informational guidance for {scope_label} during {season}."},
        "cards": [
            {
                "key": "region",
                "title": {"en": "Region"},
                "value": {"en": scope_label},
                "detail": {"en": "Backend-owned geography and climate mappings are used as guidance, not as a farmer-entry blocker."},
            },
            {
                "key": "season_weather",
                "title": {"en": "Season & weather"},
                "value": {"en": season},
                "detail": {"en": "Use local rainfall, temperature, and season timing as advisory context. Live weather remains backend/provider gated."},
            },
            {
                "key": "soil_water",
                "title": {"en": "Soil & water"},
                "value": {"en": "Confirm in field"},
                "detail": {"en": "Ask soil texture, drainage, irrigation source, and recent soil-test values where available."},
            },
            {
                "key": "crop_options",
                "title": {"en": "Crop options"},
                "value": {"en": "Main and alternate crops"},
                "detail": {"en": "Use this as a simple starting point; crop-stage recommendations still come from workflow templates."},
            },
        ],
        "main_crops": main_crops,
        "alternate_crops": alternate_crops,
        "caveats": [
            {"en": "This is informational guidance only and should not block farmer onboarding."},
            {"en": "Farmer observation, soil-test data, and agronomist review should override generic regional guidance."},
        ],
        "version": "v1",
        "language_code": language_code,
    }


def _override_payload(row: LandIntelligenceSummaryOverride) -> dict:
    return {
        "id": str(row.id),
        "tenant_id": row.tenant_id,
        "project_id": str(row.project_id) if row.project_id else None,
        "scope_type": row.scope_type,
        "scope_code": row.scope_code,
        "language_code": row.language_code,
        "summary_payload": row.summary_payload or {},
        "review_status": row.review_status,
        "review_notes": row.review_notes,
        "created_by": str(row.created_by) if row.created_by else None,
        "updated_by": str(row.updated_by) if row.updated_by else None,
        "published_at": row.published_at.isoformat() if row.published_at else None,
        "is_active": row.is_active,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _effective_override(
    db: Session,
    *,
    tenant_id: str,
    project_id: Optional[uuid.UUID],
    scope_type: str,
    scope_code: str,
    language_code: str,
) -> Optional[LandIntelligenceSummaryOverride]:
    query = db.query(LandIntelligenceSummaryOverride).filter(
        LandIntelligenceSummaryOverride.tenant_id == tenant_id,
        LandIntelligenceSummaryOverride.scope_type == scope_type,
        LandIntelligenceSummaryOverride.scope_code == scope_code,
        LandIntelligenceSummaryOverride.language_code == language_code,
        LandIntelligenceSummaryOverride.is_active.is_(True),
        LandIntelligenceSummaryOverride.review_status.in_(sorted(PUBLISHED_STATUSES)),
    )
    if project_id:
        query = query.filter(or_(LandIntelligenceSummaryOverride.project_id == project_id, LandIntelligenceSummaryOverride.project_id.is_(None)))
        return query.order_by(LandIntelligenceSummaryOverride.project_id.is_(None), LandIntelligenceSummaryOverride.updated_at.desc()).first()
    return query.filter(LandIntelligenceSummaryOverride.project_id.is_(None)).order_by(LandIntelligenceSummaryOverride.updated_at.desc()).first()


def _summary_response(
    db: Session,
    *,
    tenant_id: str,
    project_id: Optional[uuid.UUID],
    scope_type: str,
    scope_code: str,
    language_code: str,
    season_code: Optional[str],
    crop_code: Optional[str],
    include_override: bool,
) -> dict:
    override = _effective_override(
        db,
        tenant_id=tenant_id,
        project_id=project_id,
        scope_type=scope_type,
        scope_code=scope_code,
        language_code=language_code,
    )
    payload = (override.summary_payload if override else None) or _default_summary_payload(
        scope_type=scope_type,
        scope_code=scope_code,
        language_code=language_code,
        season_code=season_code,
        crop_code=crop_code,
    )
    return {
        "schema_version": "land_intelligence_summary.v1",
        "generated_at": _now().isoformat(),
        "tenant_id": tenant_id,
        "project_id": str(project_id) if project_id else None,
        "language_code": language_code,
        "scope": {
            "scope_type": scope_type,
            "scope_code": scope_code,
        },
        "filters": {
            "season_code": season_code,
            "crop_code": crop_code,
        },
        "summary_source": "PROJECT_OVERRIDE" if override and override.project_id else ("TENANT_OVERRIDE" if override else "DEFAULT_GENERATED"),
        "summary_payload": payload,
        "effective_override": _override_payload(override) if include_override and override else None,
        "android_contract": {
            "display_as_informational_only": True,
            "do_not_block_onboarding": True,
            "detail_clickthrough_deferred_to_v2": True,
            "backend_owned_company_editable": True,
        },
    }


@router.get("/profile/land-intelligence-summary", response_model=dict)
def get_land_intelligence_summary(
    district_lgd_code: str | None = Query(None),
    state_lgd_code: str | None = Query(None),
    pin_code: str | None = Query(None),
    scope_type: str | None = Query(None),
    scope_code: str | None = Query(None),
    crop_code: str | None = Query(None),
    season_code: str | None = Query(None),
    language_code: str = Query("en", min_length=2, max_length=12),
    project_id: uuid.UUID | None = Query(None),
    tenant_id: str = Header("default", alias="X-Tenant-ID"),
    db: Session = Depends(get_db),
):
    scope_type, scope_code = _scope_from_query(
        pin_code,
        district_lgd_code,
        state_lgd_code,
        scope_type,
        scope_code,
    )
    return _summary_response(
        db,
        tenant_id=tenant_id,
        project_id=project_id,
        scope_type=scope_type,
        scope_code=scope_code,
        language_code=_normalize_language(language_code),
        season_code=season_code.upper() if season_code else None,
        crop_code=crop_code.upper() if crop_code else None,
        include_override=False,
    )


@router.get("/admin/land-intelligence-summaries/effective", response_model=dict)
def get_admin_land_intelligence_summary_effective(
    scope_type: str = Query(...),
    scope_code: str = Query(...),
    language_code: str = Query("en", min_length=2, max_length=12),
    project_id: uuid.UUID | None = Query(None),
    season_code: str | None = Query(None),
    crop_code: str | None = Query(None),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    _principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    normalized_scope_type, normalized_scope_code = _normalize_scope(scope_type, scope_code)
    return _summary_response(
        db,
        tenant_id=x_tenant_id,
        project_id=project_id,
        scope_type=normalized_scope_type,
        scope_code=normalized_scope_code,
        language_code=_normalize_language(language_code),
        season_code=season_code.upper() if season_code else None,
        crop_code=crop_code.upper() if crop_code else None,
        include_override=True,
    )


@router.post("/admin/land-intelligence-summaries/overrides", response_model=dict)
def upsert_land_intelligence_summary_override(
    body: LandIntelligenceSummaryOverrideUpsert,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT)),
):
    tenant_id = body.tenant_id or x_tenant_id
    scope_type, scope_code = _normalize_scope(body.scope_type, body.scope_code)
    language_code = _normalize_language(body.language_code)
    review_status = body.review_status.strip().upper()

    if not body.summary_payload:
        raise HTTPException(400, {"error": "SUMMARY_PAYLOAD_REQUIRED"})

    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    if body.project_id:
        project = db.query(Project).filter(Project.id == body.project_id, Project.tenant_id == tenant_id).first()
        if not project:
            raise HTTPException(404, "Project not found for tenant")

    actor_uuid = None
    if x_actor_id:
        try:
            actor_uuid = uuid.UUID(str(x_actor_id))
        except ValueError:
            raise HTTPException(400, "X-Actor-ID must be a valid UUID")
    actor_uuid = actor_uuid or principal.user_id

    existing_query = db.query(LandIntelligenceSummaryOverride).filter(
        LandIntelligenceSummaryOverride.tenant_id == tenant_id,
        LandIntelligenceSummaryOverride.scope_type == scope_type,
        LandIntelligenceSummaryOverride.scope_code == scope_code,
        LandIntelligenceSummaryOverride.language_code == language_code,
        LandIntelligenceSummaryOverride.is_active.is_(True),
    )
    if body.project_id:
        existing_query = existing_query.filter(LandIntelligenceSummaryOverride.project_id == body.project_id)
    else:
        existing_query = existing_query.filter(LandIntelligenceSummaryOverride.project_id.is_(None))

    row = existing_query.first()
    now = _now()
    if row:
        row.summary_payload = body.summary_payload
        row.review_status = review_status
        row.review_notes = body.review_notes
        row.updated_by = actor_uuid
        row.updated_at = now
        row.published_at = now if review_status in PUBLISHED_STATUSES else row.published_at
        action = "UPDATED"
    else:
        row = LandIntelligenceSummaryOverride(
            tenant_id=tenant_id,
            project_id=body.project_id,
            scope_type=scope_type,
            scope_code=scope_code,
            language_code=language_code,
            summary_payload=body.summary_payload,
            review_status=review_status,
            review_notes=body.review_notes,
            created_by=actor_uuid,
            updated_by=actor_uuid,
            published_at=now if review_status in PUBLISHED_STATUSES else None,
            metadata_={"reason": body.reason} if body.reason else {},
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        action = "CREATED"

    db.commit()
    db.refresh(row)

    return {
        "schema_version": "land_intelligence_summary_override_upsert.v1",
        "action": action,
        "override": _override_payload(row),
        "effective": _summary_response(
            db,
            tenant_id=tenant_id,
            project_id=body.project_id,
            scope_type=scope_type,
            scope_code=scope_code,
            language_code=language_code,
            season_code=None,
            crop_code=None,
            include_override=True,
        ),
    }


@router.delete("/admin/land-intelligence-summaries/overrides/{override_id}", response_model=dict)
def deactivate_land_intelligence_summary_override(
    override_id: uuid.UUID,
    body: LandIntelligenceSummaryOverrideDeactivate | None = None,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT)),
):
    row = db.query(LandIntelligenceSummaryOverride).filter(
        LandIntelligenceSummaryOverride.id == override_id,
        LandIntelligenceSummaryOverride.tenant_id == x_tenant_id,
        LandIntelligenceSummaryOverride.is_active.is_(True),
    ).first()
    if not row:
        raise HTTPException(404, "Land intelligence summary override not found")

    actor_uuid = None
    if x_actor_id:
        try:
            actor_uuid = uuid.UUID(str(x_actor_id))
        except ValueError:
            raise HTTPException(400, "X-Actor-ID must be a valid UUID")
    row.is_active = False
    row.updated_by = actor_uuid or principal.user_id
    row.updated_at = _now()
    metadata = dict(row.metadata_ or {})
    if body and body.reason:
        metadata["deactivate_reason"] = body.reason
    row.metadata_ = metadata
    db.commit()

    return {
        "schema_version": "land_intelligence_summary_override_deactivate.v1",
        "override_id": str(override_id),
        "status": "DEACTIVATED",
    }

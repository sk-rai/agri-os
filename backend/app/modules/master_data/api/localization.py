"""Admin localization override APIs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from app.core.admin_auth import AdminPermission, AdminPrincipal, require_admin_permission
from app.core.database import get_db
from app.modules.master_data.models import LocalizedContentKey, LocalizedContentOverride
from app.modules.farmer.models import Project, Tenant


router = APIRouter(prefix="/api/v1/admin/localization", tags=["admin-localization"])

PUBLISHED_STATUSES = {"PUBLISHED", "APPROVED", "ACTIVE"}


class LocalizedContentOverrideUpsert(BaseModel):
    tenant_id: Optional[str] = None
    project_id: Optional[uuid.UUID] = None
    language_code: str = Field(..., min_length=2, max_length=12)
    override_text: str = Field(..., min_length=1, max_length=5000)
    review_status: str = Field("PUBLISHED", min_length=2, max_length=40)
    review_notes: Optional[str] = None
    reason: Optional[str] = None


class LocalizedContentOverrideDeactivate(BaseModel):
    reason: Optional[str] = None


def _now():
    return datetime.now(timezone.utc)


def _normalize_language(value: str) -> str:
    return str(value).strip().lower()


def _effective_override_query(db: Session, *, tenant_id: str, project_id: Optional[uuid.UUID], content_key_id: uuid.UUID, language_code: str):
    query = (
        db.query(LocalizedContentOverride)
        .filter(
            LocalizedContentOverride.tenant_id == tenant_id,
            LocalizedContentOverride.content_key_id == content_key_id,
            LocalizedContentOverride.language_code == language_code,
            LocalizedContentOverride.is_active.is_(True),
            LocalizedContentOverride.review_status.in_(sorted(PUBLISHED_STATUSES)),
        )
    )
    if project_id:
        query = query.filter(or_(LocalizedContentOverride.project_id == project_id, LocalizedContentOverride.project_id.is_(None)))
        return query.order_by(LocalizedContentOverride.project_id.is_(None), LocalizedContentOverride.updated_at.desc()).first()
    return query.filter(LocalizedContentOverride.project_id.is_(None)).order_by(LocalizedContentOverride.updated_at.desc()).first()


def _effective_text(key: LocalizedContentKey, override: Optional[LocalizedContentOverride], language_code: str) -> dict:
    default_labels = key.default_labels or {}
    if override:
        return {
            "text": override.override_text,
            "source": "PROJECT_OVERRIDE" if override.project_id else "TENANT_OVERRIDE",
            "override_id": str(override.id),
            "review_status": override.review_status,
        }
    if default_labels.get(language_code):
        return {
            "text": default_labels[language_code],
            "source": "PLATFORM_DEFAULT",
            "override_id": None,
            "review_status": key.review_status,
        }
    return {
        "text": default_labels.get("en", ""),
        "source": "EN_FALLBACK",
        "override_id": None,
        "review_status": key.review_status,
    }


def _override_payload(row: LocalizedContentOverride) -> dict:
    return {
        "id": str(row.id),
        "tenant_id": row.tenant_id,
        "project_id": str(row.project_id) if row.project_id else None,
        "content_key_id": str(row.content_key_id),
        "language_code": row.language_code,
        "override_text": row.override_text,
        "review_status": row.review_status,
        "review_notes": row.review_notes,
        "created_by": str(row.created_by) if row.created_by else None,
        "updated_by": str(row.updated_by) if row.updated_by else None,
        "published_at": row.published_at.isoformat() if row.published_at else None,
        "is_active": row.is_active,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _key_payload(db: Session, key: LocalizedContentKey, *, tenant_id: str, project_id: Optional[uuid.UUID], language_code: str, include_overrides: bool) -> dict:
    override = _effective_override_query(db, tenant_id=tenant_id, project_id=project_id, content_key_id=key.id, language_code=language_code)
    effective = _effective_text(key, override, language_code)
    payload = {
        "id": str(key.id),
        "content_key": key.content_key,
        "source": key.source,
        "content_kind": key.content_kind,
        "default_labels": key.default_labels or {},
        "metadata": key.metadata_ or {},
        "review_status": key.review_status,
        "effective": effective,
        "is_active": key.is_active,
        "updated_at": key.updated_at.isoformat() if key.updated_at else None,
    }
    if include_overrides:
        rows = (
            db.query(LocalizedContentOverride)
            .filter(
                LocalizedContentOverride.content_key_id == key.id,
                LocalizedContentOverride.tenant_id == tenant_id,
                LocalizedContentOverride.is_active.is_(True),
            )
            .order_by(LocalizedContentOverride.project_id.nullsfirst(), LocalizedContentOverride.language_code, LocalizedContentOverride.updated_at.desc())
            .all()
        )
        payload["overrides"] = [_override_payload(row) for row in rows]
    return payload


@router.get("/content-keys")
def list_localized_content_keys(
    source: Optional[str] = Query(None),
    content_kind: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    language_code: str = Query("en", min_length=2, max_length=12),
    tenant_id: Optional[str] = Query(None),
    project_id: Optional[uuid.UUID] = Query(None),
    include_overrides: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    effective_tenant_id = tenant_id or x_tenant_id
    language_code = _normalize_language(language_code)

    query = db.query(LocalizedContentKey).filter(LocalizedContentKey.is_active.is_(True))
    if source:
        query = query.filter(LocalizedContentKey.source == source)
    if content_kind:
        query = query.filter(LocalizedContentKey.content_kind == content_kind)
    if q:
        pattern = f"%{q.strip()}%"
        query = query.filter(
            or_(
                LocalizedContentKey.content_key.ilike(pattern),
                text("default_labels::text ilike :pattern"),
            )
        ).params(pattern=pattern)

    total = query.count()
    rows = query.order_by(LocalizedContentKey.source, LocalizedContentKey.content_key).offset(offset).limit(limit).all()

    return {
        "schema_version": "admin_localization_content_keys.v1",
        "tenant_id": effective_tenant_id,
        "project_id": str(project_id) if project_id else None,
        "language_code": language_code,
        "filters": {
            "source": source,
            "content_kind": content_kind,
            "q": q,
            "include_overrides": include_overrides,
            "limit": limit,
            "offset": offset,
        },
        "total": total,
        "count": len(rows),
        "content_keys": [
            _key_payload(db, key, tenant_id=effective_tenant_id, project_id=project_id, language_code=language_code, include_overrides=include_overrides)
            for key in rows
        ],
    }


@router.post("/content-keys/{content_key_id}/overrides")
def upsert_localized_content_override(
    content_key_id: uuid.UUID,
    body: LocalizedContentOverrideUpsert,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT)),
):
    tenant_id = body.tenant_id or x_tenant_id
    language_code = _normalize_language(body.language_code)
    review_status = body.review_status.strip().upper()

    key = db.query(LocalizedContentKey).filter(LocalizedContentKey.id == content_key_id, LocalizedContentKey.is_active.is_(True)).first()
    if not key:
        raise HTTPException(404, "Localized content key not found")

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

    existing_query = db.query(LocalizedContentOverride).filter(
        LocalizedContentOverride.tenant_id == tenant_id,
        LocalizedContentOverride.content_key_id == content_key_id,
        LocalizedContentOverride.language_code == language_code,
        LocalizedContentOverride.is_active.is_(True),
    )
    if body.project_id:
        existing_query = existing_query.filter(LocalizedContentOverride.project_id == body.project_id)
    else:
        existing_query = existing_query.filter(LocalizedContentOverride.project_id.is_(None))

    row = existing_query.first()
    now = _now()
    if row:
        row.override_text = body.override_text
        row.review_status = review_status
        row.review_notes = body.review_notes
        row.updated_by = actor_uuid
        row.published_at = now if review_status in PUBLISHED_STATUSES else row.published_at
        row.metadata_ = {**(row.metadata_ or {}), "last_reason": body.reason}
        row.updated_at = now
        action = "UPDATED"
    else:
        row = LocalizedContentOverride(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            project_id=body.project_id,
            content_key_id=content_key_id,
            language_code=language_code,
            override_text=body.override_text,
            review_status=review_status,
            review_notes=body.review_notes,
            created_by=actor_uuid,
            updated_by=actor_uuid,
            published_at=now if review_status in PUBLISHED_STATUSES else None,
            metadata_={"last_reason": body.reason},
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        action = "CREATED"

    db.commit()
    db.refresh(row)

    return {
        "schema_version": "admin_localization_override_upsert.v1",
        "action": action,
        "content_key": _key_payload(db, key, tenant_id=tenant_id, project_id=body.project_id, language_code=language_code, include_overrides=True),
        "override": _override_payload(row),
    }


@router.delete("/overrides/{override_id}")
def deactivate_localized_content_override(
    override_id: uuid.UUID,
    body: LocalizedContentOverrideDeactivate | None = None,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT)),
):
    row = (
        db.query(LocalizedContentOverride)
        .filter(
            LocalizedContentOverride.id == override_id,
            LocalizedContentOverride.tenant_id == x_tenant_id,
            LocalizedContentOverride.is_active.is_(True),
        )
        .first()
    )
    if not row:
        raise HTTPException(404, "Localized content override not found")

    actor_uuid = None
    if x_actor_id:
        try:
            actor_uuid = uuid.UUID(str(x_actor_id))
        except ValueError:
            raise HTTPException(400, "X-Actor-ID must be a valid UUID")

    row.is_active = False
    row.updated_by = actor_uuid
    row.updated_at = _now()
    row.metadata_ = {**(row.metadata_ or {}), "deactivate_reason": body.reason if body else None}
    db.commit()

    return {
        "schema_version": "admin_localization_override_deactivate.v1",
        "override_id": str(override_id),
        "status": "DEACTIVATED",
    }


@router.get("/summary")
def localization_summary(
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    rows = db.execute(text("""
        select source, count(*) as count
        from localized_content_keys
        where is_active = true
        group by source
        order by source
    """)).mappings().all()
    override_count = int(db.execute(text("""
        select count(*) from localized_content_overrides
        where tenant_id = :tenant_id and is_active = true
    """), {"tenant_id": x_tenant_id}).scalar() or 0)

    return {
        "schema_version": "admin_localization_summary.v1",
        "tenant_id": x_tenant_id,
        "content_keys_by_source": {row["source"]: row["count"] for row in rows},
        "active_override_count": override_count,
    }

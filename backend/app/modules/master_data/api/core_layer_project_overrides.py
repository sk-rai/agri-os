"""Project-scoped Core geography layer overrides."""

import json
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.admin_auth import AdminPermission, require_admin_permission
from app.core.database import get_db
from app.modules.master_data.api.geography import _project_contains_village


router = APIRouter(
    prefix="/geography/core-layer-project-overrides",
    tags=["geography"],
)

CORE_PROJECT_OVERRIDE_REGION_SYSTEMS = {
    "CORE_STACK_AGRO_CLIMATIC_ZONE",
    "CORE_STACK_AGRO_ECOLOGICAL_ZONE",
    "CORE_STACK_BIOGEOGRAPHIC_ZONE",
}


class CoreLayerProjectOverrideRequest(BaseModel):
    region_id: UUID
    rollback_token: str = Field(min_length=8, max_length=80)
    reason: str = Field(min_length=3, max_length=500)
    evidence_basis: str = Field(min_length=3, max_length=80)
    dry_run: bool = True
    confirm_apply: bool = False
    supersede_existing: bool = False


def _guardrails(written: bool) -> dict:
    return {
        "db_writes_attempted": written,
        "project_override_rows_written": written,
        "global_climate_mappings_changed": False,
        "canonical_geography_changed": False,
        "runtime_climate_activation_changed": False,
        "fallback_mappings_changed": False,
        "android_behavior_changed": False,
    }


def _project(db: Session, project_id: UUID, tenant_id: str) -> dict:
    row = db.execute(text("""
        select id::text as project_id, tenant_id, name, status
        from projects
        where id = :project_id
          and tenant_id = :tenant_id
          and is_active = true
    """), {
        "project_id": str(project_id),
        "tenant_id": tenant_id,
    }).mappings().first()

    if not row:
        raise HTTPException(
            status_code=404,
            detail="ACTIVE_TENANT_PROJECT_NOT_FOUND",
        )
    return dict(row)


def _payload(db: Session, override_id: UUID | str) -> dict:
    row = db.execute(text("""
        select
          o.id::text as override_id,
          o.tenant_id,
          o.project_id::text,
          o.village_id::text,
          v.lgd_code as village_lgd_code,
          v.canonical_name as village_name,
          o.region_id::text,
          r.region_code,
          r.region_name,
          o.region_system,
          o.assignment_source,
          o.assignment_status,
          o.evidence_basis,
          o.reviewer,
          o.review_notes,
          o.applied_by,
          o.applied_at,
          o.rolled_back_by,
          o.rolled_back_at,
          o.rollback_token,
          o.metadata,
          o.is_active,
          o.created_at,
          o.updated_at
        from geography_core_layer_project_overrides o
        join geography_villages v on v.id = o.village_id
        join geography_climate_regions r on r.id = o.region_id
        where o.id = :override_id
    """), {"override_id": str(override_id)}).mappings().one()

    return dict(row)


@router.get("/projects/{project_id}/assignments")
def list_project_core_layer_overrides(
    project_id: UUID,
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal=Depends(
        require_admin_permission(
            AdminPermission.VIEW,
            project_scoped=True,
        )
    ),
) -> dict:
    _project(db, project_id, x_tenant_id)
    active_filter = "" if include_inactive else "and is_active = true"

    rows = db.execute(text(f"""
        select id::text as override_id
        from geography_core_layer_project_overrides
        where tenant_id = :tenant_id
          and project_id = :project_id
          {active_filter}
        order by is_active desc, created_at desc
    """), {
        "tenant_id": x_tenant_id,
        "project_id": str(project_id),
    }).mappings().all()

    items = [_payload(db, row["override_id"]) for row in rows]
    return {
        "schema_version": "core_layer_project_overrides.v1",
        "mode": "PROJECT_SCOPED_CORE_LAYER_OVERRIDES",
        "tenant_id": x_tenant_id,
        "project_id": str(project_id),
        "count": len(items),
        "active_count": sum(
            1 for item in items if item["is_active"]
        ),
        "items": items,
        "guardrails": _guardrails(False),
    }


@router.get("/projects/{project_id}/villages/{village_id}")
def get_project_core_layer_override_context(
    project_id: UUID,
    village_id: UUID,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal=Depends(
        require_admin_permission(
            AdminPermission.VIEW,
            project_scoped=True,
        )
    ),
) -> dict:
    project = _project(db, project_id, x_tenant_id)

    if not _project_contains_village(db, project_id, village_id):
        raise HTTPException(
            status_code=409,
            detail="VILLAGE_NOT_IN_PROJECT_SCOPE",
        )

    village = db.execute(text("""
        select
          id::text as village_id,
          lgd_code as village_lgd_code,
          canonical_name as village_name
        from geography_villages
        where id = :village_id
          and is_active = true
    """), {"village_id": str(village_id)}).mappings().first()

    if not village:
        raise HTTPException(
            status_code=404,
            detail="ACTIVE_VILLAGE_NOT_FOUND",
        )

    regions = [
        dict(row)
        for row in db.execute(text("""
            select
              id::text as region_id,
              region_code,
              region_name,
              region_system,
              confidence,
              review_status
            from geography_climate_regions
            where is_active = true
              and region_system = any(:region_systems)
            order by region_system, region_name, region_code
        """), {
            "region_systems": sorted(
                CORE_PROJECT_OVERRIDE_REGION_SYSTEMS
            ),
        }).mappings().all()
    ]

    active_rows = db.execute(text("""
        select id::text as override_id
        from geography_core_layer_project_overrides
        where tenant_id = :tenant_id
          and project_id = :project_id
          and village_id = :village_id
          and is_active = true
        order by region_system
    """), {
        "tenant_id": x_tenant_id,
        "project_id": str(project_id),
        "village_id": str(village_id),
    }).mappings().all()

    return {
        "schema_version":
            "core_layer_project_override_context.v1",
        "mode":
            "READ_ONLY_PROJECT_SCOPED_CORE_LAYER_OPTIONS",
        "project": project,
        "village": dict(village),
        "allowed_region_systems": sorted(
            CORE_PROJECT_OVERRIDE_REGION_SYSTEMS
        ),
        "region_option_count": len(regions),
        "region_options": regions,
        "active_overrides": [
            _payload(db, row["override_id"])
            for row in active_rows
        ],
        "guardrails": _guardrails(False),
    }


@router.put("/projects/{project_id}/villages/{village_id}")
def assign_project_core_layer_override(
    project_id: UUID,
    village_id: UUID,
    body: CoreLayerProjectOverrideRequest,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal=Depends(
        require_admin_permission(
            AdminPermission.PROJECT_EDIT,
            project_scoped=True,
        )
    ),
) -> dict:
    _project(db, project_id, x_tenant_id)

    if not _project_contains_village(db, project_id, village_id):
        raise HTTPException(
            status_code=409,
            detail="VILLAGE_NOT_IN_PROJECT_SCOPE",
        )

    region = db.execute(text("""
        select
          id::text as region_id,
          region_code,
          region_name,
          region_system,
          confidence,
          review_status,
          is_active
        from geography_climate_regions
        where id = :region_id
    """), {"region_id": str(body.region_id)}).mappings().first()

    if not region or not region["is_active"]:
        raise HTTPException(
            status_code=404,
            detail="ACTIVE_CORE_REGION_NOT_FOUND",
        )

    if (
        region["region_system"]
        not in CORE_PROJECT_OVERRIDE_REGION_SYSTEMS
    ):
        raise HTTPException(
            status_code=409,
            detail="REGION_SYSTEM_NOT_PROJECT_OVERRIDE_ELIGIBLE",
        )

    existing = db.execute(text("""
        select id::text, region_id::text, rollback_token
        from geography_core_layer_project_overrides
        where tenant_id = :tenant_id
          and project_id = :project_id
          and village_id = :village_id
          and region_system = :region_system
          and is_active = true
        for update
    """), {
        "tenant_id": x_tenant_id,
        "project_id": str(project_id),
        "village_id": str(village_id),
        "region_system": region["region_system"],
    }).mappings().first()

    same_region = bool(
        existing
        and existing["region_id"] == str(body.region_id)
    )
    action = (
        "IDEMPOTENT_NO_OP"
        if same_region
        else "SUPERSEDE_AND_APPLY"
        if existing
        else "APPLY"
    )

    preview = {
        "action": action,
        "assignment_scope": "PROJECT_ONLY",
        "tenant_id": x_tenant_id,
        "project_id": str(project_id),
        "village_id": str(village_id),
        "region_id": str(body.region_id),
        "region_code": region["region_code"],
        "region_name": region["region_name"],
        "region_system": region["region_system"],
        "would_supersede_existing": bool(
            existing and not same_region
        ),
    }

    if body.dry_run:
        return {
            "schema_version":
                "core_layer_project_override_assignment.v1",
            "mode": "DRY_RUN",
            "status": "DRY_RUN_READY_NOT_APPLIED",
            "preview": preview,
            "guardrails": _guardrails(False),
        }

    if not body.confirm_apply:
        raise HTTPException(
            status_code=409,
            detail="EXPLICIT_APPLY_CONFIRMATION_REQUIRED",
        )

    if same_region:
        return {
            "schema_version":
                "core_layer_project_override_assignment.v1",
            "mode": "APPLY",
            "action": "IDEMPOTENT_NO_OP",
            "assignment": _payload(db, existing["id"]),
            "guardrails": _guardrails(False),
        }

    if existing and not body.supersede_existing:
        raise HTTPException(
            status_code=409,
            detail=(
                "ACTIVE_PROJECT_VILLAGE_LAYER_OVERRIDE_EXISTS"
            ),
        )

    actor = str(principal.user_id)

    if existing:
        db.execute(text("""
            update geography_core_layer_project_overrides
            set
              is_active = false,
              assignment_status = 'ROLLED_BACK',
              rolled_back_by = :actor,
              rolled_back_at = now(),
              rollback_report = jsonb_build_object(
                'reason', 'EXPLICIT_SUPERSESSION',
                'superseded_by_region_id', :region_id,
                'actor', :actor
              ),
              updated_at = now()
            where id = :override_id
        """), {
            "actor": actor,
            "region_id": str(body.region_id),
            "override_id": existing["id"],
        })

    override_id = uuid4()
    apply_report = {
        **preview,
        "applied_by": actor,
        "global_climate_mappings_changed": False,
        "canonical_geography_changed": False,
        "runtime_climate_activation_changed": False,
    }
    metadata = {
        "reason": body.reason,
        "assignment_scope": "PROJECT_ONLY",
        "region_confidence": region["confidence"],
        "region_review_status": region["review_status"],
        "global_mapping_unchanged": True,
    }

    db.execute(text("""
        insert into geography_core_layer_project_overrides (
          id,
          tenant_id,
          project_id,
          village_id,
          region_id,
          region_system,
          assignment_source,
          assignment_status,
          evidence_basis,
          reviewer,
          review_notes,
          applied_by,
          applied_at,
          rollback_token,
          dry_run_report,
          apply_report,
          rollback_report,
          metadata,
          is_active,
          created_at,
          updated_at,
          version
        ) values (
          :id,
          :tenant_id,
          :project_id,
          :village_id,
          :region_id,
          :region_system,
          'ADMIN_PROJECT_OVERRIDE',
          'APPLIED',
          :evidence_basis,
          :actor,
          :reason,
          :actor,
          now(),
          :rollback_token,
          cast(:dry_run_report as jsonb),
          cast(:apply_report as jsonb),
          '{}'::jsonb,
          cast(:metadata as jsonb),
          true,
          now(),
          now(),
          'v1.0'
        )
    """), {
        "id": str(override_id),
        "tenant_id": x_tenant_id,
        "project_id": str(project_id),
        "village_id": str(village_id),
        "region_id": str(body.region_id),
        "region_system": region["region_system"],
        "evidence_basis": body.evidence_basis,
        "actor": actor,
        "reason": body.reason,
        "rollback_token": body.rollback_token,
        "dry_run_report": json.dumps(preview),
        "apply_report": json.dumps(apply_report),
        "metadata": json.dumps(metadata),
    })
    db.commit()

    return {
        "schema_version":
            "core_layer_project_override_assignment.v1",
        "mode": "APPLY",
        "action": (
            "SUPERSEDED_AND_APPLIED"
            if existing
            else "APPLIED"
        ),
        "assignment": _payload(db, override_id),
        "guardrails": _guardrails(True),
    }


@router.delete("/projects/{project_id}/villages/{village_id}")
def rollback_project_core_layer_override(
    project_id: UUID,
    village_id: UUID,
    region_system: str = Query(...),
    rollback_token: str = Query(min_length=8, max_length=80),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal=Depends(
        require_admin_permission(
            AdminPermission.PROJECT_EDIT,
            project_scoped=True,
        )
    ),
) -> dict:
    _project(db, project_id, x_tenant_id)

    if region_system not in CORE_PROJECT_OVERRIDE_REGION_SYSTEMS:
        raise HTTPException(
            status_code=409,
            detail="INVALID_CORE_REGION_SYSTEM",
        )

    existing = db.execute(text("""
        select id::text, rollback_token
        from geography_core_layer_project_overrides
        where tenant_id = :tenant_id
          and project_id = :project_id
          and village_id = :village_id
          and region_system = :region_system
          and is_active = true
        for update
    """), {
        "tenant_id": x_tenant_id,
        "project_id": str(project_id),
        "village_id": str(village_id),
        "region_system": region_system,
    }).mappings().first()

    if not existing:
        raise HTTPException(
            status_code=404,
            detail=(
                "ACTIVE_PROJECT_CORE_LAYER_OVERRIDE_NOT_FOUND"
            ),
        )

    if existing["rollback_token"] != rollback_token:
        raise HTTPException(
            status_code=409,
            detail="ROLLBACK_TOKEN_MISMATCH",
        )

    actor = str(principal.user_id)
    db.execute(text("""
        update geography_core_layer_project_overrides
        set
          is_active = false,
          assignment_status = 'ROLLED_BACK',
          rolled_back_by = :actor,
          rolled_back_at = now(),
          rollback_report = jsonb_build_object(
            'reason', 'ADMIN_PROJECT_OVERRIDE_ROLLBACK',
            'rollback_token', :rollback_token,
            'actor', :actor
          ),
          updated_at = now()
        where id = :override_id
    """), {
        "actor": actor,
        "rollback_token": rollback_token,
        "override_id": existing["id"],
    })
    db.commit()

    return {
        "schema_version":
            "core_layer_project_override_assignment.v1",
        "mode": "ROLLBACK",
        "action": "ROLLED_BACK",
        "assignment": _payload(db, existing["id"]),
        "guardrails": _guardrails(True),
    }

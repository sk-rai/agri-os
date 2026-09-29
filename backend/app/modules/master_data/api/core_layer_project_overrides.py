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



def resolve_effective_project_core_layers(
    db: Session,
    *,
    tenant_id: str,
    project_id: UUID,
    village_id: UUID,
) -> dict:
    """Resolve project override first, then canonical global fallback."""

    project = _project(db, project_id, tenant_id)
    if not _project_contains_village(
        db,
        project_id,
        village_id,
    ):
        raise HTTPException(
            status_code=409,
            detail="VILLAGE_NOT_IN_PROJECT_SCOPE",
        )

    village = db.execute(text("""
        select
          v.id::text as village_id,
          v.lgd_code::text as village_lgd_code,
          v.canonical_name as village_name,
          d.lgd_code::text as district_lgd_code,
          d.canonical_name as district_name,
          s.lgd_code::text as state_lgd_code,
          s.canonical_name as state_name
        from geography_villages v
        join geography_districts d on d.id = v.district_id
        join geography_states s on s.id = d.state_id
        where v.id = :village_id
          and v.is_active = true
          and d.is_active = true
          and s.is_active = true
    """), {
        "village_id": str(village_id),
    }).mappings().first()

    if not village:
        raise HTTPException(
            status_code=404,
            detail="ACTIVE_VILLAGE_HIERARCHY_NOT_FOUND",
        )

    fallback_rows = [
        dict(row)
        for row in db.execute(text("""
            with village_context as (
              select
                v.id,
                v.lgd_code::text as village_lgd_code,
                d.lgd_code::text as district_lgd_code,
                s.lgd_code::text as state_lgd_code
              from geography_villages v
              join geography_districts d on d.id = v.district_id
              join geography_states s on s.id = d.state_id
              where v.id = :village_id
            ),
            candidate_mappings as (
              select
                m.id as mapping_id,
                m.region_id,
                m.region_code,
                m.scope_level,
                m.confidence as mapping_confidence,
                m.review_status as mapping_review_status,
                case m.scope_level
                  when 'VILLAGE' then 1
                  when 'PIN' then 2
                  when 'DISTRICT' then 3
                  when 'STATE' then 4
                  else 9
                end as scope_rank
              from geography_climate_region_mappings m
              cross join village_context vc
              where m.is_active = true
                and (
                  (
                    m.scope_level = 'VILLAGE'
                    and m.village_lgd_code =
                        vc.village_lgd_code
                  )
                  or (
                    m.scope_level = 'PIN'
                    and exists (
                      select 1
                      from geography_village_pin_links vpl
                      where vpl.geography_village_id = vc.id
                        and vpl.is_active = true
                        and vpl.match_status = 'MATCHED'
                        and vpl.pin_code = m.pin_code
                    )
                  )
                  or (
                    m.scope_level = 'DISTRICT'
                    and m.district_lgd_code =
                        vc.district_lgd_code
                  )
                  or (
                    m.scope_level = 'STATE'
                    and m.state_lgd_code =
                        vc.state_lgd_code
                  )
                )
            ),
            ranked as (
              select
                cm.*,
                r.region_name,
                r.region_system,
                r.confidence as region_confidence,
                r.review_status as region_review_status,
                row_number() over (
                  partition by r.region_system
                  order by
                    cm.scope_rank,
                    cm.region_code,
                    cm.mapping_id
                ) as resolution_rank
              from candidate_mappings cm
              join geography_climate_regions r
                on r.id = cm.region_id
               and r.is_active = true
              where r.region_system = any(:region_systems)
            )
            select
              region_id::text,
              region_code,
              region_name,
              region_system,
              scope_level,
              mapping_confidence,
              mapping_review_status,
              region_confidence,
              region_review_status
            from ranked
            where resolution_rank = 1
            order by region_system
        """), {
            "village_id": str(village_id),
            "region_systems": sorted(
                CORE_PROJECT_OVERRIDE_REGION_SYSTEMS
            ),
        }).mappings().all()
    ]

    override_rows = [
        dict(row)
        for row in db.execute(text("""
            select
              o.id::text as override_id,
              o.region_id::text,
              r.region_code,
              r.region_name,
              r.region_system,
              r.confidence as region_confidence,
              r.review_status as region_review_status,
              o.evidence_basis,
              o.reviewer,
              o.review_notes,
              o.applied_by,
              o.applied_at,
              o.rollback_token
            from geography_core_layer_project_overrides o
            join geography_climate_regions r
              on r.id = o.region_id
             and r.is_active = true
            where o.tenant_id = :tenant_id
              and o.project_id = :project_id
              and o.village_id = :village_id
              and o.is_active = true
              and o.assignment_status = 'APPLIED'
              and o.region_system = any(:region_systems)
            order by o.region_system
        """), {
            "tenant_id": tenant_id,
            "project_id": str(project_id),
            "village_id": str(village_id),
            "region_systems": sorted(
                CORE_PROJECT_OVERRIDE_REGION_SYSTEMS
            ),
        }).mappings().all()
    ]

    fallback_by_system = {
        row["region_system"]: row
        for row in fallback_rows
    }
    override_by_system = {
        row["region_system"]: row
        for row in override_rows
    }

    effective = []
    unresolved = []

    for region_system in sorted(
        CORE_PROJECT_OVERRIDE_REGION_SYSTEMS
    ):
        override = override_by_system.get(region_system)
        fallback = fallback_by_system.get(region_system)

        if override:
            effective.append({
                **override,
                "resolution_source": "PROJECT_OVERRIDE",
                "resolution_scope": "PROJECT_VILLAGE",
                "global_fallback_available": fallback is not None,
                "global_fallback_region_code": (
                    fallback["region_code"]
                    if fallback
                    else None
                ),
                "global_fallback_region_name": (
                    fallback["region_name"]
                    if fallback
                    else None
                ),
                "global_fallback_scope": (
                    fallback["scope_level"]
                    if fallback
                    else None
                ),
            })
        elif fallback:
            effective.append({
                **fallback,
                "override_id": None,
                "resolution_source": "GLOBAL_MAPPING_FALLBACK",
                "resolution_scope": fallback["scope_level"],
                "global_fallback_available": True,
                "global_fallback_region_code":
                    fallback["region_code"],
                "global_fallback_region_name":
                    fallback["region_name"],
                "global_fallback_scope":
                    fallback["scope_level"],
            })
        else:
            unresolved.append(region_system)

    return {
        "schema_version":
            "core_layer_project_effective_resolution.v1",
        "mode":
            "READ_ONLY_PROJECT_OVERRIDE_THEN_GLOBAL_FALLBACK",
        "tenant_id": tenant_id,
        "project": project,
        "village": dict(village),
        "precedence": [
            "PROJECT_OVERRIDE",
            "GLOBAL_VILLAGE_MAPPING",
            "GLOBAL_PIN_MAPPING",
            "GLOBAL_DISTRICT_MAPPING",
            "GLOBAL_STATE_MAPPING",
        ],
        "effective_region_count": len(effective),
        "project_override_count": len(override_rows),
        "global_fallback_count": sum(
            1
            for row in effective
            if row["resolution_source"]
            == "GLOBAL_MAPPING_FALLBACK"
        ),
        "unresolved_region_systems": unresolved,
        "effective_regions": effective,
        "guardrails": _guardrails(False),
    }


@router.get(
    "/projects/{project_id}/villages/{village_id}/effective"
)
def get_effective_project_core_layers(
    project_id: UUID,
    village_id: UUID,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(
        "default",
        alias="X-Tenant-ID",
    ),
    principal=Depends(
        require_admin_permission(
            AdminPermission.VIEW,
            project_scoped=True,
        )
    ),
) -> dict:
    return resolve_effective_project_core_layers(
        db,
        tenant_id=x_tenant_id,
        project_id=project_id,
        village_id=village_id,
    )

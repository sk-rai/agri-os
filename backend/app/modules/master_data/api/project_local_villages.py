"""Single-admin project-local village overlays; global geography is immutable."""
import json
import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.admin_auth import AdminPermission, require_admin_permission
from app.core.database import get_db
from app.modules.master_data.api.project_village_resolutions import (
    PIN_RE,
    project,
    project_village_sql,
)

router = APIRouter(
    prefix="/geography/project-village-resolutions",
    tags=["geography"],
)


class ProjectLocalVillageAuthorization(BaseModel):
    nwdp_source_feature_id: UUID
    display_name: str = Field(min_length=2, max_length=180)
    pin_codes: list[str] = Field(default_factory=list, max_length=20)
    reason: str = Field(min_length=8, max_length=1000)
    rollback_token: str = Field(min_length=8, max_length=80)
    confirmation_phrase: str


class ProjectLocalVillageRetirement(BaseModel):
    rollback_token: str = Field(min_length=8, max_length=80)
    reason: str = Field(min_length=8, max_length=500)
    confirmation_phrase: str


def _source_feature(db: Session, source_id: UUID):
    return db.execute(
        text(
            """
            select
              f.id::text source_feature_id,
              f.source_vlcode,
              f.source_state_name,
              f.source_district_name,
              f.source_subdistrict_name,
              f.source_block_name,
              f.source_village_name
            from geography_boundary_source_features f
            join geography_boundary_import_batches batch
              on batch.id = f.import_batch_id
             and batch.source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
            where f.id = :source_id
              and not exists (
                select 1
                from geography_boundary_crosswalk_candidates candidate
                where candidate.source_feature_id = f.id
                  and candidate.proposed_village_id is not null
              )
              and not exists (
                select 1
                from geography_boundary_runtime_crosswalks runtime
                join geography_boundary_crosswalk_candidates candidate
                  on candidate.id = runtime.source_candidate_id
                where candidate.source_feature_id = f.id
                  and runtime.is_active
              )
            """
        ),
        {"source_id": str(source_id)},
    ).mappings().first()


def _parent_matches(db: Session, project_row: dict, source: dict) -> dict:
    scope = project_row.get("geography_scope") or {}
    if isinstance(scope, str):
        try:
            scope = json.loads(scope)
        except Exception:
            scope = {}
    project_sql, scope_params, _sources = project_village_sql(scope)
    row = db.execute(
        text(
            """with project_villages as ("""
            + project_sql
            + """)
            select
              coalesce(bool_or(lower(trim(state.canonical_name)) =
                lower(trim(:source_state))), false) state_match,
              coalesce(bool_or(lower(trim(district.canonical_name)) =
                lower(trim(:source_district))), false) district_match,
              coalesce(bool_or(lower(trim(block.canonical_name)) in (
                lower(trim(:source_subdistrict)),
                lower(trim(:source_block))
              )), false) tehsil_or_block_match
            from project_villages scoped
            join geography_villages village
              on village.id = cast(scoped.village_id as uuid)
             and village.is_active
            join geography_blocks block on block.id = village.block_id
            join geography_districts district on district.id = village.district_id
            join geography_states state on state.id = district.state_id
            """
        ),
        {
            "project_id": project_row["project_id"],
            "source_state": source["source_state_name"] or "",
            "source_district": source["source_district_name"] or "",
            "source_subdistrict": source["source_subdistrict_name"] or "",
            "source_block": source["source_block_name"] or "",
            **scope_params,
        },
    ).mappings().one()
    return {
        "state": bool(row["state_match"]),
        "district": bool(row["district_match"]),
        "tehsil_or_block": bool(row["tehsil_or_block_match"]),
    }


@router.post("/projects/{project_id}/local-additions")
def authorize_project_local_village(
    project_id: UUID,
    body: ProjectLocalVillageAuthorization,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal=Depends(
        require_admin_permission(AdminPermission.PROJECT_EDIT, project_scoped=True)
    ),
):
    project_row = project(db, project_id, x_tenant_id)
    if body.confirmation_phrase != "AUTHORIZE PROJECT LOCAL VILLAGE":
        raise HTTPException(
            400, {"code": "PROJECT_LOCAL_VILLAGE_CONFIRMATION_REQUIRED"}
        )
    if any(not PIN_RE.fullmatch(pin) for pin in body.pin_codes):
        raise HTTPException(400, "INVALID_PIN_CODE")
    source = _source_feature(db, body.nwdp_source_feature_id)
    if not source:
        raise HTTPException(
            409, "NWDP_SOURCE_NOT_ELIGIBLE_FOR_PROJECT_LOCAL_ADDITION"
        )
    parent_matches = _parent_matches(db, project_row, dict(source))
    if not any(parent_matches.values()):
        raise HTTPException(
            409,
            {
                "code": "PROJECT_LOCAL_VILLAGE_PARENT_MISMATCH",
                "parent_matches": parent_matches,
            },
        )
    if body.pin_codes:
        found = set(
            db.execute(
                text(
                    "select distinct pin_code from geography_postal_references "
                    "where is_active and pin_code=any(:pins)"
                ),
                {"pins": body.pin_codes},
            ).scalars()
        )
        if found != set(body.pin_codes):
            raise HTTPException(
                409,
                {
                    "code": "PIN_EVIDENCE_NOT_FOUND",
                    "missing": sorted(set(body.pin_codes) - found),
                },
            )
    existing = db.execute(
        text(
            """
            select id::text
            from geography_project_village_resolutions
            where tenant_id = :tenant
              and project_id = :project
              and nwdp_source_feature_id = :source
              and resolution_status in ('DRAFT','APPROVED','ACTIVE')
            for update
            """
        ),
        {
            "tenant": x_tenant_id,
            "project": str(project_id),
            "source": str(body.nwdp_source_feature_id),
        },
    ).scalar()
    if existing:
        raise HTTPException(
            409,
            {"code": "ACTIVE_PROJECT_LOCAL_VILLAGE_EXISTS", "resolution_id": existing},
        )
    resolution_id = uuid.uuid4()
    event_id = uuid.uuid4()
    project_code = (
        "nwdp:"
        + str(source["source_vlcode"] or body.nwdp_source_feature_id)
        + ":"
        + str(resolution_id)[:8]
    )
    evidence = {
        "authorization_model": "SINGLE_PROJECT_ADMIN",
        "reason": body.reason,
        "parent_matches": parent_matches,
        "source_feature_id": str(body.nwdp_source_feature_id),
        "source_hierarchy": dict(source),
        "project_visible": True,
        "android_visible": False,
        "global_geography_changed": False,
    }
    db.execute(
        text(
            """
            insert into geography_project_village_resolutions(
              id, tenant_id, project_id, resolution_mode,
              nwdp_source_feature_id, project_village_code, display_name,
              hierarchy_labels, pin_codes, pin_evidence, resolution_status,
              evidence_basis, reviewer, review_notes, rollback_token,
              metadata, version, is_active
            ) values(
              :id, :tenant, :project, 'PROJECT_LOCAL_ADDITION',
              :source, :code, :name, cast(:hierarchy as jsonb), :pins,
              cast(:pin_evidence as jsonb), 'ACTIVE',
              'SINGLE_ADMIN_PARENT_MATCH', :reviewer, :notes, :rollback,
              cast(:metadata as jsonb), 'v1.0', true
            )
            """
        ),
        {
            "id": str(resolution_id),
            "tenant": x_tenant_id,
            "project": str(project_id),
            "source": str(body.nwdp_source_feature_id),
            "code": project_code,
            "name": body.display_name,
            "hierarchy": json.dumps(dict(source)),
            "pins": body.pin_codes,
            "pin_evidence": json.dumps(
                {"verified_against_active_postal_reference": bool(body.pin_codes)}
            ),
            "reviewer": str(principal.user_id),
            "notes": body.reason,
            "rollback": body.rollback_token,
            "metadata": json.dumps(evidence),
        },
    )
    db.execute(
        text(
            """
            insert into geography_project_village_resolution_events(
              id, tenant_id, project_id, resolution_id, action, actor_id, evidence
            ) values(
              :id, :tenant, :project, :resolution, 'APPLIED', :actor,
              cast(:evidence as jsonb)
            )
            """
        ),
        {
            "id": str(event_id),
            "tenant": x_tenant_id,
            "project": str(project_id),
            "resolution": str(resolution_id),
            "actor": str(principal.user_id),
            "evidence": json.dumps(evidence),
        },
    )
    db.commit()
    return {
        "schema_version": "project_local_village_authorization.v1",
        "status": "ACTIVE",
        "resolution_id": str(resolution_id),
        "project_village_code": project_code,
        "audit_event_id": str(event_id),
        "authorization_model": "SINGLE_PROJECT_ADMIN",
        "parent_matches": parent_matches,
        "project_visible": True,
        "android_visible": False,
        "global_geography_changed": False,
        "rollback_available": True,
    }


@router.post("/projects/{project_id}/local-additions/{resolution_id}/retire")
def retire_project_local_village(
    project_id: UUID,
    resolution_id: UUID,
    body: ProjectLocalVillageRetirement,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal=Depends(
        require_admin_permission(AdminPermission.PROJECT_EDIT, project_scoped=True)
    ),
):
    project(db, project_id, x_tenant_id)
    if body.confirmation_phrase != "RETIRE PROJECT LOCAL VILLAGE":
        raise HTTPException(
            400, {"code": "PROJECT_LOCAL_VILLAGE_RETIREMENT_CONFIRMATION_REQUIRED"}
        )
    row = db.execute(
        text(
            """
            update geography_project_village_resolutions
            set resolution_status = 'RETIRED', is_active = false,
                updated_at = now(),
                metadata = metadata || cast(:metadata as jsonb)
            where id = :id and tenant_id = :tenant and project_id = :project
              and resolution_mode = 'PROJECT_LOCAL_ADDITION'
              and rollback_token = :token and is_active
            returning id::text
            """
        ),
        {
            "id": str(resolution_id),
            "tenant": x_tenant_id,
            "project": str(project_id),
            "token": body.rollback_token,
            "metadata": json.dumps(
                {"retired_by": str(principal.user_id), "retirement_reason": body.reason}
            ),
        },
    ).scalar()
    if not row:
        raise HTTPException(
            409, {"code": "ACTIVE_PROJECT_LOCAL_VILLAGE_OR_TOKEN_NOT_FOUND"}
        )
    event_id = uuid.uuid4()
    db.execute(
        text(
            """
            insert into geography_project_village_resolution_events(
              id, tenant_id, project_id, resolution_id, action, actor_id, evidence
            ) values(
              :id, :tenant, :project, :resolution, 'ROLLED_BACK', :actor,
              cast(:evidence as jsonb)
            )
            """
        ),
        {
            "id": str(event_id),
            "tenant": x_tenant_id,
            "project": str(project_id),
            "resolution": str(resolution_id),
            "actor": str(principal.user_id),
            "evidence": json.dumps(
                {
                    "reason": body.reason,
                    "project_visible": False,
                    "android_visible": False,
                    "global_geography_changed": False,
                }
            ),
        },
    )
    db.commit()
    return {
        "schema_version": "project_local_village_retirement.v1",
        "status": "RETIRED",
        "resolution_id": str(resolution_id),
        "audit_event_id": str(event_id),
        "project_visible": False,
        "android_visible": False,
        "global_geography_changed": False,
    }

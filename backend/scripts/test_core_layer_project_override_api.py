#!/usr/bin/env python3
"""Transactional regression for project-scoped Core overrides."""

import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1]),
)

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import engine
from app.modules.master_data.api.core_layer_project_overrides import (
    CORE_PROJECT_OVERRIDE_REGION_SYSTEMS,
    CoreLayerProjectOverrideRequest,
    _project,
    assign_project_core_layer_override,
    get_project_core_layer_override_context,
    list_project_core_layer_overrides,
    rollback_project_core_layer_override,
)
from app.modules.master_data.api.geography import (
    _project_contains_village,
)


def expect_http_error(
    status_code: int,
    detail: str,
    fn,
) -> None:
    try:
        fn()
    except HTTPException as exc:
        assert exc.status_code == status_code, (
            exc.status_code,
            exc.detail,
        )
        assert exc.detail == detail, (
            exc.status_code,
            exc.detail,
        )
        return
    raise AssertionError(
        f"Expected HTTP {status_code}: {detail}"
    )


def find_project_village(db: Session) -> dict:
    row = db.execute(text("""
        select
          p.id::text as project_id,
          p.tenant_id,
          v.id::text as village_id,
          v.lgd_code::text as village_lgd_code,
          v.canonical_name as village_name
        from projects p
        cross join lateral (
          select id, lgd_code, canonical_name
          from geography_villages
          where is_active = true
            and lgd_code is not null
          order by id
          limit 1
        ) v
        where p.is_active = true
        order by p.id
        limit 1
    """)).mappings().first()

    if not row:
        raise RuntimeError(
            "No active project and village fixture found"
        )

    fixture = dict(row)

    # The fixture is deliberately scoped inside the outer
    # rollback-only transaction. No project change persists.
    db.execute(text("""
        update projects
        set geography_scope = jsonb_build_object(
              'village_lgd_codes',
              jsonb_build_array(:village_lgd_code)
            ),
            updated_at = now()
        where id = :project_id
    """), {
        "project_id": fixture["project_id"],
        "village_lgd_code": fixture["village_lgd_code"],
    })
    db.flush()

    project_id = UUID(fixture["project_id"])
    village_id = UUID(fixture["village_id"])
    if not _project_contains_village(
        db,
        project_id,
        village_id,
    ):
        raise RuntimeError(
            "Transactional project geography scope did not resolve"
        )

    return fixture


def find_out_of_scope_village(
    db: Session,
    project_id: UUID,
    selected_village_id: UUID,
) -> UUID:
    rows = db.execute(text("""
        select id::text as village_id
        from geography_villages
        where is_active = true
          and id <> :selected_village_id
        order by id
        limit 2000
    """), {
        "selected_village_id": str(selected_village_id),
    }).mappings().all()

    for row in rows:
        village_id = UUID(row["village_id"])
        if not _project_contains_village(
            db,
            project_id,
            village_id,
        ):
            return village_id

    raise RuntimeError(
        "Could not find an out-of-project village fixture"
    )


def find_region_pair(db: Session) -> tuple[dict, dict]:
    rows = [
        dict(row)
        for row in db.execute(text("""
            select
              id::text as region_id,
              region_code,
              region_name,
              region_system
            from geography_climate_regions
            where is_active = true
              and region_system = any(:region_systems)
            order by region_system, region_code, id
        """), {
            "region_systems": sorted(
                CORE_PROJECT_OVERRIDE_REGION_SYSTEMS
            ),
        }).mappings().all()
    ]

    by_system: dict[str, list[dict]] = {}
    for row in rows:
        by_system.setdefault(
            row["region_system"],
            [],
        ).append(row)

    for region_system in sorted(by_system):
        candidates = by_system[region_system]
        if len(candidates) >= 2:
            return candidates[0], candidates[1]

    raise RuntimeError(
        "No active Core region system has two regions"
    )


def protected_counts(db: Session) -> dict:
    return {
        "climate_regions": db.execute(text("""
            select count(*)
            from geography_climate_regions
        """)).scalar_one(),
        "climate_mappings": db.execute(text("""
            select count(*)
            from geography_climate_region_mappings
        """)).scalar_one(),
        "villages": db.execute(text("""
            select count(*)
            from geography_villages
        """)).scalar_one(),
        "active_villages": db.execute(text("""
            select count(*)
            from geography_villages
            where is_active = true
        """)).scalar_one(),
    }


def override_counts(
    db: Session,
    project_id: UUID,
    village_id: UUID,
    region_system: str,
) -> dict:
    row = db.execute(text("""
        select
          count(*)::bigint as total,
          count(*) filter (
            where is_active = true
          )::bigint as active,
          count(*) filter (
            where assignment_status = 'APPLIED'
          )::bigint as applied,
          count(*) filter (
            where assignment_status = 'ROLLED_BACK'
          )::bigint as rolled_back
        from geography_core_layer_project_overrides
        where project_id = :project_id
          and village_id = :village_id
          and region_system = :region_system
    """), {
        "project_id": str(project_id),
        "village_id": str(village_id),
        "region_system": region_system,
    }).mappings().one()
    return dict(row)


def main() -> int:
    connection = engine.connect()
    outer_transaction = connection.begin()
    db = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
    )

    try:
        fixture = find_project_village(db)
        project_id = UUID(fixture["project_id"])
        village_id = UUID(fixture["village_id"])
        tenant_id = fixture["tenant_id"]
        out_of_scope_village_id = find_out_of_scope_village(
            db,
            project_id,
            village_id,
        )
        first_region, second_region = find_region_pair(db)
        region_system = first_region["region_system"]
        principal = SimpleNamespace(
            user_id="core-project-override-regression"
        )

        initial_overrides = override_counts(
            db,
            project_id,
            village_id,
            region_system,
        )
        assert initial_overrides == {
            "total": 0,
            "active": 0,
            "applied": 0,
            "rolled_back": 0,
        }, initial_overrides

        protected_before = protected_counts(db)

        expect_http_error(
            404,
            "ACTIVE_TENANT_PROJECT_NOT_FOUND",
            lambda: _project(
                db,
                project_id,
                "wrong-tenant",
            ),
        )
        print("PASS Cross-tenant project access is rejected")

        expect_http_error(
            409,
            "VILLAGE_NOT_IN_PROJECT_SCOPE",
            lambda: get_project_core_layer_override_context(
                project_id=project_id,
                village_id=out_of_scope_village_id,
                db=db,
                x_tenant_id=tenant_id,
                principal=principal,
            ),
        )
        print("PASS Out-of-project village is rejected")

        context = get_project_core_layer_override_context(
            project_id=project_id,
            village_id=village_id,
            db=db,
            x_tenant_id=tenant_id,
            principal=principal,
        )
        assert context["mode"] == (
            "READ_ONLY_PROJECT_SCOPED_CORE_LAYER_OPTIONS"
        )
        assert context["village"]["village_id"] == str(
            village_id
        )
        assert context["active_overrides"] == []
        assert context["region_option_count"] > 0
        assert (
            context["guardrails"]["db_writes_attempted"]
            is False
        )
        print("PASS Authorized read-only context succeeds")

        dry_run_body = CoreLayerProjectOverrideRequest(
            region_id=UUID(first_region["region_id"]),
            rollback_token="core-regression-token-1",
            reason="Transactional project override regression",
            evidence_basis="ADMIN_PROJECT_REVIEW",
        )
        dry_run = assign_project_core_layer_override(
            project_id=project_id,
            village_id=village_id,
            body=dry_run_body,
            db=db,
            x_tenant_id=tenant_id,
            principal=principal,
        )
        assert dry_run["mode"] == "DRY_RUN"
        assert dry_run["status"] == (
            "DRY_RUN_READY_NOT_APPLIED"
        )
        assert dry_run["preview"]["action"] == "APPLY"
        assert override_counts(
            db,
            project_id,
            village_id,
            region_system,
        )["total"] == 0
        print("PASS Dry run writes no override row")

        unconfirmed_body = dry_run_body.copy(
            update={
                "dry_run": False,
                "confirm_apply": False,
            }
        )
        expect_http_error(
            409,
            "EXPLICIT_APPLY_CONFIRMATION_REQUIRED",
            lambda: assign_project_core_layer_override(
                project_id=project_id,
                village_id=village_id,
                body=unconfirmed_body,
                db=db,
                x_tenant_id=tenant_id,
                principal=principal,
            ),
        )
        assert override_counts(
            db,
            project_id,
            village_id,
            region_system,
        )["total"] == 0
        print("PASS Unconfirmed apply is rejected")

        apply_body = dry_run_body.copy(
            update={
                "dry_run": False,
                "confirm_apply": True,
            }
        )
        applied = assign_project_core_layer_override(
            project_id=project_id,
            village_id=village_id,
            body=apply_body,
            db=db,
            x_tenant_id=tenant_id,
            principal=principal,
        )
        assert applied["action"] == "APPLIED"
        assert applied["assignment"]["is_active"] is True
        assert applied["assignment"]["region_id"] == (
            first_region["region_id"]
        )
        assert applied["assignment"]["tenant_id"] == tenant_id
        assert applied["guardrails"][
            "project_override_rows_written"
        ] is True
        assert override_counts(
            db,
            project_id,
            village_id,
            region_system,
        ) == {
            "total": 1,
            "active": 1,
            "applied": 1,
            "rolled_back": 0,
        }
        print("PASS Confirmed project override is applied")

        idempotent = assign_project_core_layer_override(
            project_id=project_id,
            village_id=village_id,
            body=apply_body,
            db=db,
            x_tenant_id=tenant_id,
            principal=principal,
        )
        assert idempotent["action"] == "IDEMPOTENT_NO_OP"
        assert override_counts(
            db,
            project_id,
            village_id,
            region_system,
        )["total"] == 1
        print("PASS Repeated assignment is idempotent")

        second_body = CoreLayerProjectOverrideRequest(
            region_id=UUID(second_region["region_id"]),
            rollback_token="core-regression-token-2",
            reason="Explicit project override supersession",
            evidence_basis="ADMIN_PROJECT_REVIEW",
            dry_run=False,
            confirm_apply=True,
        )
        expect_http_error(
            409,
            "ACTIVE_PROJECT_VILLAGE_LAYER_OVERRIDE_EXISTS",
            lambda: assign_project_core_layer_override(
                project_id=project_id,
                village_id=village_id,
                body=second_body,
                db=db,
                x_tenant_id=tenant_id,
                principal=principal,
            ),
        )
        print("PASS Implicit supersession is rejected")

        supersede_body = second_body.copy(
            update={"supersede_existing": True}
        )
        superseded = assign_project_core_layer_override(
            project_id=project_id,
            village_id=village_id,
            body=supersede_body,
            db=db,
            x_tenant_id=tenant_id,
            principal=principal,
        )
        assert superseded["action"] == (
            "SUPERSEDED_AND_APPLIED"
        )
        counts = override_counts(
            db,
            project_id,
            village_id,
            region_system,
        )
        assert counts == {
            "total": 2,
            "active": 1,
            "applied": 1,
            "rolled_back": 1,
        }, counts
        print("PASS Explicit supersession preserves history")

        assignments = list_project_core_layer_overrides(
            project_id=project_id,
            include_inactive=True,
            db=db,
            x_tenant_id=tenant_id,
            principal=principal,
        )
        assert assignments["count"] == 2
        assert assignments["active_count"] == 1
        print("PASS Assignment history is project scoped")

        expect_http_error(
            409,
            "ROLLBACK_TOKEN_MISMATCH",
            lambda: rollback_project_core_layer_override(
                project_id=project_id,
                village_id=village_id,
                region_system=region_system,
                rollback_token="incorrect-token",
                db=db,
                x_tenant_id=tenant_id,
                principal=principal,
            ),
        )
        print("PASS Incorrect rollback token is rejected")

        rolled_back = rollback_project_core_layer_override(
            project_id=project_id,
            village_id=village_id,
            region_system=region_system,
            rollback_token="core-regression-token-2",
            db=db,
            x_tenant_id=tenant_id,
            principal=principal,
        )
        assert rolled_back["action"] == "ROLLED_BACK"
        assert rolled_back["assignment"]["is_active"] is False

        counts = override_counts(
            db,
            project_id,
            village_id,
            region_system,
        )
        assert counts == {
            "total": 2,
            "active": 0,
            "applied": 0,
            "rolled_back": 2,
        }, counts
        print("PASS Token-guarded rollback succeeds")

        protected_after = protected_counts(db)
        assert protected_after == protected_before, {
            "before": protected_before,
            "after": protected_after,
        }
        print("PASS Canonical and global mapping counts unchanged")

        print({
            "project_id": str(project_id),
            "tenant_id": tenant_id,
            "village_id": str(village_id),
            "region_system": region_system,
            "first_region": first_region,
            "second_region": second_region,
            "protected_before": protected_before,
            "protected_after": protected_after,
            "transactional_rows_before_rollback": counts,
        })
        print(
            "CORE LAYER PROJECT OVERRIDE API "
            "TRANSACTIONAL REGRESSION PASSED"
        )
        return 0
    finally:
        db.close()
        if outer_transaction.is_active:
            outer_transaction.rollback()
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())

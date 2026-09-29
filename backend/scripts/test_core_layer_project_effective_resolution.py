#!/usr/bin/env python3
"""Transactional test for effective Core-layer resolution."""

import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

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
    resolve_effective_project_core_layers,
)


def expect_http_error(status: int, detail: str, fn) -> None:
    try:
        fn()
    except HTTPException as exc:
        assert exc.status_code == status
        assert exc.detail == detail
        return
    raise AssertionError(
        f"Expected HTTP {status}: {detail}"
    )


def main() -> int:
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
    )

    try:
        fixture = db.execute(text("""
            select
              p.id::text as project_id,
              p.tenant_id,
              v.id::text as village_id,
              v.lgd_code::text as village_lgd_code
            from projects p
            cross join lateral (
              select id, lgd_code
              from geography_villages
              where is_active = true
                and lgd_code is not null
              order by id
              limit 1
            ) v
            where p.is_active = true
            order by p.id
            limit 1
        """)).mappings().one()

        project_id = UUID(fixture["project_id"])
        village_id = UUID(fixture["village_id"])
        tenant_id = fixture["tenant_id"]

        db.execute(text("""
            update projects
            set geography_scope = jsonb_build_object(
                  'village_lgd_codes',
                  jsonb_build_array(:village_lgd_code)
                ),
                updated_at = now()
            where id = :project_id
        """), {
            "project_id": str(project_id),
            "village_lgd_code":
                fixture["village_lgd_code"],
        })
        db.flush()

        baseline = resolve_effective_project_core_layers(
            db,
            tenant_id=tenant_id,
            project_id=project_id,
            village_id=village_id,
        )
        assert baseline["mode"] == (
            "READ_ONLY_PROJECT_OVERRIDE_THEN_GLOBAL_FALLBACK"
        )
        assert baseline["project_override_count"] == 0
        assert (
            baseline["guardrails"]["db_writes_attempted"]
            is False
        )
        print("PASS Global fallback baseline resolves read-only")

        region = db.execute(text("""
            select
              id::text as region_id,
              region_system
            from geography_climate_regions
            where is_active = true
              and region_system = any(:systems)
            order by region_system, region_code
            limit 1
        """), {
            "systems": sorted(
                CORE_PROJECT_OVERRIDE_REGION_SYSTEMS
            ),
        }).mappings().one()

        override_id = uuid4()
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
              'TRANSACTIONAL_TEST',
              'APPLIED',
              'ADMIN_PROJECT_REVIEW',
              'effective-resolution-test',
              'Rollback-only effective resolver fixture',
              'effective-resolution-test',
              now(),
              'effective-resolution-token',
              '{}'::jsonb,
              '{}'::jsonb,
              '{}'::jsonb,
              '{}'::jsonb,
              true,
              now(),
              now(),
              'v1.0'
            )
        """), {
            "id": str(override_id),
            "tenant_id": tenant_id,
            "project_id": str(project_id),
            "village_id": str(village_id),
            "region_id": region["region_id"],
            "region_system": region["region_system"],
        })
        db.flush()

        effective = resolve_effective_project_core_layers(
            db,
            tenant_id=tenant_id,
            project_id=project_id,
            village_id=village_id,
        )
        selected = next(
            row
            for row in effective["effective_regions"]
            if row["region_system"]
            == region["region_system"]
        )

        assert selected["resolution_source"] == (
            "PROJECT_OVERRIDE"
        )
        assert selected["override_id"] == str(override_id)
        assert selected["region_id"] == region["region_id"]
        assert effective["project_override_count"] == 1
        assert effective["precedence"][0] == (
            "PROJECT_OVERRIDE"
        )
        print("PASS Project override wins within its layer")

        other_layers = [
            row
            for row in effective["effective_regions"]
            if row["region_system"]
            != region["region_system"]
        ]
        assert all(
            row["resolution_source"]
            == "GLOBAL_MAPPING_FALLBACK"
            for row in other_layers
        )
        print("PASS Other layers retain global fallback")

        expect_http_error(
            404,
            "ACTIVE_TENANT_PROJECT_NOT_FOUND",
            lambda: resolve_effective_project_core_layers(
                db,
                tenant_id="wrong-tenant",
                project_id=project_id,
                village_id=village_id,
            ),
        )
        print("PASS Cross-tenant resolution is rejected")

        print({
            "project_id": str(project_id),
            "village_id": str(village_id),
            "override_region_system":
                region["region_system"],
            "effective_region_count":
                effective["effective_region_count"],
            "project_override_count":
                effective["project_override_count"],
            "global_fallback_count":
                effective["global_fallback_count"],
            "unresolved_region_systems":
                effective["unresolved_region_systems"],
        })
        print(
            "CORE LAYER EFFECTIVE RESOLUTION "
            "TRANSACTIONAL REGRESSION PASSED"
        )
        return 0
    finally:
        db.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())

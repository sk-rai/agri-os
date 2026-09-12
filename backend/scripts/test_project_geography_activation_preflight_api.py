#!/usr/bin/env python3
"""Regression for read-only project geography activation preflight."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

ROOT = Path.cwd()
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.database import SessionLocal
from app.main import app
from scripts.admin_auth_test_utils import (
    create_test_admin,
    delete_test_admin,
)

TENANT_ID = "default"
NAME_PREFIX = "Project Geography Activation Preflight Regression"


def check(condition: bool, label: str, detail=None) -> None:
    print(("PASS" if condition else "FAIL"), label)
    if detail is not None and not condition:
        print(json.dumps(detail, indent=2, default=str)[:5000])
    if not condition:
        raise AssertionError(label)


def protected_counts(db) -> dict:
    tables = [
        "projects",
        "project_app_config_audit_events",
        "geography_boundary_crosswalk_candidates",
        "geography_boundary_project_matches",
        "geography_boundary_runtime_sets",
        "geography_boundary_runtime_features",
        "geography_boundary_runtime_crosswalks",
    ]
    return {
        table: int(
            db.execute(
                text(f"select count(*)::bigint from {table}")
            ).scalar_one()
        )
        for table in tables
    }


def create_project(
    client,
    headers,
    name: str,
    village_lgd_code: str | None,
) -> dict:
    body = {
        "name": name,
        "description": "Temporary activation preflight fixture.",
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
        "crop_scope": ["RICE"],
        "geography_scope": (
            {"village_lgd_codes": [village_lgd_code]}
            if village_lgd_code
            else {}
        ),
    }
    if village_lgd_code:
        body["geography_scope_reason"] = (
            "Configure canonical geography for activation preflight"
        )

    response = client.post(
        "/api/v1/projects",
        headers=headers,
        json=body,
    )
    data = response.json()
    check(
        response.status_code == 201,
        f"Create fixture project: {name}",
        data,
    )
    return data


def blocker_codes(payload: dict) -> set[str]:
    return {
        blocker["code"]
        for blocker in payload["decision"]["blockers"]
    }


def main() -> int:
    print("=" * 72)
    print("PROJECT GEOGRAPHY ACTIVATION PREFLIGHT API REGRESSION")
    print("=" * 72)

    client = TestClient(app)
    db = SessionLocal()
    admin = None
    created_project_ids: list[str] = []

    try:
        eligible = db.execute(text("""
            select
              village.id::text as village_id,
              village.lgd_code::text as village_lgd_code,
              village.canonical_name as village_name
            from geography_villages village
            where village.is_active = true
              and village.lgd_code is not null
              and exists (
                select 1
                from geography_boundary_import_batches batch
                join geography_boundary_crosswalk_candidates candidate
                  on candidate.import_batch_id = batch.id
                join geography_boundary_source_features feature
                  on feature.id = candidate.source_feature_id
                where batch.source_system =
                      'NWDP_GSI_VILLAGE_BOUNDARY'
                  and candidate.proposed_village_id = village.id
                  and feature.geometry_validation_status =
                      'VALIDATED'
                  and candidate.candidate_bucket =
                      'DIRECT_VLCODE_MATCH'
                  and candidate.review_status = 'AUTO_CANDIDATE'
                  and candidate.is_active = false
                  and candidate.promotion_status = 'NOT_PROMOTED'
              )
              and not exists (
                select 1
                from geography_boundary_import_batches batch
                join geography_boundary_crosswalk_candidates candidate
                  on candidate.import_batch_id = batch.id
                where batch.source_system =
                      'NWDP_GSI_VILLAGE_BOUNDARY'
                  and candidate.proposed_village_id = village.id
                  and candidate.review_status in (
                    'MANUAL_REVIEW',
                    'BLOCKED'
                  )
                  and candidate.is_active = false
                  and candidate.promotion_status = 'NOT_PROMOTED'
              )
            order by village.lgd_code
            limit 1
        """)).mappings().first()

        missing = db.execute(text("""
            select
              village.id::text as village_id,
              village.lgd_code::text as village_lgd_code,
              village.canonical_name as village_name
            from geography_villages village
            where village.is_active = true
              and village.lgd_code is not null
              and not exists (
                select 1
                from geography_boundary_import_batches batch
                join geography_boundary_crosswalk_candidates candidate
                  on candidate.import_batch_id = batch.id
                join geography_boundary_source_features feature
                  on feature.id = candidate.source_feature_id
                where batch.source_system =
                      'NWDP_GSI_VILLAGE_BOUNDARY'
                  and candidate.proposed_village_id = village.id
                  and feature.geometry_validation_status =
                      'VALIDATED'
                  and candidate.candidate_bucket =
                      'DIRECT_VLCODE_MATCH'
                  and candidate.review_status = 'AUTO_CANDIDATE'
                  and candidate.is_active = false
                  and candidate.promotion_status = 'NOT_PROMOTED'
              )
            order by village.lgd_code
            limit 1
        """)).mappings().first()

        review_backlog = db.execute(text("""
            select
              village.id::text as village_id,
              village.lgd_code::text as village_lgd_code,
              village.canonical_name as village_name,
              candidate.review_status
            from geography_villages village
            join geography_boundary_crosswalk_candidates candidate
              on candidate.proposed_village_id = village.id
             and candidate.is_active = false
             and candidate.promotion_status = 'NOT_PROMOTED'
             and candidate.review_status in (
               'MANUAL_REVIEW',
               'BLOCKED'
             )
            join geography_boundary_import_batches batch
              on batch.id = candidate.import_batch_id
             and batch.source_system =
                 'NWDP_GSI_VILLAGE_BOUNDARY'
            where village.is_active = true
              and village.lgd_code is not null
            order by candidate.review_status, village.lgd_code
            limit 1
        """)).mappings().first()

        check(
            eligible is not None and missing is not None,
            "Eligible and missing canonical villages are available",
            {
                "eligible": dict(eligible) if eligible else None,
                "missing": dict(missing) if missing else None,
            },
        )

        admin, headers = create_test_admin(
            db,
            role="ENTERPRISE_ADMIN",
            tenant_id=TENANT_ID,
        )

        ready_project = create_project(
            client,
            headers,
            f"{NAME_PREFIX} Ready",
            eligible["village_lgd_code"],
        )
        created_project_ids.append(ready_project["id"])

        missing_project = create_project(
            client,
            headers,
            f"{NAME_PREFIX} Missing",
            missing["village_lgd_code"],
        )
        created_project_ids.append(missing_project["id"])

        empty_project = create_project(
            client,
            headers,
            f"{NAME_PREFIX} Empty",
            None,
        )
        created_project_ids.append(empty_project["id"])

        active_project = create_project(
            client,
            headers,
            f"{NAME_PREFIX} Active",
            eligible["village_lgd_code"],
        )
        created_project_ids.append(active_project["id"])

        db.execute(text("""
            update projects
            set status = 'ACTIVE'
            where id = cast(:project_id as uuid)
        """), {"project_id": active_project["id"]})
        db.commit()

        unresolved_project = create_project(
            client,
            headers,
            f"{NAME_PREFIX} Unresolved",
            None,
        )
        created_project_ids.append(unresolved_project["id"])

        db.execute(text("""
            update projects
            set geography_scope = cast(:scope as jsonb)
            where id = cast(:project_id as uuid)
        """), {
            "project_id": unresolved_project["id"],
            "scope": json.dumps({
                "source": "regression_fixture",
                "village_lgd_codes": ["999999999"],
            }),
        })
        db.commit()

        review_project = None
        if review_backlog:
            review_project = create_project(
                client,
                headers,
                f"{NAME_PREFIX} Review",
                review_backlog["village_lgd_code"],
            )
            created_project_ids.append(review_project["id"])
        else:
            print(
                "SKIP Canonical blocked/manual-review fixture "
                "(no linked candidate exists)"
            )

        before_reads = protected_counts(db)

        ready_response = client.get(
            "/api/v1/master-data/geography/projects/"
            f"{ready_project['id']}/activation-preflight",
            headers=headers,
        )
        ready_data = ready_response.json()

        check(
            ready_response.status_code == 200,
            "Ready project preflight succeeds",
            ready_data,
        )
        check(
            ready_data["schema_version"] ==
            "project_geography_activation_preflight.v1",
            "Preflight schema version is stable",
            ready_data,
        )
        check(
            ready_data["mode"] ==
            "READ_ONLY_PROJECT_ACTIVATION_PREFLIGHT",
            "Preflight declares read-only mode",
            ready_data,
        )
        check(
            ready_data["decision"]["can_activate_geography"]
            is True,
            "Fully covered planned project passes geography preflight",
            ready_data,
        )
        check(
            ready_data["decision"]["blocker_count"] == 0,
            "Ready project has no geography blockers",
            ready_data,
        )
        check(
            ready_data["summary"]["configured_village_code_count"]
            == 1
            and ready_data["summary"]["resolved_village_count"]
            == 1
            and ready_data["summary"][
                "villages_with_eligible_boundary"
            ] == 1
            and ready_data["summary"][
                "villages_without_eligible_boundary"
            ] == 0,
            "Ready project reports complete eligible coverage",
            ready_data,
        )
        check(
            ready_data["policy"]["maximum_village_count"] == 500
            and ready_data["policy"][
                "required_geometry_validation_status"
            ] == "VALIDATED"
            and ready_data["policy"]["blocked_candidates_excluded"]
            is True,
            "Preflight exposes established geography policy",
            ready_data,
        )
        check(
            ready_data["links"]["boundary_review"].endswith(
                f"project_id={ready_project['id']}"
            ),
            "Preflight exposes project boundary-review link",
            ready_data,
        )

        missing_response = client.get(
            "/api/v1/master-data/geography/projects/"
            f"{missing_project['id']}/activation-preflight",
            headers=headers,
        )
        missing_data = missing_response.json()

        check(
            missing_response.status_code == 200,
            "Missing-boundary project preflight succeeds",
            missing_data,
        )
        check(
            missing_data["decision"]["can_activate_geography"]
            is False
            and "MISSING_ELIGIBLE_BOUNDARIES"
            in blocker_codes(missing_data),
            "Missing eligible boundary blocks geography activation",
            missing_data,
        )

        empty_response = client.get(
            "/api/v1/master-data/geography/projects/"
            f"{empty_project['id']}/activation-preflight",
            headers=headers,
        )
        empty_data = empty_response.json()

        check(
            empty_response.status_code == 200,
            "Empty-scope project preflight succeeds",
            empty_data,
        )
        check(
            empty_data["decision"]["can_activate_geography"]
            is False
            and "EMPTY_GEOGRAPHY_SCOPE"
            in blocker_codes(empty_data),
            "Empty canonical scope blocks geography activation",
            empty_data,
        )

        unresolved_response = client.get(
            "/api/v1/master-data/geography/projects/"
            f"{unresolved_project['id']}/activation-preflight",
            headers=headers,
        )
        unresolved_data = unresolved_response.json()

        check(
            unresolved_response.status_code == 200,
            "Unresolved-scope project preflight succeeds",
            unresolved_data,
        )
        check(
            unresolved_data["summary"][
                "unresolved_village_code_count"
            ] == 1
            and "UNRESOLVED_VILLAGE_CODES"
            in blocker_codes(unresolved_data),
            "Unresolved canonical code blocks geography activation",
            unresolved_data,
        )

        active_response = client.get(
            "/api/v1/master-data/geography/projects/"
            f"{active_project['id']}/activation-preflight",
            headers=headers,
        )
        active_data = active_response.json()

        check(
            active_response.status_code == 200,
            "Non-planned project preflight remains readable",
            active_data,
        )
        check(
            active_data["decision"]["can_activate_geography"]
            is False
            and "PROJECT_NOT_PLANNED"
            in blocker_codes(active_data),
            "Non-planned project is not activation-ready",
            active_data,
        )

        if review_project:
            review_response = client.get(
                "/api/v1/master-data/geography/projects/"
                f"{review_project['id']}/activation-preflight",
                headers=headers,
            )
            review_data = review_response.json()
            expected_code = (
                "BLOCKED_BOUNDARY_CANDIDATES"
                if review_backlog["review_status"] == "BLOCKED"
                else "MANUAL_BOUNDARY_REVIEW_REQUIRED"
            )
            check(
                review_response.status_code == 200,
                "Review-backlog project preflight succeeds",
                review_data,
            )
            check(
                expected_code in blocker_codes(review_data)
                and review_data["decision"][
                    "can_activate_geography"
                ] is False,
                "Blocked/manual-review candidate blocks activation",
                review_data,
            )

        unknown_response = client.get(
            "/api/v1/master-data/geography/projects/"
            "00000000-0000-0000-0000-000000000000/"
            "activation-preflight",
            headers=headers,
        )
        check(
            unknown_response.status_code == 404,
            "Unknown project is rejected",
            unknown_response.json(),
        )

        wrong_tenant_headers = {
            **headers,
            "X-Tenant-ID": "not-the-project-tenant",
        }
        cross_tenant_response = client.get(
            "/api/v1/master-data/geography/projects/"
            f"{ready_project['id']}/activation-preflight",
            headers=wrong_tenant_headers,
        )
        check(
            cross_tenant_response.status_code in (403, 404),
            "Cross-tenant preflight access is rejected",
            {
                "status": cross_tenant_response.status_code,
                "body": cross_tenant_response.json(),
            },
        )

        after_reads = protected_counts(db)
        check(
            after_reads == before_reads,
            "All preflight reads perform no protected-table writes",
            {
                "before": before_reads,
                "after": after_reads,
            },
        )

        guardrails = ready_data["guardrails"]
        check(
            guardrails["database_writes_attempted"] is False
            and guardrails["project_status_changed"] is False
            and guardrails["candidate_activation_changed"] is False
            and guardrails["candidate_promotion_changed"] is False
            and guardrails["runtime_tables_written"] is False
            and guardrails["runtime_lookup_enabled"] is False
            and guardrails["android_behavior_changed"] is False,
            "Preflight preserves lifecycle and runtime guardrails",
            guardrails,
        )

        print("=" * 72)
        print(
            "PROJECT GEOGRAPHY ACTIVATION PREFLIGHT "
            "API REGRESSION PASSED"
        )
        print("=" * 72)
        return 0
    finally:
        if created_project_ids:
            db.execute(text("""
                delete from project_app_config_audit_events
                where project_id = any(
                    cast(:project_ids as uuid[])
                )
            """), {"project_ids": created_project_ids})
            db.execute(text("""
                delete from projects
                where id = any(cast(:project_ids as uuid[]))
                  and name like :name_pattern
            """), {
                "project_ids": created_project_ids,
                "name_pattern": f"{NAME_PREFIX}%",
            })
            db.commit()

        if admin is not None:
            delete_test_admin(db, admin.id)
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

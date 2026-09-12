#!/usr/bin/env python3
"""Regression for fingerprint-guarded project activation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

ROOT = Path.cwd()
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.database import SessionLocal, get_db
from app.main import app
from scripts.admin_auth_test_utils import (
    create_test_admin,
    delete_test_admin,
)

TENANT_ID = "default"
NAME_PREFIX = "Guarded Project Activation Regression"


def check(condition: bool, label: str, detail=None) -> None:
    print(("PASS" if condition else "FAIL"), label)
    if detail is not None and not condition:
        print(json.dumps(detail, indent=2, default=str)[:6000])
    if not condition:
        raise AssertionError(label)


def create_project(client, headers, name, lgd_code) -> dict:
    response = client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "name": name,
            "description": "Temporary guarded activation fixture.",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "crop_scope": ["RICE"],
            "geography_scope": {
                "village_lgd_codes": [lgd_code],
            },
            "geography_scope_reason": (
                "Configure geography for guarded activation"
            ),
        },
    )
    data = response.json()
    check(
        response.status_code == 201,
        f"Create fixture project: {name}",
        data,
    )
    return data


def preflight(client, headers, project_id) -> dict:
    response = client.get(
        "/api/v1/master-data/geography/projects/"
        f"{project_id}/activation-preflight",
        headers=headers,
    )
    data = response.json()
    check(
        response.status_code == 200,
        f"Load activation preflight for {project_id}",
        data,
    )
    return data


def project_status(db, project_id) -> str:
    db.expire_all()
    return db.execute(text("""
        select status
        from projects
        where id = cast(:project_id as uuid)
    """), {"project_id": project_id}).scalar_one()


def activation_audits(db, project_id) -> list[dict]:
    db.expire_all()
    return [
        dict(row)
        for row in db.execute(text("""
            select
              id::text,
              actor_id::text,
              action,
              patched_sections,
              before_config,
              after_config,
              config_patch,
              reason,
              created_at::text
            from project_app_config_audit_events
            where project_id = cast(:project_id as uuid)
              and action = 'ACTIVATE_PROJECT'
            order by created_at
        """), {"project_id": project_id}).mappings().all()
    ]


def runtime_counts(db) -> dict:
    tables = [
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


def main() -> int:
    print("=" * 72)
    print("GUARDED PROJECT ACTIVATION API REGRESSION")
    print("=" * 72)

    client = TestClient(app)
    db = SessionLocal()
    admin = None
    project_ids: list[str] = []

    try:
        eligible = db.execute(text("""
            select
              village.id::text as village_id,
              village.lgd_code::text as village_lgd_code
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
              village.lgd_code::text as village_lgd_code
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

        check(
            eligible is not None and missing is not None,
            "Eligible and missing activation fixtures are available",
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

        ready = create_project(
            client,
            headers,
            f"{NAME_PREFIX} Ready",
            eligible["village_lgd_code"],
        )
        blocked = create_project(
            client,
            headers,
            f"{NAME_PREFIX} Blocked",
            missing["village_lgd_code"],
        )
        completed = create_project(
            client,
            headers,
            f"{NAME_PREFIX} Completed",
            eligible["village_lgd_code"],
        )
        failure = create_project(
            client,
            headers,
            f"{NAME_PREFIX} Forced Failure",
            eligible["village_lgd_code"],
        )

        project_ids.extend([
            ready["id"],
            blocked["id"],
            completed["id"],
            failure["id"],
        ])

        db.execute(text("""
            update projects
            set status = 'COMPLETED'
            where id = cast(:project_id as uuid)
        """), {"project_id": completed["id"]})
        db.commit()

        ready_preflight = preflight(
            client,
            headers,
            ready["id"],
        )
        repeated_preflight = preflight(
            client,
            headers,
            ready["id"],
        )
        blocked_preflight = preflight(
            client,
            headers,
            blocked["id"],
        )
        failure_preflight = preflight(
            client,
            headers,
            failure["id"],
        )

        fingerprint = ready_preflight["decision"][
            "preflight_fingerprint"
        ]

        check(
            len(fingerprint) == 64
            and all(
                char in "0123456789abcdef"
                for char in fingerprint
            ),
            "Ready preflight exposes a SHA-256 fingerprint",
            ready_preflight,
        )
        check(
            repeated_preflight["decision"][
                "preflight_fingerprint"
            ] == fingerprint,
            "Unchanged preflight fingerprint is stable",
            {
                "first": fingerprint,
                "second": repeated_preflight["decision"][
                    "preflight_fingerprint"
                ],
            },
        )

        stale_response = client.post(
            f"/api/v1/projects/{ready['id']}/activate",
            headers=headers,
            json={
                "reason": "Attempt activation with stale preflight",
                "preflight_fingerprint": "0" * 64,
            },
        )
        stale_data = stale_response.json()

        check(
            stale_response.status_code == 409
            and stale_data["detail"]["error"] ==
                "STALE_PROJECT_ACTIVATION_PREFLIGHT",
            "Stale preflight fingerprint is rejected",
            stale_data,
        )
        check(
            project_status(db, ready["id"]) == "PLANNED"
            and activation_audits(db, ready["id"]) == [],
            "Stale activation performs no status or audit write",
            {
                "status": project_status(db, ready["id"]),
                "audits": activation_audits(db, ready["id"]),
            },
        )

        blocked_fingerprint = blocked_preflight["decision"][
            "preflight_fingerprint"
        ]
        blocked_response = client.post(
            f"/api/v1/projects/{blocked['id']}/activate",
            headers=headers,
            json={
                "reason": "Attempt blocked geography activation",
                "preflight_fingerprint": blocked_fingerprint,
            },
        )
        blocked_data = blocked_response.json()

        check(
            blocked_response.status_code == 409
            and blocked_data["detail"]["error"] ==
                "PROJECT_GEOGRAPHY_ACTIVATION_BLOCKED",
            "Current blocked preflight prevents activation",
            blocked_data,
        )
        check(
            project_status(db, blocked["id"]) == "PLANNED"
            and activation_audits(db, blocked["id"]) == [],
            "Blocked activation performs no lifecycle write",
            {
                "status": project_status(db, blocked["id"]),
                "audits": activation_audits(db, blocked["id"]),
            },
        )

        completed_response = client.post(
            f"/api/v1/projects/{completed['id']}/activate",
            headers=headers,
            json={
                "reason": "Attempt completed project activation",
                "preflight_fingerprint": fingerprint,
            },
        )
        completed_data = completed_response.json()

        check(
            completed_response.status_code == 409
            and completed_data["detail"]["error"] ==
                "PROJECT_STATUS_NOT_ACTIVATABLE",
            "Completed project cannot be activated",
            completed_data,
        )

        wrong_tenant_response = client.post(
            f"/api/v1/projects/{ready['id']}/activate",
            headers={
                **headers,
                "X-Tenant-ID": "not-the-project-tenant",
            },
            json={
                "reason": "Attempt cross-tenant activation",
                "preflight_fingerprint": fingerprint,
            },
        )
        check(
            wrong_tenant_response.status_code in (403, 404),
            "Cross-tenant activation is rejected",
            {
                "status": wrong_tenant_response.status_code,
                "body": wrong_tenant_response.json(),
            },
        )

        before_runtime = runtime_counts(db)

        activation_reason = (
            "Approve guarded activation after geography preflight"
        )
        activate_response = client.post(
            f"/api/v1/projects/{ready['id']}/activate",
            headers=headers,
            json={
                "reason": activation_reason,
                "preflight_fingerprint": fingerprint,
            },
        )
        activate_data = activate_response.json()

        check(
            activate_response.status_code == 200,
            "Ready project activation succeeds",
            activate_data,
        )
        check(
            activate_data["project"]["status"] == "ACTIVE"
            and activate_data["activation"]["activated"] is True
            and activate_data["activation"]["idempotent"] is False,
            "Successful activation changes only project lifecycle",
            activate_data,
        )

        audits = activation_audits(db, ready["id"])
        check(
            project_status(db, ready["id"]) == "ACTIVE"
            and len(audits) == 1,
            "Activation writes one status transition and audit",
            {
                "status": project_status(db, ready["id"]),
                "audits": audits,
            },
        )
        check(
            audits[0]["actor_id"] == str(admin.id)
            and audits[0]["action"] == "ACTIVATE_PROJECT"
            and audits[0]["reason"] == activation_reason
            and audits[0]["before_config"] == {
                "status": "PLANNED"
            }
            and audits[0]["after_config"] == {
                "status": "ACTIVE"
            },
            "Activation audit records actor, reason, and transition",
            audits[0],
        )
        check(
            audits[0]["config_patch"][
                "preflight_fingerprint"
            ] == fingerprint
            and audits[0]["config_patch"][
                "geography_summary"
            ] == ready_preflight["summary"],
            "Activation audit pins the approved geography preflight",
            audits[0],
        )

        retry_response = client.post(
            f"/api/v1/projects/{ready['id']}/activate",
            headers=headers,
            json={
                "reason": "Idempotent activation retry",
                "preflight_fingerprint": fingerprint,
            },
        )
        retry_data = retry_response.json()

        check(
            retry_response.status_code == 200
            and retry_data["activation"]["activated"] is False
            and retry_data["activation"]["idempotent"] is True,
            "Repeated activation is idempotent",
            retry_data,
        )
        check(
            len(activation_audits(db, ready["id"])) == 1,
            "Idempotent retry writes no duplicate audit",
            activation_audits(db, ready["id"]),
        )

        after_runtime = runtime_counts(db)
        check(
            after_runtime == before_runtime,
            "Activation leaves boundary and runtime tables unchanged",
            {
                "before": before_runtime,
                "after": after_runtime,
            },
        )

        guardrails = activate_data["guardrails"]
        check(
            guardrails["boundary_candidates_activated"] is False
            and guardrails["boundary_candidates_promoted"] is False
            and guardrails["runtime_tables_written"] is False
            and guardrails["runtime_lookup_enabled"] is False
            and guardrails["android_behavior_changed"] is False,
            "Activation response preserves runtime guardrails",
            guardrails,
        )

        failure_fingerprint = failure_preflight["decision"][
            "preflight_fingerprint"
        ]
        failure_db = SessionLocal()
        original_commit = failure_db.commit

        def override_db():
            try:
                yield failure_db
            finally:
                pass

        def forced_commit_failure():
            raise RuntimeError(
                "forced project activation commit failure"
            )

        app.dependency_overrides[get_db] = override_db
        failure_db.commit = forced_commit_failure

        try:
            failure_client = TestClient(
                app,
                raise_server_exceptions=False,
            )
            failure_response = failure_client.post(
                f"/api/v1/projects/{failure['id']}/activate",
                headers=headers,
                json={
                    "reason": "Exercise atomic activation rollback",
                    "preflight_fingerprint": failure_fingerprint,
                },
            )
        finally:
            failure_db.commit = original_commit
            failure_db.rollback()
            failure_db.close()
            app.dependency_overrides.pop(get_db, None)

        check(
            failure_response.status_code == 500,
            "Forced activation commit failure is surfaced",
            {
                "status": failure_response.status_code,
                "body": failure_response.text[:1000],
            },
        )
        check(
            project_status(db, failure["id"]) == "PLANNED"
            and activation_audits(db, failure["id"]) == [],
            "Forced failure rolls back status and audit atomically",
            {
                "status": project_status(db, failure["id"]),
                "audits": activation_audits(db, failure["id"]),
            },
        )

        print("=" * 72)
        print("GUARDED PROJECT ACTIVATION API REGRESSION PASSED")
        print("=" * 72)
        return 0
    finally:
        app.dependency_overrides.pop(get_db, None)

        if project_ids:
            db.execute(text("""
                delete from project_app_config_audit_events
                where project_id = any(
                    cast(:project_ids as uuid[])
                )
            """), {"project_ids": project_ids})
            db.execute(text("""
                delete from projects
                where id = any(cast(:project_ids as uuid[]))
                  and name like :name_pattern
            """), {
                "project_ids": project_ids,
                "name_pattern": f"{NAME_PREFIX}%",
            })
            db.commit()

        if admin is not None:
            delete_test_admin(db, admin.id)
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

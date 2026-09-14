#!/usr/bin/env python3
"""Regression for fingerprint-guarded project deactivation."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

ROOT = Path.cwd()
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.database import SessionLocal, get_db
from app.main import app
from app.modules.farmer.models import ProjectRole
from scripts.admin_auth_test_utils import (
    create_test_admin,
    delete_test_admin,
)

TENANT_ID = "default"
NAME_PREFIX = "Guarded Project Deactivation Regression"


def check(condition: bool, label: str, detail=None) -> None:
    print(("PASS" if condition else "FAIL"), label)
    if detail is not None and not condition:
        print(json.dumps(detail, indent=2, default=str)[:8000])
    if not condition:
        raise AssertionError(label)


def create_project(client, headers, name, lgd_code) -> dict:
    response = client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "name": name,
            "description": (
                "Temporary guarded project deactivation fixture."
            ),
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "crop_scope": ["RICE"],
            "geography_scope": {
                "village_lgd_codes": [lgd_code],
            },
            "geography_scope_reason": (
                "Configure geography for guarded deactivation"
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


def activation_preflight(client, headers, project_id) -> dict:
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


def activate(client, headers, project_id) -> dict:
    preflight = activation_preflight(
        client,
        headers,
        project_id,
    )
    response = client.post(
        f"/api/v1/projects/{project_id}/activate",
        headers=headers,
        json={
            "reason": (
                "Activate fixture before guarded deactivation"
            ),
            "preflight_fingerprint": preflight["decision"][
                "preflight_fingerprint"
            ],
        },
    )
    data = response.json()
    check(
        response.status_code == 200
        and data["project"]["status"] == "ACTIVE",
        f"Activate fixture project: {project_id}",
        data,
    )
    return data


def deactivation_preflight(
    client,
    headers,
    project_id,
) -> dict:
    response = client.get(
        f"/api/v1/projects/{project_id}/deactivation-preflight",
        headers=headers,
    )
    data = response.json()
    check(
        response.status_code == 200,
        f"Load deactivation preflight for {project_id}",
        data,
    )
    return data


def project_status(db, project_id) -> str:
    db.expire_all()
    return db.execute(
        text("""
            select status
            from projects
            where id = cast(:project_id as uuid)
        """),
        {"project_id": project_id},
    ).scalar_one()


def lifecycle_audits(db, project_id) -> list[dict]:
    db.expire_all()
    return [
        dict(row)
        for row in db.execute(
            text("""
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
                  and action in (
                    'ACTIVATE_PROJECT',
                    'DEACTIVATE_PROJECT'
                  )
                order by created_at, id
            """),
            {"project_id": project_id},
        ).mappings().all()
    ]


def deactivation_audits(db, project_id) -> list[dict]:
    return [
        event
        for event in lifecycle_audits(db, project_id)
        if event["action"] == "DEACTIVATE_PROJECT"
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
    print("GUARDED PROJECT DEACTIVATION API REGRESSION")
    print("=" * 72)

    client = TestClient(app)
    db = SessionLocal()
    admin = None
    project_ids: list[str] = []
    role_ids: list[uuid.UUID] = []

    try:
        eligible = db.execute(
            text("""
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
            """)
        ).mappings().first()

        check(
            eligible is not None,
            "Eligible activation fixture is available",
            dict(eligible) if eligible else None,
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
            eligible["village_lgd_code"],
        )
        planned = create_project(
            client,
            headers,
            f"{NAME_PREFIX} Never Active",
            eligible["village_lgd_code"],
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
            planned["id"],
            completed["id"],
            failure["id"],
        ])

        activate(client, headers, ready["id"])
        activate(client, headers, blocked["id"])
        activate(client, headers, failure["id"])

        db.execute(
            text("""
                update projects
                set status = 'COMPLETED'
                where id = cast(:project_id as uuid)
            """),
            {"project_id": completed["id"]},
        )
        db.commit()

        ready_preflight = deactivation_preflight(
            client,
            headers,
            ready["id"],
        )
        repeated_preflight = deactivation_preflight(
            client,
            headers,
            ready["id"],
        )

        fingerprint = ready_preflight["decision"][
            "preflight_fingerprint"
        ]

        check(
            ready_preflight["schema_version"] ==
                "project_deactivation_preflight.v2"
            and len(fingerprint) == 64
            and all(
                char in "0123456789abcdef"
                for char in fingerprint
            ),
            "Ready preflight exposes a stable SHA-256 fingerprint",
            ready_preflight,
        )
        check(
            repeated_preflight["decision"][
                "preflight_fingerprint"
            ] == fingerprint,
            "Unchanged deactivation fingerprint is stable",
            {
                "first": fingerprint,
                "second": repeated_preflight["decision"][
                    "preflight_fingerprint"
                ],
            },
        )
        check(
            ready_preflight["decision"]["can_deactivate"] is True
            and ready_preflight["decision"][
                "deactivation_supported"
            ] is True
            and ready_preflight["decision"]["blocker_count"] == 0,
            "Clean active project is deactivation-ready",
            ready_preflight,
        )

        stale_response = client.post(
            f"/api/v1/projects/{ready['id']}/deactivate",
            headers=headers,
            json={
                "reason": "Attempt stale project deactivation",
                "preflight_fingerprint": "0" * 64,
            },
        )
        stale_data = stale_response.json()

        check(
            stale_response.status_code == 409
            and stale_data["detail"]["error"] ==
                "STALE_PROJECT_DEACTIVATION_PREFLIGHT",
            "Stale deactivation fingerprint is rejected",
            stale_data,
        )
        check(
            project_status(db, ready["id"]) == "ACTIVE"
            and deactivation_audits(db, ready["id"]) == [],
            "Stale deactivation performs no lifecycle write",
            {
                "status": project_status(db, ready["id"]),
                "audits": deactivation_audits(
                    db,
                    ready["id"],
                ),
            },
        )

        blocked_role_id = uuid.uuid4()
        role_ids.append(blocked_role_id)
        db.add(
            ProjectRole(
                id=blocked_role_id,
                project_id=uuid.UUID(blocked["id"]),
                user_id=admin.id,
                role="MANAGER",
                territory_scope={},
                is_active=True,
            )
        )
        db.commit()

        blocked_preflight = deactivation_preflight(
            client,
            headers,
            blocked["id"],
        )
        blocked_fingerprint = blocked_preflight["decision"][
            "preflight_fingerprint"
        ]

        check(
            blocked_preflight["decision"]["can_deactivate"]
                is False
            and any(
                blocker["code"] == "PROJECT_ROLES_ASSIGNED"
                and blocker["count"] == 1
                for blocker in blocked_preflight["decision"][
                    "blockers"
                ]
            ),
            "Operational project role blocks deactivation",
            blocked_preflight,
        )

        blocked_response = client.post(
            f"/api/v1/projects/{blocked['id']}/deactivate",
            headers=headers,
            json={
                "reason": "Attempt operationally blocked deactivation",
                "preflight_fingerprint": blocked_fingerprint,
            },
        )
        blocked_data = blocked_response.json()

        check(
            blocked_response.status_code == 409
            and blocked_data["detail"]["error"] ==
                "PROJECT_DEACTIVATION_BLOCKED",
            "Current operational blockers prevent deactivation",
            blocked_data,
        )
        check(
            project_status(db, blocked["id"]) == "ACTIVE"
            and deactivation_audits(db, blocked["id"]) == [],
            "Blocked deactivation performs no lifecycle write",
            {
                "status": project_status(db, blocked["id"]),
                "audits": deactivation_audits(
                    db,
                    blocked["id"],
                ),
            },
        )

        never_active_response = client.post(
            f"/api/v1/projects/{planned['id']}/deactivate",
            headers=headers,
            json={
                "reason": "Attempt never-active project deactivation",
                "preflight_fingerprint": fingerprint,
            },
        )
        never_active_data = never_active_response.json()

        check(
            never_active_response.status_code == 409
            and never_active_data["detail"]["error"] ==
                "PROJECT_STATUS_NOT_DEACTIVATABLE",
            "Never-active planned project is not idempotent",
            never_active_data,
        )

        completed_response = client.post(
            f"/api/v1/projects/{completed['id']}/deactivate",
            headers=headers,
            json={
                "reason": "Attempt completed project deactivation",
                "preflight_fingerprint": fingerprint,
            },
        )
        completed_data = completed_response.json()

        check(
            completed_response.status_code == 409
            and completed_data["detail"]["error"] ==
                "PROJECT_STATUS_NOT_DEACTIVATABLE",
            "Completed project cannot be deactivated",
            completed_data,
        )

        wrong_tenant_response = client.post(
            f"/api/v1/projects/{ready['id']}/deactivate",
            headers={
                **headers,
                "X-Tenant-ID": "not-the-project-tenant",
            },
            json={
                "reason": "Attempt cross-tenant deactivation",
                "preflight_fingerprint": fingerprint,
            },
        )

        check(
            wrong_tenant_response.status_code in (403, 404),
            "Cross-tenant deactivation is rejected",
            {
                "status": wrong_tenant_response.status_code,
                "body": wrong_tenant_response.text[:1000],
            },
        )

        before_runtime = runtime_counts(db)
        deactivation_reason = (
            "Return project to planning after operational review"
        )

        deactivate_response = client.post(
            f"/api/v1/projects/{ready['id']}/deactivate",
            headers=headers,
            json={
                "reason": deactivation_reason,
                "preflight_fingerprint": fingerprint,
            },
        )
        deactivate_data = deactivate_response.json()

        check(
            deactivate_response.status_code == 200,
            "Ready project deactivation succeeds",
            deactivate_data,
        )
        check(
            deactivate_data["project"]["status"] == "PLANNED"
            and deactivate_data["deactivation"][
                "deactivated"
            ] is True
            and deactivate_data["deactivation"][
                "idempotent"
            ] is False,
            "Successful deactivation changes only lifecycle status",
            deactivate_data,
        )

        audits = deactivation_audits(db, ready["id"])
        check(
            project_status(db, ready["id"]) == "PLANNED"
            and len(audits) == 1,
            "Deactivation writes one immutable lifecycle event",
            {
                "status": project_status(db, ready["id"]),
                "audits": audits,
            },
        )

        audit = audits[0]
        check(
            audit["actor_id"] == str(admin.id)
            and audit["action"] == "DEACTIVATE_PROJECT"
            and audit["patched_sections"] == ["status"]
            and audit["before_config"] == {
                "status": "ACTIVE"
            }
            and audit["after_config"] == {
                "status": "PLANNED"
            }
            and audit["reason"] == deactivation_reason,
            "Deactivation audit records actor and transition",
            audit,
        )
        check(
            audit["config_patch"][
                "preflight_fingerprint"
            ] == fingerprint
            and audit["config_patch"][
                "deactivation_summary"
            ]["operational_counts"] ==
                ready_preflight["operational_counts"]
            and audit["config_patch"][
                "deactivation_summary"
            ]["blockers"] == [],
            "Deactivation audit pins approved preflight evidence",
            audit,
        )

        history_response = client.get(
            f"/api/v1/projects/{ready['id']}/lifecycle/audit",
            headers=headers,
        )
        history = history_response.json()

        check(
            history_response.status_code == 200
            and history["count"] == 2,
            "Lifecycle history includes activation and deactivation",
            history,
        )
        check(
            history["events"][0]["action"] ==
                "DEACTIVATE_PROJECT"
            and history["events"][0]["transition"] == {
                "from_status": "ACTIVE",
                "to_status": "PLANNED",
            }
            and history["events"][0][
                "preflight_fingerprint"
            ] == fingerprint,
            "Newest lifecycle event exposes deactivation evidence",
            history,
        )

        retry_response = client.post(
            f"/api/v1/projects/{ready['id']}/deactivate",
            headers=headers,
            json={
                "reason": "Idempotent deactivation retry",
                "preflight_fingerprint": fingerprint,
            },
        )
        retry_data = retry_response.json()

        check(
            retry_response.status_code == 200
            and retry_data["deactivation"][
                "deactivated"
            ] is False
            and retry_data["deactivation"][
                "idempotent"
            ] is True
            and retry_data["deactivation"][
                "audit_event_id"
            ] == str(audit["id"]),
            "Repeated successful deactivation is idempotent",
            retry_data,
        )
        check(
            len(deactivation_audits(db, ready["id"])) == 1,
            "Idempotent retry writes no duplicate audit",
            deactivation_audits(db, ready["id"]),
        )

        after_runtime = runtime_counts(db)
        check(
            after_runtime == before_runtime,
            "Deactivation leaves boundary and runtime tables unchanged",
            {
                "before": before_runtime,
                "after": after_runtime,
            },
        )

        guardrails = deactivate_data["guardrails"]
        check(
            guardrails["boundary_assignments_changed"] is False
            and guardrails[
                "boundary_candidates_activated"
            ] is False
            and guardrails[
                "boundary_candidates_promoted"
            ] is False
            and guardrails["runtime_tables_written"] is False
            and guardrails["runtime_lookup_enabled"] is False
            and guardrails["android_behavior_changed"] is False,
            "Deactivation response preserves runtime guardrails",
            guardrails,
        )

        failure_preflight = deactivation_preflight(
            client,
            headers,
            failure["id"],
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
                "forced project deactivation commit failure"
            )

        app.dependency_overrides[get_db] = override_db
        failure_db.commit = forced_commit_failure

        try:
            failure_client = TestClient(
                app,
                raise_server_exceptions=False,
            )
            failure_response = failure_client.post(
                f"/api/v1/projects/{failure['id']}/deactivate",
                headers=headers,
                json={
                    "reason": (
                        "Exercise atomic deactivation rollback"
                    ),
                    "preflight_fingerprint":
                        failure_fingerprint,
                },
            )
        finally:
            failure_db.commit = original_commit
            failure_db.rollback()
            failure_db.close()
            app.dependency_overrides.pop(get_db, None)

        check(
            failure_response.status_code == 500,
            "Forced deactivation commit failure is surfaced",
            {
                "status": failure_response.status_code,
                "body": failure_response.text[:1000],
            },
        )
        check(
            project_status(db, failure["id"]) == "ACTIVE"
            and deactivation_audits(
                db,
                failure["id"],
            ) == [],
            "Forced failure rolls back status and audit atomically",
            {
                "status": project_status(db, failure["id"]),
                "audits": deactivation_audits(
                    db,
                    failure["id"],
                ),
            },
        )

        print("=" * 72)
        print("GUARDED PROJECT DEACTIVATION API REGRESSION PASSED")
        print("=" * 72)
        return 0
    finally:
        app.dependency_overrides.pop(get_db, None)

        if role_ids:
            db.query(ProjectRole).filter(
                ProjectRole.id.in_(role_ids)
            ).delete(synchronize_session=False)
            db.commit()

        if project_ids:
            db.execute(
                text("""
                    delete from project_app_config_audit_events
                    where project_id = any(
                        cast(:project_ids as uuid[])
                    )
                """),
                {"project_ids": project_ids},
            )
            db.execute(
                text("""
                    delete from projects
                    where id = any(cast(:project_ids as uuid[]))
                      and name like :name_pattern
                """),
                {
                    "project_ids": project_ids,
                    "name_pattern": f"{NAME_PREFIX}%",
                },
            )
            db.commit()

        if admin is not None:
            delete_test_admin(db, admin.id)

        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

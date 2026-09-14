#!/usr/bin/env python3
"""Regression for fingerprint-guarded project completion."""

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
from app.modules.farmer.models import (
    Farmer,
    FarmerProjectEnrollment,
)
from scripts.admin_auth_test_utils import (
    create_test_admin,
    delete_test_admin,
)

TENANT_ID = "default"
NAME_PREFIX = "Guarded Project Completion Regression"


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
                "Temporary guarded project completion fixture."
            ),
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "crop_scope": ["RICE"],
            "geography_scope": {
                "village_lgd_codes": [lgd_code],
            },
            "geography_scope_reason": (
                "Configure geography for guarded completion"
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
                "Activate fixture before guarded completion"
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


def completion_preflight(
    client,
    headers,
    project_id,
) -> dict:
    response = client.get(
        f"/api/v1/projects/{project_id}/completion-preflight",
        headers=headers,
    )
    data = response.json()
    check(
        response.status_code == 200,
        f"Load completion preflight for {project_id}",
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
                    'COMPLETE_PROJECT'
                  )
                order by created_at, id
            """),
            {"project_id": project_id},
        ).mappings().all()
    ]


def completion_audits(db, project_id) -> list[dict]:
    return [
        event
        for event in lifecycle_audits(db, project_id)
        if event["action"] == "COMPLETE_PROJECT"
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
    print("GUARDED PROJECT COMPLETION API REGRESSION")
    print("=" * 72)

    client = TestClient(app)
    db = SessionLocal()
    admin = None
    project_ids: list[str] = []
    farmer_ids: list[uuid.UUID] = []
    enrollment_ids: list[uuid.UUID] = []

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

        ready_preflight = completion_preflight(
            client,
            headers,
            ready["id"],
        )
        repeated_preflight = completion_preflight(
            client,
            headers,
            ready["id"],
        )

        fingerprint = ready_preflight["decision"][
            "preflight_fingerprint"
        ]

        check(
            ready_preflight["schema_version"] ==
                "project_completion_preflight.v1"
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
            "Unchanged completion fingerprint is stable",
            {
                "first": fingerprint,
                "second": repeated_preflight["decision"][
                    "preflight_fingerprint"
                ],
            },
        )
        check(
            ready_preflight["decision"]["can_complete"] is True
            and ready_preflight["decision"][
                "completion_supported"
            ] is True
            and ready_preflight["decision"]["blocker_count"] == 0,
            "Clean active project is completion-ready",
            ready_preflight,
        )

        stale_response = client.post(
            f"/api/v1/projects/{ready['id']}/complete",
            headers=headers,
            json={
                "reason": "Attempt stale project completion",
                "preflight_fingerprint": "0" * 64,
            },
        )
        stale_data = stale_response.json()

        check(
            stale_response.status_code == 409
            and stale_data["detail"]["error"] ==
                "STALE_PROJECT_COMPLETION_PREFLIGHT",
            "Stale completion fingerprint is rejected",
            stale_data,
        )
        check(
            project_status(db, ready["id"]) == "ACTIVE"
            and completion_audits(db, ready["id"]) == [],
            "Stale completion performs no lifecycle write",
            {
                "status": project_status(db, ready["id"]),
                "audits": completion_audits(
                    db,
                    ready["id"],
                ),
            },
        )

        blocked_farmer_id = uuid.uuid4()
        blocked_enrollment_id = uuid.uuid4()
        farmer_ids.append(blocked_farmer_id)
        enrollment_ids.append(blocked_enrollment_id)

        db.add(
            Farmer(
                id=blocked_farmer_id,
                tenant_id=TENANT_ID,
                project_id=uuid.UUID(blocked["id"]),
                mobile_number="+919700000001",
                village_id=uuid.UUID(eligible["village_id"]),
                primary_crop_code="RICE",
                display_name="Completion regression farmer",
                status="ACTIVE",
                is_active=True,
            )
        )
        db.flush()

        db.add(
            FarmerProjectEnrollment(
                id=blocked_enrollment_id,
                tenant_id=TENANT_ID,
                farmer_id=blocked_farmer_id,
                project_id=uuid.UUID(blocked["id"]),
                enrollment_method="WEB_ADMIN",
                enrollment_source="completion_regression",
                enrolled_by=admin.id,
                status="ACTIVE",
                parcel_ids=[],
                assigned_user_ids=[],
                metadata_={},
                is_active=True,
            )
        )
        db.commit()

        blocked_preflight = completion_preflight(
            client,
            headers,
            blocked["id"],
        )
        blocked_fingerprint = blocked_preflight["decision"][
            "preflight_fingerprint"
        ]

        check(
            blocked_preflight["decision"]["can_complete"]
                is False
            and any(
                blocker["code"] == "UNFINISHED_ENROLLMENTS"
                and blocker["count"] == 1
                for blocker in blocked_preflight["decision"][
                    "blockers"
                ]
            ),
            "Active farmer enrollment blocks completion",
            blocked_preflight,
        )

        blocked_response = client.post(
            f"/api/v1/projects/{blocked['id']}/complete",
            headers=headers,
            json={
                "reason": "Attempt operationally blocked completion",
                "preflight_fingerprint": blocked_fingerprint,
            },
        )
        blocked_data = blocked_response.json()

        check(
            blocked_response.status_code == 409
            and blocked_data["detail"]["error"] ==
                "PROJECT_COMPLETION_BLOCKED",
            "Current operational blockers prevent completion",
            blocked_data,
        )
        check(
            project_status(db, blocked["id"]) == "ACTIVE"
            and completion_audits(db, blocked["id"]) == [],
            "Blocked completion performs no lifecycle write",
            {
                "status": project_status(db, blocked["id"]),
                "audits": completion_audits(
                    db,
                    blocked["id"],
                ),
            },
        )

        never_active_response = client.post(
            f"/api/v1/projects/{planned['id']}/complete",
            headers=headers,
            json={
                "reason": "Attempt never-active project completion",
                "preflight_fingerprint": fingerprint,
            },
        )
        never_active_data = never_active_response.json()

        check(
            never_active_response.status_code == 409
            and never_active_data["detail"]["error"] ==
                "PROJECT_STATUS_NOT_COMPLETABLE",
            "Never-active planned project is not idempotent",
            never_active_data,
        )

        completed_response = client.post(
            f"/api/v1/projects/{completed['id']}/complete",
            headers=headers,
            json={
                "reason": "Attempt completed project completion",
                "preflight_fingerprint": fingerprint,
            },
        )
        completed_data = completed_response.json()

        check(
            completed_response.status_code == 409
            and completed_data["detail"]["error"] ==
                "PROJECT_STATUS_NOT_COMPLETABLE",
            "Completed project cannot be completed",
            completed_data,
        )

        wrong_tenant_response = client.post(
            f"/api/v1/projects/{ready['id']}/complete",
            headers={
                **headers,
                "X-Tenant-ID": "not-the-project-tenant",
            },
            json={
                "reason": "Attempt cross-tenant completion",
                "preflight_fingerprint": fingerprint,
            },
        )

        check(
            wrong_tenant_response.status_code in (403, 404),
            "Cross-tenant completion is rejected",
            {
                "status": wrong_tenant_response.status_code,
                "body": wrong_tenant_response.text[:1000],
            },
        )

        before_runtime = runtime_counts(db)
        completion_reason = (
            "Complete project after all operational work is terminal"
        )

        completion_response = client.post(
            f"/api/v1/projects/{ready['id']}/complete",
            headers=headers,
            json={
                "reason": completion_reason,
                "preflight_fingerprint": fingerprint,
            },
        )
        completion_data = completion_response.json()

        check(
            completion_response.status_code == 200,
            "Ready project completion succeeds",
            completion_data,
        )
        check(
            completion_data["project"]["status"] == "COMPLETED"
            and completion_data["completion"][
                "completed"
            ] is True
            and completion_data["completion"][
                "idempotent"
            ] is False,
            "Successful completion changes only lifecycle status",
            completion_data,
        )

        audits = completion_audits(db, ready["id"])
        check(
            project_status(db, ready["id"]) == "COMPLETED"
            and len(audits) == 1,
            "Completion writes one immutable lifecycle event",
            {
                "status": project_status(db, ready["id"]),
                "audits": audits,
            },
        )

        audit = audits[0]
        check(
            audit["actor_id"] == str(admin.id)
            and audit["action"] == "COMPLETE_PROJECT"
            and audit["patched_sections"] == ["status"]
            and audit["before_config"] == {
                "status": "ACTIVE"
            }
            and audit["after_config"] == {
                "status": "COMPLETED"
            }
            and audit["reason"] == completion_reason,
            "Completion audit records actor and transition",
            audit,
        )
        check(
            audit["config_patch"][
                "preflight_fingerprint"
            ] == fingerprint
            and audit["config_patch"][
                "completion_summary"
            ]["operational_counts"] ==
                ready_preflight["operational_counts"]
            and audit["config_patch"][
                "completion_summary"
            ]["blockers"] == [],
            "Completion audit pins approved preflight evidence",
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
            "Lifecycle history includes activation and completion",
            history,
        )
        check(
            history["events"][0]["action"] ==
                "COMPLETE_PROJECT"
            and history["events"][0]["transition"] == {
                "from_status": "ACTIVE",
                "to_status": "COMPLETED",
            }
            and history["events"][0][
                "preflight_fingerprint"
            ] == fingerprint,
            "Newest lifecycle event exposes completion evidence",
            history,
        )

        retry_response = client.post(
            f"/api/v1/projects/{ready['id']}/complete",
            headers=headers,
            json={
                "reason": "Idempotent completion retry",
                "preflight_fingerprint": fingerprint,
            },
        )
        retry_data = retry_response.json()

        check(
            retry_response.status_code == 200
            and retry_data["completion"][
                "completed"
            ] is False
            and retry_data["completion"][
                "idempotent"
            ] is True
            and retry_data["completion"][
                "audit_event_id"
            ] == str(audit["id"]),
            "Repeated successful completion is idempotent",
            retry_data,
        )
        check(
            len(completion_audits(db, ready["id"])) == 1,
            "Idempotent retry writes no duplicate audit",
            completion_audits(db, ready["id"]),
        )

        after_runtime = runtime_counts(db)
        check(
            after_runtime == before_runtime,
            "Completion leaves boundary and runtime tables unchanged",
            {
                "before": before_runtime,
                "after": after_runtime,
            },
        )

        guardrails = completion_data["guardrails"]
        check(
            guardrails["operational_records_changed"] is False
            and guardrails["boundary_assignments_changed"] is False
            and guardrails[
                "boundary_candidates_activated"
            ] is False
            and guardrails[
                "boundary_candidates_promoted"
            ] is False
            and guardrails["runtime_tables_written"] is False
            and guardrails["runtime_lookup_enabled"] is False
            and guardrails["android_behavior_changed"] is False,
            "Completion response preserves runtime guardrails",
            guardrails,
        )

        failure_preflight = completion_preflight(
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
                "forced project completion commit failure"
            )

        app.dependency_overrides[get_db] = override_db
        failure_db.commit = forced_commit_failure

        try:
            failure_client = TestClient(
                app,
                raise_server_exceptions=False,
            )
            failure_response = failure_client.post(
                f"/api/v1/projects/{failure['id']}/complete",
                headers=headers,
                json={
                    "reason": (
                        "Exercise atomic completion rollback"
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
            "Forced completion commit failure is surfaced",
            {
                "status": failure_response.status_code,
                "body": failure_response.text[:1000],
            },
        )
        check(
            project_status(db, failure["id"]) == "ACTIVE"
            and completion_audits(
                db,
                failure["id"],
            ) == [],
            "Forced failure rolls back status and audit atomically",
            {
                "status": project_status(db, failure["id"]),
                "audits": completion_audits(
                    db,
                    failure["id"],
                ),
            },
        )

        print("=" * 72)
        print("GUARDED PROJECT COMPLETION API REGRESSION PASSED")
        print("=" * 72)
        return 0
    finally:
        app.dependency_overrides.pop(get_db, None)

        if enrollment_ids:
            db.query(FarmerProjectEnrollment).filter(
                FarmerProjectEnrollment.id.in_(enrollment_ids)
            ).delete(synchronize_session=False)
            db.commit()

        if farmer_ids:
            db.query(Farmer).filter(
                Farmer.id.in_(farmer_ids)
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

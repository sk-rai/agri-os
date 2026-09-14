#!/usr/bin/env python3
"""Regression for fingerprint-guarded project archive and restore."""

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
NAME_PREFIX = "Guarded Project Archive Restore Regression"


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
                "Temporary guarded project archive fixture."
            ),
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "crop_scope": ["RICE"],
            "geography_scope": {
                "village_lgd_codes": [lgd_code],
            },
            "geography_scope_reason": (
                "Configure geography for guarded archive"
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
                "Activate fixture before guarded archive"
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


def archive_preflight(
    client,
    headers,
    project_id,
) -> dict:
    response = client.get(
        f"/api/v1/projects/{project_id}/archive-preflight",
        headers=headers,
    )
    data = response.json()
    check(
        response.status_code == 200,
        f"Load archive preflight for {project_id}",
        data,
    )
    return data


def restore_preflight(
    client,
    headers,
    project_id,
) -> dict:
    response = client.get(
        f"/api/v1/projects/{project_id}/restore-preflight",
        headers=headers,
    )
    data = response.json()
    check(
        response.status_code == 200,
        f"Load restore preflight for {project_id}",
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
                    'ARCHIVE_PROJECT',
                    'RESTORE_PROJECT'
                  )
                order by created_at, id
            """),
            {"project_id": project_id},
        ).mappings().all()
    ]


def archive_audits(db, project_id) -> list[dict]:
    return [
        event
        for event in lifecycle_audits(db, project_id)
        if event["action"] == "ARCHIVE_PROJECT"
    ]


def restore_audits(db, project_id) -> list[dict]:
    return [
        event
        for event in lifecycle_audits(db, project_id)
        if event["action"] == "RESTORE_PROJECT"
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
    print("GUARDED PROJECT ARCHIVE AND RESTORE API REGRESSION")
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
        archived = create_project(
            client,
            headers,
            f"{NAME_PREFIX} Archived",
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
            archived["id"],
            failure["id"],
        ])

        activate(client, headers, ready["id"])
        activate(client, headers, blocked["id"])
        activate(client, headers, failure["id"])

        db.execute(
            text("""
                update projects
                set status = 'COMPLETED'
                where id = any(cast(:project_ids as uuid[]))
            """),
            {
                "project_ids": [
                    ready["id"],
                    blocked["id"],
                    failure["id"],
                ],
            },
        )
        db.execute(
            text("""
                update projects
                set status = 'ARCHIVED'
                where id = cast(:project_id as uuid)
            """),
            {"project_id": archived["id"]},
        )
        db.commit()

        ready_preflight = archive_preflight(
            client,
            headers,
            ready["id"],
        )
        repeated_preflight = archive_preflight(
            client,
            headers,
            ready["id"],
        )

        fingerprint = ready_preflight["decision"][
            "preflight_fingerprint"
        ]

        check(
            ready_preflight["schema_version"] ==
                "project_archive_preflight.v1"
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
            "Unchanged archive fingerprint is stable",
            {
                "first": fingerprint,
                "second": repeated_preflight["decision"][
                    "preflight_fingerprint"
                ],
            },
        )
        check(
            ready_preflight["decision"]["can_archive"] is True
            and ready_preflight["decision"][
                "archive_supported"
            ] is True
            and ready_preflight["decision"]["blocker_count"] == 0,
            "Clean completed project is archive-ready",
            ready_preflight,
        )

        stale_response = client.post(
            f"/api/v1/projects/{ready['id']}/archive",
            headers=headers,
            json={
                "reason": "Attempt stale project archive",
                "preflight_fingerprint": "0" * 64,
            },
        )
        stale_data = stale_response.json()

        check(
            stale_response.status_code == 409
            and stale_data["detail"]["error"] ==
                "STALE_PROJECT_ARCHIVE_PREFLIGHT",
            "Stale archive fingerprint is rejected",
            stale_data,
        )
        check(
            project_status(db, ready["id"]) == "COMPLETED"
            and archive_audits(db, ready["id"]) == [],
            "Stale archive performs no lifecycle write",
            {
                "status": project_status(db, ready["id"]),
                "audits": archive_audits(
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
                display_name="Archive regression farmer",
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
                enrollment_source="archive_regression",
                enrolled_by=admin.id,
                status="ACTIVE",
                parcel_ids=[],
                assigned_user_ids=[],
                metadata_={},
                is_active=True,
            )
        )
        db.commit()

        blocked_preflight = archive_preflight(
            client,
            headers,
            blocked["id"],
        )
        blocked_fingerprint = blocked_preflight["decision"][
            "preflight_fingerprint"
        ]

        check(
            blocked_preflight["decision"]["can_archive"]
                is False
            and any(
                blocker["code"] == "UNFINISHED_ENROLLMENTS"
                and blocker["count"] == 1
                for blocker in blocked_preflight["decision"][
                    "blockers"
                ]
            ),
            "Active farmer enrollment blocks archive",
            blocked_preflight,
        )

        blocked_response = client.post(
            f"/api/v1/projects/{blocked['id']}/archive",
            headers=headers,
            json={
                "reason": "Attempt operationally blocked archive",
                "preflight_fingerprint": blocked_fingerprint,
            },
        )
        blocked_data = blocked_response.json()

        check(
            blocked_response.status_code == 409
            and blocked_data["detail"]["error"] ==
                "PROJECT_ARCHIVE_BLOCKED",
            "Current operational blockers prevent archive",
            blocked_data,
        )
        check(
            project_status(db, blocked["id"]) == "COMPLETED"
            and archive_audits(db, blocked["id"]) == [],
            "Blocked archive performs no lifecycle write",
            {
                "status": project_status(db, blocked["id"]),
                "audits": archive_audits(
                    db,
                    blocked["id"],
                ),
            },
        )

        never_active_response = client.post(
            f"/api/v1/projects/{planned['id']}/archive",
            headers=headers,
            json={
                "reason": "Attempt never-active project archive",
                "preflight_fingerprint": fingerprint,
            },
        )
        never_active_data = never_active_response.json()

        check(
            never_active_response.status_code == 409
            and never_active_data["detail"]["error"] ==
                "PROJECT_STATUS_NOT_ARCHIVABLE",
            "Planned project cannot be archived",
            never_active_data,
        )

        archived_response = client.post(
            f"/api/v1/projects/{archived['id']}/archive",
            headers=headers,
            json={
                "reason": "Attempt archived project archive",
                "preflight_fingerprint": fingerprint,
            },
        )
        archived_data = archived_response.json()

        check(
            archived_response.status_code == 409
            and archived_data["detail"]["error"] ==
                "PROJECT_STATUS_NOT_ARCHIVABLE",
            "Archived project without archive evidence is rejected",
            archived_data,
        )

        wrong_tenant_response = client.post(
            f"/api/v1/projects/{ready['id']}/archive",
            headers={
                **headers,
                "X-Tenant-ID": "not-the-project-tenant",
            },
            json={
                "reason": "Attempt cross-tenant archive",
                "preflight_fingerprint": fingerprint,
            },
        )

        check(
            wrong_tenant_response.status_code in (403, 404),
            "Cross-tenant archive is rejected",
            {
                "status": wrong_tenant_response.status_code,
                "body": wrong_tenant_response.text[:1000],
            },
        )

        before_runtime = runtime_counts(db)
        archive_reason = (
            "Archive completed project after retention review"
        )

        archive_response = client.post(
            f"/api/v1/projects/{ready['id']}/archive",
            headers=headers,
            json={
                "reason": archive_reason,
                "preflight_fingerprint": fingerprint,
            },
        )
        archive_data = archive_response.json()

        check(
            archive_response.status_code == 200,
            "Ready project archive succeeds",
            archive_data,
        )
        check(
            archive_data["project"]["status"] == "ARCHIVED"
            and archive_data["archive"][
                "archived"
            ] is True
            and archive_data["archive"][
                "idempotent"
            ] is False,
            "Successful archive changes only lifecycle status",
            archive_data,
        )

        audits = archive_audits(db, ready["id"])
        check(
            project_status(db, ready["id"]) == "ARCHIVED"
            and len(audits) == 1,
            "Archive writes one immutable lifecycle event",
            {
                "status": project_status(db, ready["id"]),
                "audits": audits,
            },
        )

        audit = audits[0]
        check(
            audit["actor_id"] == str(admin.id)
            and audit["action"] == "ARCHIVE_PROJECT"
            and audit["patched_sections"] == ["status"]
            and audit["before_config"] == {
                "status": "COMPLETED"
            }
            and audit["after_config"] == {
                "status": "ARCHIVED"
            }
            and audit["reason"] == archive_reason,
            "Archive audit records actor and transition",
            audit,
        )
        check(
            audit["config_patch"][
                "preflight_fingerprint"
            ] == fingerprint
            and audit["config_patch"][
                "archive_summary"
            ]["unfinished_counts"] ==
                ready_preflight["unfinished_counts"]
            and audit["config_patch"][
                "archive_summary"
            ]["retained_counts"] ==
                ready_preflight["retained_counts"]
            and audit["config_patch"][
                "archive_summary"
            ]["blockers"] == [],
            "Archive audit pins approved preflight evidence",
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
            "Lifecycle history includes activation and archive",
            history,
        )
        check(
            history["events"][0]["action"] ==
                "ARCHIVE_PROJECT"
            and history["events"][0]["transition"] == {
                "from_status": "COMPLETED",
                "to_status": "ARCHIVED",
            }
            and history["events"][0][
                "preflight_fingerprint"
            ] == fingerprint,
            "Newest lifecycle event exposes archive evidence",
            history,
        )

        retry_response = client.post(
            f"/api/v1/projects/{ready['id']}/archive",
            headers=headers,
            json={
                "reason": "Idempotent archive retry",
                "preflight_fingerprint": fingerprint,
            },
        )
        retry_data = retry_response.json()

        check(
            retry_response.status_code == 200
            and retry_data["archive"][
                "archived"
            ] is False
            and retry_data["archive"][
                "idempotent"
            ] is True
            and retry_data["archive"][
                "audit_event_id"
            ] == str(audit["id"]),
            "Repeated successful archive is idempotent",
            retry_data,
        )
        check(
            len(archive_audits(db, ready["id"])) == 1,
            "Idempotent retry writes no duplicate audit",
            archive_audits(db, ready["id"]),
        )

        after_runtime = runtime_counts(db)
        check(
            after_runtime == before_runtime,
            "Archive leaves boundary and runtime tables unchanged",
            {
                "before": before_runtime,
                "after": after_runtime,
            },
        )

        guardrails = archive_data["guardrails"]
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
            "Archive response preserves runtime guardrails",
            guardrails,
        )

        restore_ready = restore_preflight(
            client,
            headers,
            ready["id"],
        )
        repeated_restore = restore_preflight(
            client,
            headers,
            ready["id"],
        )
        restore_fingerprint = restore_ready["decision"][
            "preflight_fingerprint"
        ]

        check(
            restore_ready["schema_version"] ==
                "project_restore_preflight.v1"
            and restore_ready["mode"] ==
                "READ_ONLY_PREFLIGHT"
            and len(restore_fingerprint) == 64
            and repeated_restore["decision"][
                "preflight_fingerprint"
            ] == restore_fingerprint,
            "Restore preflight schema and fingerprint are stable",
            restore_ready,
        )
        check(
            restore_ready["decision"]["can_restore"] is True
            and restore_ready["decision"][
                "restore_supported"
            ] is True
            and restore_ready["decision"]["blocker_count"] == 0
            and restore_ready["prior_archive_event"]["id"] ==
                str(audit["id"])
            and restore_ready["retained_counts"] ==
                ready_preflight["retained_counts"],
            "Archived project with evidence is restore-ready",
            restore_ready,
        )

        stale_restore = client.post(
            f"/api/v1/projects/{ready['id']}/restore",
            headers=headers,
            json={
                "reason": "Attempt stale project restoration",
                "preflight_fingerprint": "0" * 64,
            },
        )
        stale_restore_data = stale_restore.json()
        check(
            stale_restore.status_code == 409
            and stale_restore_data["detail"]["error"] ==
                "STALE_PROJECT_RESTORE_PREFLIGHT",
            "Stale restore fingerprint is rejected",
            stale_restore_data,
        )
        check(
            project_status(db, ready["id"]) == "ARCHIVED"
            and restore_audits(db, ready["id"]) == [],
            "Stale restore performs no lifecycle write",
        )

        missing_evidence = restore_preflight(
            client,
            headers,
            archived["id"],
        )
        check(
            missing_evidence["decision"]["can_restore"] is False
            and any(
                blocker["code"] ==
                    "ARCHIVE_EVIDENCE_MISSING"
                for blocker in missing_evidence["decision"][
                    "blockers"
                ]
            ),
            "Archived project without evidence is blocked",
            missing_evidence,
        )

        missing_response = client.post(
            f"/api/v1/projects/{archived['id']}/restore",
            headers=headers,
            json={
                "reason": "Attempt restore without archive evidence",
                "preflight_fingerprint":
                    missing_evidence["decision"][
                        "preflight_fingerprint"
                    ],
            },
        )
        check(
            missing_response.status_code == 409
            and missing_response.json()["detail"]["error"] ==
                "PROJECT_RESTORE_BLOCKED",
            "Restore requires immutable archive evidence",
            missing_response.json(),
        )

        wrong_tenant_restore = client.post(
            f"/api/v1/projects/{ready['id']}/restore",
            headers={
                **headers,
                "X-Tenant-ID": "not-the-project-tenant",
            },
            json={
                "reason": "Attempt cross-tenant restore",
                "preflight_fingerprint": restore_fingerprint,
            },
        )
        check(
            wrong_tenant_restore.status_code in (403, 404),
            "Cross-tenant restore is rejected",
            {
                "status": wrong_tenant_restore.status_code,
                "body": wrong_tenant_restore.text[:1000],
            },
        )

        restore_reason = (
            "Restore archived project to completed records"
        )
        restore_response = client.post(
            f"/api/v1/projects/{ready['id']}/restore",
            headers=headers,
            json={
                "reason": restore_reason,
                "preflight_fingerprint": restore_fingerprint,
            },
        )
        restore_data = restore_response.json()

        check(
            restore_response.status_code == 200
            and restore_data["project"]["status"] ==
                "COMPLETED"
            and restore_data["restore"]["restored"] is True
            and restore_data["restore"]["idempotent"] is False,
            "Ready archived project restores successfully",
            restore_data,
        )

        restore_events = restore_audits(db, ready["id"])
        check(
            project_status(db, ready["id"]) == "COMPLETED"
            and len(restore_events) == 1,
            "Restore writes one immutable lifecycle event",
            restore_events,
        )

        restore_event = restore_events[0]
        check(
            restore_event["actor_id"] == str(admin.id)
            and restore_event["before_config"] == {
                "status": "ARCHIVED"
            }
            and restore_event["after_config"] == {
                "status": "COMPLETED"
            }
            and restore_event["reason"] == restore_reason
            and restore_event["config_patch"][
                "preflight_fingerprint"
            ] == restore_fingerprint
            and restore_event["config_patch"][
                "restore_summary"
            ]["prior_archive_event_id"] ==
                str(audit["id"]),
            "Restore audit pins archive evidence and actor",
            restore_event,
        )

        restored_history = client.get(
            f"/api/v1/projects/{ready['id']}/lifecycle/audit",
            headers=headers,
        )
        restored_history_data = restored_history.json()
        check(
            restored_history.status_code == 200
            and restored_history_data["count"] == 3
            and restored_history_data["events"][0]["action"] ==
                "RESTORE_PROJECT"
            and restored_history_data["events"][0][
                "transition"
            ] == {
                "from_status": "ARCHIVED",
                "to_status": "COMPLETED",
            },
            "Lifecycle history includes archive and restore",
            restored_history_data,
        )

        retry_restore = client.post(
            f"/api/v1/projects/{ready['id']}/restore",
            headers=headers,
            json={
                "reason": "Idempotent restore retry",
                "preflight_fingerprint": restore_fingerprint,
            },
        )
        retry_restore_data = retry_restore.json()
        check(
            retry_restore.status_code == 200
            and retry_restore_data["restore"]["restored"] is False
            and retry_restore_data["restore"]["idempotent"] is True
            and retry_restore_data["restore"]["audit_event_id"] ==
                str(restore_event["id"]),
            "Repeated successful restore is idempotent",
            retry_restore_data,
        )
        check(
            len(restore_audits(db, ready["id"])) == 1,
            "Restore retry writes no duplicate audit",
            restore_audits(db, ready["id"]),
        )
        check(
            runtime_counts(db) == before_runtime,
            "Archive and restore leave runtime tables unchanged",
        )

        restore_guardrails = restore_data["guardrails"]
        check(
            restore_guardrails[
                "operational_records_changed"
            ] is False
            and restore_guardrails["records_deleted"] is False
            and restore_guardrails[
                "boundary_assignments_changed"
            ] is False
            and restore_guardrails[
                "boundary_candidates_activated"
            ] is False
            and restore_guardrails[
                "boundary_candidates_promoted"
            ] is False
            and restore_guardrails[
                "runtime_tables_written"
            ] is False
            and restore_guardrails[
                "runtime_lookup_enabled"
            ] is False
            and restore_guardrails[
                "android_behavior_changed"
            ] is False,
            "Restore preserves retention and runtime guardrails",
            restore_guardrails,
        )

        failure_preflight = archive_preflight(
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
                "forced project archive commit failure"
            )

        app.dependency_overrides[get_db] = override_db
        failure_db.commit = forced_commit_failure

        try:
            failure_client = TestClient(
                app,
                raise_server_exceptions=False,
            )
            failure_response = failure_client.post(
                f"/api/v1/projects/{failure['id']}/archive",
                headers=headers,
                json={
                    "reason": (
                        "Exercise atomic archive rollback"
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
            "Forced archive commit failure is surfaced",
            {
                "status": failure_response.status_code,
                "body": failure_response.text[:1000],
            },
        )
        check(
            project_status(db, failure["id"]) == "COMPLETED"
            and archive_audits(
                db,
                failure["id"],
            ) == [],
            "Forced failure rolls back status and audit atomically",
            {
                "status": project_status(db, failure["id"]),
                "audits": archive_audits(
                    db,
                    failure["id"],
                ),
            },
        )

        failure_archive_preflight = archive_preflight(
            client,
            headers,
            failure["id"],
        )
        failure_archive_response = client.post(
            f"/api/v1/projects/{failure['id']}/archive",
            headers=headers,
            json={
                "reason": (
                    "Archive fixture before forced restore failure"
                ),
                "preflight_fingerprint":
                    failure_archive_preflight["decision"][
                        "preflight_fingerprint"
                    ],
            },
        )
        check(
            failure_archive_response.status_code == 200
            and failure_archive_response.json()["project"][
                "status"
            ] == "ARCHIVED",
            "Prepare archived fixture for forced restore failure",
            failure_archive_response.json(),
        )

        failure_restore_preflight = restore_preflight(
            client,
            headers,
            failure["id"],
        )
        failure_restore_fingerprint = (
            failure_restore_preflight["decision"][
                "preflight_fingerprint"
            ]
        )
        restore_audits_before_failure = restore_audits(
            db,
            failure["id"],
        )

        restore_failure_db = SessionLocal()
        original_restore_commit = restore_failure_db.commit

        def override_restore_db():
            try:
                yield restore_failure_db
            finally:
                pass

        def forced_restore_commit_failure():
            raise RuntimeError(
                "forced project restore commit failure"
            )

        app.dependency_overrides[get_db] = override_restore_db
        restore_failure_db.commit = forced_restore_commit_failure

        try:
            restore_failure_client = TestClient(
                app,
                raise_server_exceptions=False,
            )
            restore_failure_response = (
                restore_failure_client.post(
                    f"/api/v1/projects/{failure['id']}/restore",
                    headers=headers,
                    json={
                        "reason": (
                            "Exercise atomic restore rollback"
                        ),
                        "preflight_fingerprint":
                            failure_restore_fingerprint,
                    },
                )
            )
        finally:
            restore_failure_db.commit = original_restore_commit
            restore_failure_db.rollback()
            restore_failure_db.close()
            app.dependency_overrides.pop(get_db, None)

        check(
            restore_failure_response.status_code == 500,
            "Forced restore commit failure is surfaced",
            {
                "status": restore_failure_response.status_code,
                "body": restore_failure_response.text[:1000],
            },
        )
        check(
            project_status(db, failure["id"]) == "ARCHIVED"
            and restore_audits(
                db,
                failure["id"],
            ) == restore_audits_before_failure,
            (
                "Forced restore failure rolls back status and "
                "audit atomically"
            ),
            {
                "status": project_status(db, failure["id"]),
                "audits": restore_audits(
                    db,
                    failure["id"],
                ),
            },
        )

        print("=" * 72)
        print("GUARDED PROJECT ARCHIVE AND RESTORE API REGRESSION PASSED")
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

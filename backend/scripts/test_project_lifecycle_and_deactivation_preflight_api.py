#!/usr/bin/env python3
"""Regression for project lifecycle history and deactivation preflight."""

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

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import ProjectRole
from scripts.admin_auth_test_utils import (
    create_test_admin,
    delete_test_admin,
)

TENANT_ID = "default"
NAME_PREFIX = "Project Lifecycle Preflight Regression"


def check(condition: bool, label: str, detail=None) -> None:
    print(("PASS" if condition else "FAIL"), label)
    if detail is not None and not condition:
        print(json.dumps(detail, indent=2, default=str)[:8000])
    if not condition:
        raise AssertionError(label)


def create_ready_project(client, headers, lgd_code: str) -> dict:
    response = client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "name": f"{NAME_PREFIX} Ready",
            "description": (
                "Temporary lifecycle and deactivation-preflight fixture."
            ),
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "crop_scope": ["RICE"],
            "geography_scope": {
                "village_lgd_codes": [lgd_code],
            },
            "geography_scope_reason": (
                "Configure canonical geography for lifecycle regression"
            ),
        },
    )
    data = response.json()
    check(
        response.status_code == 201,
        "Create lifecycle fixture project",
        data,
    )
    return data


def activation_preflight(client, headers, project_id: str) -> dict:
    response = client.get(
        "/api/v1/master-data/geography/projects/"
        f"{project_id}/activation-preflight",
        headers=headers,
    )
    data = response.json()
    check(
        response.status_code == 200,
        "Activation preflight succeeds",
        data,
    )
    return data


def lifecycle_history(client, headers, project_id: str):
    return client.get(
        f"/api/v1/projects/{project_id}/lifecycle/audit",
        headers=headers,
    )


def deactivation_preflight(client, headers, project_id: str):
    return client.get(
        f"/api/v1/projects/{project_id}/deactivation-preflight",
        headers=headers,
    )


def protected_counts(db, project_id: str) -> dict:
    db.expire_all()
    return dict(
        db.execute(
            text("""
                select
                  (
                    select count(*)::bigint
                    from project_app_config_audit_events
                    where project_id = cast(:project_id as uuid)
                  ) as audit_count,
                  (
                    select count(*)::bigint
                    from geography_boundary_project_matches
                    where project_id = cast(:project_id as uuid)
                  ) as boundary_assignment_count,
                  (
                    select count(*)::bigint
                    from geography_boundary_runtime_sets
                  ) as runtime_set_count,
                  (
                    select count(*)::bigint
                    from geography_boundary_runtime_features
                  ) as runtime_feature_count,
                  (
                    select count(*)::bigint
                    from geography_boundary_runtime_crosswalks
                  ) as runtime_crosswalk_count
            """),
            {"project_id": project_id},
        ).mappings().one()
    )


def project_status(db, project_id: str) -> str:
    db.expire_all()
    return db.execute(
        text("""
            select status
            from projects
            where id = cast(:project_id as uuid)
        """),
        {"project_id": project_id},
    ).scalar_one()


def main() -> int:
    print("=" * 72)
    print("PROJECT LIFECYCLE AND DEACTIVATION PREFLIGHT API REGRESSION")
    print("=" * 72)

    client = TestClient(app)
    db = SessionLocal()
    admin = None
    project_id = None
    role_id = None

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
            "Eligible canonical activation village is available",
            dict(eligible) if eligible else None,
        )

        admin, headers = create_test_admin(
            db,
            role="ENTERPRISE_ADMIN",
            tenant_id=TENANT_ID,
        )

        project = create_ready_project(
            client,
            headers,
            eligible["village_lgd_code"],
        )
        project_id = project["id"]

        empty_history_response = lifecycle_history(
            client,
            headers,
            project_id,
        )
        empty_history = empty_history_response.json()

        check(
            empty_history_response.status_code == 200,
            "Lifecycle history succeeds before activation",
            empty_history,
        )
        check(
            empty_history["schema_version"] ==
                "project_lifecycle_audit.v1"
            and empty_history["count"] == 0
            and empty_history["events"] == [],
            "Geography configuration events are excluded",
            empty_history,
        )

        planned_preflight_response = deactivation_preflight(
            client,
            headers,
            project_id,
        )
        planned_preflight = planned_preflight_response.json()

        check(
            planned_preflight_response.status_code == 200,
            "Planned-project deactivation preflight succeeds",
            planned_preflight,
        )
        check(
            planned_preflight["decision"]["can_deactivate"] is False
            and any(
                blocker["code"] == "PROJECT_NOT_ACTIVE"
                for blocker in planned_preflight["decision"]["blockers"]
            ),
            "Non-active project cannot enter deactivation",
            planned_preflight,
        )

        activation = activation_preflight(
            client,
            headers,
            project_id,
        )
        fingerprint = activation["decision"]["preflight_fingerprint"]
        activation_reason = (
            "Activate project for lifecycle history regression"
        )

        activate_response = client.post(
            f"/api/v1/projects/{project_id}/activate",
            headers=headers,
            json={
                "reason": activation_reason,
                "preflight_fingerprint": fingerprint,
            },
        )
        activate_data = activate_response.json()

        check(
            activate_response.status_code == 200
            and activate_data["project"]["status"] == "ACTIVE",
            "Guarded project activation succeeds",
            activate_data,
        )

        history_response = lifecycle_history(
            client,
            headers,
            project_id,
        )
        history = history_response.json()

        check(
            history_response.status_code == 200,
            "Lifecycle history succeeds after activation",
            history,
        )
        check(
            history["schema_version"] ==
                "project_lifecycle_audit.v1"
            and history["tenant_id"] == TENANT_ID
            and history["project"]["id"] == project_id
            and history["count"] == 1,
            "Lifecycle history is project and tenant scoped",
            history,
        )

        event = history["events"][0]
        check(
            event["action"] == "ACTIVATE_PROJECT"
            and event["transition"] == {
                "from_status": "PLANNED",
                "to_status": "ACTIVE",
            },
            "Lifecycle event exposes the status transition",
            event,
        )
        check(
            event["actor"]["id"] == str(admin.id)
            and event["actor"]["display_name"] ==
                admin.display_name
            and event["actor"]["role"] == admin.role,
            "Lifecycle event resolves actor identity",
            event,
        )
        check(
            event["reason"] == activation_reason
            and event["created_at"] is not None,
            "Lifecycle event exposes reason and timestamp",
            event,
        )
        check(
            event["preflight_fingerprint"] == fingerprint
            and len(event["preflight_fingerprint"]) == 64
            and event["geography_summary"] ==
                activation["summary"],
            "Lifecycle event pins activation evidence",
            event,
        )
        check(
            history["governance"]["mode"] == "READ_ONLY"
            and history["governance"][
                "database_write_performed"
            ] is False
            and history["governance"][
                "project_status_changed"
            ] is False,
            "Lifecycle history declares read-only governance",
            history["governance"],
        )

        before_read_counts = protected_counts(db, project_id)
        before_read_status = project_status(db, project_id)

        clean_response = deactivation_preflight(
            client,
            headers,
            project_id,
        )
        clean = clean_response.json()

        check(
            clean_response.status_code == 200,
            "Active-project deactivation preflight succeeds",
            clean,
        )
        check(
            clean["schema_version"] ==
                "project_deactivation_preflight.v2"
            and clean["mode"] == "READ_ONLY_PREFLIGHT",
            "Deactivation preflight schema and mode are stable",
            clean,
        )
        check(
            all(
                value == 0
                for value in clean["operational_counts"].values()
            ),
            "Freshly activated fixture has no operational blockers",
            clean,
        )
        check(
            clean["decision"]["can_deactivate"] is True
            and clean["decision"]["deactivation_supported"] is True
            and clean["decision"]["blocker_count"] == 0,
            "Clean active project is eligible for guarded deactivation",
            clean,
        )

        role_id = uuid.uuid4()
        db.add(
            ProjectRole(
                id=role_id,
                project_id=uuid.UUID(project_id),
                user_id=admin.id,
                role="MANAGER",
                territory_scope={},
                is_active=True,
            )
        )
        db.commit()

        blocked_response = deactivation_preflight(
            client,
            headers,
            project_id,
        )
        blocked = blocked_response.json()

        check(
            blocked_response.status_code == 200,
            "Blocked deactivation preflight succeeds",
            blocked,
        )
        check(
            blocked["operational_counts"]["project_role_count"] == 1
            and any(
                blocker["code"] == "PROJECT_ROLES_ASSIGNED"
                and blocker["count"] == 1
                for blocker in blocked["decision"]["blockers"]
            ),
            "Active project role is reported as a blocker",
            blocked,
        )
        check(
            blocked["decision"]["can_deactivate"] is False
            and blocked["decision"]["deactivation_supported"] is True,
            "Operational blocker prevents deactivation readiness",
            blocked,
        )

        expected_count_keys = {
            "farmer_count",
            "enrollment_count",
            "parcel_count",
            "crop_cycle_count",
            "project_role_count",
            "active_boundary_assignment_count",
            "field_event_count",
        }
        check(
            set(blocked["operational_counts"]) ==
                expected_count_keys,
            "Preflight covers all required operational domains",
            blocked["operational_counts"],
        )

        guardrails = blocked["governance"]
        check(
            guardrails["database_write_performed"] is False
            and guardrails["project_status_changed"] is False
            and guardrails["boundary_assignments_changed"] is False
            and guardrails["candidate_activation_changed"] is False
            and guardrails["candidate_promotion_changed"] is False
            and guardrails["runtime_tables_written"] is False
            and guardrails["runtime_lookup_enabled"] is False
            and guardrails["android_behavior_changed"] is False,
            "Deactivation preflight preserves runtime guardrails",
            guardrails,
        )

        after_read_counts = protected_counts(db, project_id)
        after_read_status = project_status(db, project_id)

        check(
            before_read_counts == after_read_counts
            and before_read_status == after_read_status == "ACTIVE",
            "History and preflight reads perform no protected writes",
            {
                "before_counts": before_read_counts,
                "after_counts": after_read_counts,
                "before_status": before_read_status,
                "after_status": after_read_status,
            },
        )

        wrong_headers = {
            **headers,
            "X-Tenant-ID": "not-the-project-tenant",
        }
        wrong_history = lifecycle_history(
            client,
            wrong_headers,
            project_id,
        )
        wrong_preflight = deactivation_preflight(
            client,
            wrong_headers,
            project_id,
        )

        check(
            wrong_history.status_code in (403, 404)
            and wrong_preflight.status_code in (403, 404),
            "Cross-tenant lifecycle reads are rejected",
            {
                "history_status": wrong_history.status_code,
                "history_body": wrong_history.text[:1000],
                "preflight_status": wrong_preflight.status_code,
                "preflight_body": wrong_preflight.text[:1000],
            },
        )

        unknown_id = str(uuid.uuid4())
        unknown_history = lifecycle_history(
            client,
            headers,
            unknown_id,
        )
        unknown_preflight = deactivation_preflight(
            client,
            headers,
            unknown_id,
        )

        check(
            unknown_history.status_code == 404
            and unknown_preflight.status_code == 404,
            "Unknown projects are rejected",
            {
                "history_status": unknown_history.status_code,
                "preflight_status": unknown_preflight.status_code,
            },
        )

        print("=" * 72)
        print(
            "PROJECT LIFECYCLE AND DEACTIVATION PREFLIGHT "
            "API REGRESSION PASSED"
        )
        print("=" * 72)
        return 0
    finally:
        if role_id is not None:
            db.query(ProjectRole).filter(
                ProjectRole.id == role_id
            ).delete(synchronize_session=False)
            db.commit()

        if project_id is not None:
            db.execute(
                text("""
                    delete from project_app_config_audit_events
                    where project_id = cast(:project_id as uuid)
                """),
                {"project_id": project_id},
            )
            db.execute(
                text("""
                    delete from projects
                    where id = cast(:project_id as uuid)
                      and name like :name_pattern
                """),
                {
                    "project_id": project_id,
                    "name_pattern": f"{NAME_PREFIX}%",
                },
            )
            db.commit()

        if admin is not None:
            delete_test_admin(db, admin.id)

        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

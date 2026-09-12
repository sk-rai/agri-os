#!/usr/bin/env python3
"""Regression for canonical geography during project creation."""

from __future__ import annotations

import json
import sys
import uuid
from datetime import date
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
NAME_PREFIX = "Project Creation Geography Regression"


def check(condition: bool, label: str, detail=None) -> None:
    print(("PASS" if condition else "FAIL"), label)
    if detail is not None and not condition:
        print(json.dumps(detail, indent=2, default=str)[:5000])
    if not condition:
        raise AssertionError(label)


def matching_project_count(db) -> int:
    return int(db.execute(text("""
        select count(*)::bigint
        from projects
        where tenant_id = :tenant_id
          and name like :name_pattern
    """), {
        "tenant_id": TENANT_ID,
        "name_pattern": f"{NAME_PREFIX}%",
    }).scalar_one())


def matching_audit_count(db) -> int:
    return int(db.execute(text("""
        select count(*)::bigint
        from project_app_config_audit_events event
        join projects project on project.id = event.project_id
        where project.tenant_id = :tenant_id
          and project.name like :name_pattern
    """), {
        "tenant_id": TENANT_ID,
        "name_pattern": f"{NAME_PREFIX}%",
    }).scalar_one())


def payload(name: str, geography_scope=None, reason=None) -> dict:
    result = {
        "name": name,
        "description": "Temporary canonical geography creation fixture.",
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
        "crop_scope": ["RICE"],
        "geography_scope": geography_scope or {},
    }
    if reason is not None:
        result["geography_scope_reason"] = reason
    return result


def main() -> int:
    print("=" * 72)
    print("PROJECT CREATION GEOGRAPHY SCOPE API REGRESSION")
    print("=" * 72)

    client = TestClient(app)
    db = SessionLocal()
    admin = None
    created_project_ids: list[str] = []

    try:
        village_rows = [
            dict(row)
            for row in db.execute(text("""
                select
                  village.id::text as village_id,
                  village.lgd_code::text as village_lgd_code,
                  village.canonical_name as village_name,
                  block.canonical_name as block_name,
                  district.canonical_name as district_name,
                  state.canonical_name as state_name
                from geography_villages village
                join geography_blocks block
                  on block.id = village.block_id
                 and block.is_active = true
                join geography_districts district
                  on district.id = village.district_id
                 and district.is_active = true
                join geography_states state
                  on state.id = district.state_id
                 and state.is_active = true
                where village.is_active = true
                  and village.lgd_code is not null
                order by village.lgd_code
                limit 501
            """)).mappings().all()
        ]
        check(
            len(village_rows) == 501,
            "At least 501 canonical villages are available",
            {"count": len(village_rows)},
        )

        admin, headers = create_test_admin(
            db,
            role="ENTERPRISE_ADMIN",
            tenant_id=TENANT_ID,
        )

        baseline_projects = matching_project_count(db)
        baseline_audits = matching_audit_count(db)

        empty_response = client.post(
            "/api/v1/projects",
            headers=headers,
            json=payload(f"{NAME_PREFIX} Empty"),
        )
        empty_data = empty_response.json()

        check(
            empty_response.status_code == 201,
            "Project creation without geography remains supported",
            empty_data,
        )
        created_project_ids.append(empty_data["id"])
        check(
            empty_data["geography_scope"] == {},
            "Empty project geography remains empty",
            empty_data,
        )
        check(
            matching_audit_count(db) == baseline_audits,
            "Empty geography creates no geography audit event",
            {"audits": matching_audit_count(db)},
        )

        before_invalid_projects = matching_project_count(db)
        before_invalid_audits = matching_audit_count(db)

        malformed_response = client.post(
            "/api/v1/projects",
            headers=headers,
            json=payload(
                f"{NAME_PREFIX} Malformed",
                {"village_lgd_codes": "645063"},
                "Malformed scope must not create a project",
            ),
        )
        check(
            malformed_response.status_code == 422,
            "Malformed geography scope is rejected",
            malformed_response.json(),
        )

        unknown_response = client.post(
            "/api/v1/projects",
            headers=headers,
            json=payload(
                f"{NAME_PREFIX} Unknown",
                {"village_lgd_codes": ["999999999"]},
                "Unknown village must not create a project",
            ),
        )
        check(
            unknown_response.status_code == 422,
            "Unknown village LGD code is rejected",
            unknown_response.json(),
        )

        valid_codes = [
            village_rows[0]["village_lgd_code"],
            village_rows[1]["village_lgd_code"],
        ]
        missing_reason_response = client.post(
            "/api/v1/projects",
            headers=headers,
            json=payload(
                f"{NAME_PREFIX} Missing Reason",
                {"village_lgd_codes": valid_codes},
            ),
        )
        check(
            missing_reason_response.status_code == 422,
            "Geography creation requires an audit reason",
            missing_reason_response.json(),
        )

        oversized_codes = [
            row["village_lgd_code"]
            for row in village_rows
        ]
        oversized_response = client.post(
            "/api/v1/projects",
            headers=headers,
            json=payload(
                f"{NAME_PREFIX} Oversized",
                {"village_lgd_codes": oversized_codes},
                "Oversized scope must not create a project",
            ),
        )
        oversized_data = oversized_response.json()
        check(
            oversized_response.status_code == 422,
            "Creation rejects more than 500 unique villages",
            oversized_data,
        )
        check(
            oversized_data["detail"]["error"]
            == "PROJECT_GEOGRAPHY_SCOPE_LIMIT_EXCEEDED",
            "Over-limit response exposes a stable error",
            oversized_data,
        )

        check(
            matching_project_count(db) == before_invalid_projects
            and matching_audit_count(db) == before_invalid_audits,
            "Invalid submissions create neither project nor audit",
            {
                "projects": matching_project_count(db),
                "audits": matching_audit_count(db),
                "expected_projects": before_invalid_projects,
                "expected_audits": before_invalid_audits,
            },
        )

        reason = "Configure canonical villages during project creation"
        valid_response = client.post(
            "/api/v1/projects",
            headers=headers,
            json=payload(
                f"{NAME_PREFIX} Valid",
                {
                    "village_lgd_codes": [
                        valid_codes[1],
                        valid_codes[0],
                        valid_codes[1],
                    ],
                },
                reason,
            ),
        )
        valid_data = valid_response.json()

        check(
            valid_response.status_code == 201,
            "Project creation with canonical geography succeeds",
            valid_data,
        )
        created_project_ids.append(valid_data["id"])

        scope = valid_data["geography_scope"]
        check(
            scope["source"] == "admin_project_creation",
            "Created scope records its source",
            scope,
        )
        check(
            scope["village_lgd_codes"] == sorted(valid_codes),
            "Created scope is deduplicated and canonicalized",
            scope,
        )
        check(
            len(scope["village_ids"]) == 2
            and len(scope["village_names"]) == 2,
            "Created scope contains resolved IDs and names",
            scope,
        )
        check(
            scope["states"],
            "Created scope contains canonical state labels",
            scope,
        )

        audit_rows = [
            dict(row)
            for row in db.execute(text("""
                select
                  actor_id::text,
                  action,
                  before_config,
                  after_config,
                  config_patch,
                  reason
                from project_app_config_audit_events
                where project_id = cast(:project_id as uuid)
                order by created_at
            """), {"project_id": valid_data["id"]})
            .mappings()
            .all()
        ]

        check(
            len(audit_rows) == 1,
            "Canonical geography creation writes one audit event",
            audit_rows,
        )
        audit = audit_rows[0]
        check(
            audit["action"] == "CREATE_PROJECT_GEOGRAPHY_SCOPE"
            and audit["actor_id"] == str(admin.id),
            "Creation audit records action and actor",
            audit,
        )
        check(
            audit["reason"] == reason,
            "Creation audit records the submitted reason",
            audit,
        )
        check(
            audit["before_config"] == {"geography_scope": {}}
            and audit["after_config"]["geography_scope"]
            ["village_lgd_codes"] == sorted(valid_codes),
            "Creation audit records canonical before and after scope",
            audit,
        )

        history_response = client.get(
            f"/api/v1/projects/{valid_data['id']}/"
            "geography-scope/audit",
            headers=headers,
        )
        history_data = history_response.json()

        check(
            history_response.status_code == 200,
            "Creation event is available through scope history",
            history_data,
        )
        check(
            history_data["count"] == 1
            and history_data["events"][0]["action"]
            == "CREATE_PROJECT_GEOGRAPHY_SCOPE",
            "Scope history includes only the creation event",
            history_data,
        )
        check(
            history_data["events"][0]["summary"]["added_count"]
            == 2
            and history_data["events"][0]["before_village_count"]
            == 0
            and history_data["events"][0]["after_village_count"]
            == 2,
            "Creation history classifies initial villages as added",
            history_data["events"][0],
        )
        check(
            history_data["events"][0]["actor"]["display_name"]
            == admin.display_name,
            "Creation history resolves the actor label",
            history_data["events"][0]["actor"],
        )

        check(
            matching_project_count(db) == baseline_projects + 2,
            "Only the empty and valid projects were created",
            {"projects": matching_project_count(db)},
        )
        check(
            matching_audit_count(db) == baseline_audits + 1,
            "Only valid canonical creation wrote an audit",
            {"audits": matching_audit_count(db)},
        )

        print("=" * 72)
        print(
            "PROJECT CREATION GEOGRAPHY SCOPE "
            "API REGRESSION PASSED"
        )
        print("=" * 72)
        return 0
    finally:
        db.rollback()

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
            """), {"project_ids": created_project_ids})
            db.commit()

        if admin is not None:
            delete_test_admin(db, admin.id)

        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

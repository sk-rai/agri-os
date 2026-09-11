#!/usr/bin/env python3
"""Regression for resolved project geography-scope audit history."""

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


def check(condition: bool, label: str, detail=None) -> None:
    print(("PASS" if condition else "FAIL"), label)
    if detail is not None and not condition:
        print(json.dumps(detail, indent=2, default=str)[:5000])
    if not condition:
        raise AssertionError(label)


def table_counts(db, project_id: str) -> dict:
    return {
        "projects": int(db.execute(text("""
            select count(*)::bigint
            from projects
            where id = cast(:project_id as uuid)
        """), {"project_id": project_id}).scalar_one()),
        "audits": int(db.execute(text("""
            select count(*)::bigint
            from project_app_config_audit_events
            where project_id = cast(:project_id as uuid)
        """), {"project_id": project_id}).scalar_one()),
        "matches": int(db.execute(text("""
            select count(*)::bigint
            from geography_boundary_project_matches
            where project_id = cast(:project_id as uuid)
        """), {"project_id": project_id}).scalar_one()),
    }


def main() -> int:
    print("=" * 72)
    print("PROJECT GEOGRAPHY SCOPE AUDIT API REGRESSION")
    print("=" * 72)

    client = TestClient(app)
    db = SessionLocal()
    admin = None
    project_id = str(uuid.uuid4())
    other_project_id = str(uuid.uuid4())

    try:
        fixture = db.execute(text("""
            with eligible as (
                select distinct on (v.id)
                  v.id::text as village_id,
                  v.lgd_code::text as lgd_code,
                  v.canonical_name as village_name,
                  b.canonical_name as block_name,
                  d.canonical_name as district_name,
                  s.canonical_name as state_name
                from geography_boundary_crosswalk_candidates c
                join geography_boundary_import_batches batch
                  on batch.id = c.import_batch_id
                join geography_boundary_source_features feature
                  on feature.id = c.source_feature_id
                join geography_villages v
                  on v.id = c.proposed_village_id
                join geography_blocks b on b.id = v.block_id
                join geography_districts d on d.id = v.district_id
                join geography_states s on s.id = d.state_id
                where batch.source_system =
                        'NWDP_GSI_VILLAGE_BOUNDARY'
                  and feature.geometry_validation_status = 'VALIDATED'
                  and c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
                  and c.review_status = 'AUTO_CANDIDATE'
                  and c.promotion_status = 'NOT_PROMOTED'
                  and c.is_active = false
                  and v.is_active = true
                  and b.is_active = true
                  and d.is_active = true
                  and s.is_active = true
                order by v.id, v.lgd_code
                limit 1
            ),
            blocked as (
                select distinct on (v.id)
                  v.id::text as village_id,
                  v.lgd_code::text as lgd_code,
                  v.canonical_name as village_name,
                  b.canonical_name as block_name,
                  d.canonical_name as district_name,
                  s.canonical_name as state_name
                from geography_boundary_crosswalk_candidates c
                join geography_boundary_import_batches batch
                  on batch.id = c.import_batch_id
                join geography_villages v
                  on v.id = c.proposed_village_id
                join geography_blocks b on b.id = v.block_id
                join geography_districts d on d.id = v.district_id
                join geography_states s on s.id = d.state_id
                where batch.source_system =
                        'NWDP_GSI_VILLAGE_BOUNDARY'
                  and c.review_status = 'BLOCKED'
                  and c.promotion_status = 'NOT_PROMOTED'
                  and c.is_active = false
                  and v.is_active = true
                  and b.is_active = true
                  and d.is_active = true
                  and s.is_active = true
                  and not exists (
                      select 1
                      from geography_boundary_crosswalk_candidates ec
                      join geography_boundary_import_batches eb
                        on eb.id = ec.import_batch_id
                      join geography_boundary_source_features ef
                        on ef.id = ec.source_feature_id
                      where ec.proposed_village_id = v.id
                        and eb.source_system =
                          'NWDP_GSI_VILLAGE_BOUNDARY'
                        and ef.geometry_validation_status =
                          'VALIDATED'
                        and ec.candidate_bucket =
                          'DIRECT_VLCODE_MATCH'
                        and ec.review_status = 'AUTO_CANDIDATE'
                        and ec.promotion_status = 'NOT_PROMOTED'
                        and ec.is_active = false
                  )
                order by v.id, v.lgd_code
                limit 1
            ),
            missing as (
                select
                  v.id::text as village_id,
                  v.lgd_code::text as lgd_code,
                  v.canonical_name as village_name,
                  b.canonical_name as block_name,
                  d.canonical_name as district_name,
                  s.canonical_name as state_name
                from geography_villages v
                join geography_blocks b on b.id = v.block_id
                join geography_districts d on d.id = v.district_id
                join geography_states s on s.id = d.state_id
                where v.is_active = true
                  and b.is_active = true
                  and d.is_active = true
                  and s.is_active = true
                  and v.lgd_code is not null
                  and not exists (
                      select 1
                      from geography_boundary_crosswalk_candidates c
                      join geography_boundary_import_batches batch
                        on batch.id = c.import_batch_id
                      where c.proposed_village_id = v.id
                        and batch.source_system =
                          'NWDP_GSI_VILLAGE_BOUNDARY'
                        and c.review_status in (
                          'AUTO_CANDIDATE',
                          'BLOCKED'
                        )
                        and c.promotion_status = 'NOT_PROMOTED'
                        and c.is_active = false
                  )
                order by v.lgd_code
                limit 1
            )
            select
              (select row_to_json(eligible) from eligible)
                as eligible,
              (select row_to_json(blocked) from blocked)
                as blocked,
              (select row_to_json(missing) from missing)
                as missing
        """)).mappings().one()

        fixture = dict(fixture)
        check(
            fixture["eligible"] is not None
            and fixture["missing"] is not None,
            "Eligible and missing villages are available",
            fixture,
        )

        blocked_fixture_available = fixture["blocked"] is not None
        if blocked_fixture_available:
            print("PASS Canonical blocked-village fixture is available")
        else:
            print(
                "SKIP Canonical blocked-village classification "
                "(no blocked candidate is linked to a canonical village)"
            )
            fixture["blocked"] = fixture["missing"]

        db.execute(text("""
            insert into projects (
              id, tenant_id, name, description,
              start_date, end_date, status,
              geography_scope, crop_scope, config,
              created_at, updated_at, version, is_active
            ) values
            (
              cast(:project_id as uuid),
              :tenant_id,
              'Project Geography Audit Regression',
              'Temporary geography audit fixture.',
              :start_date,
              :end_date,
              'PLANNED',
              '{}'::jsonb,
              '[]'::jsonb,
              '{}'::jsonb,
              now(), now(), 'v1.0', true
            ),
            (
              cast(:other_project_id as uuid),
              :tenant_id,
              'Other Project Geography Audit Regression',
              'Tenant-scope exclusion fixture.',
              :start_date,
              :end_date,
              'PLANNED',
              '{}'::jsonb,
              '[]'::jsonb,
              '{}'::jsonb,
              now(), now(), 'v1.0', true
            )
        """), {
            "project_id": project_id,
            "other_project_id": other_project_id,
            "tenant_id": TENANT_ID,
            "start_date": date(2026, 1, 1),
            "end_date": date(2026, 12, 31),
        })
        db.commit()

        admin, headers = create_test_admin(
            db,
            role="ENTERPRISE_ADMIN",
            tenant_id=TENANT_ID,
        )

        first_response = client.patch(
            f"/api/v1/projects/{project_id}/geography-scope",
            headers=headers,
            json={
                "village_lgd_codes": [
                    fixture["eligible"]["lgd_code"],
                    fixture["blocked"]["lgd_code"],
                ],
                "reason": "Establish initial geography audit fixture",
            },
        )
        check(
            first_response.status_code == 200,
            "Initial geography scope update succeeds",
            first_response.json(),
        )

        second_response = client.patch(
            f"/api/v1/projects/{project_id}/geography-scope",
            headers=headers,
            json={
                "village_lgd_codes": [
                    fixture["eligible"]["lgd_code"],
                    fixture["missing"]["lgd_code"],
                ],
                "reason": "Replace blocked village with missing village",
            },
        )
        check(
            second_response.status_code == 200,
            "Second geography scope update succeeds",
            second_response.json(),
        )

        db.execute(text("""
            insert into project_app_config_audit_events (
              id, tenant_id, project_id, actor_id, action,
              patched_sections, before_config, after_config,
              config_patch, reason, created_at
            ) values
            (
              cast(:generic_event_id as uuid),
              :tenant_id,
              cast(:project_id as uuid),
              cast(:actor_id as uuid),
              'UPDATE_PROJECT_APP_CONFIG',
              '["branding"]'::jsonb,
              '{}'::jsonb,
              '{}'::jsonb,
              '{}'::jsonb,
              'Generic event must be excluded',
              now()
            ),
            (
              cast(:other_event_id as uuid),
              :tenant_id,
              cast(:other_project_id as uuid),
              cast(:actor_id as uuid),
              'UPDATE_PROJECT_GEOGRAPHY_SCOPE',
              '["geography_scope"]'::jsonb,
              '{}'::jsonb,
              '{}'::jsonb,
              '{}'::jsonb,
              'Other project event must be excluded',
              now()
            )
        """), {
            "generic_event_id": str(uuid.uuid4()),
            "other_event_id": str(uuid.uuid4()),
            "tenant_id": TENANT_ID,
            "project_id": project_id,
            "other_project_id": other_project_id,
            "actor_id": str(admin.id),
        })
        db.commit()

        counts_before = table_counts(db, project_id)

        response = client.get(
            f"/api/v1/projects/{project_id}/geography-scope/audit",
            headers=headers,
        )
        data = response.json()

        check(
            response.status_code == 200,
            "Geography audit endpoint succeeds",
            data,
        )
        check(
            data["schema_version"]
            == "project_geography_scope_audit.v1",
            "Audit schema version is stable",
            data,
        )
        check(
            data["count"] == 2 and len(data["events"]) == 2,
            "Only geography events for the selected project are returned",
            data["events"],
        )
        check(
            all(
                event["action"] == "UPDATE_PROJECT_GEOGRAPHY_SCOPE"
                for event in data["events"]
            ),
            "Generic app-config events are excluded",
            data["events"],
        )

        latest = data["events"][0]
        changes = {
            row["lgd_code"]: row
            for row in latest["changes"]
        }

        eligible_code = fixture["eligible"]["lgd_code"]
        blocked_code = fixture["blocked"]["lgd_code"]
        missing_code = fixture["missing"]["lgd_code"]

        check(
            latest["reason"]
            == "Replace blocked village with missing village",
            "Newest event is returned first",
            latest,
        )
        check(
            latest["actor"]["id"] == str(admin.id)
            and latest["actor"]["display_name"]
            == admin.display_name
            and latest["actor"]["role"] == admin.role,
            "Actor identity and label are resolved",
            latest["actor"],
        )
        check(
            changes[eligible_code]["change_type"] == "UNCHANGED",
            "Retained village is classified unchanged",
            changes,
        )
        if blocked_fixture_available:
            check(
                changes[blocked_code]["change_type"] == "REMOVED",
                "Removed village is classified removed",
                changes,
            )
            check(
                changes[missing_code]["change_type"] == "ADDED",
                "New village is classified added",
                changes,
            )
        else:
            check(
                changes[missing_code]["change_type"] == "UNCHANGED",
                "Fallback missing village is classified unchanged",
                changes,
            )
        check(
            changes[eligible_code]["boundary_status"] == "ELIGIBLE",
            "Eligible village uses established readiness policy",
            changes[eligible_code],
        )
        if blocked_fixture_available:
            check(
                changes[blocked_code]["boundary_status"] == "BLOCKED",
                "Blocked village is classified",
                changes[blocked_code],
            )
        else:
            check(
                changes[blocked_code]["boundary_status"] == "MISSING",
                "Fallback village is classified missing",
                changes[blocked_code],
            )
        check(
            changes[missing_code]["boundary_status"] == "MISSING",
            "Missing-boundary village is classified",
            changes[missing_code],
        )
        check(
            all(
                row["resolved"]
                and row["village_name"]
                and row["block_name"]
                and row["district_name"]
                and row["state_name"]
                for row in latest["changes"]
            ),
            "Canonical hierarchy is resolved for every change",
            latest["changes"],
        )
        expected_summary = {
            "added_count": 0 if not blocked_fixture_available else 1,
            "removed_count": 0 if not blocked_fixture_available else 1,
            "unchanged_count": 2 if not blocked_fixture_available else 1,
            "eligible_count": 1,
            "missing_count": 1,
            "blocked_count": 1 if blocked_fixture_available else 0,
        }
        check(
            latest["summary"] == expected_summary,
            "Event summary reports change and boundary counts",
            {
                "expected": expected_summary,
                "actual": latest["summary"],
            },
        )
        check(
            data["guardrails"]["db_writes_attempted"] is False,
            "Endpoint declares read-only governance",
            data["guardrails"],
        )
        check(
            table_counts(db, project_id) == counts_before,
            "Reading audit history performs no database writes",
            {
                "before": counts_before,
                "after": table_counts(db, project_id),
            },
        )

        wrong_tenant_headers = {
            **headers,
            "X-Tenant-ID": "tenant-isolation-fixture",
        }
        isolated_response = client.get(
            f"/api/v1/projects/{project_id}/geography-scope/audit",
            headers=wrong_tenant_headers,
        )
        check(
            isolated_response.status_code in {403, 404},
            "Cross-tenant audit access is rejected",
            {
                "status": isolated_response.status_code,
                "body": isolated_response.json(),
            },
        )

        print("=" * 72)
        print("PROJECT GEOGRAPHY SCOPE AUDIT API REGRESSION PASSED")
        print("=" * 72)
        return 0
    finally:
        db.rollback()

        db.execute(text("""
            delete from project_app_config_audit_events
            where project_id in (
              cast(:project_id as uuid),
              cast(:other_project_id as uuid)
            )
        """), {
            "project_id": project_id,
            "other_project_id": other_project_id,
        })
        db.execute(text("""
            delete from projects
            where id in (
              cast(:project_id as uuid),
              cast(:other_project_id as uuid)
            )
        """), {
            "project_id": project_id,
            "other_project_id": other_project_id,
        })
        db.commit()

        if admin is not None:
            delete_test_admin(db, admin.id)

        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

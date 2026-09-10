#!/usr/bin/env python3
"""Regression for project geography-scope CSV preview and export."""

from __future__ import annotations

import csv
import io
import json
import sys
import uuid
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from scripts.admin_auth_test_utils import (  # noqa: E402
    create_test_admin,
    delete_test_admin,
)

TENANT_ID = "default"


def check(condition: bool, label: str, detail=None) -> None:
    print(("PASS" if condition else "FAIL"), label)
    if detail is not None and not condition:
        print(json.dumps(detail, indent=2, default=str)[:4000])
    if not condition:
        raise AssertionError(label)


def audit_count(db, project_id: str) -> int:
    return int(db.execute(text("""
        select count(*)::bigint
        from project_app_config_audit_events
        where project_id = cast(:project_id as uuid)
    """), {"project_id": project_id}).scalar_one())


def project_scope(db, project_id: str) -> dict:
    value = db.execute(text("""
        select geography_scope
        from projects
        where id = cast(:project_id as uuid)
    """), {"project_id": project_id}).scalar_one()
    return value or {}


def main() -> int:
    print("=" * 72)
    print("PROJECT GEOGRAPHY SCOPE IMPORT/EXPORT API REGRESSION")
    print("=" * 72)

    client = TestClient(app)
    db = SessionLocal()
    admin = None
    project_id = str(uuid.uuid4())

    try:
        villages = [
            dict(row)
            for row in db.execute(text("""
                select
                  v.id::text as village_id,
                  v.lgd_code::text as village_lgd_code,
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
                order by v.lgd_code
                limit 2
            """)).mappings().all()
        ]
        check(
            len(villages) == 2,
            "Two canonical villages are available",
            villages,
        )

        db.execute(text("""
            insert into projects (
              id, tenant_id, name, description,
              start_date, end_date, status,
              geography_scope, crop_scope, config,
              created_at, updated_at, version, is_active
            )
            values (
              cast(:project_id as uuid),
              :tenant_id,
              'Project Geography CSV Regression',
              'Temporary import/export fixture.',
              :start_date,
              :end_date,
              'PLANNED',
              '{}'::jsonb,
              '[]'::jsonb,
              '{}'::jsonb,
              now(),
              now(),
              'v1.0',
              true
            )
        """), {
            "project_id": project_id,
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

        first_code = villages[0]["village_lgd_code"]
        second_code = villages[1]["village_lgd_code"]
        unknown_code = "999999999"
        invalid_code = "not-an-lgd-code"

        before_scope = project_scope(db, project_id)
        before_audits = audit_count(db, project_id)

        invalid_preview = client.post(
            f"/api/v1/projects/{project_id}/"
            "geography-scope/import-preview",
            headers=headers,
            json={
                "village_lgd_codes": [
                    second_code,
                    first_code,
                    second_code,
                    unknown_code,
                    invalid_code,
                ],
            },
        )
        invalid_data = invalid_preview.json()

        check(
            invalid_preview.status_code == 200,
            "Mixed import preview succeeds",
            invalid_data,
        )
        check(
            invalid_data["summary"]["input_row_count"] == 5,
            "Preview counts source rows",
            invalid_data["summary"],
        )
        check(
            invalid_data["duplicate_village_lgd_codes"]
            == [second_code],
            "Preview reports duplicate LGD codes",
            invalid_data,
        )
        check(
            invalid_data["invalid_village_lgd_codes"]
            == [invalid_code],
            "Preview reports malformed LGD codes",
            invalid_data,
        )
        check(
            invalid_data["unknown_village_lgd_codes"]
            == [unknown_code],
            "Preview reports unknown LGD codes",
            invalid_data,
        )
        check(
            invalid_data["summary"]["can_apply"] is False,
            "Invalid preview cannot be applied",
            invalid_data["summary"],
        )
        check(
            invalid_data["governance"]["database_write_performed"]
            is False,
            "Preview declares read-only governance",
            invalid_data["governance"],
        )

        valid_preview = client.post(
            f"/api/v1/projects/{project_id}/"
            "geography-scope/import-preview",
            headers=headers,
            json={
                "village_lgd_codes": [
                    second_code,
                    first_code,
                ],
            },
        )
        valid_data = valid_preview.json()

        check(
            valid_preview.status_code == 200,
            "Valid import preview succeeds",
            valid_data,
        )
        check(
            valid_data["summary"]["can_apply"] is True,
            "Valid preview can be applied",
            valid_data["summary"],
        )
        check(
            valid_data["normalized_village_lgd_codes"]
            == [second_code, first_code],
            "Preview preserves first-seen LGD order",
            valid_data,
        )
        check(
            valid_data["accepted_villages"][0]["village_name"]
            == villages[1]["village_name"],
            "Preview returns canonical village labels",
            valid_data["accepted_villages"],
        )
        check(
            project_scope(db, project_id) == before_scope
            and audit_count(db, project_id) == before_audits,
            "Preview performs no project or audit writes",
            {
                "scope": project_scope(db, project_id),
                "audits": audit_count(db, project_id),
            },
        )

        empty_export = client.get(
            f"/api/v1/projects/{project_id}/"
            "geography-scope/export.csv",
            headers=headers,
        )
        empty_rows = list(csv.DictReader(
            io.StringIO(empty_export.text)
        ))

        check(
            empty_export.status_code == 200,
            "Empty scope export succeeds",
            empty_export.text,
        )
        check(
            empty_rows == [],
            "Empty scope export contains only its header",
            empty_rows,
        )

        apply_response = client.patch(
            f"/api/v1/projects/{project_id}/geography-scope",
            headers=headers,
            json={
                "village_lgd_codes":
                    valid_data["normalized_village_lgd_codes"],
                "reason":
                    "Apply validated project geography CSV preview",
            },
        )
        apply_data = apply_response.json()

        check(
            apply_response.status_code == 200,
            "Validated preview applies through guarded PATCH",
            apply_data,
        )
        check(
            set(
                apply_data["geography_scope"]
                ["village_lgd_codes"]
            ) == {first_code, second_code},
            "Applied scope contains both canonical villages",
            apply_data["geography_scope"],
        )
        check(
            audit_count(db, project_id) == before_audits + 1,
            "Apply creates exactly one audit event",
            {"audits": audit_count(db, project_id)},
        )

        export_response = client.get(
            f"/api/v1/projects/{project_id}/"
            "geography-scope/export.csv",
            headers=headers,
        )
        export_rows = list(csv.DictReader(
            io.StringIO(export_response.text)
        ))

        check(
            export_response.status_code == 200,
            "Populated scope export succeeds",
            export_response.text,
        )
        check(
            export_response.headers[
                "x-project-geography-scope-count"
            ] == "2",
            "Export reports the scope count",
            dict(export_response.headers),
        )
        check(
            len(export_rows) == 2,
            "Export contains one row per scoped village",
            export_rows,
        )
        check(
            {
                row["village_lgd_code"]
                for row in export_rows
            } == {first_code, second_code},
            "Export contains canonical LGD codes",
            export_rows,
        )
        check(
            all(
                row["village_name"]
                and row["district_name"]
                and row["state_name"]
                for row in export_rows
            ),
            "Export contains canonical hierarchy labels",
            export_rows,
        )

        db.execute(text("""
            update projects
            set status = 'ACTIVE'
            where id = cast(:project_id as uuid)
        """), {"project_id": project_id})
        db.commit()

        locked_preview = client.post(
            f"/api/v1/projects/{project_id}/"
            "geography-scope/import-preview",
            headers=headers,
            json={"village_lgd_codes": [first_code]},
        )
        locked_data = locked_preview.json()

        check(
            locked_preview.status_code == 200,
            "Locked project preview remains readable",
            locked_data,
        )
        check(
            locked_data["summary"]["can_apply"] is False,
            "Locked project preview cannot be applied",
            locked_data,
        )
        check(
            locked_data["edit_policy"]["lock_state"]
            == "LOCKED",
            "Preview exposes project lock state",
            locked_data["edit_policy"],
        )

        print("=" * 72)
        print(
            "PROJECT GEOGRAPHY SCOPE IMPORT/EXPORT "
            "API REGRESSION PASSED"
        )
        print("=" * 72)
        return 0
    finally:
        db.rollback()

        db.execute(text("""
            delete from project_app_config_audit_events
            where project_id = cast(:project_id as uuid)
        """), {"project_id": project_id})
        db.execute(text("""
            delete from projects
            where id = cast(:project_id as uuid)
        """), {"project_id": project_id})
        db.commit()

        if admin is not None:
            delete_test_admin(db, admin.id)

        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

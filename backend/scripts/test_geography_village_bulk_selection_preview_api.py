#!/usr/bin/env python3
"""Regression for district/block canonical village bulk previews."""

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


def check(condition: bool, label: str, detail=None) -> None:
    print(("PASS" if condition else "FAIL"), label)
    if detail is not None and not condition:
        print(json.dumps(detail, indent=2, default=str)[:5000])
    if not condition:
        raise AssertionError(label)


def protected_counts(db) -> dict:
    tables = [
        "geography_villages",
        "geography_boundary_crosswalk_candidates",
        "geography_boundary_project_matches",
        "project_app_config_audit_events",
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
    print("GEOGRAPHY VILLAGE BULK-SELECTION PREVIEW API REGRESSION")
    print("=" * 72)

    client = TestClient(app)
    db = SessionLocal()
    admin = None

    try:
        selectable_block = db.execute(text("""
            select
              block.id::text as block_id,
              block.canonical_name as block_name,
              district.id::text as district_id,
              district.canonical_name as district_name,
              count(village.id)::bigint as village_count
            from geography_blocks block
            join geography_districts district
              on district.id = block.district_id
             and district.is_active = true
            join geography_states state
              on state.id = district.state_id
             and state.is_active = true
            join geography_villages village
              on village.block_id = block.id
             and village.is_active = true
             and village.lgd_code is not null
            where block.is_active = true
            group by
              block.id,
              block.canonical_name,
              district.id,
              district.canonical_name
            having count(village.id) between 2 and 500
            order by count(village.id) desc, block.id
            limit 1
        """)).mappings().first()

        selectable_district = db.execute(text("""
            select
              district.id::text as district_id,
              district.canonical_name as district_name,
              count(village.id)::bigint as village_count
            from geography_districts district
            join geography_states state
              on state.id = district.state_id
             and state.is_active = true
            join geography_villages village
              on village.district_id = district.id
             and village.is_active = true
             and village.lgd_code is not null
            join geography_blocks block
              on block.id = village.block_id
             and block.is_active = true
            where district.is_active = true
            group by district.id, district.canonical_name
            having count(village.id) between 2 and 500
            order by count(village.id) desc, district.id
            limit 1
        """)).mappings().first()

        oversized_district = db.execute(text("""
            select
              district.id::text as district_id,
              district.canonical_name as district_name,
              count(village.id)::bigint as village_count
            from geography_districts district
            join geography_states state
              on state.id = district.state_id
             and state.is_active = true
            join geography_villages village
              on village.district_id = district.id
             and village.is_active = true
             and village.lgd_code is not null
            join geography_blocks block
              on block.id = village.block_id
             and block.is_active = true
            where district.is_active = true
            group by district.id, district.canonical_name
            having count(village.id) > 500
            order by count(village.id) desc, district.id
            limit 1
        """)).mappings().first()

        fixtures = {
            "selectable_block": (
                dict(selectable_block)
                if selectable_block else None
            ),
            "selectable_district": (
                dict(selectable_district)
                if selectable_district else None
            ),
            "oversized_district": (
                dict(oversized_district)
                if oversized_district else None
            ),
        }
        check(
            all(fixtures.values()),
            "Selectable block/district and oversized district exist",
            fixtures,
        )

        admin, headers = create_test_admin(
            db,
            role="ENTERPRISE_ADMIN",
            tenant_id="default",
        )

        before = protected_counts(db)

        block_response = client.get(
            "/api/v1/master-data/geography/"
            "villages/bulk-selection-preview",
            headers=headers,
            params={
                "block_id": selectable_block["block_id"],
            },
        )
        block_data = block_response.json()

        check(
            block_response.status_code == 200,
            "Block bulk preview succeeds",
            block_data,
        )
        check(
            block_data["scope"]["scope_type"] == "BLOCK"
            and block_data["scope"]["scope_id"]
            == selectable_block["block_id"],
            "Block scope metadata is returned",
            block_data["scope"],
        )
        check(
            block_data["summary"]["total_village_count"]
            == selectable_block["village_count"],
            "Block preview reports the complete village count",
            block_data["summary"],
        )
        check(
            block_data["summary"]["returned_village_count"]
            == selectable_block["village_count"]
            and block_data["summary"]["can_select_entire_scope"]
            is True,
            "Selectable block returns every village",
            block_data["summary"],
        )
        check(
            all(
                row["block_id"] == selectable_block["block_id"]
                for row in block_data["items"]
            ),
            "Block preview contains only block villages",
            block_data["items"][:5],
        )
        check(
            (
                block_data["summary"]["eligible_village_count"]
                + block_data["summary"]["missing_village_count"]
                + block_data["summary"]["blocked_village_count"]
            )
            == block_data["summary"]["total_village_count"],
            "Block readiness counts account for every village",
            block_data["summary"],
        )

        district_response = client.get(
            "/api/v1/master-data/geography/"
            "villages/bulk-selection-preview",
            headers=headers,
            params={
                "district_id":
                    selectable_district["district_id"],
            },
        )
        district_data = district_response.json()

        check(
            district_response.status_code == 200,
            "District bulk preview succeeds",
            district_data,
        )
        check(
            district_data["scope"]["scope_type"] == "DISTRICT"
            and district_data["scope"]["scope_id"]
            == selectable_district["district_id"],
            "District scope metadata is returned",
            district_data["scope"],
        )
        check(
            district_data["summary"]["total_village_count"]
            == selectable_district["village_count"]
            and len(district_data["items"])
            == selectable_district["village_count"],
            "Selectable district returns every village",
            district_data["summary"],
        )
        check(
            all(
                row["district_id"]
                == selectable_district["district_id"]
                for row in district_data["items"]
            ),
            "District preview contains only district villages",
            district_data["items"][:5],
        )
        check(
            all(
                row["village_lgd_code"]
                and row["village_name"]
                and row["block_name"]
                and row["district_name"]
                and row["state_name"]
                and row["boundary_status"]
                in {"ELIGIBLE", "MISSING", "BLOCKED"}
                for row in district_data["items"]
            ),
            "Preview rows contain canonical hierarchy and readiness",
            district_data["items"][:5],
        )

        oversized_response = client.get(
            "/api/v1/master-data/geography/"
            "villages/bulk-selection-preview",
            headers=headers,
            params={
                "district_id":
                    oversized_district["district_id"],
            },
        )
        oversized_data = oversized_response.json()

        check(
            oversized_response.status_code == 200,
            "Oversized district preview succeeds",
            oversized_data,
        )
        check(
            oversized_data["summary"]["total_village_count"]
            == oversized_district["village_count"]
            and oversized_data["summary"]["returned_village_count"]
            == 500,
            "Oversized preview reports total and returned counts",
            oversized_data["summary"],
        )
        check(
            oversized_data["summary"]["can_select_entire_scope"]
            is False
            and oversized_data["summary"]
            ["scope_within_selection_limit"] is False,
            "Oversized district cannot be selected silently",
            oversized_data["summary"],
        )
        check(
            oversized_data["guardrails"]["results_truncated"]
            is True
            and oversized_data["guardrails"]
            ["oversized_scope_rejected"] is True,
            "Oversized truncation is explicit",
            oversized_data["guardrails"],
        )

        missing_scope = client.get(
            "/api/v1/master-data/geography/"
            "villages/bulk-selection-preview",
            headers=headers,
        )
        check(
            missing_scope.status_code == 400,
            "Preview rejects a missing scope",
            missing_scope.json(),
        )

        duplicate_scope = client.get(
            "/api/v1/master-data/geography/"
            "villages/bulk-selection-preview",
            headers=headers,
            params={
                "district_id":
                    selectable_district["district_id"],
                "block_id": selectable_block["block_id"],
            },
        )
        check(
            duplicate_scope.status_code == 400,
            "Preview rejects district and block together",
            duplicate_scope.json(),
        )

        unknown_scope = client.get(
            "/api/v1/master-data/geography/"
            "villages/bulk-selection-preview",
            headers=headers,
            params={
                "block_id":
                    "00000000-0000-0000-0000-000000000000",
            },
        )
        check(
            unknown_scope.status_code == 404,
            "Preview rejects an unknown scope",
            unknown_scope.json(),
        )

        check(
            block_data["guardrails"]["database_write_performed"]
            is False,
            "Preview declares read-only governance",
            block_data["guardrails"],
        )
        check(
            protected_counts(db) == before,
            "Bulk previews perform no protected-table writes",
            {
                "before": before,
                "after": protected_counts(db),
            },
        )

        print("=" * 72)
        print(
            "GEOGRAPHY VILLAGE BULK-SELECTION "
            "PREVIEW API REGRESSION PASSED"
        )
        print("=" * 72)
        return 0
    finally:
        db.rollback()
        if admin is not None:
            delete_test_admin(db, admin.id)
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

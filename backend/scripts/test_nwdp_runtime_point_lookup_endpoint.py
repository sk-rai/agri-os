#!/usr/bin/env python3
"""Regression for guarded native NWDP runtime point lookup."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal
from app.main import app
from scripts.admin_auth_test_utils import (
    create_test_admin,
    delete_test_admin,
)


ENDPOINT = (
    "/api/v1/master-data/geography/"
    "nwdp-boundary-runtime/point-lookup"
)
RUNTIME_SET_ID = (
    "e5f93e27-a0bd-5c8b-bef3-d97986e14c55"
)


def check(condition: bool, label: str, detail=None) -> None:
    print(f"{'PASS' if condition else 'FAIL'} {label}")
    if not condition:
        raise AssertionError(f"{label}: {detail}")


def database_counts(db) -> dict[str, int]:
    row = db.execute(text("""
        select
          (
            select count(*)::bigint
            from geography_boundary_runtime_sets
          ) as runtime_set_rows,
          (
            select count(*)::bigint
            from geography_boundary_runtime_features
          ) as runtime_feature_rows,
          (
            select count(*)::bigint
            from geography_boundary_runtime_crosswalks
          ) as runtime_crosswalk_rows,
          (
            select count(*)::bigint
            from geography_boundary_project_matches
          ) as project_match_rows,
          (
            select count(*)::bigint
            from geography_boundary_crosswalk_candidates
            where is_active = true
          ) as active_candidate_rows,
          (
            select count(*)::bigint
            from geography_boundary_crosswalk_candidates
            where promotion_status = 'PROMOTED'
          ) as promoted_candidate_rows
    """)).mappings().one()

    return {
        key: int(value or 0)
        for key, value in row.items()
    }


def main() -> int:
    client = TestClient(app)
    db = SessionLocal()
    admin = None
    original_flag = (
        settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED
    )

    try:
        before = database_counts(db)

        unauthenticated = client.get(
            ENDPOINT,
            params={
                "latitude": 15.9,
                "longitude": 75.5,
                "runtime_set_id": RUNTIME_SET_ID,
            },
        )
        check(
            unauthenticated.status_code in {401, 403},
            "Unauthenticated lookup is denied",
            unauthenticated.text,
        )

        admin, headers = create_test_admin(
            db,
            role="ADMIN_VIEWER",
            tenant_id="default",
        )

        settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED = False

        disabled = client.get(
            ENDPOINT,
            params={
                "latitude": 15.9,
                "longitude": 75.5,
                "runtime_set_id": RUNTIME_SET_ID,
            },
            headers=headers,
        )
        check(
            disabled.status_code == 503,
            "Feature flag defaults closed",
            disabled.text,
        )
        check(
            disabled.json()["detail"]["code"]
            == "NWDP_RUNTIME_LOOKUP_DISABLED",
            "Disabled response has stable code",
            disabled.text,
        )

        missing_scope = client.get(
            ENDPOINT,
            params={
                "latitude": 15.9,
                "longitude": 75.5,
            },
            headers=headers,
        )
        check(
            missing_scope.status_code == 422,
            "Runtime set scope is required",
            missing_scope.text,
        )

        invalid = client.get(
            ENDPOINT,
            params={
                "latitude": 91,
                "longitude": 75.5,
                "runtime_set_id": RUNTIME_SET_ID,
            },
            headers=headers,
        )
        check(
            invalid.status_code == 422,
            "Coordinate bounds are enforced",
            invalid.text,
        )

        point = db.execute(
            text("""
                select
                  ST_Y(
                    ST_PointOnSurface(
                      geometry_wgs84_geom
                    )
                  ) as latitude,
                  ST_X(
                    ST_PointOnSurface(
                      geometry_wgs84_geom
                    )
                  ) as longitude,
                  id::text as runtime_feature_id
                from geography_boundary_runtime_features
                where runtime_set_id =
                      cast(:runtime_set_id as uuid)
                  and is_active = true
                  and geometry_wgs84_geom is not null
                order by id
                limit 1
            """),
            {"runtime_set_id": RUNTIME_SET_ID},
        ).mappings().one()

        settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED = True

        matched = client.get(
            ENDPOINT,
            params={
                "latitude": float(point["latitude"]),
                "longitude": float(point["longitude"]),
                "runtime_set_id": RUNTIME_SET_ID,
            },
            headers=headers,
        )
        check(
            matched.status_code == 200,
            "Admin viewer can run enabled lookup",
            matched.text,
        )

        matched_data = matched.json()
        check(
            matched_data["schema_version"]
            == "nwdp_boundary_runtime_point_lookup.v1",
            "Lookup response schema is stable",
            matched_data,
        )
        check(
            matched_data["status"] == "MATCHED",
            "Interior point is matched",
            matched_data,
        )
        check(
            matched_data["match_count"] == 1,
            "Interior point matches exactly once",
            matched_data,
        )
        check(
            matched_data["runtime_feature_id"]
            == point["runtime_feature_id"],
            "Expected runtime feature is returned",
            matched_data,
        )
        check(
            matched_data["runtime_set_id"]
            == RUNTIME_SET_ID,
            "Expected runtime set is returned",
            matched_data,
        )
        check(
            matched_data["runtime_scope"] == "village",
            "Village runtime scope is returned",
            matched_data,
        )
        check(
            matched_data["village_id"] is not None
            and matched_data["village_lgd_code"] is not None,
            "Village identity is complete",
            matched_data,
        )
        check(
            matched_data["geometry_hash"] is not None,
            "Geometry lineage hash is returned",
            matched_data,
        )

        outside = client.get(
            ENDPOINT,
            params={
                "latitude": 0,
                "longitude": 0,
                "runtime_set_id": RUNTIME_SET_ID,
            },
            headers=headers,
        )
        check(
            outside.status_code == 200,
            "Outside lookup completes",
            outside.text,
        )
        check(
            outside.json()["status"] == "UNMATCHED"
            and outside.json()["match_count"] == 0,
            "Outside point remains unmatched",
            outside.json(),
        )

        after = database_counts(db)
        check(
            after == before,
            "Lookup leaves database counts unchanged",
            {
                "before": before,
                "after": after,
            },
        )
        check(
            after["active_candidate_rows"] == 0,
            "Candidates remain inactive",
            after,
        )
        check(
            after["promoted_candidate_rows"] == 0,
            "Candidates remain unpromoted",
            after,
        )
        check(
            after["project_match_rows"] == 0,
            "Project matches remain unwritten",
            after,
        )

        print(
            "\n# NWDP RUNTIME POINT LOOKUP "
            "ENDPOINT REGRESSION PASSED"
        )
        return 0
    finally:
        settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED = (
            original_flag
        )
        if admin is not None:
            delete_test_admin(db, admin.id)
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

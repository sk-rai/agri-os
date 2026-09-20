#!/usr/bin/env python3
"""Read-only point lookup against the pinned 10-row runtime fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.database import engine

EXPECTED_SET_ID = "e5f93e27-a0bd-5c8b-bef3-d97986e14c55"
EXPECTED_FEATURE_COUNT = 10


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fixture",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--points",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def database_counts(connection) -> dict[str, int]:
    row = connection.execute(text("""
        select
          (
            select count(*)::bigint
            from geography_boundary_runtime_sets
            where is_active = true
          ) as active_runtime_set_count,
          (
            select count(*)::bigint
            from geography_boundary_runtime_features
            where is_active = true
          ) as active_runtime_feature_count,
          (
            select count(*)::bigint
            from geography_boundary_runtime_crosswalks
            where is_active = true
          ) as active_runtime_crosswalk_count,
          (
            select count(*)::bigint
            from geography_boundary_crosswalk_candidates
            where is_active = true
          ) as active_candidate_count,
          (
            select count(*)::bigint
            from geography_boundary_crosswalk_candidates
            where promotion_status = 'PROMOTED'
          ) as promoted_candidate_count,
          (
            select count(*)::bigint
            from geography_boundary_project_matches
          ) as project_match_count
    """)).mappings().one()

    return {
        key: int(value or 0)
        for key, value in row.items()
    }


def main() -> int:
    options = arguments()

    fixture = json.loads(
        options.fixture.read_text(encoding="utf-8")
    )
    points = json.loads(
        options.points.read_text(encoding="utf-8")
    )

    polygons = fixture.get("features") or []
    point_features = points.get("features") or []

    if fixture.get("type") != "FeatureCollection":
        raise SystemExit("LOOKUP_FIXTURE_NOT_FEATURE_COLLECTION")
    if len(polygons) != EXPECTED_FEATURE_COUNT:
        raise SystemExit(
            "LOOKUP_FIXTURE_FEATURE_COUNT_MISMATCH"
        )
    if points.get("type") != "FeatureCollection":
        raise SystemExit("LOOKUP_POINTS_NOT_FEATURE_COLLECTION")
    if not point_features:
        raise SystemExit("LOOKUP_POINTS_EMPTY")

    runtime_feature_ids = {
        row.get("properties", {}).get("runtime_feature_id")
        for row in polygons
    }
    runtime_crosswalk_ids = {
        row.get("properties", {}).get("runtime_crosswalk_id")
        for row in polygons
    }
    source_indexes = {
        row.get("properties", {}).get("source_feature_index")
        for row in polygons
    }

    if None in runtime_feature_ids or len(runtime_feature_ids) != 10:
        raise SystemExit("LOOKUP_RUNTIME_FEATURE_IDENTITIES_INVALID")
    if None in runtime_crosswalk_ids or len(runtime_crosswalk_ids) != 10:
        raise SystemExit("LOOKUP_RUNTIME_CROSSWALK_IDENTITIES_INVALID")
    if None in source_indexes or len(source_indexes) != 10:
        raise SystemExit("LOOKUP_SOURCE_INDEXES_INVALID")

    point_ids = []
    for position, feature in enumerate(point_features):
        properties = feature.get("properties") or {}
        point_id = str(
            properties.get("point_id")
            or feature.get("id")
            or f"point-{position + 1}"
        )
        geometry = feature.get("geometry") or {}

        if geometry.get("type") != "Point":
            raise SystemExit(
                f"LOOKUP_POINT_GEOMETRY_INVALID:{point_id}"
            )

        coordinates = geometry.get("coordinates") or []
        if len(coordinates) < 2:
            raise SystemExit(
                f"LOOKUP_POINT_COORDINATES_INVALID:{point_id}"
            )

        longitude = float(coordinates[0])
        latitude = float(coordinates[1])
        if not (-180 <= longitude <= 180):
            raise SystemExit(
                f"LOOKUP_LONGITUDE_INVALID:{point_id}"
            )
        if not (-90 <= latitude <= 90):
            raise SystemExit(
                f"LOOKUP_LATITUDE_INVALID:{point_id}"
            )

        properties["point_id"] = point_id
        feature["properties"] = properties
        point_ids.append(point_id)

    if len(set(point_ids)) != len(point_ids):
        raise SystemExit("LOOKUP_POINT_IDENTITIES_NOT_UNIQUE")

    polygon_payload = json.dumps(
        polygons,
        separators=(",", ":"),
    )
    point_payload = json.dumps(
        point_features,
        separators=(",", ":"),
    )

    with engine.connect() as connection:
        before = database_counts(connection)

        rows = [
            dict(row)
            for row in connection.execute(
                text("""
                    with polygon_input as (
                      select
                        p.id as fixture_feature_id,
                        p.properties,
                        ST_SetSRID(
                          ST_GeomFromGeoJSON(
                            p.geometry::text
                          ),
                          4326
                        ) as geom
                      from jsonb_to_recordset(
                        cast(:polygons as jsonb)
                      ) as p(
                        type text,
                        id text,
                        properties jsonb,
                        geometry jsonb
                      )
                    ),
                    point_input as (
                      select
                        q.properties->>'point_id'
                          as point_id,
                        (q.geometry->'coordinates'->>0)
                          ::double precision
                          as longitude,
                        (q.geometry->'coordinates'->>1)
                          ::double precision
                          as latitude,
                        ST_SetSRID(
                          ST_MakePoint(
                            (q.geometry->'coordinates'->>0)
                              ::double precision,
                            (q.geometry->'coordinates'->>1)
                              ::double precision
                          ),
                          4326
                        ) as geom
                      from jsonb_to_recordset(
                        cast(:points as jsonb)
                      ) as q(
                        type text,
                        id text,
                        properties jsonb,
                        geometry jsonb
                      )
                    )
                    select
                      q.point_id,
                      q.longitude,
                      q.latitude,
                      count(p.fixture_feature_id)::bigint
                        as match_count,
                      coalesce(
                        jsonb_agg(
                          jsonb_build_object(
                            'runtime_feature_id',
                              p.properties
                                ->>'runtime_feature_id',
                            'runtime_crosswalk_id',
                              p.properties
                                ->>'runtime_crosswalk_id',
                            'source_feature_index',
                              p.properties
                                ->>'source_feature_index',
                            'village_id',
                              p.properties
                                ->>'village_id',
                            'village_lgd_code',
                              p.properties
                                ->>'village_lgd_code'
                          )
                          order by
                            p.properties
                              ->>'runtime_feature_id'
                        ) filter (
                          where p.fixture_feature_id
                            is not null
                        ),
                        '[]'::jsonb
                      ) as matches
                    from point_input q
                    left join polygon_input p
                      on ST_Covers(p.geom, q.geom)
                    group by
                      q.point_id,
                      q.longitude,
                      q.latitude
                    order by q.point_id
                """),
                {
                    "polygons": polygon_payload,
                    "points": point_payload,
                },
            ).mappings().all()
        ]

        after = database_counts(connection)

    normalized_rows = []
    for row in rows:
        normalized_rows.append({
            "point_id": row["point_id"],
            "longitude": float(row["longitude"]),
            "latitude": float(row["latitude"]),
            "match_count": int(row["match_count"]),
            "status": (
                "MATCHED"
                if int(row["match_count"]) == 1
                else (
                    "UNMATCHED"
                    if int(row["match_count"]) == 0
                    else "AMBIGUOUS"
                )
            ),
            "matches": row["matches"],
        })

    matched_count = sum(
        row["status"] == "MATCHED"
        for row in normalized_rows
    )
    unmatched_count = sum(
        row["status"] == "UNMATCHED"
        for row in normalized_rows
    )
    ambiguous_count = sum(
        row["status"] == "AMBIGUOUS"
        for row in normalized_rows
    )

    checks = {
        "fixture_has_exactly_10_features":
            len(polygons) == 10,
        "runtime_feature_identities_unique":
            len(runtime_feature_ids) == 10,
        "runtime_crosswalk_identities_unique":
            len(runtime_crosswalk_ids) == 10,
        "source_feature_indexes_unique":
            len(source_indexes) == 10,
        "all_points_evaluated":
            len(normalized_rows) == len(point_features),
        "no_ambiguous_matches":
            ambiguous_count == 0,
        "database_counts_unchanged":
            before == after,
    }

    report = {
        "schema_version":
            "nwdp_runtime_point_lookup_preview.v1",
        "generated_at":
            datetime.now(timezone.utc).isoformat(),
        "healthy": all(checks.values()),
        "mode":
            "READ_ONLY_10_ROW_POINT_LOOKUP_PREVIEW",
        "runtime_set_id": EXPECTED_SET_ID,
        "spatial_predicate": "ST_Covers",
        "fixture": {
            "path": str(options.fixture.resolve()),
            "sha256": sha256_file(options.fixture),
            "feature_count": len(polygons),
        },
        "point_input": {
            "path": str(options.points.resolve()),
            "sha256": sha256_file(options.points),
            "point_count": len(point_features),
        },
        "summary": {
            "point_count": len(normalized_rows),
            "matched_count": matched_count,
            "unmatched_count": unmatched_count,
            "ambiguous_count": ambiguous_count,
        },
        "checks": checks,
        "results": normalized_rows,
        "database_counts": {
            "before": before,
            "after": after,
            "unchanged": before == after,
        },
        "guardrails": {
            "database_writes_attempted": False,
            "runtime_tables_written": False,
            "runtime_lookup_enabled": False,
            "runtime_spatial_matching_changed": False,
            "project_matches_written": False,
            "candidate_activation_changed": False,
            "candidate_promotion_changed": False,
            "source_features_changed": False,
            "source_files_changed": False,
            "android_behavior_changed": False,
        },
        "readiness": {
            "preview_complete": all(checks.values()),
            "production_lookup_enabled": False,
            "production_lookup_ready": False,
            "requires_separate_production_checkpoint": True,
        },
    }

    options.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    options.output.write_text(
        json.dumps(
            report,
            indent=2,
            sort_keys=True,
            default=str,
        ) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(
        report,
        indent=2,
        sort_keys=True,
        default=str,
    ))

    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

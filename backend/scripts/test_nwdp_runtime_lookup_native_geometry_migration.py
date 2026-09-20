#!/usr/bin/env python3
"""Static regression for runtime lookup native geometry migration."""

from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "backend/alembic/versions/"
    / "059_add_runtime_lookup_native_geometry.py"
)


def check(
    label: str,
    condition: bool,
    payload=None,
) -> None:
    if not condition:
        print(f"FAIL {label}")
        if payload is not None:
            print(json.dumps(
                payload,
                indent=2,
                default=str,
            )[:3000])
        raise SystemExit(1)
    print(f"PASS {label}")


def main() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    tree = ast.parse(source)

    check(
        "Migration parses",
        isinstance(tree, ast.Module),
    )
    check(
        "Migration revision follows 058",
        'revision = "059"' in source
        and 'down_revision = "058"' in source,
    )
    check(
        "Migration targets runtime features",
        (
            'TABLE = '
            '"geography_boundary_runtime_features"'
        ) in source,
    )
    check(
        "Native geometry column is explicit",
        'COLUMN = "geometry_wgs84_geom"' in source
        and 'geometry_type="GEOMETRY"' in source
        and "srid=4326" in source,
    )
    check(
        "Native geometry starts nullable",
        "nullable=True" in source,
    )
    check(
        "Automatic spatial index is disabled",
        "spatial_index=False" in source,
    )
    check(
        "SRID constraint is present",
        "ST_SRID" in source
        and "= 4326" in source,
    )
    check(
        "Polygon type constraint is present",
        "ST_GeometryType" in source
        and "ST_Polygon" in source
        and "ST_MultiPolygon" in source,
    )
    check(
        "Validity constraints are present",
        "ST_IsValid" in source
        and "ST_IsEmpty" in source,
    )
    check(
        "Existing null rows remain valid",
        source.count(
            'f"{COLUMN} is null "'
        ) == 3,
    )
    check(
        "Partial GiST index is present",
        "using gist" in source.lower()
        and "where is_active = true" in source
        and (
            "and {COLUMN} is not null"
            in source
        ),
    )
    check(
        "Index creation is concurrent",
        "create index concurrently" in source.lower()
        and "autocommit_block()" in source,
    )
    check(
        "Migration contains no geometry backfill",
        "update geography_boundary_runtime_features"
        not in source.lower()
        and "ST_GeomFromGeoJSON" not in source,
    )
    check(
        "Migration contains no lookup endpoint",
        "@router." not in source
        and "lookup_api_enabled" not in source,
    )
    check(
        "Downgrade drops index first",
        source.index(
            "drop index concurrently"
        )
        < source.index(
            "op.drop_constraint"
        )
        < source.index(
            "op.drop_column"
        ),
    )
    check(
        "Migration claim boundary is explicit",
        "does not backfill geometry" in source
        and "enable lookup" in source,
    )

    print()
    print(
        "# NWDP RUNTIME LOOKUP NATIVE GEOMETRY "
        "MIGRATION REGRESSION PASSED"
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Static regression for guarded native geometry rehearsal."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    ROOT
    / "backend/scripts/"
    / "rehearse_nwdp_runtime_lookup_native_geometry.py"
)


def check(label: str, condition: bool) -> None:
    if not condition:
        print(f"FAIL {label}")
        raise SystemExit(1)
    print(f"PASS {label}")


def main() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    ast.parse(source)

    check(
        "Explicit confirmation is required",
        "--confirm-rollback-only-rehearsal"
        in source
        and (
            "ROLLBACK_ONLY_REHEARSAL_"
            "CONFIRMATION_REQUIRED"
        ) in source,
    )
    check(
        "Alembic upgrade is never invoked",
        "alembic upgrade" not in source.lower()
        and "command.upgrade" not in source,
    )
    check(
        "Alembic version is read only",
        "from alembic_version" in source
        and "update alembic_version" not in source.lower()
        and "insert into alembic_version"
        not in source.lower(),
    )
    check(
        "Transaction rollback is unconditional",
        "finally:" in source
        and "transaction.rollback()" in source,
    )
    check(
        "Native geometry is rehearsed",
        "geometry(Geometry,4326)" in source,
    )
    check(
        "All three constraints are rehearsed",
        "ST_SRID" in source
        and "ST_GeometryType" in source
        and "ST_IsValid" in source
        and "ST_IsEmpty" in source,
    )
    check(
        "Partial GiST index is rehearsed",
        "using gist" in source.lower()
        and "where is_active = true" in source,
    )
    check(
        "Concurrent index is not executed in transaction",
        (
            "connection.execute(text(f\"\"\"\n"
            "            create index concurrently"
        ) not in source.lower()
        and (
            "connection.execute(text(f\"\"\"\n"
            "            create index {index}"
        ) in source.lower(),
    )
    check(
        "Fresh connection verifies rollback",
        "after_catalog = catalog(connection)"
        in source,
    )
    check(
        "No backfill is present",
        (
            "update "
            "geography_boundary_runtime_features"
        ) not in source.lower()
        and "ST_GeomFromGeoJSON" not in source,
    )
    check(
        "Lookup remains disabled",
        '"lookup_api_enabled": False' in source,
    )

    print()
    print(
        "# NWDP RUNTIME LOOKUP NATIVE GEOMETRY "
        "REHEARSAL CONTRACT PASSED"
    )


if __name__ == "__main__":
    main()

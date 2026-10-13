#!/usr/bin/env python3
"""Static authorization contract for weather snapshot reads."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = (
    ROOT / "backend/app/modules/media/weather_api.py"
)
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)

ROUTES = {
    "list_weather_snapshots",
    "latest_weather_snapshot",
}


def check(condition: bool, label: str) -> None:
    print(f"{'PASS' if condition else 'FAIL'} {label}")
    if not condition:
        raise AssertionError(label)


def function_source(name: str) -> str:
    node = next(
        (
            item
            for item in ast.walk(TREE)
            if isinstance(item, ast.FunctionDef)
            and item.name == name
        ),
        None,
    )
    if node is None:
        raise AssertionError(f"{name} not found")
    value = ast.get_source_segment(SOURCE, node)
    if value is None:
        raise AssertionError(
            f"Could not extract {name}"
        )
    return value


for name in sorted(ROUTES):
    route = function_source(name)
    check(
        (
            "require_admin_permission("
            "AdminPermission.VIEW)"
        ) in route,
        f"{name} requires view permission",
    )
    check(
        "tenant_id = principal.tenant_id" in route,
        f"{name} derives verified tenant",
    )
    check(
        "actor_id = principal.user_id" in route,
        f"{name} derives verified actor",
    )
    check(
        "_snapshot_query(db, tenant_id)" in route,
        f"{name} tenant-bounds snapshot query",
    )
    check(
        'alias="X-Tenant-ID"' not in route,
        f"{name} does not trust tenant header directly",
    )

listing = function_source("list_weather_snapshots")
for field in (
    "provider_id",
    "project_id",
    "farmer_id",
    "parcel_id",
    "location_scope",
    "location_key",
):
    check(
        (
            f"WeatherSnapshot.{field}"
            if field.endswith("_id")
            else f"WeatherSnapshot.{field}"
        ) in listing,
        f"Weather list preserves {field} filter",
    )

latest = function_source("latest_weather_snapshot")
check(
    'raise HTTPException(404, "Weather snapshot not found")'
    in latest,
    "Latest weather read hides unavailable snapshot",
)

print(
    "WEATHER SNAPSHOT READ AUTH "
    "STATIC CONTRACT PASSED"
)

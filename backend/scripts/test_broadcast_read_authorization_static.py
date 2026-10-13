#!/usr/bin/env python3
"""Static authorization contract for broadcast read routes."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = (
    ROOT / "backend/app/modules/media/broadcast_api.py"
)
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)

ADMIN_READS = {
    "list_broadcast_campaigns",
    "list_broadcast_deliveries",
    "preview_broadcast_audience",
    "list_broadcast_audit_events",
    "get_broadcast_campaign",
}
FARMER_READ = "list_farmer_broadcasts"


def check(condition: bool, label: str) -> None:
    print(f"{'PASS' if condition else 'FAIL'} {label}")
    if not condition:
        raise AssertionError(label)


def function_source(name: str) -> str:
    node = next(
        (
            item
            for item in ast.walk(TREE)
            if isinstance(
                item,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            )
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


for name in sorted(ADMIN_READS):
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
        'alias="X-Tenant-ID"' not in route,
        f"{name} does not trust tenant header directly",
    )

farmer_route = function_source(FARMER_READ)
check(
    "require_authenticated_human()" in farmer_route,
    "Farmer broadcast feed requires authenticated human",
)
check(
    "tenant_id = principal.tenant_id" in farmer_route,
    "Farmer broadcast feed derives verified tenant",
)
check(
    "actor_id = principal.user_id" in farmer_route,
    "Farmer broadcast feed derives verified actor",
)
check(
    (
        "_require_broadcast_farmer_access("
        "db, farmer, principal)"
    ) in farmer_route,
    "Farmer broadcast feed enforces ownership or assignment",
)
check(
    'alias="X-Tenant-ID"' not in farmer_route,
    "Farmer broadcast feed does not trust tenant header directly",
)

helper = function_source(
    "_require_broadcast_farmer_access"
)
check(
    (
        "farmer.tenant_id "
        "!= principal.tenant_id"
    ) in helper,
    "Farmer access helper enforces tenant boundary",
)
check(
    (
        "farmer.user_id "
        "== principal.user_id"
    ) in helper,
    "Farmer access helper permits linked farmer owner",
)
check(
    (
        "FarmerProjectEnrollment.tenant_id "
        "== principal.tenant_id"
    ) in helper,
    "Farmer access helper tenant-bounds assignments",
)
check(
    (
        "FarmerProjectEnrollment.status "
        '== "ACTIVE"'
    ) in helper,
    "Farmer access helper requires active assignment",
)
check(
    '"BROADCAST_FARMER_ACCESS_DENIED"' in helper,
    "Farmer access helper exposes stable denial code",
)

print(
    "BROADCAST READ AUTHORIZATION "
    "STATIC CONTRACT PASSED"
)

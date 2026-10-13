#!/usr/bin/env python3
"""Static authorization contract for soil-enrichment operations."""

from __future__ import annotations

import ast
from pathlib import Path


SOURCE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app/modules/farmer/soil_profile.py"
)
source = SOURCE_PATH.read_text(encoding="utf-8-sig")
tree = ast.parse(source)


def function_source(name: str) -> str:
    node = next(
        (
            item
            for item in ast.walk(tree)
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and item.name == name
        ),
        None,
    )
    if node is None:
        raise AssertionError(f"{name} not found")
    value = ast.get_source_segment(source, node)
    if value is None:
        raise AssertionError(f"Could not extract {name}")
    return value


def check(condition, label):
    print(f"{'PASS' if condition else 'FAIL'} {label}")
    if not condition:
        raise AssertionError(label)


scope = function_source(
    "_assert_soil_enrichment_operational_scope"
)
record = function_source(
    "record_soil_enrichment_job_audit"
)
route_worker = function_source(
    "run_soil_enrichment_queue_worker"
)
worker = function_source(
    "_run_soil_enrichment_queue_worker"
)

for name, body in (
    ("record_soil_enrichment_job_audit", record),
    ("run_soil_enrichment_queue_worker", route_worker),
):
    check(
        "AdminPermission.EDIT" in body,
        f"{name} requires edit permission",
    )
    check(
        "tenant_id = principal.tenant_id" in body,
        f"{name} derives verified tenant",
    )
    check(
        "actor_id = principal.user_id" in body,
        f"{name} derives verified actor",
    )
    check(
        "x_tenant_id" not in body,
        f"{name} does not trust tenant header directly",
    )
    check(
        "_assert_soil_enrichment_operational_scope(" in body,
        f"{name} validates operational references",
    )

check(
    "Farmer.tenant_id == tenant_id" in scope,
    "Operational scope tenant-bounds farmer",
)
check(
    "Parcel.tenant_id == tenant_id" in scope,
    "Operational scope tenant-bounds parcel",
)
check(
    "Project.tenant_id == tenant_id" in scope,
    "Operational scope tenant-bounds project",
)
check(
    '"SOIL_ENRICHMENT_SCOPE_MISMATCH"' in scope,
    "Operational scope rejects inconsistent references",
)

check(
    "tenant_id=tenant_id" in record,
    "Manual audit persists verified tenant",
)
check(
    '"recorded_by": str(actor_id)' in record,
    "Manual audit records verified administrator",
)
check(
    '"recorded_via": "ADMIN_API"' in record,
    "Manual audit records administrative source",
)

check(
    "actor_id=actor_id" in route_worker,
    "Worker receives verified administrator",
)
check(
    "_soil_enrichment_reference_uuid(" in route_worker,
    "Worker validates demo target UUIDs",
)
check(
    "demo_parcel_id" in route_worker,
    "Worker tenant-bounds demo parcel target",
)
check(
    "actor_id: Optional[uuid.UUID] = None" in worker,
    "Worker helper accepts explicit verified actor",
)
check(
    '"requested_by": str(actor_id) if actor_id else None'
    in worker,
    "Worker attributes created audit rows",
)
check(
    "requested_by: Optional[str] = None" in source,
    "Worker response exposes verified administrator",
)

print("SOIL ENRICHMENT OPERATIONS AUTH STATIC CONTRACT PASSED")

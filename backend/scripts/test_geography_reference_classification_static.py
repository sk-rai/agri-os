#!/usr/bin/env python3
"""Static contract for canonical geography reference GET routes."""

import ast
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GEOGRAPHY_PATH = (
    ROOT / "backend/app/modules/master_data/api/geography.py"
)
AUDIT_PATH = (
    ROOT / "backend/scripts/audit_tenant_actor_trust_boundary.py"
)

EXPECTED = {
    "geography_hierarchy_profile":
        "/geography/hierarchy-profile",
    "list_states":
        "/geography/states",
    "list_districts":
        "/geography/districts",
    "list_blocks":
        "/geography/blocks",
    "list_villages":
        "/geography/villages",
    "villages_by_lgd_codes":
        "/geography/villages/by-lgd-codes",
    "villages_by_pin_code":
        "/geography/villages/by-pin-code",
    "search_villages":
        "/geography/villages/search",
}


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print("PASS", message)


source = GEOGRAPHY_PATH.read_text(encoding="utf-8-sig")
tree = ast.parse(source)
functions = {
    node.name: node
    for node in ast.walk(tree)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}

check(
    set(EXPECTED) <= set(functions),
    "All geography reference GET routes exist",
)

for name in EXPECTED:
    node = functions[name]
    function_source = ast.get_source_segment(source, node) or ""
    check(
        all(
            token not in function_source
            for token in (
                "db.add(",
                "db.commit(",
                "db.flush(",
                "db.delete(",
                ".update(",
                ".delete(",
            )
        ),
        f"{name} remains database read-only",
    )
    check(
        "tenant_id" not in function_source,
        f"{name} exposes no tenant-scoped data",
    )
    check(
        "farmer_id" not in function_source,
        f"{name} exposes no farmer-scoped data",
    )
    check(
        "project_id" not in function_source,
        f"{name} exposes no project-scoped data",
    )
    check(
        "require_admin_permission" not in function_source
        and "require_authenticated_human" not in function_source,
        f"{name} remains available as canonical reference data",
    )

hierarchy_source = ast.get_source_segment(
    source, functions["geography_hierarchy_profile"]
) or ""
check(
    "db." not in hierarchy_source
    and "Depends(get_db)" not in hierarchy_source,
    "Geography hierarchy profile remains static",
)
check(
    "'canonical_source'" in hierarchy_source,
    "Geography hierarchy profile identifies canonical source",
)
check(
    "'android_guidance'" in hierarchy_source,
    "Geography hierarchy profile preserves client guidance",
)

active_reference_functions = {
    "list_states",
    "list_districts",
    "list_blocks",
    "list_villages",
    "villages_by_lgd_codes",
    "villages_by_pin_code",
    "search_villages",
}
for name in active_reference_functions:
    function_source = (
        ast.get_source_segment(source, functions[name]) or ""
    )
    check(
        "is_active" in function_source,
        f"{name} restricts results to active reference data",
    )

check(
    "GeographyDistrict.state_id == state_id" in (
        ast.get_source_segment(source, functions["list_districts"])
        or ""
    ),
    "District list remains state-scoped",
)
check(
    "GeographyBlock.district_id == district_id" in (
        ast.get_source_segment(source, functions["list_blocks"])
        or ""
    ),
    "Block list remains district-scoped",
)
village_source = (
    ast.get_source_segment(source, functions["list_villages"]) or ""
)
check(
    "Either block_id or district_id is required" in village_source,
    "Village list requires a hierarchy scope",
)
check(
    "len(requested_codes) > 500" in (
        ast.get_source_segment(
            source, functions["villages_by_lgd_codes"]
        ) or ""
    ),
    "LGD-code resolution preserves request limit",
)
check(
    'pattern=r"^[0-9]{6}$"' in (
        ast.get_source_segment(
            source, functions["villages_by_pin_code"]
        ) or ""
    ),
    "PIN lookup preserves six-digit validation",
)
check(
    "limit: int = Query(20, ge=1, le=100)" in (
        ast.get_source_segment(source, functions["search_villages"])
        or ""
    ),
    "Village search preserves bounded result limit",
)

audit_source = AUDIT_PATH.read_text(encoding="utf-8")
check(
    "REFERENCE_GET_PATHS" in audit_source,
    "Auditor supports exact reference GET classification",
)
for route in EXPECTED.values():
    check(
        f'"{route}"' in audit_source,
        f"Auditor explicitly classifies {route}",
    )
check(
    "full in REFERENCE_GET_PATHS" in audit_source,
    "Exact geography exceptions are method-constrained GET references",
)

spec = importlib.util.spec_from_file_location(
    "tenant_actor_audit", AUDIT_PATH
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

rows = [
    row for row in audit.scan(GEOGRAPHY_PATH)
    if row["function"] in EXPECTED
]
check(
    len(rows) == len(EXPECTED),
    "Auditor finds all eight geography reference routes",
)

by_function = {row["function"]: row for row in rows}
for name, route in EXPECTED.items():
    row = by_function[name]
    check(row["method"] == "GET", f"{name} is classified as GET")
    check(
        row["path"] == route,
        f"{name} has the expected audited path",
    )
    check(
        row["reference"] is True,
        f"{name} is explicitly reference data",
    )
    check(
        row["public"] is False,
        f"{name} is not classified as public authentication",
    )
    check(
        not row["flags"],
        f"{name} has no trust-boundary findings",
    )

print(
    "GEOGRAPHY REFERENCE CLASSIFICATION STATIC CONTRACT PASSED"
)

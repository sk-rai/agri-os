#!/usr/bin/env python3
"""Static contract for intentional public crop master-data reference reads."""

import ast
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CROPS_PATH = ROOT / "backend/app/modules/master_data/api/crops.py"
AUDIT_PATH = ROOT / "backend/scripts/audit_tenant_actor_trust_boundary.py"

EXPECTED = {
    "list_crop_categories": "/crops/categories",
    "list_crops": "/crops",
    "list_varieties": "/crops/{crop_id}/varieties",
    "list_lifecycle_templates": "/crops/{crop_id}/lifecycle-templates",
}


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print("PASS", message)


def functions_by_name(source):
    tree = ast.parse(source)
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


crop_source = CROPS_PATH.read_text(encoding="utf-8-sig")
functions = functions_by_name(crop_source)

check(set(EXPECTED) <= set(functions), "All crop reference read routes exist")

for name in EXPECTED:
    node = functions[name]
    function_source = ast.get_source_segment(crop_source, node) or ""
    check(
        "is_active == True" in function_source,
        f"{name} returns active reference rows only",
    )
    check(
        "require_admin_permission" not in function_source
        and "require_authenticated_human" not in function_source,
        f"{name} remains available as reference master data",
    )
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
    "Crop.category_id == category_id" in
    (ast.get_source_segment(crop_source, functions["list_crops"]) or ""),
    "Crop list preserves category filtering",
)
check(
    "season.upper()" in
    (ast.get_source_segment(crop_source, functions["list_crops"]) or ""),
    "Crop list preserves normalized season filtering",
)
check(
    "CropVariety.crop_id == crop_id" in
    (ast.get_source_segment(crop_source, functions["list_varieties"]) or ""),
    "Variety list remains crop-scoped",
)
template_source = (
    ast.get_source_segment(crop_source, functions["list_lifecycle_templates"])
    or ""
)
check(
    "CropLifecycleTemplate.crop_id == crop_id" in template_source,
    "Lifecycle-template list remains crop-scoped",
)
check(
    "season_code.upper()" in template_source,
    "Lifecycle-template list preserves normalized season filtering",
)

audit_source = AUDIT_PATH.read_text(encoding="utf-8")
check(
    '"/crops"' in audit_source,
    "Auditor explicitly classifies crop master-data reference reads",
)

spec = importlib.util.spec_from_file_location("tenant_actor_audit", AUDIT_PATH)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

rows = audit.scan(CROPS_PATH)
matches = [
    row for row in rows
    if row["function"] in EXPECTED
]
check(len(matches) == 4, "Auditor finds all four crop reference routes")

by_function = {row["function"]: row for row in matches}
for name, path in EXPECTED.items():
    row = by_function[name]
    check(row["method"] == "GET", f"{name} is classified as GET")
    check(row["path"] == path, f"{name} has the expected audited path")
    check(row["reference"] is True, f"{name} is explicitly reference data")
    check(row["public"] is False, f"{name} is not classified as public auth")
    check(not row["flags"], f"{name} has no trust-boundary findings")

print("MASTER-DATA CROP REFERENCE CLASSIFICATION STATIC CONTRACT PASSED")

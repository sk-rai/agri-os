#!/usr/bin/env python3
"""Static contract for intentional profile and soil reference GET routes."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
AUDIT_PATH = ROOT / "backend/scripts/audit_tenant_actor_trust_boundary.py"

ROUTES = {
    "soil_enrichment_source_contract": {
        "file": ROOT / "backend/app/modules/farmer/soil_profile.py",
        "path": "/api/v1/soil-profiles/enrichments/source-contract",
    },
    "infer_soil_from_district": {
        "file": ROOT / "backend/app/modules/farmer/soil_profile.py",
        "path": "/api/v1/soil-profiles/infer/{district_name}",
    },
    "get_form_field_config": {
        "file": ROOT / "backend/app/modules/farmer/api.py",
        "path": "/api/v1/config/form-fields",
    },
}


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"PASS {message}")


def function_nodes(path: Path) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    tree = ast.parse(path.read_text())
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def function_source(path: Path, node: ast.AST) -> str:
    source = path.read_text()
    segment = ast.get_source_segment(source, node)
    assert segment is not None
    return segment


def decorator_method_and_path(node: ast.FunctionDef | ast.AsyncFunctionDef):
    matches = []
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        func = decorator.func
        if not (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "router"
        ):
            continue
        if func.attr.lower() != "get" or not decorator.args:
            continue
        value = ast.literal_eval(decorator.args[0])
        matches.append(("GET", value))
    return matches


audit_text = AUDIT_PATH.read_text()
audit_tree = ast.parse(audit_text)
assignments = {
    target.id: node.value
    for node in audit_tree.body
    if isinstance(node, ast.Assign)
    for target in node.targets
    if isinstance(target, ast.Name)
}
reference_paths = set(ast.literal_eval(assignments["REFERENCE_GET_PATHS"]))

expected_paths = {route["path"] for route in ROUTES.values()}
check(
    expected_paths.issubset(reference_paths),
    "Auditor explicitly classifies all three profile reference GET paths",
)
check(
    'method=="GET"' in audit_text
    and "full in REFERENCE_GET_PATHS" in audit_text,
    "Exact profile reference exceptions are method-constrained GET routes",
)

for function_name, route in ROUTES.items():
    nodes = function_nodes(route["file"])
    check(function_name in nodes, f"{function_name} exists")
    node = nodes[function_name]
    decorators = decorator_method_and_path(node)
    check(len(decorators) == 1, f"{function_name} has one GET route")
    source = function_source(route["file"], node)

    check(
        "db:" not in source and "Depends(get_db)" not in source,
        f"{function_name} is database independent",
    )
    check(
        not any(
            marker in source
            for marker in (
                ".add(",
                ".delete(",
                ".commit(",
                ".flush(",
                ".update(",
            )
        ),
        f"{function_name} remains read-only",
    )

spec = importlib.util.spec_from_file_location("audit", AUDIT_PATH)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

rows = []
for source_path in sorted({route["file"] for route in ROUTES.values()}):
    rows.extend(audit.scan(source_path))

matches = [
    row for row in rows
    if row["function"] in ROUTES
]

check(len(matches) == 3, "Auditor finds all three profile reference routes")

by_function = {row["function"]: row for row in matches}
for function_name, route in ROUTES.items():
    row = by_function[function_name]
    check(row["method"] == "GET", f"{function_name} is classified as GET")
    check(
        row["path"] == route["path"],
        f"{function_name} has the expected audited path",
    )
    check(row["reference"] is True, f"{function_name} is reference data")
    check(row["public"] is False, f"{function_name} is not public authentication")
    check(not row["flags"], f"{function_name} has no trust-boundary findings")

print("PROFILE REFERENCE CLASSIFICATION STATIC CONTRACT PASSED")

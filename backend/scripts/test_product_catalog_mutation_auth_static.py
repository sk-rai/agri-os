#!/usr/bin/env python3
"""Static authorization contract for product-catalog administrative mutations."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "app/modules/master_data/api/product_catalog.py"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8-sig")
TREE = ast.parse(SOURCE)

TARGETS = {
    "apply_product_csv_import": ("EDIT", False),
    "create_manufacturer": ("EDIT", False),
    "update_manufacturer": ("EDIT", False),
    "create_product": ("EDIT", False),
    "add_product_package": ("EDIT", False),
    "update_product": ("EDIT", False),
    "approve_product": ("PROJECT_EDIT", True),
}


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


functions = {
    node.name: node
    for node in ast.walk(TREE)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}

for function_name, (permission, project_scoped) in TARGETS.items():
    node = functions.get(function_name)
    check(node is not None, f"{function_name} exists")
    body = ast.unparse(node)

    check(
        f"AdminPermission.{permission}" in body,
        f"{function_name} requires {permission} permission",
    )
    check(
        "tenant_id = principal.tenant_id" in body,
        f"{function_name} derives tenant from verified administrator",
    )
    check(
        "actor_id = principal.user_id" in body,
        f"{function_name} derives actor from verified administrator",
    )
    check(
        body.count("x_tenant_id") == 1,
        f"{function_name} does not use tenant header as mutation authority",
    )
    check(
        "record_audit(db, tenant_id, actor_id" in body,
        f"{function_name} audits verified administrator",
    )
    if project_scoped:
        check(
            "project_scoped=True" in body.replace(" ", ""),
            f"{function_name} enforces project-scoped authorization",
        )

record_node = functions.get("record_audit")
check(record_node is not None, "product catalog audit helper exists")
record_body = ast.unparse(record_node)
check(
    "tenant_id=tenant_id" in record_body.replace(" ", ""),
    "product catalog audit persists verified tenant",
)
check(
    "actor_id=actor_id" in record_body.replace(" ", ""),
    "product catalog audit persists verified actor",
)
check(
    "principal.user_id" not in record_body,
    "product catalog audit helper receives explicit verified identity",
)

print("PRODUCT CATALOG MUTATION AUTH STATIC CONTRACT PASSED")

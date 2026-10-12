#!/usr/bin/env python3
"""Static authorization contract for project geography import preview."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_PATH = ROOT / "app/modules/farmer/api.py"


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


source = API_PATH.read_text(encoding="utf-8-sig")
tree = ast.parse(source)
node = next(
    (
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef)
        and item.name
        == "preview_project_geography_scope_import"
    ),
    None,
)
check(node is not None, "Project geography import preview exists")
preview = ast.get_source_segment(source, node) or ""

check(
    "AdminPermission.PROJECT_EDIT" in preview,
    "Geography import preview requires project-edit permission",
)
check(
    "project_scoped=True" in preview,
    "Geography import preview enforces project-scoped authorization",
)
check(
    "tenant_id = principal.tenant_id" in preview,
    "Geography import preview derives verified tenant",
)
check(
    "actor_id = principal.user_id" in preview,
    "Geography import preview derives verified actor",
)
check(
    "Project.tenant_id == tenant_id" in preview,
    "Geography import preview tenant-bounds project",
)
check(
    '"tenant_id": tenant_id' in preview,
    "Geography import preview reports verified tenant",
)
check(
    '"previewed_by": str(actor_id)' in preview,
    "Geography import preview reports verified administrator",
)
check(
    "Header(" not in preview and "x_tenant_id" not in preview,
    "Geography import preview does not trust identity headers directly",
)
check(
    "db.add(" not in preview
    and "db.commit(" not in preview
    and "db.flush(" not in preview
    and "db.delete(" not in preview,
    "Geography import preview remains database read-only",
)
check(
    '"database_write_performed": False' in preview,
    "Geography import preview preserves read-only governance marker",
)

print(
    "PROJECT GEOGRAPHY IMPORT PREVIEW AUTH "
    "STATIC CONTRACT PASSED"
)

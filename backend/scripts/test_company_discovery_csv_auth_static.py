#!/usr/bin/env python3
"""Static authorization contract for company-discovery CSV operations."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_PATH = ROOT / "app/modules/farmer/api.py"


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


def function_source(
    tree: ast.Module,
    source: str,
    name: str,
) -> str:
    node = next(
        (
            item
            for item in tree.body
            if isinstance(
                item,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            )
            and item.name == name
        ),
        None,
    )
    check(node is not None, f"{name} exists")
    return ast.get_source_segment(source, node) or ""


source = API_PATH.read_text(encoding="utf-8-sig")
tree = ast.parse(source)

validate = function_source(
    tree,
    source,
    "validate_company_discovery_csv",
)
import_csv = function_source(
    tree,
    source,
    "import_company_discovery_csv",
)

check(
    "AdminPermission.EDIT" in validate,
    "Company discovery CSV validation requires edit permission",
)
check(
    "tenant_id = principal.tenant_id" in validate,
    "CSV validation derives tenant from verified administrator",
)
check(
    "actor_id = principal.user_id" in validate,
    "CSV validation derives actor from verified administrator",
)
check(
    'validation["validated_by"] = str(actor_id)' in validate,
    "CSV validation reports verified validator",
)
check(
    "Header(" not in validate and "x_tenant_id" not in validate,
    "CSV validation does not trust identity headers directly",
)

check(
    "AdminPermission.EDIT" in import_csv,
    "Company discovery CSV import requires edit permission",
)
check(
    "tenant_id = principal.tenant_id" in import_csv,
    "CSV import derives tenant from verified administrator",
)
check(
    "actor_id = principal.user_id" in import_csv,
    "CSV import derives actor from verified administrator",
)
check(
    "Tenant.id == tenant_id" in import_csv,
    "CSV import tenant-bounds destination tenant",
)
check(
    "tenant_id=tenant_id" in import_csv,
    "CSV import persists verified tenant",
)
check(
    '"imported_by": str(actor_id)' in import_csv,
    "CSV import records verified actor in candidate provenance",
)
check(
    "CompanyProfileAuditEvent(" in import_csv,
    "CSV import writes immutable batch audit",
)
check(
    "actor_id=actor_id" in import_csv,
    "CSV import audit records verified administrator",
)
check(
    'action="IMPORT_COMPANY_DISCOVERY_CSV"' in import_csv,
    "CSV import audit action is stable",
)
check(
    "Header(" not in import_csv
    and "x_tenant_id" not in import_csv,
    "CSV import does not trust identity headers directly",
)

check(
    "validated_by: str" in source,
    "CSV validation response declares validator attribution",
)

print("COMPANY DISCOVERY CSV AUTH STATIC CONTRACT PASSED")

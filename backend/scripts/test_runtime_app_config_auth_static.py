#!/usr/bin/env python3
"""Static authorization contract for runtime app-configuration mutations."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_PATH = ROOT / "app/modules/farmer/api.py"
MODEL_PATH = ROOT / "app/modules/farmer/models.py"
MIGRATION_PATH = (
    ROOT / "alembic/versions/068_add_tenant_app_config_audit_events.py"
)


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


def function_source(tree: ast.Module, source: str, name: str) -> str:
    node = next(
        (
            item
            for item in tree.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and item.name == name
        ),
        None,
    )
    check(node is not None, f"{name} exists")
    return ast.get_source_segment(source, node) or ""


api_source = API_PATH.read_text(encoding="utf-8-sig")
api_tree = ast.parse(api_source)

tenant = function_source(
    api_tree,
    api_source,
    "update_tenant_app_config",
)
project = function_source(
    api_tree,
    api_source,
    "update_project_app_config",
)

check(
    "AdminPermission.MANAGE_USERS" in tenant,
    "Tenant app-config requires manage-users permission",
)
check(
    "authenticated_tenant_id = principal.tenant_id" in tenant,
    "Tenant app-config derives tenant from verified administrator",
)
check(
    "actor_id = principal.user_id" in tenant,
    "Tenant app-config derives actor from verified administrator",
)
check(
    "tenant_id != authenticated_tenant_id" in tenant,
    "Tenant app-config validates path against verified tenant",
)
check(
    "TenantAppConfigAuditEvent(" in tenant,
    "Tenant app-config writes immutable audit event",
)
check(
    "actor_id=actor_id" in tenant,
    "Tenant app-config audit records verified administrator",
)
check(
    'action="UPDATE_TENANT_APP_CONFIG"' in tenant,
    "Tenant app-config audit action is stable",
)
check(
    'Header(' not in tenant and "x_tenant_id" not in tenant,
    "Tenant app-config does not trust identity headers directly",
)

check(
    "AdminPermission.PROJECT_EDIT" in project,
    "Project app-config requires project-edit permission",
)
check(
    "project_scoped=True" in project,
    "Project app-config enforces project-scoped authorization",
)
check(
    "tenant_id = principal.tenant_id" in project,
    "Project app-config derives tenant from verified administrator",
)
check(
    "actor_id = principal.user_id" in project,
    "Project app-config derives actor from verified administrator",
)
check(
    "Project.tenant_id == tenant_id" in project,
    "Project app-config tenant-bounds selected project",
)
check(
    "ProjectAppConfigAuditEvent(" in project,
    "Project app-config writes immutable audit event",
)
check(
    "actor_id=actor_id" in project,
    "Project app-config audit records verified administrator",
)
check(
    'action="UPDATE_PROJECT_APP_CONFIG"' in project,
    "Project app-config audit action is stable",
)
check(
    'Header(' not in project and "x_tenant_id" not in project,
    "Project app-config does not trust identity headers directly",
)

model_source = MODEL_PATH.read_text(encoding="utf-8-sig")
check(
    "class TenantAppConfigAuditEvent" in model_source,
    "Tenant app-config immutable audit model exists",
)
check(
    '__tablename__ = "tenant_app_config_audit_events"' in model_source,
    "Tenant app-config audit table name is stable",
)

migration_source = MIGRATION_PATH.read_text(encoding="utf-8-sig")
check(
    'revision = "068"' in migration_source
    and 'down_revision = "067"' in migration_source,
    "Tenant app-config audit migration follows current head",
)
check(
    '"tenant_app_config_audit_events"' in migration_source,
    "Tenant app-config audit migration creates expected table",
)

print("RUNTIME APP CONFIG AUTH STATIC CONTRACT PASSED")

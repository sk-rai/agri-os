#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


def function_source(path: Path, name: str) -> str:
    source = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    node = next(
        (
            candidate
            for candidate in ast.walk(tree)
            if isinstance(
                candidate,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            )
            and candidate.name == name
        ),
        None,
    )
    if node is None:
        raise AssertionError(f"{name} not found")
    result = ast.get_source_segment(source, node)
    if result is None:
        raise AssertionError(f"Could not extract {name}")
    return result


route = function_source(
    ROOT / "app/modules/farmer/api.py",
    "create_tenant",
)
models = (
    ROOT / "app/modules/farmer/models.py"
).read_text(encoding="utf-8-sig")
migration = (
    ROOT
    / "alembic/versions/069_add_tenant_provisioning_audit_events.py"
).read_text(encoding="utf-8-sig")

require(
    "AdminPermission.MANAGE_USERS" in route,
    "Tenant provisioning requires manage-users permission",
)
require(
    "actor_tenant_id = principal.tenant_id" in route,
    "Tenant provisioning derives verified actor tenant",
)
require(
    "actor_id = principal.user_id" in route,
    "Tenant provisioning derives verified actor",
)
require(
    'actor_tenant_id != "default"' in route,
    "Tenant provisioning requires platform tenant",
)
require(
    'principal.role != "ENTERPRISE_ADMIN"' in route,
    "Tenant provisioning requires enterprise administrator",
)
require(
    "PLATFORM_TENANT_PROVISIONING_REQUIRED" in route,
    "Tenant provisioning exposes stable platform-boundary error",
)
require(
    "TenantProvisioningAuditEvent(" in route,
    "Tenant provisioning writes immutable audit event",
)
require(
    "actor_tenant_id=actor_tenant_id" in route,
    "Tenant provisioning audit records verified actor tenant",
)
require(
    "actor_id=actor_id" in route,
    "Tenant provisioning audit records verified administrator",
)
require(
    'action="CREATE_TENANT"' in route,
    "Tenant provisioning audit action is stable",
)
require(
    "x_tenant_id" not in route
    and "x_actor_id" not in route,
    "Tenant provisioning does not trust identity headers directly",
)

require(
    "class TenantProvisioningAuditEvent" in models,
    "Tenant provisioning audit model exists",
)
require(
    '__tablename__ = "tenant_provisioning_audit_events"'
    in models,
    "Tenant provisioning audit table name is stable",
)
require(
    'revision: str = "069"' in migration
    and 'down_revision: Union[str, None] = "068"' in migration,
    "Tenant provisioning audit migration follows current head",
)
require(
    '"tenant_provisioning_audit_events"' in migration,
    "Tenant provisioning audit migration creates expected table",
)
require(
    '"target_tenant_id"' in migration
    and '"actor_tenant_id"' in migration
    and '"actor_id"' in migration,
    "Tenant provisioning migration preserves target and actor boundary",
)

print("TENANT PROVISIONING AUTH STATIC CONTRACT PASSED")

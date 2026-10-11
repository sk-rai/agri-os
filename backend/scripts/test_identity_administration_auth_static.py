#!/usr/bin/env python3
"""Static authorization contract for identity-administration mutations."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app/modules/auth/admin_api.py"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"))


def check(condition: bool, label: str) -> None:
    print(f"{'PASS' if condition else 'FAIL'} {label}")
    if not condition:
        raise AssertionError(label)


functions = {
    node.name: node
    for node in ast.walk(TREE)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}

targets = {
    "upsert_agent_profile",
    "update_agent_profile",
    "assign_project_access",
    "revoke_project_access",
}

for name in sorted(targets):
    check(name in functions, f"{name} exists")
    body = ast.unparse(functions[name])

    check(
        "require_admin_permission(AdminPermission.MANAGE_USERS)" in body,
        f"{name} requires manage-users permission",
    )
    check(
        "tenant_id = principal.tenant_id" in body,
        f"{name} derives tenant from verified administrator",
    )
    check(
        "actor_id = principal.user_id" in body,
        f"{name} derives actor from verified administrator",
    )
    check(
        body.count("x_tenant_id") == 1,
        f"{name} does not use tenant header as mutation authority",
    )
    check(
        "tenant_id=tenant_id" in body and "actor_id=actor_id" in body,
        f"{name} audits verified identity",
    )

assign_body = ast.unparse(functions["assign_project_access"])
check(
    "Project.tenant_id == tenant_id" in assign_body,
    "Project access assignment tenant-bounds project",
)

revoke_body = ast.unparse(functions["revoke_project_access"])
check(
    "Project.tenant_id == tenant_id" in revoke_body,
    "Project access revocation tenant-bounds project",
)

upsert_body = ast.unparse(functions["upsert_agent_profile"])
check(
    "AgentProfile.tenant_id == tenant_id" in upsert_body,
    "Agent profile upsert tenant-bounds profile",
)
check(
    "_tenant_user(db, body.user_id, tenant_id)" in upsert_body,
    "Agent profile upsert tenant-bounds target user",
)

update_body = ast.unparse(functions["update_agent_profile"])
check(
    "AgentProfile.tenant_id == tenant_id" in update_body,
    "Agent profile update tenant-bounds profile",
)

audit_body = ast.unparse(functions["_record_access_audit"])
check(
    "tenant_id=tenant_id" in audit_body,
    "Access audit persists verified tenant",
)
check(
    "actor_id=actor_id" in audit_body,
    "Access audit persists verified actor",
)
check(
    "principal" not in audit_body,
    "Access audit receives explicit verified identity",
)

print("IDENTITY ADMINISTRATION AUTH STATIC CONTRACT PASSED")

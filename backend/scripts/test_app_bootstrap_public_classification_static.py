#!/usr/bin/env python3
"""Static contract for the intentional public app-bootstrap read."""

import ast
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API_PATH = ROOT / "backend/app/modules/app_config/api.py"
AUDIT_PATH = (
    ROOT / "backend/scripts/audit_tenant_actor_trust_boundary.py"
)

source = API_PATH.read_text(encoding="utf-8-sig")
tree = ast.parse(source)


def check(condition, label):
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


node = next(
    (
        item
        for item in ast.walk(tree)
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == "get_app_bootstrap_config"
    ),
    None,
)
check(node is not None, "App bootstrap route exists")
route = ast.get_source_segment(source, node) or ""

check(
    "safe to call before or after login" in route,
    "App bootstrap explicitly documents pre-login use",
)
check(
    'x_tenant_id or DEFAULT_BOOTSTRAP_CONFIG' in route,
    "App bootstrap preserves default self-service context",
)
check(
    "Tenant.id == tenant_id" in route
    and "Tenant.is_active == True" in route,
    "App bootstrap resolves only active requested tenant",
)
check(
    "Project.tenant_id == tenant_id" in route
    and "Project.is_active == True" in route,
    "App bootstrap tenant-bounds optional active project",
)
check(
    '"schema_version": "app_bootstrap.v1"' in route,
    "App bootstrap response schema is stable",
)
for key in [
    '"service"',
    '"tenant"',
    '"project"',
    '"branding"',
    '"localization"',
    '"units"',
    '"enabled_modules"',
    '"feature_flags"',
    '"self_service"',
    '"forms"',
    '"profile_forms"',
    '"contracts"',
]:
    check(
        key in route,
        f"App bootstrap exposes expected client field {key}",
    )
check(
    "db.add(" not in route
    and "db.commit(" not in route
    and "db.flush(" not in route
    and "db.delete(" not in route,
    "App bootstrap remains database read-only",
)
check(
    "require_admin_permission" not in route
    and "require_authenticated_human" not in route,
    "App bootstrap remains available before login",
)

spec = importlib.util.spec_from_file_location(
    "trust_boundary_audit",
    AUDIT_PATH,
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

matches = [
    row
    for row in audit.scan(API_PATH)
    if row["function"] == "get_app_bootstrap_config"
]
check(len(matches) == 1, "App bootstrap has one audited route")
row = matches[0]
check(row["public"] is True, "App bootstrap is explicitly public")
check(
    row["reference"] is False,
    "App bootstrap is not misclassified as reference data",
)
check(not row["flags"], "Public app bootstrap has no audit findings")

audit_source = AUDIT_PATH.read_text(encoding="utf-8-sig")
check(
    'PUBLIC_GET_PATHS=("/api/v1/app-config/bootstrap",)'
    in audit_source,
    "Auditor uses exact public bootstrap GET classification",
)
check(
    'method=="GET" and full in PUBLIC_GET_PATHS'
    in audit_source,
    "Public bootstrap exception is method constrained",
)

print("APP BOOTSTRAP PUBLIC CLASSIFICATION STATIC CONTRACT PASSED")

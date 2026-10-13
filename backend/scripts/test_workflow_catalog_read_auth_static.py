#!/usr/bin/env python3
"""Static authorization contract for workflow catalog operational reads."""

import ast
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = ROOT / "backend/app/modules/workflow/catalog_api.py"
AUDIT_PATH = (
    ROOT / "backend/scripts/audit_tenant_actor_trust_boundary.py"
)

RUNTIME = {
    "list_enabled_crop_workflows",
    "preview_workflow_template_version",
}
ADMIN_VIEW = {
    "preview_draft_workflow_template_version",
    "get_draft_publish_impact",
    "list_legacy_cycle_pin_candidates",
    "list_workflow_template_versions",
    "list_workflow_template_audit_events",
}
ADMIN_EDIT = {
    "validate_draft_workflow_template_version",
}
EXPECTED = RUNTIME | ADMIN_VIEW | ADMIN_EDIT


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print("PASS", message)


source = SOURCE_PATH.read_text(encoding="utf-8-sig")
tree = ast.parse(source)
functions = {
    node.name: node
    for node in ast.walk(tree)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}
check(EXPECTED <= set(functions), "All workflow catalog reads exist")

def function_source(name):
    return ast.get_source_segment(source, functions[name]) or ""


helper = function_source("_assert_workflow_runtime_project_access")
check(
    "Project.tenant_id == principal.tenant_id" in helper,
    "Runtime project helper tenant-bounds project",
)
check(
    "resolve_human_persona_scope(db, principal)" in helper,
    "Runtime project helper resolves verified persona scope",
)
check(
    "scope.has_project_access(project_id)" in helper,
    "Runtime project helper permits project roles",
)
check(
    "Farmer.user_id == principal.user_id" in helper,
    "Runtime project helper identifies verified farmer owner",
)
check(
    "FarmerProjectEnrollment.status == \"ACTIVE\"" in helper,
    "Runtime project helper requires active farmer enrollment",
)
check(
    "WORKFLOW_PROJECT_SCOPE_DENIED" in helper,
    "Runtime project helper exposes stable denial code",
)

for name in RUNTIME:
    body = function_source(name)
    check(
        "require_authenticated_human()" in body,
        f"{name} requires authenticated human",
    )
    check(
        "tenant_id = principal.tenant_id" in body,
        f"{name} derives verified tenant",
    )
    check(
        "actor_id = principal.user_id" in body,
        f"{name} derives verified actor",
    )
    check(
        "_assert_workflow_runtime_project_access(" in body,
        f"{name} enforces optional project scope",
    )
    check(
        "x_tenant_id" not in body
        and "X-Tenant-ID" not in body,
        f"{name} does not trust tenant header directly",
    )

for name in ADMIN_VIEW:
    body = function_source(name)
    check(
        "AdminPermission.VIEW" in body,
        f"{name} requires view permission",
    )
    check(
        "tenant_id = principal.tenant_id" in body,
        f"{name} derives verified tenant",
    )
    check(
        "actor_id = principal.user_id" in body,
        f"{name} derives verified actor",
    )
    check(
        "x_tenant_id" not in body
        and "X-Tenant-ID" not in body,
        f"{name} does not trust tenant header directly",
    )

validation = function_source(
    "validate_draft_workflow_template_version"
)
check(
    "AdminPermission.EDIT" in validation,
    "Draft validation requires edit permission",
)
check(
    "tenant_id = principal.tenant_id" in validation,
    "Draft validation derives verified tenant",
)
check(
    "actor_id = principal.user_id" in validation,
    "Draft validation derives verified actor",
)
check(
    "actor_id=actor_id" in validation,
    "Draft validation audit records verified administrator",
)
check(
    "x_tenant_id" not in validation
    and "x_actor_id" not in validation
    and "X-Tenant-ID" not in validation
    and "X-Actor-ID" not in validation,
    "Draft validation does not trust identity headers directly",
)
check(
    'action="VALIDATE_DRAFT"' in validation
    and "db.commit()" in validation,
    "Draft validation preserves immutable audit event",
)

audit_read = function_source(
    "list_workflow_template_audit_events"
)
check(
    "db.commit()" not in audit_read,
    "Workflow audit history read remains database read-only",
)

for name in EXPECTED - ADMIN_EDIT:
    body = function_source(name)
    check(
        all(
            token not in body
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

spec = importlib.util.spec_from_file_location(
    "tenant_actor_audit", AUDIT_PATH
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

rows = [
    row for row in audit.scan(SOURCE_PATH)
    if row["function"] in EXPECTED
]
check(len(rows) == 8, "Auditor finds all workflow catalog reads")
for row in rows:
    check(
        row["admin_dependency"] or row["bearer_marker"],
        f'{row["function"]} has an authentication marker',
    )
    check(
        row["tenant_marker"],
        f'{row["function"]} has a verified tenant marker',
    )
    check(
        row["actor_marker"],
        f'{row["function"]} has a verified actor marker',
    )
    check(
        not row["flags"],
        f'{row["function"]} has no trust-boundary findings',
    )

print("WORKFLOW CATALOG READ AUTH STATIC CONTRACT PASSED")

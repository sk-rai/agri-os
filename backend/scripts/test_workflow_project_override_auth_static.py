#!/usr/bin/env python3
"""Static authorization contract for project workflow override mutations."""

from __future__ import annotations

import ast
from pathlib import Path


SOURCE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app/modules/workflow/catalog_api.py"
)
source = SOURCE_PATH.read_text(encoding="utf-8-sig")
tree = ast.parse(source)


def function_source(name: str) -> str:
    node = next(
        (
            item
            for item in ast.walk(tree)
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and item.name == name
        ),
        None,
    )
    if node is None:
        raise AssertionError(f"{name} not found")
    value = ast.get_source_segment(source, node)
    if value is None:
        raise AssertionError(f"Could not extract {name}")
    return value


def check(condition, label):
    print(f"{'PASS' if condition else 'FAIL'} {label}")
    if not condition:
        raise AssertionError(label)


create = function_source("create_project_workflow_override")
archive = function_source("delete_project_workflow_override")

for name, body in (
    ("create_project_workflow_override", create),
    ("delete_project_workflow_override", archive),
):
    check(name in source, f"{name} exists")
    check(
        "AdminPermission.PROJECT_EDIT" in body,
        f"{name} requires project-edit permission",
    )
    check(
        "project_scoped=True" in body,
        f"{name} enforces project-scoped authorization",
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
        "Project.tenant_id == tenant_id" in body,
        f"{name} tenant-bounds project",
    )
    check(
        "x_tenant_id" not in body and "Header(" not in body,
        f"{name} does not trust identity headers directly",
    )
    check(
        "_record_workflow_audit_event(" in body,
        f"{name} writes immutable workflow audit",
    )
    check(
        "actor_id=actor_id" in body,
        f"{name} audits verified administrator",
    )

check(
    'WorkflowTemplate.tenant_id.in_([tenant_id, "default"])' in create,
    "Override creation tenant-bounds selectable workflow template",
)
check(
    "tenant_id=tenant_id" in create,
    "Override creation persists verified tenant",
)
check(
    'action="CREATE_PROJECT_WORKFLOW_OVERRIDE"' in create,
    "Override creation audit action is stable",
)
check(
    "template_id=template.id" in create,
    "Override creation audit references selected workflow template",
)
check(
    "after=override_snapshot" in create,
    "Override creation audit preserves resulting override",
)

check(
    "WorkflowTemplateOverride.tenant_id == tenant_id" in archive,
    "Override archival tenant-bounds selected override",
)
check(
    'WorkflowTemplate.tenant_id.in_([tenant_id, "default"])' in archive,
    "Override archival tenant-bounds workflow template",
)
check(
    "override.is_active = False" in archive,
    "Override deletion remains recoverable archival",
)
check(
    'action="ARCHIVE_PROJECT_WORKFLOW_OVERRIDE"' in archive,
    "Override archival audit action is stable",
)
check(
    "before=before_snapshot" in archive
    and "after=after_snapshot" in archive,
    "Override archival audit preserves before and after state",
)

print("WORKFLOW PROJECT OVERRIDE AUTH STATIC CONTRACT PASSED")

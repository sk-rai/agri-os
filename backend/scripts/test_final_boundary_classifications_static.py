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
        raise AssertionError(f"{name} not found in {path}")
    result = ast.get_source_segment(source, node)
    if result is None:
        raise AssertionError(f"Could not extract {name}")
    return result


audit_source = (
    ROOT / "scripts/audit_tenant_actor_trust_boundary.py"
).read_text(encoding="utf-8-sig")
auth_source = function_source(
    ROOT / "app/modules/auth/api.py",
    "device_login",
)
sync_source = function_source(
    ROOT / "app/modules/master_data/api/sync.py",
    "sync_master_data",
)
dry_run_source = function_source(
    ROOT
    / "app/modules/master_data/api/project_village_resolutions.py",
    "dry_run",
)
workflow_source = function_source(
    ROOT / "app/modules/workflow/catalog_api.py",
    "validate_workflow_csv_against_draft",
)

require(
    '"/api/v1/auth/device"' in audit_source,
    "Device login is explicitly classified as public authentication",
)
require(
    'REFERENCE_POST_PATHS=("/sync",)' in audit_source,
    "Master-data sync POST is explicitly classified as reference transport",
)
require(
    "not reference and not(admin or bearer)" in audit_source,
    "Reference POST classification bypasses mutation auth findings",
)
require(
    "service.authenticate_device" in auth_source
    and "service.create_jwt" in auth_source,
    "Device login remains credential verification and token issuance",
)
require(
    "db.add(" not in sync_source
    and "db.commit(" not in sync_source
    and "db.delete(" not in sync_source,
    "Master-data sync remains database read-only",
)

require(
    "tenant_id=principal.tenant_id" in dry_run_source,
    "Project resolution dry run derives verified tenant",
)
require(
    "actor_id=principal.user_id" in dry_run_source,
    "Project resolution dry run derives verified actor",
)
require(
    "project(db,project_id,tenant_id)" in dry_run_source,
    "Project resolution dry run tenant-bounds project",
)
require(
    "requested_by" in dry_run_source,
    "Project resolution dry run reports verified administrator",
)
require(
    "x_tenant_id" not in dry_run_source,
    "Project resolution dry run does not trust tenant header directly",
)
require(
    "db.add(" not in dry_run_source
    and "db.commit(" not in dry_run_source,
    "Project resolution dry run remains write-free",
)

require(
    "tenant_id = principal.tenant_id" in workflow_source,
    "Workflow CSV validation derives verified tenant",
)
require(
    "actor_id = principal.user_id" in workflow_source,
    "Workflow CSV validation derives verified actor",
)
require(
    "_get_draft_template_version" in workflow_source
    and "tenant_id" in workflow_source,
    "Workflow CSV validation tenant-bounds selected draft",
)
require(
    'report["validated_by"] = str(actor_id)' in workflow_source,
    "Workflow CSV validation reports verified administrator",
)
require(
    "x_tenant_id" not in workflow_source,
    "Workflow CSV validation does not trust tenant header directly",
)
require(
    "db.add(" not in workflow_source
    and "db.commit(" not in workflow_source,
    "Workflow CSV validation remains write-free",
)

print("FINAL BOUNDARY CLASSIFICATIONS STATIC CONTRACT PASSED")

#!/usr/bin/env python3
"""Static authorization contract for sync operational reads."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFLICTS_PATH = ROOT / "app/modules/sync/conflicts.py"
DASHBOARD_PATH = ROOT / "app/modules/sync/dashboard.py"


def functions(path):
    source = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    return {
        node.name: ast.get_source_segment(source, node) or ""
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def check(condition, label):
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


conflicts = functions(CONFLICTS_PATH)
dashboard = functions(DASHBOARD_PATH)

for name in ["list_conflicts", "get_conflict"]:
    source = conflicts[name]
    check(
        "AdminPermission.VIEW" in source,
        f"{name} requires view permission",
    )
    check(
        "tenant_id = principal.tenant_id" in source,
        f"{name} derives verified tenant",
    )
    check(
        "actor_id = principal.user_id" in source,
        f"{name} derives verified actor",
    )
    check(
        "SyncConflict.tenant_id == tenant_id" in source,
        f"{name} tenant-bounds conflicts",
    )
    check(
        "Header(" not in source and "x_tenant_id" not in source,
        f"{name} does not trust tenant header directly",
    )

pending = conflicts["list_android_pending_conflicts"]
check(
    "require_authenticated_human()" in pending,
    "Android pending feed requires authenticated human",
)
check(
    "tenant_id = principal.tenant_id" in pending,
    "Android pending feed derives verified tenant",
)
check(
    "actor_id = principal.user_id" in pending,
    "Android pending feed derives verified actor",
)
check(
    "SyncConflict.tenant_id == tenant_id" in pending,
    "Android pending feed tenant-bounds conflicts",
)
check(
    "SyncConflict.actor_id == actor_id" in pending,
    "Android pending feed restricts conflicts to submitter",
)
check(
    "Header(" not in pending and "x_tenant_id" not in pending,
    "Android pending feed does not trust tenant header directly",
)
check(
    "_safe_payload_summary" in pending,
    "Android pending feed preserves redacted payload summaries",
)

operational = dashboard["get_operational_dashboard"]
check(
    "AdminPermission.VIEW" in operational,
    "Operational dashboard requires view permission",
)
check(
    "tenant_id = principal.tenant_id" in operational,
    "Operational dashboard derives verified tenant",
)
check(
    "actor_id = principal.user_id" in operational,
    "Operational dashboard derives verified actor",
)
check(
    "SyncProcessedEvent.tenant_id == tenant_id" in operational,
    "Operational dashboard tenant-bounds sync events",
)
check(
    "SyncConflict.tenant_id == tenant_id" in operational,
    "Operational dashboard tenant-bounds conflicts",
)
check(
    "AuditChainEntry.tenant_id == tenant_id" in operational,
    "Operational dashboard tenant-bounds audit chain",
)
check(
    "Header(" not in operational and "x_tenant_id" not in operational,
    "Operational dashboard does not trust tenant header directly",
)

print("SYNC OPERATIONAL READ AUTH STATIC CONTRACT PASSED")

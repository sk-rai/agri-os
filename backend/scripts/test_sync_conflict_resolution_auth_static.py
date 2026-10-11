#!/usr/bin/env python3
"""Static authorization contract for sync conflict resolution."""

from pathlib import Path


SOURCE = (
    Path(__file__).resolve().parents[1]
    / "app/modules/sync/conflicts.py"
).read_text(encoding="utf-8")

START = SOURCE.index("def resolve_conflict(")
BLOCK = SOURCE[START:]


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


def main() -> None:
    check(
        "principal: AdminPrincipal = Depends(" in BLOCK
        and "require_admin_permission(AdminPermission.EDIT)" in BLOCK,
        "Conflict resolution requires admin edit permission",
    )
    check(
        "tenant_id = principal.tenant_id" in BLOCK,
        "Conflict resolution derives tenant from verified administrator",
    )
    check(
        "actor_id = str(principal.user_id)" in BLOCK,
        "Conflict resolution derives actor from verified administrator",
    )
    check(
        "SyncConflict.tenant_id == tenant_id" in BLOCK,
        "Conflict resolution tenant-bounds selected conflict",
    )
    check(
        BLOCK.count("SyncConflict.tenant_id == tenant_id") >= 2,
        "Conflict resolution tenant-bounds duplicate pending conflicts",
    )
    check(
        "resolved_by = principal.user_id" in BLOCK,
        "Conflict resolution records verified administrator",
    )
    check(
        "tenant_id=tenant_id" in BLOCK
        and "actor_id=actor_id" in BLOCK,
        "Conflict resolution audit uses verified identity",
    )
    check(
        "x_tenant_id" not in BLOCK
        and "x_actor_id" not in BLOCK,
        "Conflict resolution does not trust identity headers directly",
    )
    check(
        '"CONFLICT_RESOLVED"' in BLOCK,
        "Conflict resolution preserves immutable audit action",
    )
    print("SYNC CONFLICT RESOLUTION AUTH STATIC CONTRACT PASSED")


if __name__ == "__main__":
    main()

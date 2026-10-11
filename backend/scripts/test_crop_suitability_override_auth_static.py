#!/usr/bin/env python3
"""Static authorization contract for crop suitability override publishing."""

from pathlib import Path


SOURCE = (
    Path(__file__).resolve().parents[1]
    / "app/modules/master_data/api/crop_catalog.py"
).read_text(encoding="utf-8")

START = SOURCE.index("def publish_crop_climate_suitability_override(")
END = SOURCE.index("\n@router.get(\"/suitability-regions\"", START)
BLOCK = SOURCE[START:END]


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


def main() -> None:
    check(
        "principal: AdminPrincipal = Depends(" in BLOCK
        and "require_admin_permission(AdminPermission.PUBLISH)" in BLOCK,
        "Suitability override requires publish permission",
    )
    check(
        "tenant_id = principal.tenant_id" in BLOCK,
        "Suitability override derives tenant from verified publisher",
    )
    check(
        "actor_id = str(principal.user_id)" in BLOCK,
        "Suitability override derives actor from verified publisher",
    )
    check(
        "Project.tenant_id == tenant_id" in BLOCK
        and "Project.is_active == True" in BLOCK,
        "Suitability override tenant-bounds active project",
    )
    check(
        "published_by=actor_id" in BLOCK,
        "Suitability override records verified publisher",
    )
    check(
        'tenant_id: str = Header' not in BLOCK
        and 'actor_id: str | None = Header' not in BLOCK,
        "Suitability override does not trust identity headers directly",
    )
    check(
        'raise HTTPException(404, "Project not found")' in BLOCK,
        "Suitability override fails closed for inaccessible project",
    )
    print("CROP SUITABILITY OVERRIDE AUTH STATIC CONTRACT PASSED")


if __name__ == "__main__":
    main()

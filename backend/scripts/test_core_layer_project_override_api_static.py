#!/usr/bin/env python3
"""Static contract for the project-scoped Core override API."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
API = (
    ROOT
    / "backend/app/modules/master_data/api/"
    "core_layer_project_overrides.py"
)
API_INIT = ROOT / "backend/app/modules/master_data/api/__init__.py"


def main() -> int:
    source = API.read_text(encoding="utf-8")
    api_init = API_INIT.read_text(encoding="utf-8")

    checks = [
        (
            "CORE_PROJECT_OVERRIDE_REGION_SYSTEMS",
            "Core systems are allowlisted",
        ),
        (
            "CoreLayerProjectOverrideRequest",
            "Request contract exists",
        ),
        (
            "dry_run: bool = True",
            "Dry-run is the default",
        ),
        (
            "confirm_apply: bool = False",
            "Apply confirmation is explicit",
        ),
        (
            "AdminPermission.PROJECT_EDIT",
            "Writes require project edit permission",
        ),
        (
            "project_scoped=True",
            "Authorization is project scoped",
        ),
        (
            "ACTIVE_TENANT_PROJECT_NOT_FOUND",
            "Tenant/project boundary is enforced",
        ),
        (
            "VILLAGE_NOT_IN_PROJECT_SCOPE",
            "Village scope is enforced",
        ),
        (
            "REGION_SYSTEM_NOT_PROJECT_OVERRIDE_ELIGIBLE",
            "Region system is guarded",
        ),
        (
            "EXPLICIT_APPLY_CONFIRMATION_REQUIRED",
            "Unconfirmed apply is rejected",
        ),
        (
            "ACTIVE_PROJECT_VILLAGE_LAYER_OVERRIDE_EXISTS",
            "Supersession is explicit",
        ),
        (
            "ROLLBACK_TOKEN_MISMATCH",
            "Rollback token is guarded",
        ),
        (
            "geography_core_layer_project_overrides",
            "Dedicated table is used",
        ),
        (
            '"global_climate_mappings_changed": False',
            "Global mappings remain unchanged",
        ),
        (
            '"canonical_geography_changed": False',
            "Canonical geography remains unchanged",
        ),
        (
            '"runtime_climate_activation_changed": False',
            "Runtime remains unchanged",
        ),
        (
            '"android_behavior_changed": False',
            "Android remains unchanged",
        ),
    ]

    for needle, label in checks:
        if needle not in source:
            raise AssertionError(
                f"{label}: missing {needle!r}"
            )
        print(f"PASS {label}")

    if "core_layer_project_overrides_router" not in api_init:
        raise AssertionError("Core override router is not registered")
    print("PASS Core override router is registered")

    lowered = source.lower()
    protected_tables = (
        "geography_climate_region_mappings",
        "geography_climate_regions",
        "geography_villages",
    )
    for table in protected_tables:
        for operation in (
            "insert into",
            "update",
            "delete from",
        ):
            needle = f"{operation} {table}"
            if needle in lowered:
                raise AssertionError(
                    f"Forbidden global mutation: {needle}"
                )

    print(
        "CORE LAYER PROJECT OVERRIDE API "
        "STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

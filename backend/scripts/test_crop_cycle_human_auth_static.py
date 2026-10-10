#!/usr/bin/env python3
"""Static contract for authenticated crop-cycle mutations."""

from pathlib import Path


SOURCE = (
    Path(__file__).resolve().parents[1]
    / "app/modules/workflow/api.py"
).read_text()


def require(condition, label):
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


def block(name, next_name):
    start = SOURCE.index(f"def {name}(")
    end = SOURCE.index(f"\ndef {next_name}(", start)
    return SOURCE[start:end]


def main():
    create = block("create_crop_cycle", "list_crop_cycles")
    advance = block("advance_stage", "complete_crop_cycle")
    complete = block("complete_crop_cycle", "log_activity")
    activity = block("log_activity", "list_activities")

    require(
        "def _require_principal_can_operate_cycle_farmer(" in SOURCE,
        "Crop-cycle persona authorization helper exists",
    )
    require(
        "resolve_human_persona_scope(db, principal)" in SOURCE,
        "Crop-cycle authorization resolves persisted persona scope",
    )
    require(
        "_workflow_admin_can_edit(principal)" in SOURCE,
        "Crop-cycle authorization keeps explicit web-admin boundary",
    )
    require(
        "CROP_CYCLE_SCOPE_DENIED" in SOURCE,
        "Crop-cycle denial has stable error",
    )

    for label, route in [
        ("Crop-cycle creation", create),
        ("Crop-stage transition", advance),
        ("Crop-cycle completion", complete),
        ("Crop activity logging", activity),
    ]:
        require(
            "Depends(" in route
            and "require_authenticated_human()" in route,
            f"{label} requires authenticated human",
        )
        require(
            "tenant_id = principal.tenant_id" in route,
            f"{label} derives tenant from verified identity",
        )
        require(
            "actor_id = str(principal.user_id)" in route,
            f"{label} derives actor from verified identity",
        )
        require(
            "_require_principal_can_operate_cycle_farmer(" in route,
            f"{label} applies persona-scoped farmer authorization",
        )
        require(
            "X-Tenant-ID" not in route
            and "x_tenant_id" not in route
            and "X-Actor-ID" not in route
            and "x_actor_id" not in route,
            f"{label} does not trust identity headers directly",
        )

    require(
        "Parcel.tenant_id == tenant_id" in create
        and "Farmer.tenant_id == tenant_id" in create,
        "Crop-cycle creation tenant-bounds parcel and farmer",
    )
    require(
        "body.farmer_id != farmer.id" in create,
        "Crop-cycle creation validates supplied farmer against parcel",
    )
    require(
        "any_farmer" not in create
        and "mobile_number" not in create,
        "Crop-cycle creation removes unsafe farmer fallbacks",
    )
    require(
        "CropCycle.tenant_id == tenant_id" in advance
        and "CropStageInstance.tenant_id == tenant_id" in advance,
        "Crop-stage transition tenant-bounds cycle and stage",
    )
    require(
        "CropCycle.tenant_id == tenant_id" in complete,
        "Crop-cycle completion tenant-bounds cycle",
    )
    require(
        "CropCycle.tenant_id == tenant_id" in activity,
        "Crop activity logging tenant-bounds cycle",
    )
    require(
        "actor_id=actor_id" in create
        and "actor_id=actor_id" in advance
        and "actor_id=actor_id" in complete
        and "actor_id=actor_id" in activity,
        "Crop-cycle audit uses verified actor",
    )

    print("CROP CYCLE HUMAN AUTH STATIC CONTRACT PASSED")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Static contract for authenticated farmer and parcel mutations."""
from pathlib import Path

SOURCE = (Path(__file__).resolve().parents[1] / "app/modules/farmer/api.py").read_text()


def require(condition, label):
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


def block(name, next_name):
    return SOURCE.split(f"def {name}(", 1)[1].split(f"def {next_name}(", 1)[0]


def main():
    enroll = block("enroll_farmer", "list_farmers")
    farmer_update = block("update_farmer_profile", "download_project_enrollment_csv_template")
    parcel_create = block("create_parcel", "list_parcels")
    parcel_update = block("update_parcel_profile", "update_parcel_geometry")
    geometry = block("update_parcel_geometry", "get_form_field_config")
    for label, route in [
        ("Farmer enrollment", enroll),
        ("Farmer update", farmer_update),
        ("Parcel creation", parcel_create),
        ("Parcel update", parcel_update),
        ("Parcel geometry update", geometry),
    ]:
        require("Depends(require_authenticated_human())" in route, f"{label} requires an authenticated human")
        require("principal.tenant_id" in route, f"{label} derives tenant from verified identity")
        require("X-Actor-ID" not in route and "x_actor_id" not in route, f"{label} does not trust actor headers")
    require("resolve_human_persona_scope" in SOURCE, "Mutations resolve persisted persona scope")
    require("resolve_human_persona_scope(db, principal).can_operate_farmer" in SOURCE, "Farmer operations require ownership or assignment")
    require("_farmer_admin_can_edit" in SOURCE, "Web-admin bypass is explicit")
    require("principal.user_id" in enroll, "Enrollment records authenticated actor")
    require("user_id=principal.user_id if self_enrollment else None" in enroll, "Self enrollment binds farmer profile to authenticated user")
    require("principal.user_id" in geometry, "Geometry capture records authenticated actor")
    require("FARMER_SCOPE_DENIED" in SOURCE, "Denied persona scope has a stable error")
    print("FARMER PARCEL HUMAN AUTH STATIC CONTRACT PASSED")


if __name__ == "__main__":
    main()

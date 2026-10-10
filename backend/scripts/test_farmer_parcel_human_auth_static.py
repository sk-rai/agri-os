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
    enroll = block("enroll_farmer", "_readable_farmer_ids")
    farmer_read = block("list_farmers", "list_farmer_profile_readiness")
    readiness_read = block("list_farmer_profile_readiness", "get_field_agent_worklist")
    worklist_read = block("get_field_agent_worklist", "update_farmer_profile")
    enrollment_read = block("list_farmer_project_enrollments", "list_project_farmer_enrollments")
    launch_read = block("get_farmer_launch_context", "create_parcel")
    enrollment_create = block(
        "create_farmer_project_enrollment",
        "update_farmer_project_agent_assignment",
    )
    agent_assignment = block(
        "update_farmer_project_agent_assignment",
        "_update_enrollment_lifecycle_status",
    )
    enrollment_status_update = block(
        "update_farmer_project_enrollment_status",
        "preview_project_enrollment_lifecycle",
    )
    self_resolver = block("_resolve_authenticated_user_farmer", "_model_patch_values")
    duplicate_read = block("list_duplicate_farmers", "archive_duplicate_farmers")
    duplicate_archive = block("archive_duplicate_farmers", "get_farmer_profile_by_mobile")
    by_mobile_read = block("get_farmer_profile_by_mobile", "get_my_profile_hydration")
    self_hydration_read = block("get_my_profile_hydration", "get_my_farmer_profile")
    self_farmer_read = block("get_my_farmer_profile", "get_land_intelligence_context")
    farmer_update = block("update_farmer_profile", "download_project_enrollment_csv_template")
    parcel_create = block("create_parcel", "list_parcels")
    parcel_read = block("list_parcels", "update_parcel_profile")
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
    for label, route in [
        ("Farmer listing", farmer_read),
        ("Parcel listing", parcel_read),
    ]:
        require(
            "Depends(require_authenticated_human())" in route,
            f"{label} requires an authenticated human",
        )
        require(
            "principal.tenant_id" in route,
            f"{label} derives tenant from verified identity",
        )
        require(
            "_readable_farmer_ids" in route,
            f"{label} applies persona-scoped farmer visibility",
        )
        require(
            "X-Tenant-ID" not in route and "x_tenant_id" not in route,
            f"{label} does not trust tenant headers directly",
        )
    require(
        "scope.own_farmer_ids | scope.assigned_farmer_ids" in SOURCE,
        "Read visibility combines personal and assigned farmers",
    )
    require(
        "if _farmer_admin_can_edit(principal):" in SOURCE,
        "Read visibility keeps an explicit web-admin boundary",
    )
    require(
        "Depends(require_authenticated_human())" in readiness_read,
        "Profile readiness requires an authenticated human",
    )
    require(
        "principal.tenant_id" in readiness_read,
        "Profile readiness derives tenant from verified identity",
    )
    require(
        "_readable_farmer_ids" in readiness_read,
        "Profile readiness applies persona-scoped farmer visibility",
    )
    require(
        "X-Tenant-ID" not in readiness_read
        and "x_tenant_id" not in readiness_read,
        "Profile readiness does not trust tenant headers directly",
    )
    require(
        "Depends(require_authenticated_human())" in worklist_read,
        "Field-agent worklist requires an authenticated human",
    )
    require(
        "principal.tenant_id" in worklist_read,
        "Field-agent worklist derives tenant from verified identity",
    )
    require(
        "resolve_human_persona_scope(db, principal)" in worklist_read,
        "Field-agent worklist resolves persisted persona scope",
    )
    require(
        "scope.assigned_farmer_ids" in worklist_read,
        "Field-agent worklist is restricted to assigned farmers",
    )
    require(
        "actor_id != principal.user_id" in worklist_read,
        "Field-agent worklist rejects actor impersonation",
    )
    require(
        "actor_uuid = principal.user_id" in worklist_read,
        "Field-agent worklist derives actor from verified identity",
    )
    require(
        "X-Tenant-ID" not in worklist_read
        and "x_tenant_id" not in worklist_read
        and "X-Actor-ID" not in worklist_read
        and "x_actor_id" not in worklist_read,
        "Field-agent worklist does not trust identity headers directly",
    )
    for label, route in [
        ("Farmer project-enrollment read", enrollment_read),
        ("Farmer launch-context read", launch_read),
    ]:
        require(
            "Depends(require_authenticated_human())" in route,
            f"{label} requires an authenticated human",
        )
        require(
            "principal.tenant_id" in route,
            f"{label} derives tenant from verified identity",
        )
        require(
            "_readable_farmer_ids" in route,
            f"{label} applies persona-scoped farmer visibility",
        )
        require(
            'raise HTTPException(404, "Farmer not found")' in route,
            f"{label} fails closed without farmer disclosure",
        )
        require(
            "Project.tenant_id == tenant_id" in route,
            f"{label} tenant-bounds joined projects",
        )
        require(
            "X-Tenant-ID" not in route
            and "x_tenant_id" not in route,
            f"{label} does not trust tenant headers directly",
        )
    require(
        "require_admin_permission(AdminPermission.VIEW)" in duplicate_read,
        "Duplicate farmer listing requires admin view permission",
    )
    require(
        "tenant_id = principal.tenant_id" in duplicate_read,
        "Duplicate farmer listing derives tenant from verified admin",
    )
    require(
        "X-Tenant-ID" not in duplicate_read
        and "x_tenant_id" not in duplicate_read,
        "Duplicate farmer listing does not trust tenant headers directly",
    )
    require(
        "require_admin_permission(AdminPermission.EDIT)" in duplicate_archive,
        "Duplicate farmer archive requires admin edit permission",
    )
    require(
        "tenant_id = principal.tenant_id" in duplicate_archive,
        "Duplicate farmer archive derives tenant from verified admin",
    )
    require(
        '"actor_id": str(principal.user_id)' in duplicate_archive,
        "Duplicate farmer archive records verified administrator",
    )
    require(
        "X-Tenant-ID" not in duplicate_archive
        and "x_tenant_id" not in duplicate_archive
        and "X-Actor-ID" not in duplicate_archive
        and "x_actor_id" not in duplicate_archive,
        "Duplicate farmer archive does not trust identity headers directly",
    )
    require(
        "Depends(require_authenticated_human())" in by_mobile_read,
        "Farmer by-mobile hydration requires an authenticated human",
    )
    require(
        "tenant_id = principal.tenant_id" in by_mobile_read,
        "Farmer by-mobile hydration derives tenant from verified identity",
    )
    require(
        "_readable_farmer_ids" in by_mobile_read,
        "Farmer by-mobile hydration applies persona-scoped visibility",
    )
    require(
        "Farmer.user_id == principal.user_id" in by_mobile_read,
        "Farmer by-mobile hydration detects explicit personal linkage",
    )
    require(
        "user.mobile_number" in by_mobile_read
        and "persisted_mobile_matches" in by_mobile_read,
        "Farmer by-mobile hydration limits compatibility to persisted mobile",
    )
    require(
        "has_linked_farmer or not persisted_mobile_matches" in by_mobile_read,
        "Farmer by-mobile hydration disables fallback after explicit linkage",
    )
    require(
        'raise HTTPException(\n                404,' in by_mobile_read,
        "Farmer by-mobile hydration fails closed without mobile disclosure",
    )
    require(
        "X-Tenant-ID" not in by_mobile_read
        and "x_tenant_id" not in by_mobile_read
        and "X-Actor-ID" not in by_mobile_read
        and "x_actor_id" not in by_mobile_read,
        "Farmer by-mobile hydration does not trust identity headers directly",
    )
    for label, route in [
        ("Farmer self hydration", self_hydration_read),
        ("Farmer self profile", self_farmer_read),
    ]:
        require(
            "Depends(require_authenticated_human())" in route,
            f"{label} requires an authenticated human",
        )
        require(
            "_resolve_authenticated_user_farmer" in route,
            f"{label} resolves a persisted farmer identity",
        )
        require(
            "X-Tenant-ID" not in route
            and "x_tenant_id" not in route
            and "X-Actor-ID" not in route
            and "x_actor_id" not in route,
            f"{label} does not trust identity headers directly",
        )
    require(
        "User.id == principal.user_id" in self_resolver
        and "User.tenant_id == principal.tenant_id" in self_resolver,
        "Self-profile resolution tenant-bounds the authenticated user",
    )
    require(
        "Farmer.user_id == principal.user_id" in self_resolver,
        "Self-profile resolution prefers explicit farmer linkage",
    )
    require(
        "_select_hydration_farmer" in self_resolver
        and "user.mobile_number" in self_resolver,
        "Self-profile resolution keeps verified persisted-mobile compatibility",
    )
    require(
        "principal.tenant_id" in self_hydration_read,
        "Farmer self hydration derives tenant from verified identity",
    )
    require(
        "require_admin_permission(AdminPermission.PROJECT_EDIT)"
        in enrollment_create,
        "Farmer project enrollment creation requires project-edit permission",
    )
    require(
        "_farmer_admin_can_edit(principal)" in enrollment_create,
        "Farmer project enrollment creation keeps an explicit web-admin boundary",
    )
    require(
        "tenant_id = principal.tenant_id" in enrollment_create,
        "Farmer project enrollment creation derives tenant from verified admin",
    )
    require(
        "Farmer.tenant_id == tenant_id" in enrollment_create,
        "Farmer project enrollment creation tenant-bounds farmer",
    )
    require(
        "Project.tenant_id == tenant_id" in enrollment_create,
        "Farmer project enrollment creation tenant-bounds project",
    )
    require(
        "Parcel.tenant_id == tenant_id" in enrollment_create,
        "Farmer project enrollment creation tenant-bounds parcels",
    )
    require(
        "enrollment.enrolled_by = principal.user_id" in enrollment_create,
        "Farmer project enrollment creation records verified administrator",
    )
    require(
        "X-Tenant-ID" not in enrollment_create
        and "x_tenant_id" not in enrollment_create
        and "X-Actor-ID" not in enrollment_create
        and "x_actor_id" not in enrollment_create,
        "Farmer project enrollment creation does not trust identity headers directly",
    )
    require(
        "require_admin_permission(AdminPermission.PROJECT_EDIT)"
        in agent_assignment,
        "Project agent assignment requires project-edit permission",
    )
    require(
        "_farmer_admin_can_edit(principal)" in agent_assignment,
        "Project agent assignment keeps an explicit web-admin boundary",
    )
    require(
        "tenant_id = principal.tenant_id" in agent_assignment,
        "Project agent assignment derives tenant from verified admin",
    )
    require(
        "Farmer.tenant_id == tenant_id" in agent_assignment,
        "Project agent assignment tenant-bounds farmer",
    )
    require(
        "Project.tenant_id == tenant_id" in agent_assignment,
        "Project agent assignment tenant-bounds project",
    )
    require(
        "User.tenant_id == tenant_id" in agent_assignment,
        "Project agent assignment tenant-bounds target user",
    )
    require(
        "AgentProfile.tenant_id == tenant_id" in agent_assignment
        and 'AgentProfile.status == "ACTIVE"' in agent_assignment,
        "Project agent assignment requires an active agent profile",
    )
    require(
        "ProjectRole.project_id == body.project_id" in agent_assignment
        and "ProjectRole.user_id == body.agent_user_id" in agent_assignment
        and "ProjectRole.is_active == True" in agent_assignment,
        "Project agent assignment requires an active project role",
    )
    require(
        '"actor_id": str(principal.user_id)' in agent_assignment,
        "Project agent assignment records verified administrator",
    )
    require(
        "X-Tenant-ID" not in agent_assignment
        and "x_tenant_id" not in agent_assignment
        and "X-Actor-ID" not in agent_assignment
        and "x_actor_id" not in agent_assignment,
        "Project agent assignment does not trust identity headers directly",
    )
    require(
        "require_admin_permission(AdminPermission.PROJECT_EDIT)"
        in enrollment_status_update,
        "Enrollment lifecycle update requires project-edit permission",
    )
    require(
        "_farmer_admin_can_edit(principal)" in enrollment_status_update,
        "Enrollment lifecycle update keeps an explicit web-admin boundary",
    )
    require(
        "tenant_id = principal.tenant_id" in enrollment_status_update,
        "Enrollment lifecycle update derives tenant from verified admin",
    )
    require(
        "FarmerProjectEnrollment.tenant_id == tenant_id"
        in enrollment_status_update,
        "Enrollment lifecycle update tenant-bounds enrollment",
    )
    require(
        "Project.tenant_id == tenant_id" in enrollment_status_update,
        "Enrollment lifecycle update tenant-bounds joined project",
    )
    require(
        "actor_id=principal.user_id" in enrollment_status_update,
        "Enrollment lifecycle update records verified administrator",
    )
    require(
        "X-Tenant-ID" not in enrollment_status_update
        and "x_tenant_id" not in enrollment_status_update
        and "X-Actor-ID" not in enrollment_status_update
        and "x_actor_id" not in enrollment_status_update,
        "Enrollment lifecycle update does not trust identity headers directly",
    )
    print("FARMER PARCEL HUMAN AUTH STATIC CONTRACT PASSED")


if __name__ == "__main__":
    main()

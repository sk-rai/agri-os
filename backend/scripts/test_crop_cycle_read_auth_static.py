#!/usr/bin/env python3
"""Static contract for crop-cycle operational read authorization."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = ROOT / "backend/app/modules/workflow/api.py"
AUDIT_PATH = ROOT / "backend/scripts/audit_tenant_actor_trust_boundary.py"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8-sig")
TREE = ast.parse(SOURCE)


def check(condition, label):
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


def function_source(name):
    node = next(
        item for item in ast.walk(TREE)
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == name
    )
    return ast.get_source_segment(SOURCE, node)


RUNTIME_READS = {
    "list_crop_cycles",
    "list_eligible_parcels",
    "get_recommended_activities",
    "get_finance_report_config",
    "get_crop_cycle_stage_cost_summary",
    "get_crop_cycle_profit_loss_summary",
    "get_crop_cycle",
    "list_activities",
}


def main():
    for helper in [
        "_workflow_admin_can_view",
        "_crop_cycle_visible_farmer_ids",
        "_require_principal_can_read_cycle_farmer",
        "_load_authorized_crop_cycle",
        "_assert_crop_cycle_project_read_scope",
    ]:
        check(
            f"def {helper}(" in SOURCE,
            f"{helper} exists",
        )

    visible = function_source("_crop_cycle_visible_farmer_ids")
    check(
        "AdminPermission.VIEW" in function_source(
            "_workflow_admin_can_view"
        ),
        "Read administrator boundary uses VIEW permission",
    )
    check(
        "scope.own_farmer_ids | scope.assigned_farmer_ids" in visible,
        "Collection scope combines owned and assigned farmers",
    )

    loader = function_source("_load_authorized_crop_cycle")
    check(
        "CropCycle.tenant_id == principal.tenant_id" in loader,
        "Cycle loader tenant-bounds selected cycle",
    )
    check(
        "_require_principal_can_read_cycle_farmer(" in loader,
        "Cycle loader applies farmer persona scope",
    )

    project = function_source("_assert_crop_cycle_project_read_scope")
    check(
        "Project.tenant_id == principal.tenant_id" in project,
        "Finance project scope is tenant bounded",
    )
    check(
        "scope.has_project_access(project_id)" in project,
        "Finance project scope permits verified project role",
    )
    check(
        "FarmerProjectEnrollment.status == \"ACTIVE\"" in project,
        "Finance project scope requires active farmer enrollment",
    )

    for name in sorted(RUNTIME_READS):
        body = function_source(name)
        check(
            "require_authenticated_human()" in body,
            f"{name} requires authenticated human",
        )
        check(
            "principal.tenant_id" in body,
            f"{name} derives verified tenant",
        )
        check(
            "principal.user_id" in body,
            f"{name} derives verified actor",
        )
        check(
            "X-Tenant-ID" not in body
            and "x_tenant_id" not in body
            and "X-Actor-ID" not in body
            and "x_actor_id" not in body,
            f"{name} does not trust identity headers directly",
        )

    listing = function_source("list_crop_cycles")
    check(
        "CropCycle.farmer_id.in_(visible_farmer_ids)" in listing,
        "Crop-cycle collection filters to visible farmers",
    )

    eligible = function_source("list_eligible_parcels")
    check(
        "_require_principal_can_read_cycle_farmer(" in eligible,
        "Eligible parcels requires explicit farmer scope",
    )

    report_config = function_source("get_finance_report_config")
    check(
        "_assert_crop_cycle_project_read_scope(" in report_config,
        "Finance report config enforces optional project scope",
    )

    for name in [
        "get_recommended_activities",
        "get_crop_cycle_stage_cost_summary",
        "get_crop_cycle_profit_loss_summary",
        "get_crop_cycle",
        "list_activities",
    ]:
        check(
            "_load_authorized_crop_cycle(" in function_source(name),
            f"{name} authorizes selected cycle",
        )

    activities = function_source("list_activities")
    check(
        "CropStageInstance.tenant_id == tenant_id" in activities,
        "Activity stage lookup remains tenant bounded",
    )

    analytics = function_source("get_finance_analytics_summary")
    check(
        "require_admin_permission(AdminPermission.VIEW)" in analytics,
        "Tenant finance analytics requires administrator VIEW",
    )
    check(
        "principal.tenant_id" in analytics
        and "principal.user_id" in analytics,
        "Tenant finance analytics derives verified identity",
    )

    template = function_source("get_crop_template")
    check(
        "require_authenticated_human" not in template
        and "require_admin_permission" not in template,
        "Canonical crop template remains reference data",
    )
    check(
        'tenant_id="default"' in template,
        "Canonical crop template uses default published workflow",
    )

    spec = importlib.util.spec_from_file_location(
        "trust_audit",
        AUDIT_PATH,
    )
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    rows = audit.scan(SOURCE_PATH)
    targets = RUNTIME_READS | {
        "get_finance_analytics_summary",
        "get_crop_template",
    }
    matches = [row for row in rows if row["function"] in targets]
    check(
        len(matches) == 10,
        "Auditor finds all crop-cycle read routes",
    )
    check(
        not [row for row in matches if row["flags"]],
        "Crop-cycle reads have no audit findings",
    )

    template_row = next(
        row for row in matches
        if row["function"] == "get_crop_template"
    )
    check(
        template_row["method"] == "GET"
        and template_row["reference"] is True
        and template_row["public"] is False,
        "Crop template is an exact GET reference classification",
    )

    secured = [
        row for row in matches
        if row["function"] != "get_crop_template"
    ]
    check(
        all(
            row["admin_dependency"] or row["bearer_marker"]
            for row in secured
        ),
        "Operational crop-cycle reads have authentication markers",
    )
    check(
        all(row["tenant_marker"] for row in secured),
        "Operational crop-cycle reads have verified tenant markers",
    )
    check(
        all(row["actor_marker"] for row in secured),
        "Operational crop-cycle reads have verified actor markers",
    )

    print("CROP CYCLE READ AUTH STATIC CONTRACT PASSED")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Static contract for authenticated profile, soil, and land-intelligence reads."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOIL_PATH = ROOT / "backend/app/modules/farmer/soil_profile.py"
FARMER_PATH = ROOT / "backend/app/modules/farmer/api.py"
SUMMARY_PATH = (
    ROOT
    / "backend/app/modules/master_data/api/land_intelligence_summary.py"
)
AUDIT_PATH = ROOT / "backend/scripts/audit_tenant_actor_trust_boundary.py"


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"PASS {message}")


def functions(path: Path) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def body(node: ast.AST) -> str:
    return ast.unparse(node)


def route_methods(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    methods = []
    for decorator in node.decorator_list:
        if (
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
        ):
            methods.append(decorator.func.attr.upper())
    return methods


soil = functions(SOIL_PATH)
farmer = functions(FARMER_PATH)
summary = functions(SUMMARY_PATH)

for helper in (
    "_soil_readable_farmer_ids",
    "_require_can_read_soil_farmer",
    "_require_can_read_soil_target",
):
    check(helper in soil, f"{helper} exists")

check(
    "resolve_human_persona_scope" in body(soil["_soil_readable_farmer_ids"]),
    "Soil collection scope resolves persisted human persona",
)
check(
    "own_farmer_ids" in body(soil["_soil_readable_farmer_ids"])
    and "assigned_farmer_ids" in body(soil["_soil_readable_farmer_ids"]),
    "Soil collection scope combines owned and assigned farmers",
)
check(
    "principal.tenant_id" in body(soil["_require_can_read_soil_target"]),
    "Soil target authorization tenant-bounds target records",
)
check(
    "FARMER_SCOPE_DENIED" in SOIL_PATH.read_text(),
    "Soil read denial exposes the shared stable farmer-scope error code",
)

soil_routes = {
    "latest_soil_enrichment_snapshot",
    "list_soil_enrichment_snapshots",
    "get_soil_enrichment_summary",
    "list_soil_profiles",
}
for name in sorted(soil_routes):
    check(name in soil, f"{name} exists")
    source = body(soil[name])
    check(route_methods(soil[name]) == ["GET"], f"{name} is a GET route")
    check(
        "require_authenticated_human" in source
        and "AuthenticatedPrincipal" in source,
        f"{name} requires authenticated human",
    )
    check(
        "principal.tenant_id" in source,
        f"{name} derives verified tenant",
    )
    check(
        "principal.user_id" in source,
        f"{name} derives verified actor",
    )
    check(
        'Header(' not in source
        and "x_tenant_id" not in source
        and "x_actor_id" not in source,
        f"{name} does not trust identity headers directly",
    )
    check(
        "db.commit" not in source
        and "db.add(" not in source
        and "db.delete(" not in source,
        f"{name} remains database read-only",
    )

check(
    "_require_land_intelligence_project_read_scope" in farmer,
    "Land context project read helper exists",
)
context_helper = body(
    farmer["_require_land_intelligence_project_read_scope"]
)
check(
    "Project.tenant_id == principal.tenant_id" in context_helper,
    "Land context project helper tenant-bounds project",
)
check(
    "resolve_human_persona_scope" in context_helper
    and "has_project_access" in context_helper,
    "Land context project helper enforces persisted persona scope",
)
check(
    "FarmerProjectEnrollment.tenant_id == principal.tenant_id" in context_helper
    and "FarmerProjectEnrollment.project_id == project_id" in context_helper
    and "FarmerProjectEnrollment.status" in context_helper
    and "'ACTIVE'" in context_helper
    and "FarmerProjectEnrollment.is_active == True" in context_helper
    and "Farmer.user_id == principal.user_id" in context_helper,
    "Land context permits only the caller's active farmer enrollment",
)
check(
    "LAND_INTELLIGENCE_SCOPE_DENIED" in context_helper,
    "Land context denial exposes stable error code",
)

context = body(farmer["get_land_intelligence_context"])
check(
    "require_authenticated_human" in context,
    "Land intelligence context requires authenticated human",
)
check(
    "principal.tenant_id" in context,
    "Land intelligence context derives verified tenant",
)
check(
    "principal.user_id" in context,
    "Land intelligence context derives verified actor",
)
check(
    "_require_land_intelligence_project_read_scope" in context,
    "Land intelligence context enforces optional project scope",
)
check(
    'Header(' not in context and "x_tenant_id" not in context,
    "Land intelligence context does not trust tenant header directly",
)

check(
    "_require_land_summary_project_read_scope" in summary,
    "Land summary project read helper exists",
)
summary_helper = body(summary["_require_land_summary_project_read_scope"])
check(
    "Project.tenant_id == principal.tenant_id" in summary_helper,
    "Land summary project helper tenant-bounds project",
)
check(
    "resolve_human_persona_scope" in summary_helper
    and "has_project_access" in summary_helper,
    "Land summary project helper enforces persisted persona scope",
)
check(
    "FarmerProjectEnrollment.tenant_id == principal.tenant_id" in summary_helper
    and "FarmerProjectEnrollment.project_id == project_id" in summary_helper
    and "FarmerProjectEnrollment.status" in summary_helper
    and "'ACTIVE'" in summary_helper
    and "FarmerProjectEnrollment.is_active == True" in summary_helper
    and "Farmer.user_id == principal.user_id" in summary_helper,
    "Land summary permits only the caller's active farmer enrollment",
)
check(
    "LAND_INTELLIGENCE_SCOPE_DENIED" in summary_helper,
    "Land summary denial exposes stable error code",
)

summary_route = body(summary["get_land_intelligence_summary"])
check(
    "require_authenticated_human" in summary_route,
    "Land intelligence summary requires authenticated human",
)
check(
    "principal.tenant_id" in summary_route,
    "Land intelligence summary derives verified tenant",
)
check(
    "principal.user_id" in summary_route,
    "Land intelligence summary derives verified actor",
)
check(
    "_require_land_summary_project_read_scope" in summary_route,
    "Land intelligence summary enforces optional project scope",
)
check(
    'Header(' not in summary_route and "x_tenant_id" not in summary_route,
    "Land intelligence summary does not trust tenant header directly",
)
check(
    "db.commit" not in summary_route
    and "db.add(" not in summary_route
    and "db.delete(" not in summary_route,
    "Land intelligence summary remains database read-only",
)

spec = importlib.util.spec_from_file_location("audit", AUDIT_PATH)
audit = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(audit)

rows = []
for source_path in sorted(audit.APP.rglob("*.py")):
    if not source_path.name.startswith("__"):
        rows.extend(audit.scan(source_path))

expected_paths = {
    "/api/v1/profile/land-intelligence-context",
    "/api/v1/profile/land-intelligence-summary",
    "/api/v1/soil-profiles/enrichments/latest",
    "/api/v1/soil-profiles/enrichments",
    "/api/v1/soil-profiles/enrichments/summary",
    "/api/v1/soil-profiles",
}
matches = [
    row
    for row in rows
    if row["method"] == "GET" and row["path"] in expected_paths
]

check(len(matches) == 6, "Auditor finds all six operational profile reads")
check(
    {row["path"] for row in matches} == expected_paths,
    "Auditor finds the exact operational profile read set",
)
check(
    all(row["bearer_marker"] for row in matches),
    "Operational profile reads have authentication markers",
)
check(
    all(row["tenant_marker"] for row in matches),
    "Operational profile reads have verified tenant markers",
)
check(
    all(row["actor_marker"] for row in matches),
    "Operational profile reads have verified actor markers",
)
check(
    all(not row["public"] for row in matches),
    "Operational profile reads are not public authentication routes",
)
check(
    all(not row["reference"] for row in matches),
    "Operational profile reads are not reference exceptions",
)
check(
    all(not row["flags"] for row in matches),
    "Operational profile reads have no trust-boundary findings",
)

flagged = [row for row in rows if row["flags"]]
check(len(rows) == 361, "Full auditor route count remains stable")
check(not flagged, "Full auditor has zero trust-boundary findings")

print("PROFILE AND LAND READ AUTH STATIC CONTRACT PASSED")

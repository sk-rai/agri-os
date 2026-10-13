#!/usr/bin/env python3
"""Static authorization contract for geography review mutations."""

from __future__ import annotations

import ast
from pathlib import Path


TARGETS = {
    Path(__file__).resolve().parents[1]
    / "app/modules/master_data/api/geography.py": {
        "apply_nwdp_boundary_project_matching_disabled",
        "update_nwdp_boundary_candidate_review",
        "update_nwdp_demographic_profile_review",
        "update_core_lgd_mapping_review_decision",
    },
    Path(__file__).resolve().parents[1]
    / "app/modules/master_data/api/"
    "village_resolution_evidence_reviews.py": {
        "create_primary_review",
        "complete_second_review",
    },
}

GLOBAL_REVIEWS = {
    "update_nwdp_boundary_candidate_review",
    "update_nwdp_demographic_profile_review",
    "update_core_lgd_mapping_review_decision",
    "create_primary_review",
    "complete_second_review",
}


def check(condition, label):
    print(f"{'PASS' if condition else 'FAIL'} {label}")
    if not condition:
        raise AssertionError(label)


functions = {}
for path, names in TARGETS.items():
    source = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in names
        ):
            body = ast.get_source_segment(source, node)
            if body is None:
                raise AssertionError(f"Could not extract {node.name}")
            functions[node.name] = body

expected = set().union(*TARGETS.values())
check(set(functions) == expected, "All geography review mutations exist")

for name in sorted(expected):
    body = functions[name]
    check(
        "tenant_id = principal.tenant_id" in body,
        f"{name} derives verified tenant",
    )
    check(
        "actor_id = principal.user_id" in body,
        f"{name} derives verified actor",
    )
    check(
        "require_admin_permission(" in body,
        f"{name} requires administrator authorization",
    )
    remainder = body.replace("actor_id = principal.user_id", "")
    check(
        "principal.user_id" not in remainder,
        f"{name} uses normalized verified actor",
    )

for name in sorted(GLOBAL_REVIEWS):
    body = functions[name]
    check(
        'tenant_id != "default"' in body,
        f"{name} restricts mutation to platform tenant",
    )
    check(
        '"GLOBAL_GEOGRAPHY_REVIEW_TENANT_REQUIRED"' in body,
        f"{name} exposes stable global-review boundary error",
    )
    check(
        "str(actor_id)" in body,
        f"{name} persists verified reviewer attribution",
    )

disabled = functions[
    "apply_nwdp_boundary_project_matching_disabled"
]
check(
    "AdminPermission.PROJECT_EDIT" in disabled,
    "Disabled project matching apply requires project-edit",
)
check(
    "project_scoped=True" in disabled,
    "Disabled project matching apply enforces project scope",
)
check(
    "and tenant_id = :tenant_id" in disabled,
    "Disabled project matching apply tenant-bounds project",
)
check(
    '"tenant_id": tenant_id' in disabled,
    "Disabled project matching apply binds verified tenant",
)
check(
    '"requested_by": str(actor_id)' in disabled,
    "Disabled project matching apply reports verified administrator",
)
check(
    "db.commit(" not in disabled
    and "db.flush(" not in disabled
    and "db.add(" not in disabled,
    "Disabled project matching apply remains write-free",
)
check(
    "status_code=501" in disabled,
    "Disabled project matching apply remains disabled",
)

print("GEOGRAPHY REVIEW AUTH STATIC CONTRACT PASSED")

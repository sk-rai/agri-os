#!/usr/bin/env python3
"""Static contract for Core project override admin UI."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COMPONENT = (
    ROOT
    / "web/src/components/admin/"
    "CoreLayerProjectOverridePanel.tsx"
)
PAGE = (
    ROOT
    / "web/src/app/(admin)/"
    "geography-layer-readiness/page.tsx"
)


def main() -> int:
    component = COMPONENT.read_text(encoding="utf-8")
    page = PAGE.read_text(encoding="utf-8")
    normalized_component = " ".join(component.split())

    checks = [
        (
            "CoreLayerProjectOverridePanel",
            page,
            "Panel is rendered on geography readiness",
        ),
        (
            "projectsApi",
            component,
            "Tenant projects client is used",
        ),
        (
            ".list()",
            component,
            "Tenant projects are loaded",
        ),
        (
            "Search project village",
            component,
            "Canonical project village search is explicit",
        ),
        (
            "setVillageId(village.id)",
            component,
            "Canonical project village UUID is retained",
        ),
        (
            "core-layer-project-overrides",
            component,
            "Project-scoped API is used",
        ),
        (
            "dry_run: true",
            component,
            "Dry run precedes apply",
        ),
        (
            "confirm_apply: true",
            component,
            "Apply confirmation is explicit",
        ),
        (
            "supersede_existing: supersede",
            component,
            "Supersession is explicit",
        ),
        (
            'method: "DELETE"',
            component,
            "Rollback endpoint is used",
        ),
        (
            "rollback_token",
            component,
            "Rollback token is preserved",
        ),
        (
            "Project override active",
            component,
            "Active project override is distinguished",
        ),
        (
            "Use for this project",
            component,
            "Assignment action states project scope",
        ),
        (
            "Global/default resolution remains in effect",
            component,
            "Global fallback is distinguished",
        ),
        (
            "do not promote inactive global",
            component,
            "Global mapping guardrail is explicit",
        ),
        (
            "Canonical LGD",
            component,
            "Canonical geography guardrail is explicit",
        ),
        (
            "Android behavior remain unchanged",
            normalized_component,
            "Android guardrail is explicit",
        ),
    ]

    for needle, source, label in checks:
        if needle not in source:
            raise AssertionError(
                f"{label}: missing {needle!r}"
            )
        print(f"PASS {label}")

    forbidden = (
        "global_climate_mapping_apply",
        "runtime_climate_activation",
        "geography_climate_region_mappings",
    )
    lowered = component.lower()
    for needle in forbidden:
        if needle in lowered:
            raise AssertionError(
                f"Forbidden global/runtime UI operation: {needle}"
            )

    print(
        "CORE LAYER PROJECT OVERRIDE ADMIN UI "
        "STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Static contract for project-scoped Core village search UI."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COMPONENT = (
    ROOT
    / "web/src/components/admin/CoreLayerProjectOverridePanel.tsx"
)


def main() -> int:
    source = COMPONENT.read_text(encoding="utf-8")

    checks = [
        (
            "geographyApi",
            "Existing geography client is reused",
        ),
        (
            "resolveVillagesByLgdCodes(codes)",
            "Canonical village resolver is reused",
        ),
        (
            "selectedProject?.geography_scope?.village_lgd_codes",
            "Search scope comes from the selected project",
        ),
        (
            "GeographyVillageDetails",
            "Existing canonical village contract is reused",
        ),
        (
            'type="search"',
            "Village input is a search control",
        ),
        (
            'role="combobox"',
            "Search exposes combobox semantics",
        ),
        (
            'role="listbox"',
            "Search results expose listbox semantics",
        ),
        (
            "filteredProjectVillages",
            "Only hydrated project villages are searched",
        ),
        (
            "village.canonical_name",
            "Village canonical name is displayed",
        ),
        (
            "village.lgd_code",
            "Village LGD code is displayed",
        ),
        (
            "village.block_name",
            "Village block is displayed",
        ),
        (
            "village.district_name",
            "Village district is displayed",
        ),
        (
            "village.state_name",
            "Village state is displayed",
        ),
        (
            "setVillageId(village.id)",
            "Selection retains canonical village UUID",
        ),
        (
            "No villages in this project match the search.",
            "Empty search result is explicit",
        ),
        (
            "Selected project has no canonical village scope",
            "Missing project scope is explicit",
        ),
    ]

    for needle, label in checks:
        if needle not in source:
            raise AssertionError(f"{label}: missing {needle!r}")
        print(f"PASS {label}")

    if "Canonical village UUID" in source:
        raise AssertionError(
            "Manual canonical village UUID entry remains visible"
        )
    print("PASS Manual UUID entry is removed")

    endpoint_fragment = (
        "/core-layer-project-overrides/projects/${projectId}"
        "/villages/${villageId.trim()}"
    )
    if endpoint_fragment not in source:
        raise AssertionError(
            "Selected canonical village UUID is not passed to the "
            "project override API"
        )
    print("PASS Selected village remains project-override scoped")

    prohibited = [
        "geography_scope:",
        "projectsApi.update",
        "runtime activation",
    ]
    lower_source = source.lower()
    if "projectsapi.update" in lower_source:
        raise AssertionError("Village search must not modify project scope")
    print("PASS Search does not modify project geography scope")

    print(
        "CORE LAYER PROJECT VILLAGE SEARCH ADMIN UI "
        "STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

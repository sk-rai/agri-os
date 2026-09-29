#!/usr/bin/env python3
"""Static contract for the Core-layer effective preview admin UI."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COMPONENT = (
    ROOT
    / "web/src/components/admin/CoreLayerProjectOverridePanel.tsx"
)


def main() -> int:
    source = COMPONENT.read_text(encoding="utf-8")
    normalized = " ".join(source.split())

    checks = [
        (
            "type EffectiveResolution",
            "Effective resolution contract exists",
        ),
        (
            "type EffectiveRegion",
            "Effective region contract exists",
        ),
        (
            'api<EffectiveResolution>(`${baseUrl}/effective`)',
            "Existing effective resolver endpoint is used",
        ),
        (
            "Promise.all([",
            "Assignment context and effective preview load together",
        ),
        (
            "Effective Core layers",
            "Effective preview is visible",
        ),
        (
            "Project override",
            "Project override source is distinguished",
        ),
        (
            "Global fallback",
            "Global fallback source is distinguished",
        ),
        (
            "Scope: {effective.resolution_scope}",
            "Resolution scope is visible",
        ),
        (
            "Fallback after rollback",
            "Rollback fallback is visible",
        ),
        (
            "global_fallback_region_name",
            "Fallback region name is displayed",
        ),
        (
            "global_fallback_scope",
            "Fallback scope is displayed",
        ),
        (
            "Unresolved layers:",
            "Unresolved layers are explicit",
        ),
        (
            "No global fallback",
            "Missing fallback is explicit",
        ),
        (
            "await loadContext();",
            "Mutations refresh effective resolution",
        ),
    ]

    for needle, label in checks:
        if needle not in normalized:
            raise AssertionError(f"{label}: missing {needle!r}")
        print(f"PASS {label}")

    effective_calls = normalized.count(
        'api<EffectiveResolution>(`${baseUrl}/effective`)'
    )
    if effective_calls != 1:
        raise AssertionError(
            f"Expected one effective resolver call, found {effective_calls}"
        )
    print("PASS Effective resolver call is singular")

    prohibited = [
        'method: "POST"',
        "geography_climate_region_mappings",
        "runtime_lookup_enabled",
    ]
    preview_start = normalized.index("Effective Core layers")
    preview_end = normalized.index(
        '<div className="mt-4 grid gap-3 xl:grid-cols-3">',
        preview_start,
    )
    preview = normalized[preview_start:preview_end]
    for needle in prohibited:
        if needle.lower() in preview.lower():
            raise AssertionError(
                f"Effective preview contains prohibited operation: {needle}"
            )

    print("PASS Effective preview is read-only")
    print(
        "CORE LAYER PROJECT EFFECTIVE PREVIEW ADMIN UI "
        "STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

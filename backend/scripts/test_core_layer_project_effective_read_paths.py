#!/usr/bin/env python3
"""Static contract for project-aware Core-layer consumer read paths."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CROP_API = ROOT / "backend/app/modules/master_data/api/crop_catalog.py"
FARMER_API = ROOT / "backend/app/modules/farmer/api.py"


def main() -> int:
    crop = CROP_API.read_text(encoding="utf-8")
    farmer = FARMER_API.read_text(encoding="utf-8")

    checks = [
        (
            "village_id: str | None = Query(None)",
            crop,
            "Crop suitability accepts village context",
        ),
        (
            "village_id: str | None = Query(None)",
            farmer,
            "Land intelligence accepts village context",
        ),
        (
            "resolve_effective_project_core_layers",
            crop,
            "Crop suitability uses effective Core resolver",
        ),
        (
            "resolve_effective_project_core_layers",
            farmer,
            "Land intelligence uses effective Core resolver",
        ),
        (
            "project_id is required when village_id is provided",
            crop,
            "Crop suitability rejects unscoped village context",
        ),
        (
            "project_id is required when village_id is provided",
            farmer,
            "Land intelligence rejects unscoped village context",
        ),
        (
            '"core_layer_resolution": core_layer_resolution',
            crop,
            "Crop suitability exposes resolution provenance",
        ),
        (
            '"core_layer_resolution": core_layer_resolution',
            farmer,
            "Land intelligence exposes resolution provenance",
        ),
        (
            "PROJECT_OVERRIDE_THEN_GLOBAL_FALLBACK",
            farmer,
            "Land intelligence declares precedence",
        ),
        (
            "mapping_query = db.query(GeographyClimateRegionMapping)",
            crop,
            "Crop suitability retains legacy global lookup",
        ),
        (
            "mapping_query = db.query(GeographyClimateRegionMapping)",
            farmer,
            "Land intelligence retains legacy global lookup",
        ),
    ]

    for needle, source, label in checks:
        if needle not in source:
            raise AssertionError(f"{label}: missing {needle!r}")
        print(f"PASS {label}")

    prohibited = [
        "insert into geography_core_layer_project_overrides",
        "update geography_core_layer_project_overrides",
        "delete from geography_core_layer_project_overrides",
    ]
    combined = (crop + "\n" + farmer).lower()
    for statement in prohibited:
        if statement in combined:
            raise AssertionError(
                f"Consumer read path contains prohibited mutation: {statement}"
            )

    print("PASS Consumer read paths contain no project override mutations")
    print("CORE LAYER PROJECT EFFECTIVE READ PATH STATIC CONTRACT PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Emit the planned CoRE polygon to LGD overlay workflow.

Plan-only and read-only: this script does not call Google Earth Engine,
download boundary files, run overlays, or write database rows.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

CORE_EXPORTS = [
    {
        "layer_name": "Agro-Ecological Zone",
        "region_system": "CORE_STACK_AGRO_ECOLOGICAL_ZONE",
        "gee_asset": "projects/ext-datasets/assets/datasets/Agro_Ecological_Zones",
        "class_property": "physio_reg",
        "expected_local_path": "data/staged/core_stack/exports/Agro_Ecological_Zones.geojson",
    },
    {
        "layer_name": "Agro-Climatic Zone",
        "region_system": "CORE_STACK_AGRO_CLIMATIC_ZONE",
        "gee_asset": "projects/ext-datasets/assets/datasets/Agro_Climatic_Zones",
        "class_property": "regionname",
        "expected_local_path": "data/staged/core_stack/exports/Agro_Climatic_Zones.geojson",
    },
    {
        "layer_name": "Biogeographic Zone",
        "region_system": "CORE_STACK_BIOGEOGRAPHIC_ZONE",
        "gee_asset": "projects/ext-datasets/assets/datasets/Biogeographic_Zone_pan_india",
        "class_property": "biogeozone",
        "expected_local_path": "data/staged/core_stack/exports/Biogeographic_Zone_pan_india.geojson",
    },
]

BOUNDARY_SOURCE_PRIORITY = [
    {
        "priority": 1,
        "source": "Survey of India / India Maps",
        "role": "preferred official district/sub-district/village boundary geometry",
        "local_staging_path": "data/staged/boundaries/soi/",
    },
    {
        "priority": 2,
        "source": "LGD Directory",
        "role": "canonical state/district/block/village codes and crosswalk validation",
        "local_staging_path": "data/staged/boundaries/lgd_directory/",
    },
    {
        "priority": 3,
        "source": "Open Government Data Admin Boundaries",
        "role": "secondary geometry candidate after schema/source review",
        "local_staging_path": "data/staged/boundaries/ogd/",
    },
]


def artifact(path: str) -> dict:
    full_path = ROOT / path
    return {
        "path": path,
        "exists": full_path.exists(),
        "absolute_path": str(full_path),
    }


def main() -> int:
    result = {
        "schema_version": "core_polygon_lgd_overlay_plan.v1",
        "mode": "PLAN_ONLY",
        "external_calls_made": False,
        "db_writes_made": False,
        "current_scope": "planning and readiness verification only",
        "existing_artifacts": [
            artifact("backend/scripts/audit_climate_polygon_overlay_readiness.py"),
            artifact("backend/scripts/import_core_stack_climate_regions.py"),
            artifact("docs/core-stack-gee-export-checklist.md"),
            artifact("docs/lgd-boundary-source-checklist.md"),
            artifact("docs/crop-climate-suitability-roadmap.md"),
        ],
        "required_core_exports": CORE_EXPORTS,
        "boundary_source_priority": BOUNDARY_SOURCE_PRIORITY,
        "overlay_phases": [
            {
                "phase": 0,
                "name": "Source and license review",
                "goal": "Record source URL, license/terms, file date, CRS, geometry level, and LGD-code compatibility before using any geometry.",
                "output": "review notes under data/staged/boundaries/review_notes/; not committed unless explicitly approved",
            },
            {
                "phase": 1,
                "name": "Local file validation",
                "goal": "Confirm CoRE GeoJSON exports and candidate LGD boundary files exist and are readable.",
                "output": "readiness report; no DB writes",
            },
            {
                "phase": 2,
                "name": "Geometry validation",
                "goal": "Validate CRS, geometry type, invalid/self-intersecting polygons, empty features, and class properties.",
                "output": "geometry QA report with rejected/repair-needed feature counts",
            },
            {
                "phase": 3,
                "name": "LGD crosswalk",
                "goal": "Map boundary attributes to canonical LGD state/district/block/village codes.",
                "output": "reviewed crosswalk candidates with unresolved names separated for manual review",
            },
            {
                "phase": 4,
                "name": "Overlay candidate generation",
                "goal": "Intersect administrative units with CoRE polygons and calculate dominant overlap by area.",
                "output": "candidate mappings; still MANUAL_REVIEW",
            },
            {
                "phase": 5,
                "name": "Reviewed mapping import",
                "goal": "Write approved rows into geography_climate_region_mappings without deleting existing fallback rows.",
                "output": "new mapping rows with polygon-derived confidence and source metadata",
            },
        ],
        "database_target": {
            "table": "geography_climate_region_mappings",
            "recommended_scope_order": ["PARCEL_POINT", "VILLAGE", "BLOCK", "DISTRICT"],
            "initial_confidence": "POLYGON_DERIVED_DISTRICT_OVERLAY_REVIEW",
            "initial_review_status": "MANUAL_REVIEW",
            "fallback_policy": "Keep LOCAL_DEMO_DISTRICT_FALLBACK rows until polygon-derived rows are reviewed and proven better for the same scope.",
        },
        "android_impact": {
            "android_calls_gee": False,
            "android_calls_boundary_sources": False,
            "maestro_required_now": False,
            "reason": "This planning/export/overlay work is backend-only until reviewed mappings change backend responses.",
            "later_android_test_trigger": "Run an existing land-intelligence/profile guidance check only after polygon-derived mappings are imported and /api/v1/profile/land-intelligence-context output changes for test locations.",
        },
        "next_commands": [
            "cd ~/projects/farmint/backend",
            "../venv/bin/python scripts/audit_climate_polygon_overlay_readiness.py",
            "../venv/bin/python scripts/plan_core_polygon_lgd_overlay.py",
            "../venv/bin/python scripts/verify_core_polygon_lgd_overlay_plan.py",
        ],
        "manual_next_actions": [
            "Export the three CoRE FeatureCollections from GEE to GeoJSON.",
            "Place exports under data/staged/core_stack/exports/.",
            "Obtain/review official or acceptable LGD-compatible boundary geometry.",
            "Do not commit large boundary/export files without explicit approval.",
        ],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

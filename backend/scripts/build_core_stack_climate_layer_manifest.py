#!/usr/bin/env python3
"""Build a clean CoRE Stack climate/geography layer manifest from raw CSV."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

CSV_PATH = Path(
    "/home/lynksavvy/projects/farmint/data/staged/core_stack/"
    "CoRE Stack GEE Layers Links - Datasets.csv"
)
OUT_DIR = Path("/home/lynksavvy/projects/farmint/data/staged/core_stack")
OUT_PATH = OUT_DIR / "core_stack_climate_layer_manifest.json"

LAYER_CONFIG = {
    "Agro-Ecological Zone": {
        "layer_type": "AGRO_ECOLOGICAL_ZONE",
        "region_system": "CORE_STACK_AGRO_ECOLOGICAL_ZONE",
        "class_property": "physio_reg",
        "recommended_internal_table": "geography_climate_regions",
    },
    "Agro-Climatic Zone": {
        "layer_type": "AGRO_CLIMATIC_ZONE",
        "region_system": "CORE_STACK_AGRO_CLIMATIC_ZONE",
        "class_property": "regionname",
        "recommended_internal_table": "geography_climate_regions",
    },
    "Biogeographic Zone": {
        "layer_type": "BIOGEOGRAPHIC_ZONE",
        "region_system": "CORE_STACK_BIOGEOGRAPHIC_ZONE",
        "class_property": "biogeozone",
        "recommended_internal_table": "geography_climate_regions",
    },
}


def extract_feature_collection_asset(code: str) -> str | None:
    """Extract ee.FeatureCollection asset ID, including multiline calls."""
    match = re.search(
        r"ee\.FeatureCollection\(\s*['\"]([^'\"]+)['\"]\s*\)",
        code or "",
        flags=re.S,
    )
    return match.group(1) if match else None


def extract_palette_keys(code: str) -> list[str]:
    keys = []
    for line in (code or "").splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        left = line.split(":", 1)[0].strip().strip(",")
        if (left.startswith("'") and left.endswith("'")) or (
            left.startswith('"') and left.endswith('"')
        ):
            keys.append(left[1:-1])
    return keys


def main() -> int:
    if not CSV_PATH.exists():
        raise SystemExit(f"Missing CSV: {CSV_PATH}")

    with CSV_PATH.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))

    layers = []
    for row_number, row in enumerate(rows, start=1):
        if not row:
            continue

        layer_name = (row[0] or "").strip()
        if layer_name not in LAYER_CONFIG:
            continue

        short_name = (row[1] or "").strip() if len(row) > 1 else ""
        code = row[2] if len(row) > 2 else ""
        display_name = (row[3] or "").strip() if len(row) > 3 else ""
        format_note = (row[4] or "").strip() if len(row) > 4 else ""
        style_name = (row[5] or "").strip() if len(row) > 5 else ""
        source_note = (row[6] or "").strip() if len(row) > 6 else ""

        config = LAYER_CONFIG[layer_name]
        layers.append(
            {
                "csv_row_number": row_number,
                "layer_name": layer_name,
                "short_name": short_name,
                "layer_type": config["layer_type"],
                "region_system": config["region_system"],
                "gee_asset_id": extract_feature_collection_asset(code),
                "class_property": config["class_property"],
                "display_name": display_name,
                "format_note": format_note,
                "style_name": style_name,
                "source_note": source_note,
                "palette_class_values": extract_palette_keys(code),
                "source_references": [
                    {
                        "source": "AIKOSH_CORE_STACK_DATASET",
                        "source_url": "https://aikosh.indiaai.gov.in/web/datasets/details/agro_ecological_climatic_and_biogeographic_zone.html",
                        "license": "CC BY 4.0 as displayed on Aikosh dataset page",
                        "source_role": "DISCOVERY_AND_LAYER_REFERENCE",
                    },
                    {
                        "source": "CORE_STACK_TECHNICAL_MANUAL_V2",
                        "source_url": "https://core-stack.org/core-stack-technical-manual-v2/",
                        "source_role": "METHODOLOGY_REFERENCE",
                    },
                    {
                        "source": "LOCAL_DOWNLOADED_CSV",
                        "source_path": str(CSV_PATH),
                        "source_role": "GEE_ASSET_LINK_REFERENCE",
                    },
                ],
            }
        )

    result = {
        "schema_version": "core_stack_climate_layer_manifest.v1",
        "csv_path": str(CSV_PATH),
        "layer_count": len(layers),
        "layers": layers,
        "integration_decision": {
            "use_as": "Reference/intelligence layer over LGD geography",
            "lgd_remains_canonical": True,
            "android_calls_gee": False,
            "current_mapping_level": "STATE_FALLBACK_ONLY",
            "reason_current_mapping_is_not_village_level": (
                "Current geography_villages rows for selected states have no "
                "latitude/longitude centroids."
            ),
            "next_mapping_options": [
                "Export CoRE polygons and intersect with official LGD/district/block/village boundaries.",
                "Use parcel GPS centroid at runtime once CoRE polygon geometries are available.",
                "Build district-level crosswalk manually or via spatial overlay as an interim improvement.",
            ],
        },
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))

    print(
        json.dumps(
            {
                "schema_version": "core_stack_climate_layer_manifest_write_result.v1",
                "output_path": str(OUT_PATH),
                "layer_count": len(layers),
                "layers": [
                    {
                        "layer_name": layer["layer_name"],
                        "gee_asset_id": layer["gee_asset_id"],
                        "class_property": layer["class_property"],
                        "class_count": len(layer["palette_class_values"]),
                    }
                    for layer in layers
                ],
            },
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
    )

    return 0 if len(layers) == 3 and all(layer["gee_asset_id"] for layer in layers) else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Import CoRE Stack climate/ecology region classes into geography_climate_regions.

Dry-run by default. Use --apply to write.

This imports region class metadata only. It does not map CoRE polygons to LGD
states/districts/villages. LGD mappings require polygon export or a reviewed
crosswalk.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
from app.modules.master_data.models import GeographyClimateRegion

DEFAULT_MANIFEST_PATH = (
    Path(__file__).resolve().parents[2]
    / "data/staged/core_stack/core_stack_climate_layer_manifest.json"
)


def now():
    return datetime.now(timezone.utc)


def slugify(value: str) -> str:
    value = value.upper()
    value = re.sub(r"[^A-Z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value[:120] or "UNKNOWN"


def region_code_for(layer: dict, class_value: str) -> str:
    system = layer["region_system"]
    prefix = {
        "CORE_STACK_AGRO_ECOLOGICAL_ZONE": "CORE_AEZ",
        "CORE_STACK_AGRO_CLIMATIC_ZONE": "CORE_ACZ",
        "CORE_STACK_BIOGEOGRAPHIC_ZONE": "CORE_BGZ",
    }.get(system, slugify(system))
    return f"{prefix}_{slugify(class_value)}"


def build_region_payload(layer: dict, class_value: str) -> dict:
    source_references = list(layer.get("source_references") or [])
    source_references.append(
        {
            "source": "CORE_STACK_GEE_LAYER_MANIFEST",
            "source_role": "CLASS_VALUE_REFERENCE",
            "gee_asset_id": layer.get("gee_asset_id"),
            "class_property": layer.get("class_property"),
            "layer_name": layer.get("layer_name"),
            "csv_row_number": layer.get("csv_row_number"),
        }
    )

    return {
        "region_code": region_code_for(layer, class_value),
        "region_name": class_value,
        "region_system": layer["region_system"],
        "country_code": "IND",
        "rainfall_band_mm": {},
        "temperature_band_c": {},
        "length_of_growing_period_days": {},
        "dominant_soil_groups": [],
        "irrigation_context": {},
        "source_references": source_references,
        "confidence": "CORE_STACK_CLASS_REFERENCE",
        "review_status": "MANUAL_REVIEW",
        "metadata_": {
            "source_layer_name": layer.get("layer_name"),
            "source_layer_type": layer.get("layer_type"),
            "source_short_name": layer.get("short_name"),
            "source_display_name": layer.get("display_name"),
            "source_format_note": layer.get("format_note"),
            "source_style_name": layer.get("style_name"),
            "source_note": layer.get("source_note"),
            "gee_asset_id": layer.get("gee_asset_id"),
            "class_property": layer.get("class_property"),
            "import_policy": "CLASS_METADATA_ONLY_NO_LGD_MAPPING",
        },
    }


def import_manifest(manifest_path: Path, apply: bool) -> dict:
    manifest = json.loads(manifest_path.read_text())
    result = {
        "schema_version": "core_stack_climate_region_import_result.v1",
        "mode": "APPLY" if apply else "DRY_RUN",
        "manifest_path": str(manifest_path),
        "layers_seen": 0,
        "classes_seen": 0,
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "skipped": 0,
        "by_region_system": {},
        "warnings": [
            "Class import only; LGD geography mappings are not created by this script.",
            "Rows remain MANUAL_REVIEW until source methodology and spatial overlay are reviewed.",
        ],
    }

    db = SessionLocal()
    try:
        for layer in manifest.get("layers", []):
            result["layers_seen"] += 1
            region_system = layer.get("region_system")
            class_values = layer.get("palette_class_values") or []
            if not region_system or not class_values:
                result["skipped"] += 1
                continue

            bucket = result["by_region_system"].setdefault(
                region_system,
                {"classes_seen": 0, "created": 0, "updated": 0, "unchanged": 0},
            )

            for class_value in class_values:
                result["classes_seen"] += 1
                bucket["classes_seen"] += 1

                payload = build_region_payload(layer, class_value)
                existing = (
                    db.query(GeographyClimateRegion)
                    .filter(GeographyClimateRegion.region_code == payload["region_code"])
                    .first()
                )

                if not existing:
                    result["created"] += 1
                    bucket["created"] += 1
                    if apply:
                        row = GeographyClimateRegion(
                            id=uuid.uuid4(),
                            is_active=True,
                            created_at=now(),
                            updated_at=now(),
                            **payload,
                        )
                        db.add(row)
                    continue

                changed = False
                for key, value in payload.items():
                    if getattr(existing, key) != value:
                        changed = True
                        if apply:
                            setattr(existing, key, value)

                if changed:
                    result["updated"] += 1
                    bucket["updated"] += 1
                    if apply:
                        existing.updated_at = now()
                else:
                    result["unchanged"] += 1
                    bucket["unchanged"] += 1

        if apply:
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()

    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest-path", default=str(DEFAULT_MANIFEST_PATH))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    manifest_path = Path(args.manifest_path)
    if not manifest_path.exists():
        raise SystemExit(f"Manifest not found: {manifest_path}")

    result = import_manifest(manifest_path, args.apply)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["classes_seen"] >= 45 else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Audit readiness for CoRE Stack polygon to LGD geography overlay.

Read-only. Reports whether local DB/assets can support polygon-derived
climate/ecology mappings beyond approximate district fallback.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, text
from app.core.database import SessionLocal
from app.modules.master_data.models import (
    GeographyBlock,
    GeographyClimateRegion,
    GeographyClimateRegionMapping,
    GeographyDistrict,
    GeographyState,
    GeographyVillage,
)

ROOT = Path(__file__).resolve().parents[2]
CORE_STACK = ROOT / "data/staged/core_stack"

EXPECTED_CORE_EXPORTS = [
    (
        "Agro-Ecological Zone",
        "CORE_STACK_AGRO_ECOLOGICAL_ZONE",
        ["Agro_Ecological_Zones.geojson", "Agro_Ecological_Zones.shp", "AEZs.geojson"],
    ),
    (
        "Agro-Climatic Zone",
        "CORE_STACK_AGRO_CLIMATIC_ZONE",
        ["Agro_Climatic_Zones.geojson", "Agro_Climatic_Zones.shp", "ACZs.geojson"],
    ),
    (
        "Biogeographic Zone",
        "CORE_STACK_BIOGEOGRAPHIC_ZONE",
        ["Biogeographic_Zone_pan_india.geojson", "Biogeographic_Zone_pan_india.shp", "Biogeographic.geojson"],
    ),
]

SELECTED_STATES = {
    "27": "Maharashtra",
    "29": "Karnataka",
    "9": "Uttar Pradesh",
    "3": "Punjab",
    "19": "West Bengal",
}


def existing_export_paths(names: list[str]) -> list[str]:
    paths = []
    for name in names:
        for path in (CORE_STACK / name, CORE_STACK / "exports" / name):
            if path.exists():
                paths.append(str(path))
    return paths


def not_null_count(db, model, column) -> int:
    return db.query(model).filter(column.isnot(None)).count()


def table_columns(db, table_name: str) -> set[str]:
    rows = db.execute(
        text("""
            select column_name
            from information_schema.columns
            where table_name = :table_name
        """),
        {"table_name": table_name},
    ).all()
    return {row[0] for row in rows}


def village_point_columns(db) -> tuple[str | None, str | None]:
    columns = table_columns(db, "geography_villages")
    lat_candidates = ["centroid_lat", "latitude", "lat"]
    lng_candidates = ["centroid_lng", "longitude", "lng", "lon"]
    lat_col = next((col for col in lat_candidates if col in columns), None)
    lng_col = next((col for col in lng_candidates if col in columns), None)
    return lat_col, lng_col


def selected_state_village_points(db) -> dict:
    lat_col, lng_col = village_point_columns(db)

    if not lat_col or not lng_col:
        rows = (
            db.query(GeographyState.lgd_code, func.count(GeographyVillage.id))
            .join(GeographyDistrict, GeographyDistrict.state_id == GeographyState.id)
            .join(GeographyBlock, GeographyBlock.district_id == GeographyDistrict.id)
            .join(GeographyVillage, GeographyVillage.block_id == GeographyBlock.id)
            .filter(GeographyState.lgd_code.in_(SELECTED_STATES.keys()))
            .group_by(GeographyState.lgd_code)
            .order_by(GeographyState.lgd_code)
            .all()
        )
        return {
            state_lgd_code: {
                "state_name": SELECTED_STATES.get(state_lgd_code),
                "villages": int(villages),
                "villages_with_lat": 0,
                "villages_with_lng": 0,
                "villages_with_usable_point": 0,
                "point_columns_present": False,
            }
            for state_lgd_code, villages in rows
        }

    rows = db.execute(
        text(f"""
            select
              s.lgd_code as state_lgd_code,
              count(v.id) as villages,
              count(v.{lat_col}) as villages_with_lat,
              count(v.{lng_col}) as villages_with_lng
            from geography_villages v
            join geography_blocks b on b.id = v.block_id
            join geography_districts d on d.id = b.district_id
            join geography_states s on s.id = d.state_id
            where s.lgd_code = any(:state_codes)
            group by s.lgd_code
            order by s.lgd_code
        """),
        {"state_codes": list(SELECTED_STATES.keys())},
    ).mappings().all()

    result = {}
    for row in rows:
        lat_count = int(row["villages_with_lat"])
        lng_count = int(row["villages_with_lng"])
        state_lgd_code = row["state_lgd_code"]
        result[state_lgd_code] = {
            "state_name": SELECTED_STATES.get(state_lgd_code),
            "villages": int(row["villages"]),
            "villages_with_lat": lat_count,
            "villages_with_lng": lng_count,
            "villages_with_usable_point": min(lat_count, lng_count),
            "point_columns_present": True,
        }
    return result


def main() -> int:
    db = SessionLocal()
    try:
        core_exports = []
        for layer_name, region_system, expected_names in EXPECTED_CORE_EXPORTS:
            paths = existing_export_paths(expected_names)
            class_count = (
                db.query(GeographyClimateRegion)
                .filter(
                    GeographyClimateRegion.region_system == region_system,
                    GeographyClimateRegion.is_active == True,
                )
                .count()
            )
            core_exports.append(
                {
                    "layer_name": layer_name,
                    "region_system": region_system,
                    "class_metadata_rows": class_count,
                    "expected_local_filenames": expected_names,
                    "local_export_found": bool(paths),
                    "local_export_paths": paths,
                }
            )

        mapping_rows = (
            db.query(
                GeographyClimateRegionMapping.scope_level,
                GeographyClimateRegionMapping.confidence,
                GeographyClimateRegionMapping.review_status,
                func.count(GeographyClimateRegionMapping.id),
            )
            .group_by(
                GeographyClimateRegionMapping.scope_level,
                GeographyClimateRegionMapping.confidence,
                GeographyClimateRegionMapping.review_status,
            )
            .order_by(GeographyClimateRegionMapping.scope_level)
            .all()
        )

        mapping_counts = [
            {
                "scope_level": scope_level,
                "confidence": confidence,
                "review_status": review_status,
                "count": int(count),
            }
            for scope_level, confidence, review_status, count in mapping_rows
        ]

        lat_col, lng_col = village_point_columns(db)
        geography_counts = {
            "states": db.query(GeographyState).count(),
            "states_with_lgd_code": not_null_count(db, GeographyState, GeographyState.lgd_code),
            "districts": db.query(GeographyDistrict).count(),
            "districts_with_lgd_code": not_null_count(db, GeographyDistrict, GeographyDistrict.lgd_code),
            "blocks": db.query(GeographyBlock).count(),
            "villages": db.query(GeographyVillage).count(),
            "village_point_lat_column": lat_col,
            "village_point_lng_column": lng_col,
            "villages_with_centroid_lat": 0,
            "villages_with_centroid_lng": 0,
        }
        if lat_col and lng_col:
            point_counts = db.execute(
                text(f"select count({lat_col}) as lat_count, count({lng_col}) as lng_count from geography_villages")
            ).mappings().first()
            geography_counts["villages_with_centroid_lat"] = int(point_counts["lat_count"])
            geography_counts["villages_with_centroid_lng"] = int(point_counts["lng_count"])

        all_core_exports_found = all(item["local_export_found"] for item in core_exports)
        has_village_points = (
            geography_counts["villages_with_centroid_lat"] > 0
            and geography_counts["villages_with_centroid_lng"] > 0
        )
        has_district_fallback = any(
            row["scope_level"] == "DISTRICT"
            and row["confidence"] == "LOCAL_DEMO_DISTRICT_FALLBACK"
            and row["count"] > 0
            for row in mapping_counts
        )

        readiness = {
            "core_class_metadata_ready": all(item["class_metadata_rows"] > 0 for item in core_exports),
            "core_polygon_exports_ready": all_core_exports_found,
            "lgd_state_district_reference_ready": (
                geography_counts["states_with_lgd_code"] > 0
                and geography_counts["districts_with_lgd_code"] > 0
            ),
            "district_fallback_ready": has_district_fallback,
            "village_point_overlay_ready": has_village_points,
            "ready_for_polygon_overlay": all_core_exports_found
            and geography_counts["districts_with_lgd_code"] > 0,
            "ready_for_village_centroid_overlay": all_core_exports_found and has_village_points,
        }

        result = {
            "schema_version": "climate_polygon_overlay_readiness_audit.v1",
            "core_stack_dir": str(CORE_STACK),
            "core_exports": core_exports,
            "geography_counts": geography_counts,
            "selected_state_village_points": selected_state_village_points(db),
            "mapping_counts": mapping_counts,
            "readiness": readiness,
            "next_actions": [
                "Export CoRE AEZ/ACZ/Biogeographic geometries from GEE into data/staged/core_stack/exports/.",
                "Add or locate official LGD district/block/village boundary geometries for overlay.",
                "Use district fallback only as approximate demo intelligence until polygon-derived mappings are available.",
                "Do not call GEE or external map APIs from Android.",
            ],
        }
    finally:
        db.close()

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["readiness"]["core_class_metadata_ready"] and result["readiness"]["district_fallback_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

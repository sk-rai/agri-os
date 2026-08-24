#!/usr/bin/env python3
"""Guarded staging geometry materializer for NWDP pilot rows.

Default mode is dry-run. With --apply, updates only inactive staging source
feature geometry audit fields for a small direct-code pilot subset.

It does not write runtime tables, promote candidates, activate candidates,
enable lookup, or change Android behavior.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DEFAULT_SHP_ZIP = Path("/tmp/nwdp-karnataka-village-boundary-shp.zip")
DEFAULT_OUTPUT = Path("/tmp/nwdp-boundary-pilot-geometry-materializer.json")


def db_url_from_settings() -> str:
    from app.core.config import settings

    value = (
        getattr(settings, "database_url", None)
        or getattr(settings, "DATABASE_URL", None)
        or getattr(settings, "sqlalchemy_database_uri", None)
        or getattr(settings, "SQLALCHEMY_DATABASE_URI", None)
        or getattr(settings, "postgres_url", None)
        or getattr(settings, "POSTGRES_URL", None)
    )
    return str(value or "postgresql+psycopg2://agri_os:agri_os_dev@localhost:5432/agri_os")


def json_default(value: Any) -> str:
    return str(value)


def round_value(value: float | None, places: int = 6) -> float | None:
    return None if value is None else round(float(value), places)


def extract_selected_shp(zip_path: Path) -> tuple[tempfile.TemporaryDirectory, Path, Path | None]:
    tmp = tempfile.TemporaryDirectory(prefix="nwdp-pilot-geom-apply-")
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(tmp.name)
    root = Path(tmp.name)
    shp_files = sorted(root.rglob("*.shp"))
    prj_files = sorted(root.rglob("*.prj"))
    if not shp_files:
        raise SystemExit(f"SHP_ZIP_HAS_NO_SHP: {zip_path}")
    selected = next((p for p in shp_files if "village" in p.name.lower()), shp_files[0])
    selected_prj = prj_files[0] if prj_files else None
    return tmp, selected, selected_prj


def shape_hash(shape: Any) -> str:
    payload = {
        "shapeType": getattr(shape, "shapeType", None),
        "bbox": list(getattr(shape, "bbox", []) or []),
        "parts": list(getattr(shape, "parts", []) or []),
        "points": list(getattr(shape, "points", []) or []),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def transformed_bbox(transformer: Any, bbox: list[float]) -> dict[str, Any]:
    min_x, min_y, max_x, max_y = [float(value) for value in bbox]
    corners = [(min_x, min_y), (min_x, max_y), (max_x, min_y), (max_x, max_y)]
    wgs84 = []
    for x, y in corners:
        lon, lat = transformer.transform(x, y)
        wgs84.append({"lon": round_value(lon), "lat": round_value(lat)})
    lons = [p["lon"] for p in wgs84 if p["lon"] is not None]
    lats = [p["lat"] for p in wgs84 if p["lat"] is not None]
    return {
        "raw_bbox": [round_value(value, 3) for value in bbox],
        "corner_points_wgs84": wgs84,
        "corner_bbox_wgs84": [min(lons), min(lats), max(lons), max(lats)] if lons and lats else None,
        "all_corners_inside_karnataka_buffer": all(
            73.0 <= p["lon"] <= 79.5 and 10.5 <= p["lat"] <= 19.5
            for p in wgs84
            if p["lon"] is not None and p["lat"] is not None
        ),
    }


def transformed_centroid(transformer: Any, bbox: list[float]) -> dict[str, Any]:
    min_x, min_y, max_x, max_y = [float(value) for value in bbox]
    lon, lat = transformer.transform((min_x + max_x) / 2.0, (min_y + max_y) / 2.0)
    return {
        "lon": round_value(lon),
        "lat": round_value(lat),
        "method": "bbox_center",
        "inside_karnataka_buffer": 73.0 <= lon <= 79.5 and 10.5 <= lat <= 19.5,
    }


def selected_rows(conn, limit: int) -> list[dict[str, Any]]:
    from sqlalchemy import text

    return [dict(row) for row in conn.execute(text("""
        select
          c.id::text as candidate_id,
          c.source_feature_id::text,
          c.source_feature_index,
          f.source_village_name,
          f.source_vlcode,
          f.source_geometry_hash,
          f.transformed_bbox,
          f.transformed_centroid,
          f.geometry_validation_status
        from geography_boundary_crosswalk_candidates c
        join geography_boundary_source_features f on f.id = c.source_feature_id
        join geography_boundary_import_batches b on b.id = c.import_batch_id
        where b.state_or_ut = 'Karnataka'
          and b.source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
          and c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
          and c.is_active = false
          and c.promotion_status = 'NOT_PROMOTED'
          and c.proposed_scope in ('village', 'village_review')
        order by f.source_district_name, f.source_subdistrict_name, c.source_feature_index
        limit :limit
    """), {"limit": limit}).mappings().all()]


def runtime_counts(conn) -> dict[str, int]:
    from sqlalchemy import text

    tables = [
        "geography_boundary_runtime_sets",
        "geography_boundary_runtime_features",
        "geography_boundary_runtime_crosswalks",
        "geography_boundary_runtime_promotion_events",
    ]
    return {table: int(conn.execute(text(f"select count(*) from {table}")).scalar() or 0) for table in tables}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shp-zip", type=Path, default=DEFAULT_SHP_ZIP)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if not args.shp_zip.exists():
        report = {"schema_version": "nwdp_boundary_pilot_geometry_materializer.v1", "healthy": False, "error": "SHP_ZIP_NOT_FOUND", "path": str(args.shp_zip)}
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 1

    import pyproj
    import shapefile
    from sqlalchemy import create_engine, text

    tmp, shp_path, prj_path = extract_selected_shp(args.shp_zip)
    try:
        prj_text = prj_path.read_text(encoding="utf-8", errors="replace") if prj_path else ""
        source_crs = pyproj.CRS.from_wkt(prj_text) if prj_text else pyproj.CRS.from_epsg(7755)
        transformer = pyproj.Transformer.from_crs(source_crs, pyproj.CRS.from_epsg(4326), always_xy=True)
        reader = shapefile.Reader(str(shp_path))

        engine = create_engine(db_url_from_settings())
        with engine.begin() as conn:
            before_runtime = runtime_counts(conn)
            rows = selected_rows(conn, args.limit)
            planned = []
            updates = 0

            for row in rows:
                shape = reader.shape(int(row["source_feature_index"]))
                bbox = list(shape.bbox)
                source_hash = shape_hash(shape)
                bbox_wgs84 = transformed_bbox(transformer, bbox)
                centroid_wgs84 = transformed_centroid(transformer, bbox)
                valid = bool(bbox_wgs84.get("all_corners_inside_karnataka_buffer") and centroid_wgs84.get("inside_karnataka_buffer"))
                validation_status = "VALIDATED" if valid else "VALIDATION_REVIEW"

                planned.append({
                    **row,
                    "planned_source_geometry_hash": source_hash,
                    "planned_transformed_bbox": bbox_wgs84,
                    "planned_transformed_centroid": centroid_wgs84,
                    "planned_geometry_validation_status": validation_status,
                    "staging_update_planned": True,
                    "runtime_write_planned": False,
                })

                if args.apply:
                    conn.execute(text("""
                        update geography_boundary_source_features
                        set
                          source_geometry_hash = :source_geometry_hash,
                          source_bbox = cast(:source_bbox as jsonb),
                          transformed_bbox = cast(:transformed_bbox as jsonb),
                          transformed_centroid = cast(:transformed_centroid as jsonb),
                          geometry_validation_status = :geometry_validation_status,
                          metadata = coalesce(metadata, '{}'::jsonb) || cast(:metadata as jsonb),
                          updated_at = now()
                        where id = :source_feature_id
                          and is_active = false
                    """), {
                        "source_feature_id": row["source_feature_id"],
                        "source_geometry_hash": source_hash,
                        "source_bbox": json.dumps([round_value(value, 3) for value in bbox]),
                        "transformed_bbox": json.dumps(bbox_wgs84),
                        "transformed_centroid": json.dumps(centroid_wgs84),
                        "geometry_validation_status": validation_status,
                        "metadata": json.dumps({
                            "pilot_geometry_materialized_at": datetime.now(timezone.utc).isoformat(),
                            "pilot_geometry_materializer": "materialize_nwdp_boundary_pilot_geometry.py",
                            "runtime_write_planned": False,
                        }),
                    })
                    updates += 1

            after_runtime = runtime_counts(conn)

        report = {
            "schema_version": "nwdp_boundary_pilot_geometry_materializer.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "healthy": bool(planned),
            "apply_mode": bool(args.apply),
            "db_writes_attempted": bool(args.apply),
            "staging_rows_updated": updates,
            "runtime_tables_written": False,
            "runtime_rows_effective": 0,
            "runtime_counts_before": before_runtime,
            "runtime_counts_after": after_runtime,
            "runtime_spatial_matching_changed": False,
            "android_behavior_changed": False,
            "summary": {
                "selected_candidate_count": len(rows),
                "planned_staging_geometry_update_count": len(planned),
                "validated_geometry_count": sum(1 for item in planned if item["planned_geometry_validation_status"] == "VALIDATED"),
                "runtime_write_count": 0,
            },
            "items": planned,
        }
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
        return 0 if report["healthy"] else 1
    finally:
        tmp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())

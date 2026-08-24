#!/usr/bin/env python3
"""Read-only NWDP pilot geometry materialization planner.

Inspects the source SHP zip and selected direct-code pilot staging rows.
Does not update staging rows, runtime rows, lookup APIs, or Android behavior.
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
DEFAULT_OUTPUT = Path("/tmp/nwdp-boundary-pilot-geometry-materialization-plan.json")


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


def dependency_check() -> dict[str, Any]:
    result = {}
    for module in ["shapefile", "pyproj"]:
        try:
            __import__(module)
            result[module] = True
        except Exception as exc:
            result[module] = {"available": False, "error": str(exc)}
    return result


def extract_selected_shp(zip_path: Path) -> tuple[tempfile.TemporaryDirectory, Path]:
    tmp = tempfile.TemporaryDirectory(prefix="nwdp-pilot-geom-")
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(tmp.name)
    shp_files = sorted(Path(tmp.name).rglob("*.shp"))
    if not shp_files:
        raise SystemExit(f"SHP_ZIP_HAS_NO_SHP: {zip_path}")
    selected = next((p for p in shp_files if "village" in p.name.lower()), shp_files[0])
    return tmp, selected


def transform_bbox(bbox: list[float]) -> dict[str, Any]:
    try:
        from pyproj import Transformer
        transformer = Transformer.from_crs("EPSG:7755", "EPSG:4326", always_xy=True)
        xmin, ymin, xmax, ymax = bbox
        points = [
            transformer.transform(xmin, ymin),
            transformer.transform(xmin, ymax),
            transformer.transform(xmax, ymin),
            transformer.transform(xmax, ymax),
        ]
        lons = [p[0] for p in points]
        lats = [p[1] for p in points]
        return {
            "min_lon": min(lons),
            "min_lat": min(lats),
            "max_lon": max(lons),
            "max_lat": max(lats),
            "healthy": all(68 <= lon <= 98 for lon in lons) and all(6 <= lat <= 38 for lat in lats),
        }
    except Exception as exc:
        return {"healthy": False, "error": type(exc).__name__, "message": str(exc)}


def shape_hash(shape: Any) -> str:
    payload = {
        "shapeType": getattr(shape, "shapeType", None),
        "bbox": list(getattr(shape, "bbox", []) or []),
        "parts": list(getattr(shape, "parts", []) or []),
        "points": list(getattr(shape, "points", []) or []),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def pilot_rows(limit: int) -> list[dict[str, Any]]:
    from sqlalchemy import create_engine, text

    engine = create_engine(db_url_from_settings())
    with engine.connect() as conn:
        return [dict(row) for row in conn.execute(text("""
            select
              c.id::text as candidate_id,
              c.source_feature_index,
              f.source_village_name,
              f.source_vlcode,
              f.source_geometry_hash as staged_source_geometry_hash,
              f.transformed_bbox as staged_transformed_bbox,
              f.transformed_centroid as staged_transformed_centroid,
              f.geometry_validation_status as staged_geometry_validation_status
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shp-zip", type=Path, default=DEFAULT_SHP_ZIP)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    deps = dependency_check()
    if not args.shp_zip.exists():
        report = {
            "schema_version": "nwdp_boundary_pilot_geometry_materialization_plan.v1",
            "healthy": False,
            "error": "SHP_ZIP_NOT_FOUND",
            "path": str(args.shp_zip),
            "db_writes_attempted": False,
            "runtime_tables_written": False,
        }
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 1

    rows = pilot_rows(args.limit)
    tmp, shp_path = extract_selected_shp(args.shp_zip)
    try:
        import shapefile
        reader = shapefile.Reader(str(shp_path))
        items = []
        for row in rows:
            idx = int(row["source_feature_index"])
            shape = reader.shape(idx)
            raw_bbox = list(shape.bbox)
            materialized_hash = shape_hash(shape)
            materialized_bbox = transform_bbox(raw_bbox)
            items.append({
                **row,
                "materialized_source_geometry_hash": materialized_hash,
                "materialized_source_bbox": raw_bbox,
                "materialized_transformed_bbox": materialized_bbox,
                "geometry_payload_available": True,
                "staging_update_allowed_now": False,
                "runtime_write_allowed_now": False,
                "required_next_actions": [
                    "review materialized geometry hash/bbox",
                    "apply separate staging geometry materialization checkpoint",
                    "run geometry validation before runtime promotion",
                ],
            })
    finally:
        tmp.cleanup()

    report = {
        "schema_version": "nwdp_boundary_pilot_geometry_materialization_plan.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": bool(items),
        "mode": "READ_ONLY_GEOMETRY_MATERIALIZATION_PLAN",
        "dependency_check": deps,
        "source": {
            "shp_zip": str(args.shp_zip),
            "selected_candidate_count": len(rows),
        },
        "summary": {
            "geometry_payload_available_count": sum(1 for item in items if item["geometry_payload_available"]),
            "staging_rows_to_update_now": 0,
            "runtime_rows_to_write_now": 0,
            "requires_separate_apply_checkpoint": True,
        },
        "items": items,
        "db_writes_attempted": False,
        "runtime_tables_written": False,
        "runtime_spatial_matching_changed": False,
        "android_behavior_changed": False,
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, default=json_default), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True, default=json_default))
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

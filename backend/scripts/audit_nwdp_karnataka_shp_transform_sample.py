#!/usr/bin/env python3
"""Read-only transform sample audit for NWDP/GSI Karnataka village-boundary SHP."""

from __future__ import annotations

import argparse
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_ZIP = Path("/tmp/nwdp-karnataka-village-boundary-shp.zip")
DEFAULT_EXTRACT_DIR = Path("/tmp/nwdp-karnataka-shp-transform-sample")
DEFAULT_OUTPUT = Path("/tmp/nwdp-karnataka-boundary-shp-transform-sample.json")

KARNATAKA_BOUNDS_WGS84_BUFFERED = {
    "min_lon": 73.0,
    "max_lon": 79.5,
    "min_lat": 10.5,
    "max_lat": 19.5,
}


def round_value(value: float | None, places: int = 6) -> float | None:
    return None if value is None else round(float(value), places)


def inside_karnataka_buffer(lon: float, lat: float) -> bool:
    bounds = KARNATAKA_BOUNDS_WGS84_BUFFERED
    return (
        bounds["min_lon"] <= lon <= bounds["max_lon"]
        and bounds["min_lat"] <= lat <= bounds["max_lat"]
    )


def extract_zip(zip_path: Path, extract_dir: Path) -> dict[str, Any]:
    extract_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path) as archive:
        members = archive.namelist()
        archive.extractall(extract_dir)

    shp_files = sorted(extract_dir.rglob("*.shp"))
    prj_files = sorted(extract_dir.rglob("*.prj"))

    return {
        "members": members,
        "extract_dir": str(extract_dir),
        "shp_files": [str(path) for path in shp_files],
        "prj_files": [str(path) for path in prj_files],
        "selected_shp": str(shp_files[0]) if shp_files else None,
        "selected_prj": str(prj_files[0]) if prj_files else None,
    }

def transform_bbox(transformer: Any, bbox: list[float]) -> dict[str, Any]:
    min_x, min_y, max_x, max_y = [float(value) for value in bbox]
    corners_raw = [
        (min_x, min_y),
        (min_x, max_y),
        (max_x, min_y),
        (max_x, max_y),
    ]

    corners_wgs84 = []
    for x, y in corners_raw:
        lon, lat = transformer.transform(x, y)
        corners_wgs84.append({"lon": round_value(lon), "lat": round_value(lat)})

    lons = [point["lon"] for point in corners_wgs84 if point["lon"] is not None]
    lats = [point["lat"] for point in corners_wgs84 if point["lat"] is not None]

    return {
        "raw_bbox": [round_value(value, 3) for value in bbox],
        "corner_points_wgs84": corners_wgs84,
        "corner_bbox_wgs84": [min(lons), min(lats), max(lons), max(lats)] if lons and lats else None,
        "all_corners_inside_karnataka_buffer": all(
            inside_karnataka_buffer(point["lon"], point["lat"])
            for point in corners_wgs84
            if point["lon"] is not None and point["lat"] is not None
        ),
    }


def run_audit(zip_path: Path, extract_dir: Path, sample_limit: int) -> dict[str, Any]:
    try:
        import pyproj
    except Exception as exc:
        return {"healthy": False, "error": "PYPROJ_NOT_AVAILABLE", "message": str(exc)}

    try:
        import shapefile
    except Exception as exc:
        return {"healthy": False, "error": "PYSHAPEFILE_NOT_AVAILABLE", "message": str(exc)}

    if not zip_path.exists():
        return {"healthy": False, "error": "SHP_ZIP_NOT_FOUND", "path": str(zip_path)}

    extracted = extract_zip(zip_path, extract_dir)
    if not extracted.get("selected_shp") or not extracted.get("selected_prj"):
        return {"healthy": False, "error": "SHP_OR_PRJ_NOT_FOUND", "extracted": extracted}

    prj_text = Path(str(extracted["selected_prj"])).read_text(encoding="utf-8", errors="replace").strip()

    crs = pyproj.CRS.from_wkt(prj_text)
    transformer = pyproj.Transformer.from_crs(crs, pyproj.CRS.from_epsg(4326), always_xy=True)

    reader = shapefile.Reader(str(extracted["selected_shp"]))
    fields = [field[0] for field in reader.fields[1:]]
    dataset_bbox_transform = transform_bbox(transformer, list(reader.bbox))

    samples = []
    inside_count = 0
    outside_count = 0

    for index, shape_record in enumerate(reader.iterShapeRecords()):
        if index >= sample_limit:
            break

        shape = shape_record.shape
        record = shape_record.record.as_dict()
        bbox = list(shape.bbox)
        min_x, min_y, max_x, max_y = [float(value) for value in bbox]
        center_x = (min_x + max_x) / 2.0
        center_y = (min_y + max_y) / 2.0
        lon, lat = transformer.transform(center_x, center_y)
        inside = inside_karnataka_buffer(lon, lat)

        if inside:
            inside_count += 1
        else:
            outside_count += 1

        samples.append({
            "index": index,
            "village": str(record.get("village") or "").strip(),
            "district": str(record.get("district") or "").strip(),
            "subdistrict": str(record.get("subdistric") or "").strip(),
            "vlcode": str(record.get("vlcode") or "").strip(),
            "raw_bbox": [round_value(value, 3) for value in bbox],
            "center_wgs84": {"lon": round_value(lon), "lat": round_value(lat)},
            "center_inside_karnataka_buffer": inside,
        })

    return {
        "healthy": True,
        "pyproj_version": pyproj.__version__,
        "shapefile_record_count": len(reader),
        "shape_type": reader.shapeTypeName,
        "field_count": len(fields),
        "fields": fields,
        "source_crs": {
            "name": crs.name,
            "is_projected": crs.is_projected,
            "is_geographic": crs.is_geographic,
            "linear_units": str(crs.axis_info[0].unit_name) if crs.axis_info else None,
            "to_authority": crs.to_authority(),
            "to_epsg": crs.to_epsg(),
        },
        "target_crs": "EPSG:4326",
        "dataset_bbox_transform": dataset_bbox_transform,
        "sample_limit": sample_limit,
        "sample_count": len(samples),
        "sample_centers_inside_karnataka_buffer": inside_count,
        "sample_centers_outside_karnataka_buffer": outside_count,
        "samples": samples,
        "extracted": extracted,
    }

def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only transform sample audit for NWDP Karnataka village-boundary SHP.")
    parser.add_argument("--zip-path", default=str(DEFAULT_ZIP), help="Path to Karnataka SHP ZIP from CRS audit.")
    parser.add_argument("--extract-dir", default=str(DEFAULT_EXTRACT_DIR), help="Temporary extraction directory.")
    parser.add_argument("--sample-limit", type=int, default=25)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    audit = run_audit(Path(args.zip_path), Path(args.extract_dir), args.sample_limit)

    result = {
        "schema_version": "nwdp_karnataka_shp_transform_sample_audit.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "portal": "National Water Data Portal",
            "dataset": "Village Boundary",
            "producer_agency": "Geological Survey of India",
            "state_or_ut": "Karnataka",
            "format": "SHP",
        },
        "claim_boundary": "Transform sample audit validates CRS parsing and sample coordinate plausibility only; it does not ingest geometry or authorize runtime spatial matching.",
        "audit": audit,
        "readiness": {
            "safe_read_only": True,
            "db_writes_attempted": False,
            "ready_for_transform_planning": bool(audit.get("healthy")),
            "ready_for_runtime_spatial_matching": False,
        },
        "next_actions": [
            "If sample centers are plausible, run a larger transform and topology audit before ingestion planning.",
            "Keep village-code crosswalk review separate from CRS transformation readiness.",
            "Do not use transformed boundaries for runtime point-in-polygon until geometry validity and crosswalk policy are reviewed.",
        ],
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

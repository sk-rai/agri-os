#!/usr/bin/env python3
"""Read-only geometry/topology audit for NWDP/GSI Karnataka village-boundary SHP."""

from __future__ import annotations

import argparse
import json
import math
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_ZIP = Path("/tmp/nwdp-karnataka-village-boundary-shp.zip")
DEFAULT_EXTRACT_DIR = Path("/tmp/nwdp-karnataka-shp-geometry-topology")
DEFAULT_OUTPUT = Path("/tmp/nwdp-karnataka-boundary-shp-geometry-topology.json")

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
        "selected_shp": str(shp_files[0]) if shp_files else None,
        "selected_prj": str(prj_files[0]) if prj_files else None,
    }


def quantile(sorted_values: list[float], q: float) -> float | None:
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = (len(sorted_values) - 1) * q
    lower = math.floor(pos)
    upper = math.ceil(pos)
    if lower == upper:
        return sorted_values[int(pos)]
    weight = pos - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight

def signed_ring_area(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    area = 0.0
    for index in range(len(points)):
        x1, y1 = points[index]
        x2, y2 = points[(index + 1) % len(points)]
        area += x1 * y2 - x2 * y1
    return area / 2.0


def transformed_bbox(transformer: Any, bbox: list[float]) -> dict[str, Any]:
    min_x, min_y, max_x, max_y = [float(value) for value in bbox]
    corners = [
        (min_x, min_y),
        (min_x, max_y),
        (max_x, min_y),
        (max_x, max_y),
    ]
    wgs84 = []
    for x, y in corners:
        lon, lat = transformer.transform(x, y)
        wgs84.append({"lon": round_value(lon), "lat": round_value(lat)})
    lons = [point["lon"] for point in wgs84 if point["lon"] is not None]
    lats = [point["lat"] for point in wgs84 if point["lat"] is not None]
    return {
        "raw_bbox": [round_value(value, 3) for value in bbox],
        "corner_points_wgs84": wgs84,
        "corner_bbox_wgs84": [min(lons), min(lats), max(lons), max(lats)] if lons and lats else None,
        "all_corners_inside_karnataka_buffer": all(
            inside_karnataka_buffer(point["lon"], point["lat"])
            for point in wgs84
            if point["lon"] is not None and point["lat"] is not None
        ),
    }


def shape_area_and_parts(shape: Any) -> dict[str, Any]:
    points = [(float(x), float(y)) for x, y in shape.points]
    part_starts = list(shape.parts) + [len(points)]
    part_areas = []

    for index in range(len(part_starts) - 1):
        start = part_starts[index]
        end = part_starts[index + 1]
        ring = points[start:end]
        part_areas.append(signed_ring_area(ring))

    gross_area = sum(abs(value) for value in part_areas)
    net_signed_area = sum(part_areas)

    return {
        "point_count": len(points),
        "part_count": max(0, len(part_starts) - 1),
        "gross_area_projected_sq_m": gross_area,
        "net_signed_area_projected_sq_m": net_signed_area,
        "has_zero_area": gross_area <= 0,
    }

def run_audit(zip_path: Path, extract_dir: Path, sample_limit: int, district_sample_limit: int) -> dict[str, Any]:
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
    dataset_bbox = transformed_bbox(transformer, list(reader.bbox))

    shape_type_counts = Counter()
    district_counts = Counter()
    district_inside_counts = Counter()
    district_samples: dict[str, list[dict[str, Any]]] = defaultdict(list)

    zero_area_count = 0
    empty_points_count = 0
    outside_center_count = 0
    inside_center_count = 0
    duplicate_bbox_count = 0
    area_values = []
    point_counts = []
    part_counts = []
    bbox_signatures = Counter()
    anomaly_samples = []
    sample_records = []

    for index, shape_record in enumerate(reader.iterShapeRecords()):
        shape = shape_record.shape
        record = shape_record.record.as_dict()
        district = str(record.get("district") or "UNKNOWN").strip() or "UNKNOWN"
        village = str(record.get("village") or "").strip()
        vlcode = str(record.get("vlcode") or "").strip()
        subdistrict = str(record.get("subdistric") or "").strip()

        shape_type_counts[shape.shapeTypeName] += 1
        district_counts[district] += 1

        metrics = shape_area_and_parts(shape)
        area = float(metrics["gross_area_projected_sq_m"])
        area_values.append(area)
        point_counts.append(int(metrics["point_count"]))
        part_counts.append(int(metrics["part_count"]))

        if metrics["has_zero_area"]:
            zero_area_count += 1

        if metrics["point_count"] == 0:
            empty_points_count += 1
            if len(anomaly_samples) < sample_limit:
                anomaly_samples.append({
                    "index": index,
                    "reason": "EMPTY_POINTS",
                    "district": district,
                    "subdistrict": subdistrict,
                    "village": village,
                    "vlcode": vlcode,
                })
            continue

        bbox = list(shape.bbox)
        signature = tuple(round(float(value), 3) for value in bbox)
        bbox_signatures[signature] += 1

        min_x, min_y, max_x, max_y = [float(value) for value in bbox]
        center_x = (min_x + max_x) / 2.0
        center_y = (min_y + max_y) / 2.0
        lon, lat = transformer.transform(center_x, center_y)
        inside = inside_karnataka_buffer(lon, lat)

        if inside:
            inside_center_count += 1
            district_inside_counts[district] += 1
        else:
            outside_center_count += 1
            if len(anomaly_samples) < sample_limit:
                anomaly_samples.append({
                    "index": index,
                    "reason": "CENTER_OUTSIDE_KARNATAKA_BUFFER",
                    "district": district,
                    "subdistrict": subdistrict,
                    "village": village,
                    "vlcode": vlcode,
                    "center_wgs84": {"lon": round_value(lon), "lat": round_value(lat)},
                })

        if bbox_signatures[signature] == 2:
            duplicate_bbox_count += 1

        if len(sample_records) < sample_limit:
            sample_records.append({
                "index": index,
                "district": district,
                "subdistrict": subdistrict,
                "village": village,
                "vlcode": vlcode,
                "center_wgs84": {"lon": round_value(lon), "lat": round_value(lat)},
                "center_inside_karnataka_buffer": inside,
                "area_projected_sq_m": round_value(area, 3),
                "point_count": metrics["point_count"],
                "part_count": metrics["part_count"],
            })

        if len(district_samples[district]) < district_sample_limit:
            district_samples[district].append({
                "village": village,
                "vlcode": vlcode,
                "center_wgs84": {"lon": round_value(lon), "lat": round_value(lat)},
            })

    area_values_sorted = sorted(area_values)
    point_counts_sorted = sorted(point_counts)
    part_counts_sorted = sorted(part_counts)

    duplicate_bbox_signatures = [
        {"raw_bbox": list(signature), "count": count}
        for signature, count in bbox_signatures.most_common(20)
        if count > 1
    ]

    district_summary = []
    for district, count in district_counts.most_common():
        inside_count = district_inside_counts[district]
        district_summary.append({
            "district": district,
            "feature_count": count,
            "centers_inside_karnataka_buffer": inside_count,
            "centers_outside_karnataka_buffer": count - inside_count,
            "samples": district_samples.get(district, []),
        })

    return {
        "healthy": True,
        "pyproj_version": pyproj.__version__,
        "source_crs": {
            "name": crs.name,
            "to_epsg": crs.to_epsg(),
            "to_authority": crs.to_authority(),
            "is_projected": crs.is_projected,
            "linear_units": str(crs.axis_info[0].unit_name) if crs.axis_info else None,
        },
        "target_crs": "EPSG:4326",
        "record_count": len(reader),
        "field_count": len(fields),
        "shape_type_counts": dict(sorted(shape_type_counts.items())),
        "dataset_bbox_transform": dataset_bbox,
        "center_plausibility": {
            "inside_karnataka_buffer": inside_center_count,
            "outside_karnataka_buffer": outside_center_count,
        },
        "geometry_counts": {
            "zero_area_count": zero_area_count,
            "empty_points_count": empty_points_count,
            "duplicate_bbox_signature_count": duplicate_bbox_count,
        },
        "area_projected_sq_m_summary": {
            "min": round_value(area_values_sorted[0], 3) if area_values_sorted else None,
            "p05": round_value(quantile(area_values_sorted, 0.05), 3),
            "median": round_value(quantile(area_values_sorted, 0.50), 3),
            "p95": round_value(quantile(area_values_sorted, 0.95), 3),
            "max": round_value(area_values_sorted[-1], 3) if area_values_sorted else None,
        },
        "point_count_summary": {
            "min": point_counts_sorted[0] if point_counts_sorted else None,
            "median": quantile(point_counts_sorted, 0.50),
            "max": point_counts_sorted[-1] if point_counts_sorted else None,
        },
        "part_count_summary": {
            "min": part_counts_sorted[0] if part_counts_sorted else None,
            "median": quantile(part_counts_sorted, 0.50),
            "max": part_counts_sorted[-1] if part_counts_sorted else None,
        },
        "duplicate_bbox_samples": duplicate_bbox_signatures[:sample_limit],
        "anomaly_samples": anomaly_samples,
        "sample_records": sample_records,
        "district_summary": district_summary,
        "extracted": extracted,
    }

def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only geometry/topology audit for NWDP Karnataka village-boundary SHP.")
    parser.add_argument("--zip-path", default=str(DEFAULT_ZIP), help="Path to Karnataka SHP ZIP from CRS audit.")
    parser.add_argument("--extract-dir", default=str(DEFAULT_EXTRACT_DIR), help="Temporary extraction directory.")
    parser.add_argument("--sample-limit", type=int, default=25)
    parser.add_argument("--district-sample-limit", type=int, default=3)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    audit = run_audit(
        Path(args.zip_path),
        Path(args.extract_dir),
        args.sample_limit,
        args.district_sample_limit,
    )

    result = {
        "schema_version": "nwdp_karnataka_shp_geometry_topology_audit.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "portal": "National Water Data Portal",
            "dataset": "Village Boundary",
            "producer_agency": "Geological Survey of India",
            "state_or_ut": "Karnataka",
            "format": "SHP",
        },
        "claim_boundary": "Geometry/topology audit is read-only and evaluates source plausibility only; it does not ingest geometry or authorize runtime spatial matching.",
        "audit": audit,
        "readiness": {
            "safe_read_only": True,
            "db_writes_attempted": False,
            "ready_for_transform_planning": bool(audit.get("healthy")),
            "ready_for_runtime_spatial_matching": False,
            "ready_for_ingestion": False,
        },
        "next_actions": [
            "Review anomaly samples and duplicate bounding boxes before ingestion planning.",
            "Run a reviewed boundary-to-LGD crosswalk design before storing transformed geometry.",
            "Consider full geometry validation with Shapely/GEOS if dependencies are approved.",
        ],
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

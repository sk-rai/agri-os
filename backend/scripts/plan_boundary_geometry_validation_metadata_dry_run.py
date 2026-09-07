#!/usr/bin/env python3
"""State-scoped, read-only boundary validation metadata planner."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pyproj import CRS, Transformer
from shapely.geometry import shape
from shapely.ops import transform as transform_geometry
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.database import SessionLocal
from scripts.report_boundary_geometry_validation_repair_dry_run import (
    TARGET_CRS,
    classify_feature,
    crs_name,
    sha256_file,
)

SCHEMA_VERSION = "boundary_geometry_validation_metadata_dry_run.v1"
HASH_ALGORITHM = "NWDP_GEOJSON_GEOMETRY_CANONICAL_V1"
SOURCE_SYSTEM = "NWDP_GSI_VILLAGE_BOUNDARY"


def geometry_hash(value: dict[str, Any]) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def planned_status(classification: str) -> str:
    if classification == "VALIDATED_NO_REPAIR":
        return "VALIDATED"
    if classification == "REPAIRABLE_MAKE_VALID":
        return "REPAIR_REQUIRED"
    return "VALIDATION_REVIEW"


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = [
        "source_feature_id",
        "source_feature_index",
        "source_vlcode",
        "current_geometry_validation_status",
        "planned_geometry_validation_status",
        "source_geometry_hash",
        "classification",
        "metadata_change_planned",
        "runtime_eligibility_change_planned",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=columns,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-slug", required=True)
    parser.add_argument("--state-or-ut", required=True)
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=ROOT
        / "data/raw/nwdp_boundary_all_state/20260824T110250Z",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    if args.limit < 1 or args.limit > 500:
        raise SystemExit("--limit must be between 1 and 500")

    source_path = args.raw_dir / f"{args.state_slug}.geojson"
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    features = payload.get("features") or []

    source_crs = CRS.from_user_input(crs_name(payload))
    transformer = Transformer.from_crs(
        source_crs,
        CRS.from_user_input(TARGET_CRS),
        always_xy=True,
    )

    with SessionLocal() as db:
        batches = list(db.execute(text("""
            select
                b.id::text as import_batch_id,
                count(sf.id)::bigint as source_feature_count,
                min(sf.source_feature_index)::bigint as minimum_index,
                max(sf.source_feature_index)::bigint as maximum_index,
                count(distinct sf.source_feature_index)::bigint
                    as distinct_index_count
            from geography_boundary_import_batches b
            join geography_boundary_source_features sf
              on sf.import_batch_id = b.id
            where b.source_system = :source_system
              and lower(trim(b.state_or_ut)) =
                  lower(trim(:state_or_ut))
            group by b.id
        """), {
            "source_system": SOURCE_SYSTEM,
            "state_or_ut": args.state_or_ut,
        }).mappings())

        aligned = (
            len(batches) == 1
            and batches[0]["source_feature_count"] == len(features)
            and batches[0]["minimum_index"] == 0
            and batches[0]["maximum_index"] == len(features) - 1
            and batches[0]["distinct_index_count"] == len(features)
        )

        if not aligned:
            raise SystemExit("SOURCE_DATABASE_ALIGNMENT_FAILED")

        batch_id = batches[0]["import_batch_id"]

        db_rows = list(db.execute(text("""
            select
                id::text as source_feature_id,
                source_feature_index,
                source_vlcode,
                geometry_validation_status,
                eligible_for_runtime_after_promotion
            from geography_boundary_source_features
            where import_batch_id = cast(:batch_id as uuid)
              and geometry_validation_status = 'NOT_VALIDATED'
            order by source_feature_index
            limit :limit
        """), {
            "batch_id": batch_id,
            "limit": args.limit,
        }).mappings())

    rows = []

    for db_row in db_rows:
        index = int(db_row["source_feature_index"])
        feature = features[index]
        validation = classify_feature(index, feature, transformer)
        source_geometry = shape(feature["geometry"])
        status = planned_status(validation["classification"])

        transformed_bbox = None
        transformed_centroid = None

        if status == "VALIDATED":
            transformed = transform_geometry(
                transformer.transform,
                source_geometry,
            )
            centroid = transformed.centroid
            transformed_bbox = [
                round(float(value), 8)
                for value in transformed.bounds
            ]
            transformed_centroid = {
                "lon": round(float(centroid.x), 8),
                "lat": round(float(centroid.y), 8),
                "method": "geometry_centroid",
            }

        rows.append({
            "source_feature_id": db_row["source_feature_id"],
            "source_feature_index": index,
            "source_vlcode": db_row["source_vlcode"],
            "current_geometry_validation_status":
                db_row["geometry_validation_status"],
            "planned_geometry_validation_status": status,
            "source_geometry_hash":
                geometry_hash(feature["geometry"]),
            "source_bbox": [
                round(float(value), 3)
                for value in source_geometry.bounds
            ],
            "transformed_bbox": transformed_bbox,
            "transformed_centroid": transformed_centroid,
            "classification": validation["classification"],
            "metadata_change_planned": True,
            "runtime_eligibility_change_planned": False,
        })

    counts: dict[str, int] = {}
    for row in rows:
        status = row["planned_geometry_validation_status"]
        counts[status] = counts.get(status, 0) + 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / (
        f"{args.state_slug}_validation_metadata_dry_run.json"
    )
    csv_path = args.output_dir / (
        f"{args.state_slug}_validation_metadata_dry_run.csv"
    )

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": aligned and bool(rows),
        "mode": "READ_ONLY_BOUNDARY_VALIDATION_METADATA_DRY_RUN",
        "scope": {
            "state_slug": args.state_slug,
            "state_or_ut": args.state_or_ut,
            "limit": args.limit,
            "import_batch_id": batch_id,
        },
        "source": {
            "path": str(source_path),
            "sha256": sha256_file(source_path),
            "feature_count": len(features),
            "geometry_hash_algorithm": HASH_ALGORITHM,
        },
        "summary": {
            "selected_row_count": len(rows),
            "validated_count": counts.get("VALIDATED", 0),
            "repair_required_count":
                counts.get("REPAIR_REQUIRED", 0),
            "validation_review_count":
                counts.get("VALIDATION_REVIEW", 0),
            "metadata_update_planned_count": len(rows),
            "runtime_eligibility_change_planned_count": 0,
        },
        "rows": rows,
        "readiness": {
            "ready_for_admin_metadata_review": bool(rows),
            "ready_for_tiny_fixture_metadata_apply": bool(rows),
            "ready_for_broad_metadata_apply": False,
            "ready_for_runtime_promotion_apply": False,
            "ready_for_android_behavior_change": False,
        },
        "guardrails": {
            "db_writes_attempted": False,
            "source_files_changed": False,
            "source_features_changed": False,
            "geometry_repair_persisted": False,
            "geometry_validation_status_changed": False,
            "source_runtime_eligibility_changed": False,
            "boundary_candidates_promoted": False,
            "boundary_candidates_activated": False,
            "runtime_tables_written": False,
            "runtime_lookup_enabled": False,
            "lgd_geography_overwritten": False,
            "android_behavior_changed": False,
        },
        "output_files": {
            "json": str(json_path),
            "csv": str(csv_path),
        },
    }

    json_path.write_text(
        json.dumps(report, indent=2, default=str),
        encoding="utf-8",
    )
    write_csv(csv_path, rows)
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

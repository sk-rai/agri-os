#!/usr/bin/env python3
"""Read-only bounded state planner for boundary validation metadata."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pyproj import CRS, Transformer
from shapely.geometry import shape
from shapely.ops import transform as transform_geometry
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.database import SessionLocal  # noqa: E402
from scripts.plan_boundary_geometry_validation_metadata_dry_run import (  # noqa: E402
    HASH_ALGORITHM,
    SOURCE_SYSTEM,
    geometry_hash,
)
from scripts.report_boundary_geometry_validation_repair_dry_run import (  # noqa: E402
    TARGET_CRS,
    classify_feature,
    crs_name,
    sha256_file,
)

SCHEMA_VERSION = "boundary_geometry_validation_metadata_bounded_state_plan.v1"


def args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-slug", required=True)
    parser.add_argument("--state-or-ut", required=True)
    parser.add_argument("--expected-source-sha256", required=True)
    parser.add_argument("--cursor-after-index", type=int, default=-1)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=(
            ROOT
            / "data/raw/nwdp_boundary_all_state/20260824T110250Z"
        ),
    )
    return parser.parse_args()


def canonical_checksum(value: Any) -> str:
    body = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def database_counts(db) -> dict[str, int]:
    row = db.execute(text("""
        select
          (select count(*) from geography_boundary_source_features)
            as source_feature_rows,
          (select count(*) from geography_boundary_source_features
           where geometry_validation_status = 'NOT_VALIDATED')
            as not_validated_rows,
          (select count(*) from geography_boundary_source_features
           where geometry_validation_status = 'VALIDATED')
            as validated_rows,
          (select count(*) from geography_boundary_source_features
           where eligible_for_runtime_after_promotion = true)
            as runtime_eligible_source_rows,
          (select count(*) from geography_boundary_crosswalk_candidates)
            as candidate_rows,
          (select count(*) from geography_boundary_crosswalk_candidates
           where is_active = true)
            as active_candidate_rows,
          (select count(*) from geography_boundary_crosswalk_candidates
           where promotion_status = 'PROMOTED')
            as promoted_candidate_rows,
          (select count(*) from geography_boundary_runtime_sets)
            as runtime_set_rows,
          (select count(*) from geography_boundary_runtime_features)
            as runtime_feature_rows,
          (select count(*) from geography_boundary_runtime_crosswalks)
            as runtime_crosswalk_rows
    """)).mappings().one()
    return {key: int(value or 0) for key, value in row.items()}


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "sequence",
        "source_feature_id",
        "source_feature_index",
        "source_vlcode",
        "current_geometry_validation_status",
        "planned_geometry_validation_status",
        "classification",
        "source_geometry_hash",
        "source_bbox",
        "transformed_bbox",
        "transformed_centroid",
        "runtime_eligibility_change_planned",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
        )
        writer.writeheader()
        for row in rows:
            output = dict(row)
            for key in [
                "source_bbox",
                "transformed_bbox",
                "transformed_centroid",
            ]:
                output[key] = json.dumps(
                    output.get(key),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            writer.writerow(output)


def main() -> int:
    options = args()

    if options.limit < 1 or options.limit > 500:
        raise SystemExit("--limit must be between 1 and 500")
    if options.cursor_after_index < -1:
        raise SystemExit("--cursor-after-index must be at least -1")

    source_path = options.raw_dir / f"{options.state_slug}.geojson"
    source_checksum = sha256_file(source_path)

    if source_checksum.lower() != options.expected_source_sha256.lower():
        raise SystemExit("SOURCE_CHECKSUM_MISMATCH")

    source_payload = json.loads(source_path.read_text(encoding="utf-8"))
    features = source_payload.get("features") or []

    source_crs = CRS.from_user_input(crs_name(source_payload))
    transformer = Transformer.from_crs(
        source_crs,
        CRS.from_user_input(TARGET_CRS),
        always_xy=True,
    )

    with SessionLocal() as db:
        before_counts = database_counts(db)

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
            "state_or_ut": options.state_or_ut,
        }).mappings())

        aligned = (
            len(batches) == 1
            and int(batches[0]["source_feature_count"]) == len(features)
            and int(batches[0]["minimum_index"]) == 0
            and int(batches[0]["maximum_index"]) == len(features) - 1
            and int(batches[0]["distinct_index_count"]) == len(features)
        )
        if not aligned:
            raise SystemExit("SOURCE_DATABASE_ALIGNMENT_FAILED")

        import_batch_id = batches[0]["import_batch_id"]

        db_rows = list(db.execute(text("""
            select
              id::text as source_feature_id,
              source_feature_index,
              source_vlcode,
              geometry_validation_status,
              eligible_for_runtime_after_promotion
            from geography_boundary_source_features
            where import_batch_id = cast(:batch_id as uuid)
            order by source_feature_index
        """), {"batch_id": import_batch_id}).mappings())

        after_counts = database_counts(db)

    selected: list[dict[str, Any]] = []
    state_valid_count = 0
    state_repair_required_count = 0
    state_validation_review_count = 0
    eligible_after_cursor_count = 0

    for db_row in db_rows:
        index = int(db_row["source_feature_index"])
        feature = features[index]
        validation = classify_feature(index, feature, transformer)
        classification = validation["classification"]

        if classification == "VALIDATED_NO_REPAIR":
            state_valid_count += 1
        elif classification == "REPAIRABLE_MAKE_VALID":
            state_repair_required_count += 1
        else:
            state_validation_review_count += 1

        if (
            classification != "VALIDATED_NO_REPAIR"
            or index <= options.cursor_after_index
            or db_row["geometry_validation_status"] != "NOT_VALIDATED"
        ):
            continue

        eligible_after_cursor_count += 1
        if len(selected) >= options.limit:
            continue

        source_geometry = shape(feature["geometry"])
        transformed = transform_geometry(
            transformer.transform,
            source_geometry,
        )
        centroid = transformed.centroid

        selected.append({
            "sequence": len(selected) + 1,
            "source_feature_id": db_row["source_feature_id"],
            "source_feature_index": index,
            "source_vlcode": db_row["source_vlcode"],
            "current_geometry_validation_status":
                db_row["geometry_validation_status"],
            "planned_geometry_validation_status": "VALIDATED",
            "classification": classification,
            "source_geometry_hash": geometry_hash(feature["geometry"]),
            "source_bbox": [
                round(float(value), 3)
                for value in source_geometry.bounds
            ],
            "transformed_bbox": [
                round(float(value), 8)
                for value in transformed.bounds
            ],
            "transformed_centroid": {
                "lon": round(float(centroid.x), 8),
                "lat": round(float(centroid.y), 8),
                "method": "geometry_centroid",
            },
            "runtime_eligibility_change_planned": False,
        })

    next_cursor = (
        selected[-1]["source_feature_index"]
        if selected
        else options.cursor_after_index
    )
    remaining_count = max(
        eligible_after_cursor_count - len(selected),
        0,
    )

    checksum_payload = {
        "schema_version": SCHEMA_VERSION,
        "state_slug": options.state_slug,
        "state_or_ut": options.state_or_ut,
        "import_batch_id": import_batch_id,
        "source_sha256": source_checksum,
        "geometry_hash_algorithm": HASH_ALGORITHM,
        "cursor_after_index": options.cursor_after_index,
        "limit": options.limit,
        "rows": selected,
    }
    plan_checksum = canonical_checksum(checksum_payload)
    batch_id = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"agri-os:{SCHEMA_VERSION}:{plan_checksum}",
        )
    )

    options.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = options.output_dir / (
        f"{options.state_slug}_bounded_validation_metadata_plan.json"
    )
    csv_path = options.output_dir / (
        f"{options.state_slug}_bounded_validation_metadata_plan.csv"
    )

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": True,
        "mode": "READ_ONLY_BOUNDED_STATE_VALIDATION_METADATA_PLAN",
        "scope": {
            "state_slug": options.state_slug,
            "state_or_ut": options.state_or_ut,
            "import_batch_id": import_batch_id,
            "cursor_after_index": options.cursor_after_index,
            "limit": options.limit,
        },
        "source": {
            "path": str(source_path),
            "sha256": source_checksum,
            "feature_count": len(features),
            "source_crs": source_crs.to_string(),
            "target_crs": TARGET_CRS,
            "geometry_hash_algorithm": HASH_ALGORITHM,
        },
        "batch": {
            "batch_id": batch_id,
            "plan_checksum": plan_checksum,
            "selected_row_count": len(selected),
            "first_source_feature_index": (
                selected[0]["source_feature_index"]
                if selected else None
            ),
            "last_source_feature_index": (
                selected[-1]["source_feature_index"]
                if selected else None
            ),
            "next_cursor_after_index": next_cursor,
            "remaining_valid_not_validated_count": remaining_count,
            "has_more": remaining_count > 0,
        },
        "state_classification": {
            "valid_without_repair_count": state_valid_count,
            "repair_required_count": state_repair_required_count,
            "validation_review_count": state_validation_review_count,
        },
        "rows": selected,
        "readiness": {
            "ready_for_admin_batch_review": len(selected) > 0,
            "ready_for_bounded_state_apply": False,
            "ready_for_broad_metadata_apply": False,
            "ready_for_geometry_repair_apply": False,
            "ready_for_runtime_promotion_apply": False,
            "ready_for_android_behavior_change": False,
        },
        "database_counts": {
            "before": before_counts,
            "after": after_counts,
            "unchanged": before_counts == after_counts,
        },
        "guardrails": {
            "db_writes_attempted": False,
            "source_files_changed": False,
            "source_features_changed": False,
            "validation_metadata_written": False,
            "geometry_repair_persisted": False,
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
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    write_csv(csv_path, selected)

    print(json.dumps({
        "healthy": report["healthy"],
        "scope": report["scope"],
        "source": report["source"],
        "batch": report["batch"],
        "state_classification": report["state_classification"],
        "database_counts": report["database_counts"],
        "guardrails": report["guardrails"],
        "output_files": report["output_files"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


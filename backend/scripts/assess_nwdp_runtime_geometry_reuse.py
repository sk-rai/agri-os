import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from shapely.geometry import mapping, shape
from shapely.ops import transform as transform_geometry
from shapely.validation import explain_validity
from pyproj import CRS, Transformer
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.database import engine

SET_ID = "e5f93e27-a0bd-5c8b-bef3-d97986e14c55"

SOURCE_CRS = "EPSG:7755"
TARGET_CRS = "EPSG:4326"

EXPECTED_RUNTIME_ARCHIVE_SHA256 = (
    "fa7f7dabd7c55e59a5e8c4e916f55629"
    "4969c8a993057a574bc67a9d11f9c3e7"
)
EXPECTED_NORMALIZED_GEOJSON_SHA256 = (
    "025495a467a88833c40c2417e4b730ab"
    "9b16d6f2b8d67a3651aec8053bad125c"
)

DEFAULT_OUTPUT_DIR = (
    ROOT
    / "data/staged/core_stack/promotion_review"
    / "20260919-runtime-lookup-reuse-assessment"
)

raw_path = Path(os.environ.get(
    "RAW",
    str(
        ROOT
        / "data/raw/nwdp_boundary_all_state"
        / "20260824T110250Z"
        / "karnataka.geojson"
    ),
))
output_path = Path(os.environ.get(
    "OUT_JSON",
    str(
        DEFAULT_OUTPUT_DIR
        / "runtime_geometry_reconstruction_assessment.json"
    ),
))
extracted_path = Path(os.environ.get(
    "EXTRACTED",
    str(
        DEFAULT_OUTPUT_DIR
        / "active_10_runtime_geometry_fixture.geojson"
    ),
))

output_path.parent.mkdir(
    parents=True,
    exist_ok=True,
)
extracted_path.parent.mkdir(
    parents=True,
    exist_ok=True,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def geometry_hash(
    value: dict,
) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


def stream_geojson_features(
    path: Path,
) -> Iterator[tuple[int, dict]]:
    """Stream FeatureCollection features using bounded memory."""

    decoder = json.JSONDecoder()
    buffer = ""
    position = 0
    feature_index = 0
    found_features = False
    reached_array = False
    eof = False

    with path.open(
        "r",
        encoding="utf-8",
        errors="strict",
    ) as handle:
        while True:
            if position >= len(buffer) and not eof:
                buffer = handle.read(1024 * 1024)
                position = 0
                if not buffer:
                    eof = True

            if not found_features:
                marker = buffer.find('"features"', position)

                while marker < 0 and not eof:
                    tail = buffer[
                        max(0, len(buffer) - 64):
                    ]
                    more = handle.read(1024 * 1024)
                    if not more:
                        eof = True
                        break
                    buffer = tail + more
                    position = 0
                    marker = buffer.find('"features"')

                if marker < 0:
                    raise RuntimeError(
                        "GEOJSON_FEATURES_ARRAY_NOT_FOUND"
                    )

                position = marker + len('"features"')
                found_features = True

            if not reached_array:
                while True:
                    while (
                        position < len(buffer)
                        and buffer[position].isspace()
                    ):
                        position += 1

                    if position < len(buffer):
                        if buffer[position] != ":":
                            raise RuntimeError(
                                "GEOJSON_FEATURES_COLON_MISSING"
                            )
                        position += 1
                        break

                    more = handle.read(1024 * 1024)
                    if not more:
                        raise RuntimeError(
                            "UNEXPECTED_EOF_BEFORE_FEATURES"
                        )
                    buffer += more

                while True:
                    while (
                        position < len(buffer)
                        and buffer[position].isspace()
                    ):
                        position += 1

                    if position < len(buffer):
                        if buffer[position] != "[":
                            raise RuntimeError(
                                "GEOJSON_FEATURES_ARRAY_INVALID"
                            )
                        position += 1
                        reached_array = True
                        break

                    more = handle.read(1024 * 1024)
                    if not more:
                        raise RuntimeError(
                            "UNEXPECTED_EOF_BEFORE_ARRAY"
                        )
                    buffer += more

            while True:
                while (
                    position < len(buffer)
                    and (
                        buffer[position].isspace()
                        or buffer[position] == ","
                    )
                ):
                    position += 1

                if position < len(buffer):
                    if buffer[position] == "]":
                        return
                    break

                more = handle.read(1024 * 1024)
                if not more:
                    raise RuntimeError(
                        "UNEXPECTED_EOF_IN_FEATURE_ARRAY"
                    )
                buffer = buffer[position:] + more
                position = 0

            while True:
                try:
                    feature, end = decoder.raw_decode(
                        buffer,
                        position,
                    )
                    position = end
                    yield feature_index, feature
                    feature_index += 1

                    if position > 4 * 1024 * 1024:
                        buffer = buffer[position:]
                        position = 0
                    break
                except json.JSONDecodeError:
                    more = handle.read(1024 * 1024)
                    if not more:
                        raise RuntimeError(
                            "INCOMPLETE_GEOJSON_FEATURE"
                        )
                    buffer += more


if not raw_path.exists():
    raise SystemExit(
        f"PINNED_SOURCE_FILE_NOT_FOUND:{raw_path}"
    )

with engine.connect() as connection:
    runtime_set = dict(
        connection.execute(text("""
            select
              id::text as runtime_set_id,
              source_file_sha256,
              runtime_crs,
              activation_status,
              is_active
            from geography_boundary_runtime_sets
            where id = cast(:set_id as uuid)
        """), {"set_id": SET_ID}).mappings().one()
    )

    runtime_rows = [
        dict(row)
        for row in connection.execute(text("""
            select
              rf.id::text as runtime_feature_id,
              rf.source_feature_id::text,
              rf.source_feature_index,
              rf.geometry_hash,
              rf.geometry_validation_status,
              rf.geometry_wgs84,
              rf.metadata,
              rw.id::text as runtime_crosswalk_id,
              rw.village_id::text,
              rw.village_lgd_code,
              rw.runtime_scope
            from geography_boundary_runtime_features rf
            join geography_boundary_runtime_crosswalks rw
              on rw.runtime_feature_id = rf.id
             and rw.runtime_set_id = rf.runtime_set_id
            where rf.runtime_set_id =
                  cast(:set_id as uuid)
              and rf.is_active = true
              and rw.is_active = true
            order by rf.source_feature_index
        """), {"set_id": SET_ID}).mappings().all()
    ]

actual_source_sha256 = sha256_file(raw_path)
runtime_archive_sha256 = runtime_set[
    "source_file_sha256"
]
expected_source_sha256 = (
    EXPECTED_NORMALIZED_GEOJSON_SHA256
)

if (
    runtime_archive_sha256
    != EXPECTED_RUNTIME_ARCHIVE_SHA256
):
    raise SystemExit(
        "RUNTIME_ARCHIVE_LINEAGE_CHECKSUM_MISMATCH:"
        f"expected={EXPECTED_RUNTIME_ARCHIVE_SHA256}:"
        f"actual={runtime_archive_sha256}"
    )

if (
    actual_source_sha256
    != EXPECTED_NORMALIZED_GEOJSON_SHA256
):
    raise SystemExit(
        "NORMALIZED_GEOJSON_CHECKSUM_MISMATCH:"
        f"expected="
        f"{EXPECTED_NORMALIZED_GEOJSON_SHA256}:"
        f"actual={actual_source_sha256}"
    )

transformer = Transformer.from_crs(
    CRS.from_user_input(SOURCE_CRS),
    CRS.from_user_input(TARGET_CRS),
    always_xy=True,
)

wanted_indexes = {
    int(row["source_feature_index"])
    for row in runtime_rows
}
runtime_by_index = {
    int(row["source_feature_index"]): row
    for row in runtime_rows
}

selected = {}

for index, feature in stream_geojson_features(raw_path):
    if index in wanted_indexes:
        selected[index] = feature

    if len(selected) == len(wanted_indexes):
        break

missing_indexes = sorted(
    wanted_indexes - set(selected)
)

if missing_indexes:
    raise SystemExit(
        "PINNED_SOURCE_FEATURES_NOT_FOUND:"
        + ",".join(map(str, missing_indexes))
    )

features = []
row_assessments = []

for index in sorted(selected):
    feature = selected[index]
    runtime = runtime_by_index[index]
    geometry_payload = feature.get("geometry")

    if not isinstance(geometry_payload, dict):
        raise RuntimeError(
            f"SOURCE_GEOMETRY_MISSING:{index}"
        )

    source_geometry = shape(geometry_payload)
    source_hash = geometry_hash(
        geometry_payload
    )
    transformed_geometry = transform_geometry(
        transformer.transform,
        source_geometry,
    )
    transformed_payload = mapping(
        transformed_geometry
    )

    properties = feature.get("properties") or {}
    source_property_vlcode = str(
        properties.get("vlcode")
        or properties.get("VLCODE")
        or ""
    )
    runtime_village_lgd_code = str(
        runtime["village_lgd_code"] or ""
    )
    transformed_bounds = [
        round(float(value), 8)
        for value in transformed_geometry.bounds
    ]

    row_assessments.append({
        "source_feature_index": index,
        "runtime_feature_id":
            runtime["runtime_feature_id"],
        "runtime_crosswalk_id":
            runtime["runtime_crosswalk_id"],
        "village_id": runtime["village_id"],
        "village_lgd_code":
            runtime_village_lgd_code,
        "runtime_scope":
            runtime["runtime_scope"],
        "source_crs": SOURCE_CRS,
        "target_crs": TARGET_CRS,
        "source_geometry_type":
            source_geometry.geom_type,
        "geometry_type":
            transformed_geometry.geom_type,
        "geometry_empty":
            transformed_geometry.is_empty,
        "geometry_valid":
            transformed_geometry.is_valid,
        "validity_reason":
            explain_validity(
                transformed_geometry
            ),
        "transformed_bounds":
            transformed_bounds,
        "bounds_inside_karnataka": (
            73.0 <= transformed_bounds[0] <= 79.0
            and
            73.0 <= transformed_bounds[2] <= 79.0
            and
            11.0 <= transformed_bounds[1] <= 19.0
            and
            11.0 <= transformed_bounds[3] <= 19.0
        ),
        "source_property_vlcode":
            source_property_vlcode,
        "village_identity_matches": (
            source_property_vlcode
            == runtime_village_lgd_code
        ),
        "normalized_geojson_geometry_hash":
            source_hash,
        "runtime_archive_shape_hash":
            runtime["geometry_hash"],
        "hash_comparison": {
            "comparable": False,
            "reason": (
                "Runtime hash uses the original SHP "
                "shapeType/bbox/parts/points payload; "
                "the normalized hash uses canonical "
                "GeoJSON. Both are retained as "
                "format-specific lineage evidence."
            ),
        },
        "runtime_geometry_payload_loaded":
            bool(runtime["geometry_wgs84"]),
    })

    features.append({
        "type": "Feature",
        "id": runtime["runtime_feature_id"],
        "properties": {
            "runtime_feature_id":
                runtime["runtime_feature_id"],
            "runtime_crosswalk_id":
                runtime["runtime_crosswalk_id"],
            "source_feature_index": index,
            "village_id": runtime["village_id"],
            "village_lgd_code":
                runtime_village_lgd_code,
            "runtime_scope":
                runtime["runtime_scope"],
            "source_crs": SOURCE_CRS,
            "runtime_crs": TARGET_CRS,
            "normalized_geojson_geometry_hash":
                source_hash,
            "runtime_archive_shape_hash":
                runtime["geometry_hash"],
        },
        "geometry": transformed_payload,
    })

geometry_type_supported_count = sum(
    row["geometry_type"]
    in {"Polygon", "MultiPolygon"}
    for row in row_assessments
)
valid_count = sum(
    row["geometry_valid"]
    for row in row_assessments
)
nonempty_count = sum(
    not row["geometry_empty"]
    for row in row_assessments
)
identity_count = sum(
    bool(row["village_id"])
    and bool(row["village_lgd_code"])
    for row in row_assessments
)

runtime_hash_present_count = sum(
    bool(row["runtime_archive_shape_hash"])
    for row in row_assessments
)
normalized_hash_present_count = sum(
    bool(row["normalized_geojson_geometry_hash"])
    for row in row_assessments
)
village_identity_match_count = sum(
    row["village_identity_matches"]
    for row in row_assessments
)
bounds_inside_karnataka_count = sum(
    row["bounds_inside_karnataka"]
    for row in row_assessments
)

checks = {
    "runtime_archive_lineage_checksum_matches":
        runtime_archive_sha256
        == EXPECTED_RUNTIME_ARCHIVE_SHA256,
    "normalized_geojson_checksum_matches":
        actual_source_sha256
        == EXPECTED_NORMALIZED_GEOJSON_SHA256,
    "runtime_set_active":
        runtime_set["is_active"] is True
        and runtime_set["activation_status"]
            == "ACTIVE",
    "runtime_crs_is_wgs84":
        runtime_set["runtime_crs"]
        == TARGET_CRS,
    "exactly_10_active_runtime_links":
        len(runtime_rows) == 10,
    "exactly_10_source_features_reconstructed":
        len(features) == 10,
    "all_geometry_types_supported":
        geometry_type_supported_count == 10,
    "all_geometries_nonempty":
        nonempty_count == 10,
    "all_transformed_geometries_valid":
        valid_count == 10,
    "all_transformed_bounds_inside_karnataka":
        bounds_inside_karnataka_count == 10,
    "all_runtime_archive_shape_hashes_present":
        runtime_hash_present_count == 10,
    "all_normalized_geojson_hashes_present":
        normalized_hash_present_count == 10,
    "cross_format_hashes_not_compared":
        True,
    "all_village_identities_complete":
        identity_count == 10,
    "all_village_identities_match":
        village_identity_match_count == 10,
    "runtime_geometry_column_intentionally_empty":
        all(
            not row["runtime_geometry_payload_loaded"]
            for row in row_assessments
        ),
}

healthy = all(checks.values())

feature_collection = {
    "type": "FeatureCollection",
    "name":
        "active_10_runtime_geometry_fixture",
    "crs": {
        "type": "name",
        "properties": {
            "name": "EPSG:4326",
        },
    },
    "features": features,
}

extracted_path.write_text(
    json.dumps(
        feature_collection,
        separators=(",", ":"),
    ) + "\n",
    encoding="utf-8",
)

report = {
    "schema_version":
        "nwdp_runtime_geometry_reconstruction_assessment.v1",
    "generated_at":
        datetime.now(timezone.utc).isoformat(),
    "healthy": healthy,
    "mode":
        "READ_ONLY_PINNED_SOURCE_RECONSTRUCTION",
    "runtime_set_id": SET_ID,
    "source_lineage": {
    "runtime_import_artifact": {
        "format": "SHP",
        "sha256": runtime_archive_sha256,
        "checksum_matches": (
            runtime_archive_sha256
            == (
                "fa7f7dabd7c55e59a5e8c4e916f55629"
                "4969c8a993057a574bc67a9d11f9c3e7"
            )
        ),
    },
    "normalized_geojson": {
        "path": str(raw_path.resolve()),
        "expected_sha256":
            expected_source_sha256,
        "actual_sha256":
            actual_source_sha256,
        "checksum_matches": (
            actual_source_sha256
            == expected_source_sha256
        ),
    },
    "lineage_interpretation": (
        "The runtime set references the original "
        "SHP/ZIP import artifact. Polygon "
        "reconstruction uses the separately pinned "
        "normalized GeoJSON validated by the national "
        "metadata campaigns. Their geometry "
        "hashes use different serialization algorithms "
        "and are therefore intentionally not compared."
    ),
    "geometry_hash_algorithms": {
        "runtime_archive_shape_hash": (
            "SHA256_JSON_SORTED_SHAPETYPE_BBOX_PARTS_POINTS"
        ),
        "normalized_geojson_geometry_hash": (
            "SHA256_CANONICAL_GEOJSON_SORTED_KEYS"
        ),
        "cross_format_equality_expected": False,
    },
},
    "summary": {
        "runtime_row_count": len(runtime_rows),
        "reconstructed_feature_count":
            len(features),
        "supported_geometry_type_count":
            geometry_type_supported_count,
        "valid_geometry_count": valid_count,
        "nonempty_geometry_count":
            nonempty_count,
        "complete_village_identity_count":
            identity_count,
        "runtime_archive_shape_hash_count":
            runtime_hash_present_count,
        "normalized_geojson_hash_count":
            normalized_hash_present_count,
    },
    "checks": checks,
    "rows": row_assessments,
    "reuse_decision": {
        "runtime_identities_reusable": healthy,
        "runtime_crosswalks_reusable": healthy,
        "runtime_archive_shape_hashes_reusable":
            healthy,
        "normalized_geojson_hashes_reusable":
            healthy,
        "cross_format_hash_equality_required":
            False,
        "source_feature_indexes_reusable":
            healthy,
        "pinned_raw_polygons_reusable":
            healthy,
        "project_scope_resolver_reusable":
            True,
        "project_assignment_api_reusable":
            True,
        "production_runtime_geometry_column_ready":
            False,
        "read_only_tiny_lookup_preview_ready":
            healthy,
        "production_lookup_ready": False,
    },
    "recommended_next_checkpoint": {
        "name":
            "READ_ONLY_10_ROW_POINT_LOOKUP_PREVIEW",
        "geometry_source":
            "CHECKSUM_PINNED_EXTRACTED_FIXTURE",
        "feature_count": 10,
        "writes_allowed": False,
        "lookup_enablement_allowed": False,
        "android_behavior_change_allowed": False,
    },
    "output_files": {
        "assessment_json":
            str(output_path),
        "extracted_geojson":
            str(extracted_path),
    },
    "guardrails": {
        "database_writes_attempted": False,
        "runtime_tables_written": False,
        "runtime_lookup_enabled": False,
        "runtime_spatial_matching_changed":
            False,
        "project_matches_written": False,
        "candidate_activation_changed": False,
        "candidate_promotion_changed": False,
        "source_files_changed": False,
        "android_behavior_changed": False,
    },
}

output_path.write_text(
    json.dumps(
        report,
        indent=2,
        sort_keys=True,
        default=str,
    ) + "\n",
    encoding="utf-8",
)

print(json.dumps(
    report,
    indent=2,
    sort_keys=True,
    default=str,
))

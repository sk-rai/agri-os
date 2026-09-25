#!/usr/bin/env python3
"""Build a checksum-pinned, read-only NWDP district-drift manifest."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from shapely.geometry import mapping, shape
from shapely.validation import make_valid
from sqlalchemy import text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.database import engine
from scripts.build_nwdp_normalized_direct_rehabilitation_manifest import (
    REPAIR_AUTHORIZATION_CHECKSUM,
    REPAIR_PROPOSAL_CHECKSUM,
    SOURCE_ROOT,
    STATE_CONFIG,
    geometry_hash,
)
from scripts.nwdp_district_drift_selector import (
    EXPECTED_BY_NAME_DISPOSITION,
    EXPECTED_BY_PARENT_ISSUE,
    EXPECTED_BY_STATE,
    EXPECTED_ROWS,
    EXPECTED_STATES,
    selected_rows,
)
from scripts.run_national_direct_village_runtime_state import (
    atomic_write_json,
    canonical_checksum,
    reconstruct_geometries,
    sha256_file,
    stream_geojson_features,
)


SCHEMA_VERSION = "nwdp_district_drift_manifest.v1"

EVIDENCE_DIR = (
    PROJECT_ROOT
    / "data/staged/core_stack/promotion_review"
    / "20260924-nwdp-no-canonical-village-audit-v1"
)

NO_CANONICAL_AUDIT = (
    EVIDENCE_DIR
    / "nwdp_no_canonical_village_audit.json"
)
DISTRICT_DRIFT_AUDIT = (
    EVIDENCE_DIR
    / "nwdp_same_state_district_drift_audit.json"
)
RUNTIME_REVALIDATION = (
    EVIDENCE_DIR
    / "nwdp_district_drift_runtime_revalidation.json"
)
SELECTOR_SCRIPT = (
    BACKEND_ROOT
    / "scripts/nwdp_district_drift_selector.py"
)

NO_CANONICAL_AUDIT_SHA256 = (
    "09ff191ceed1cb894b18c2ec2cca7ab5"
    "42757618b3adf257b886cee16ca99f1d"
)
DISTRICT_DRIFT_AUDIT_SHA256 = (
    "c0a517d9a694dd2861d334f95e175033"
    "165dd921b418b96e523b7bbfe3e96078"
)
RUNTIME_REVALIDATION_SHA256 = (
    "ccdae8e45d99ca030755a4e1b60a713"
    "0e08e5d2ed20e7d3c136a7dad665e21e7"
)

# Updated after selector contract alignment below.
SELECTOR_SCRIPT_SHA256 = "772f52675d5cbe9d8ab383eb45f9dd4ff00c1e31eee7768b9d39e3f3685882bd"

DEFAULT_OUTPUT = (
    EVIDENCE_DIR
    / "nwdp_district_drift_manifest.json"
)

STATE_SOURCE = {
    item["state"]: item
    for item in STATE_CONFIG
}

EXPECTED_REPAIRED_ROWS = {
    "9c80b48a-da2d-5ae8-9d23-38b4ec9a9f73": {
        "state": "Rajasthan",
        "index": 24_795,
        "geometry_hash":
            "b48380d13c1d0a72c5b3f58cd10b22c"
            "cd5b510e4d63c0035f77664c3cf170c8f",
        "row_checksum":
            "51d20930e94262973e66a072068818067"
            "d2a06949e608cb64e2171c312723e63",
    },
}


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
    )
    return parser.parse_args()


def validate_pinned_evidence() -> None:
    pins = {
        NO_CANONICAL_AUDIT:
            NO_CANONICAL_AUDIT_SHA256,
        DISTRICT_DRIFT_AUDIT:
            DISTRICT_DRIFT_AUDIT_SHA256,
        RUNTIME_REVALIDATION:
            RUNTIME_REVALIDATION_SHA256,
        SELECTOR_SCRIPT:
            SELECTOR_SCRIPT_SHA256,
    }

    for path, expected in pins.items():
        actual = sha256_file(path)
        if actual != expected:
            raise ValueError(
                "PINNED_EVIDENCE_CHECKSUM_MISMATCH:"
                f"{path}:expected={expected}:actual={actual}"
            )

    no_canonical = json.loads(
        NO_CANONICAL_AUDIT.read_text(
            encoding="utf-8"
        )
    )
    district_drift = json.loads(
        DISTRICT_DRIFT_AUDIT.read_text(
            encoding="utf-8"
        )
    )
    revalidation = json.loads(
        RUNTIME_REVALIDATION.read_text(
            encoding="utf-8"
        )
    )

    checks = {
        "no_canonical_healthy":
            no_canonical.get("healthy") is True,
        "no_canonical_no_writes":
            no_canonical.get(
                "database_writes_attempted"
            ) is False,
        "no_canonical_rows":
            no_canonical.get("row_count")
            == 26_127,
        "district_drift_healthy":
            district_drift.get("healthy")
            is True,
        "district_drift_no_writes":
            district_drift.get(
                "database_writes_attempted"
            ) is False,
        "district_drift_rows":
            district_drift.get("row_count")
            == 3_908,
        "district_drift_deterministic":
            district_drift.get(
                "counts_by_actionability",
                {},
            ).get(
                "DETERMINISTIC_DISTRICT_DRIFT"
            ) == EXPECTED_ROWS,
        "district_drift_name_hold":
            district_drift.get(
                "counts_by_actionability",
                {},
            ).get(
                "NAME_REVIEW_REQUIRED"
            ) == 185,
        "revalidation_healthy":
            revalidation.get("healthy") is True,
        "revalidation_no_writes":
            revalidation.get(
                "database_writes_attempted"
            ) is False,
        "revalidation_rows":
            revalidation.get("row_count")
            == EXPECTED_ROWS,
        "revalidation_checks":
            all(
                revalidation.get(
                    "checks",
                    {},
                ).values()
            ),
        "revalidation_unauthorized":
            revalidation.get(
                "authorization",
                {},
            ).get("authorized") is False,
    }

    failed = sorted(
        key
        for key, value in checks.items()
        if not value
    )

    if failed:
        raise ValueError(
            "PINNED_EVIDENCE_VALIDATION_FAILED:"
            + ",".join(failed)
        )


def normalized_manifest_row(
    row: dict[str, Any],
    runtime_geometry: dict[str, Any],
) -> dict[str, Any]:
    keys = (
        "source_state",
        "source_feature_index",
        "candidate_id",
        "source_feature_id",
        "import_batch_id",
        "source_geometry_hash",
        "source_district_code",
        "source_subdistrict_code",
        "source_village_code",
        "source_village_name",
        "source_matched_block_id",
        "source_matched_block_code",
        "source_matched_block_name",
        "canonical_state_id",
        "canonical_state_lgd_code",
        "canonical_district_id",
        "canonical_district_lgd_code",
        "canonical_village_block_id",
        "canonical_village_block_code",
        "canonical_village_block_name",
        "canonical_village_id",
        "canonical_village_code",
        "canonical_village_name",
        "parent_issue",
        "name_disposition",
        "confidence",
        "proposed_scope",
        "source_codes",
        "source_names",
        "match_evidence",
        "geometry_validation_status",
        "eligible_for_runtime_after_promotion",
        "transformed_bbox",
        "transformed_centroid",
        "geometry_repair",
    )

    item = {
        key: row.get(key)
        for key in keys
    }
    item["runtime_geometry_sha256"] = (
        canonical_checksum(runtime_geometry)
    )
    item["row_sha256"] = canonical_checksum(item)
    return item


def main() -> int:
    options = arguments()
    validate_pinned_evidence()

    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("""
                select set_config(
                  'statement_timeout',
                  '600000ms',
                  true
                )
            """))
            rows = selected_rows(connection)

            candidate_ids = [
                row["candidate_id"]
                for row in rows
            ]
            source_feature_ids = [
                row["source_feature_id"]
                for row in rows
            ]

            collisions = dict(
                connection.execute(
                    text("""
                        select
                          (
                            select count(*)::bigint
                            from geography_boundary_runtime_crosswalks
                            where source_candidate_id =
                              any(cast(
                                :candidate_ids as uuid[]
                              ))
                          ) as candidate_crosswalks,
                          (
                            select count(*)::bigint
                            from geography_boundary_runtime_features
                            where source_feature_id =
                              any(cast(
                                :source_feature_ids as uuid[]
                              ))
                          ) as source_features
                    """),
                    {
                        "candidate_ids": candidate_ids,
                        "source_feature_ids":
                            source_feature_ids,
                    },
                ).mappings().one()
            )
        finally:
            transaction.rollback()

    by_state = Counter(
        row["source_state"]
        for row in rows
    )
    by_parent = Counter(
        row["parent_issue"]
        for row in rows
    )
    by_name = Counter(
        row["name_disposition"]
        for row in rows
    )

    identity_checks = {
        "row_count":
            len(rows) == EXPECTED_ROWS,
        "candidate_identity":
            len({
                row["candidate_id"]
                for row in rows
            }) == EXPECTED_ROWS,
        "source_feature_identity":
            len({
                row["source_feature_id"]
                for row in rows
            }) == EXPECTED_ROWS,
        "target_village_identity":
            len({
                row["canonical_village_id"]
                for row in rows
            }) == EXPECTED_ROWS,
        "state_counts":
            by_state == Counter(EXPECTED_BY_STATE),
        "parent_issue_counts":
            by_parent
            == Counter(EXPECTED_BY_PARENT_ISSUE),
        "name_disposition_counts":
            by_name
            == Counter(
                EXPECTED_BY_NAME_DISPOSITION
            ),
        "runtime_identity_collisions":
            all(
                int(value or 0) == 0
                for value in collisions.values()
            ),
        "active_target_collisions":
            not any(
                row["active_runtime_exists"]
                for row in rows
            ),
        "inactive_target_collisions":
            not any(
                row["inactive_runtime_exists"]
                for row in rows
            ),
        "repaired_geometry_identity":
            {
                str(row["source_feature_id"])
                for row in rows
                if row.get("geometry_repair")
                is not None
            }
            == set(EXPECTED_REPAIRED_ROWS),
    }

    failed = sorted(
        key
        for key, value in identity_checks.items()
        if not value
    )
    if failed:
        raise ValueError(
            "MANIFEST_IDENTITY_VALIDATION_FAILED:"
            + ",".join(failed)
        )

    grouped: dict[
        str,
        list[dict[str, Any]],
    ] = defaultdict(list)

    for row in rows:
        grouped[row["source_state"]].append(row)

    state_manifests = []
    national_row_hashes = []

    for sequence, state_name in enumerate(
        EXPECTED_BY_STATE,
        start=1,
    ):
        state_rows = grouped[state_name]
        source_config = STATE_SOURCE[state_name]
        source_path = (
            SOURCE_ROOT / source_config["file"]
        )

        if (
            len(state_rows)
            != EXPECTED_BY_STATE[state_name]
        ):
            raise ValueError(
                "STATE_ROW_COUNT_MISMATCH:"
                f"{state_name}:{len(state_rows)}"
            )

        if {
            row["import_batch_id"]
            for row in state_rows
        } != {source_config["import_batch_id"]}:
            raise ValueError(
                f"IMPORT_BATCH_MISMATCH:{state_name}"
            )

        actual_file_sha256 = sha256_file(source_path)
        if actual_file_sha256 != source_config["sha256"]:
            raise ValueError(
                "SOURCE_FILE_CHECKSUM_MISMATCH:"
                f"{state_name}"
            )

        rows_by_index = {
            int(row["source_feature_index"]): row
            for row in state_rows
        }

        if len(rows_by_index) != len(state_rows):
            raise ValueError(
                f"DUPLICATE_SOURCE_INDEX:{state_name}"
            )

        expected_geometry_hashes = {
            index: row["source_geometry_hash"]
            for index, row in rows_by_index.items()
        }
        observed_indexes = set()

        for index, feature in stream_geojson_features(
            source_path
        ):
            expected_hash = (
                expected_geometry_hashes.get(index)
            )
            if expected_hash is None:
                continue

            geometry = feature.get("geometry")
            if not isinstance(geometry, dict):
                raise ValueError(
                    "SOURCE_GEOMETRY_MISSING:"
                    f"{state_name}:{index}"
                )

            actual_hash = geometry_hash(geometry)

            if actual_hash != expected_hash:
                row = rows_by_index[index]
                feature_id = str(
                    row["source_feature_id"]
                )
                expected_repair = (
                    EXPECTED_REPAIRED_ROWS.get(
                        feature_id
                    )
                )
                repair = row.get("geometry_repair")

                if expected_repair is None:
                    raise ValueError(
                        "UNAUTHORIZED_GEOMETRY_REPAIR:"
                        f"{state_name}:{index}:"
                        f"{feature_id}"
                    )

                if (
                    expected_repair["state"]
                    != state_name
                    or expected_repair["index"]
                       != index
                    or expected_repair[
                        "geometry_hash"
                    ] != expected_hash
                    or not isinstance(repair, dict)
                    or repair.get("method")
                       != "SHAPELY_MAKE_VALID"
                    or repair.get(
                        "proposal_checksum"
                    ) != REPAIR_PROPOSAL_CHECKSUM
                    or repair.get(
                        "authorization_checksum"
                    ) != (
                        REPAIR_AUTHORIZATION_CHECKSUM
                    )
                    or repair.get("row_checksum")
                       != expected_repair[
                           "row_checksum"
                       ]
                ):
                    raise ValueError(
                        "GEOMETRY_REPAIR_EVIDENCE_"
                        "MISMATCH:"
                        f"{state_name}:{index}"
                    )

                source_shape = shape(geometry)

                if source_shape.is_valid:
                    raise ValueError(
                        "REPAIR_SOURCE_UNEXPECTEDLY_"
                        "VALID:"
                        f"{state_name}:{index}"
                    )

                repaired_shape = make_valid(
                    source_shape
                )
                before_area = float(
                    source_shape.area
                )
                after_area = float(
                    repaired_shape.area
                )
                relative_change = (
                    abs(after_area - before_area)
                    / before_area
                    if before_area > 0
                    else None
                )

                if (
                    repaired_shape.is_empty
                    or not repaired_shape.is_valid
                    or repaired_shape.geom_type not in {
                        "Polygon",
                        "MultiPolygon",
                    }
                    or relative_change is None
                    or relative_change > 0.000001
                    or geometry_hash(
                        mapping(repaired_shape)
                    ) != expected_hash
                ):
                    raise ValueError(
                        "GEOMETRY_REPAIR_"
                        "RECONSTRUCTION_FAILED:"
                        f"{state_name}:{index}"
                    )

            elif row := rows_by_index.get(index):
                if row.get("geometry_repair") is not None:
                    raise ValueError(
                        "REPAIR_METADATA_WITHOUT_"
                        "RAW_HASH_MISMATCH:"
                        f"{state_name}:{index}"
                    )

            observed_indexes.add(index)

        if observed_indexes != set(
            expected_geometry_hashes
        ):
            missing = sorted(
                set(expected_geometry_hashes)
                - observed_indexes
            )[:20]
            raise ValueError(
                "SOURCE_INDEX_MISSING:"
                f"{state_name}:{missing}"
            )

        runtime_geometries = reconstruct_geometries(
            source_path,
            state_rows,
        )

        manifest_rows = []

        for row in state_rows:
            index = int(
                row["source_feature_index"]
            )
            item = normalized_manifest_row(
                row,
                runtime_geometries[index],
            )
            manifest_rows.append(item)
            national_row_hashes.append(
                item["row_sha256"]
            )

        state_hash = canonical_checksum(
            [
                row["row_sha256"]
                for row in manifest_rows
            ]
        )

        state_manifests.append({
            "sequence": sequence,
            "state": state_name,
            "state_lgd_code":
                source_config["state_lgd_code"],
            "import_batch_id":
                source_config["import_batch_id"],
            "source_file":
                str(source_path.resolve()),
            "source_file_sha256":
                actual_file_sha256,
            "source_file_size_bytes":
                source_path.stat().st_size,
            "row_count": len(manifest_rows),
            "first_source_feature_index":
                manifest_rows[0][
                    "source_feature_index"
                ],
            "last_source_feature_index":
                manifest_rows[-1][
                    "source_feature_index"
                ],
            "ordered_row_manifest_sha256":
                state_hash,
            "rows": manifest_rows,
        })

        print(
            state_name,
            len(manifest_rows),
            state_hash,
            file=sys.stderr,
            flush=True,
        )

    if len(state_manifests) != EXPECTED_STATES:
        raise ValueError("STATE_COUNT_MISMATCH")

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "mode": "READ_ONLY_MANIFEST",
        "status": "PROPOSAL_EVIDENCE_ONLY",
        "healthy": True,
        "authorized": False,
        "database_writes_attempted": False,
        "expected_row_count": EXPECTED_ROWS,
        "row_count": len(national_row_hashes),
        "state_count": len(state_manifests),
        "no_canonical_audit_sha256":
            NO_CANONICAL_AUDIT_SHA256,
        "district_drift_audit_sha256":
            DISTRICT_DRIFT_AUDIT_SHA256,
        "runtime_revalidation_sha256":
            RUNTIME_REVALIDATION_SHA256,
        "selector_script_sha256":
            SELECTOR_SCRIPT_SHA256,
        "geometry_hash_algorithm":
            "NWDP_GEOJSON_GEOMETRY_CANONICAL_V1",
        "runtime_geometry_reconstruction":
            "NATIONAL_RUNTIME_STATE_ENGINE_V1",
        "ordered_national_row_manifest_sha256":
            canonical_checksum(
                national_row_hashes
            ),
        "runtime_collisions": collisions,
        "counts_by_state":
            dict(sorted(by_state.items())),
        "counts_by_parent_issue":
            dict(sorted(by_parent.items())),
        "counts_by_name_disposition":
            dict(sorted(by_name.items())),
        "checks": identity_checks,
        "guardrails": {
            "candidate_rows_changed": False,
            "source_rows_changed": False,
            "runtime_rows_changed": False,
            "runtime_activation_changed": False,
            "lookup_changed": False,
            "project_matches_changed": False,
            "source_files_changed": False,
            "android_changed": False,
        },
        "states": state_manifests,
    }

    manifest["manifest_checksum"] = (
        canonical_checksum(manifest)
    )

    atomic_write_json(options.output, manifest)

    print(json.dumps({
        "healthy": True,
        "authorized": False,
        "output": str(options.output.resolve()),
        "row_count": manifest["row_count"],
        "state_count": manifest["state_count"],
        "ordered_national_row_manifest_sha256":
            manifest[
                "ordered_national_row_manifest_sha256"
            ],
        "manifest_checksum":
            manifest["manifest_checksum"],
        "database_writes_attempted": False,
    }, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({
            "schema_version": SCHEMA_VERSION,
            "healthy": False,
            "fail_closed": True,
            "authorized": False,
            "database_writes_attempted": False,
            "error": f"{type(exc).__name__}:{exc}",
        }, indent=2, sort_keys=True), file=sys.stderr)
        raise SystemExit(1)

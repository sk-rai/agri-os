#!/usr/bin/env python3
"""Build the post-LGD deterministic inactive-staging manifest and proposal.

Database behavior: read-only. The output is proposal evidence only and grants
no authorization.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from shapely.geometry import mapping, shape
from shapely.validation import make_valid

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
SCRIPT_DIR = Path(__file__).resolve().parent

for path in (BACKEND, SCRIPT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from lgd_priority_state_common import (
    DEFAULT_OUTPUT_DIR,
    atomic_write_json,
    canonical_checksum,
    sha256_file,
)
from build_nwdp_normalized_direct_rehabilitation_manifest import (
    REPAIR_AUTHORIZATION_CHECKSUM,
    REPAIR_PROPOSAL_CHECKSUM,
    SOURCE_ROOT,
    STATE_CONFIG,
    geometry_hash,
)
from run_national_direct_village_runtime_state import (
    reconstruct_geometries,
    stream_geojson_features,
)

SCHEMA_VERSION = "nwdp_post_lgd_staging_manifest.v1"
PROPOSAL_SCHEMA_VERSION = "nwdp_post_lgd_staging_proposal.v1"

DEFAULT_ROWS = (
    DEFAULT_OUTPUT_DIR
    / "nwdp_post_lgd_staging_revalidation.jsonl"
)
DEFAULT_REVALIDATION = (
    DEFAULT_OUTPUT_DIR
    / "nwdp_post_lgd_staging_revalidation.json"
)
DEFAULT_ACTIONABILITY = (
    DEFAULT_OUTPUT_DIR
    / "nwdp_post_lgd_actionability_audit_v2.json"
)
DEFAULT_MANIFEST = (
    DEFAULT_OUTPUT_DIR
    / "nwdp_post_lgd_staging_manifest.json"
)
DEFAULT_PROPOSAL = (
    DEFAULT_OUTPUT_DIR
    / "nwdp_post_lgd_staging_proposal.json"
)

SELECTOR_SCRIPT = (
    SCRIPT_DIR
    / "nwdp_post_lgd_staging_selector.py"
)

ROWS_SHA256 = (
    "65966a6f07f0f5273744871b69cca45b"
    "6d1f33747893705cf4a3aa1263d99850"
)
REVALIDATION_SHA256 = (
    "d9e278b1f38fbe867997d17b96819fe1"
    "1e31ef5aeb145673fc2ea44385ed17c0"
)
ACTIONABILITY_SHA256 = (
    "cde548a919eaba5475c93942c9637e76"
    "5408a3d385d885f2cdaaee7c9e6a89ed"
)
SELECTOR_SCRIPT_SHA256 = (
    "3c462aa3c5dda291c1c7df4e1bf80bde"
    "001533b4f2a72756571ed861f875b3c4"
)

EXPECTED_ROWS = 17_498
EXPECTED_STATES = 8
EXPECTED_BY_STATE = {
    "Delhi": 8,
    "Haryana": 1_922,
    "Himachal Pradesh": 2_433,
    "Jammu & Kashmir": 821,
    "Ladakh": 21,
    "Punjab": 1_625,
    "Rajasthan": 9_309,
    "Uttarakhand": 1_359,
}
EXPECTED_BY_NAME = {
    "EXACT_OR_PUNCTUATION_MATCH": 11_558,
    "TRAILING_NUMERIC_SUFFIX_ONLY": 5_940,
}
EXPECTED_BY_RESOLUTION = {
    "RESOLVED_SAME_EXPECTED_DISTRICT": 16_122,
    "RESOLVED_SAME_STATE_OTHER_DISTRICT": 1_376,
}

EXPECTED_REPAIRS = {
    "800179eb-2e33-5e54-a5c8-67fa4522f71c": {
        "state": "Rajasthan",
        "index": 4_692,
        "geometry_hash":
            "8841a175ddfc0d3099b3e3fffbf0edb0"
            "8d5b8f1cee3d467b73c1c368686adc6d",
        "row_checksum":
            "3a999d58a46611d3d31ecf49c27a739"
            "2129b9269eb966676b34d57d0af893a1d",
    },
}

STATE_SOURCE = {
    config["state"]: config
    for config in STATE_CONFIG
}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(
                    f"JSONL_OBJECT_REQUIRED:{path}:{number}"
                )
            rows.append(value)
    return rows


def validate_pin(
    path: Path,
    expected: str,
    label: str,
) -> None:
    if not path.is_file():
        raise ValueError(f"{label}_NOT_FOUND:{path}")
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(
            f"{label}_PIN_MISMATCH:"
            f"expected={expected}:actual={actual}"
        )


def manifest_row(
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
        "source_district_name",
        "source_subdistrict_name",
        "source_village_name",
        "canonical_state_id",
        "canonical_state_lgd_code",
        "canonical_state_name",
        "canonical_district_id",
        "canonical_district_lgd_code",
        "canonical_district_name",
        "canonical_block_id",
        "canonical_block_lgd_code",
        "canonical_block_name",
        "canonical_village_id",
        "canonical_village_code",
        "canonical_village_name",
        "post_import_disposition",
        "nwdp_name_disposition",
        "actionability",
        "candidate_bucket",
        "review_status",
        "promotion_status",
        "source_codes",
        "source_names",
        "match_evidence",
        "confidence",
        "proposed_scope",
        "geometry_validation_status",
        "eligible_for_runtime_after_promotion",
        "transformed_bbox",
        "transformed_centroid",
        "geometry_repair",
        "input_row_checksum",
        "selector_row_checksum",
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


def validate_repair(
    row: dict[str, Any],
    raw_geometry: dict[str, Any],
    raw_hash: str,
) -> None:
    source_feature_id = str(row["source_feature_id"])
    expected = EXPECTED_REPAIRS.get(source_feature_id)
    repair = row.get("geometry_repair")

    if raw_hash == row["source_geometry_hash"]:
        if repair is not None:
            raise ValueError(
                "REPAIR_METADATA_WITHOUT_HASH_DIFFERENCE:"
                f"{row['source_state']}:"
                f"{row['source_feature_index']}"
            )
        return

    if expected is None:
        raise ValueError(
            "UNAUTHORIZED_GEOMETRY_REPAIR:"
            f"{row['source_state']}:"
            f"{row['source_feature_index']}:"
            f"{source_feature_id}"
        )

    if (
        expected["state"] != row["source_state"]
        or expected["index"]
        != int(row["source_feature_index"])
        or expected["geometry_hash"]
        != row["source_geometry_hash"]
        or not isinstance(repair, dict)
        or repair.get("method")
        != "SHAPELY_MAKE_VALID"
        or repair.get("proposal_checksum")
        != REPAIR_PROPOSAL_CHECKSUM
        or repair.get("authorization_checksum")
        != REPAIR_AUTHORIZATION_CHECKSUM
        or repair.get("row_checksum")
        != expected["row_checksum"]
    ):
        raise ValueError(
            "GEOMETRY_REPAIR_EVIDENCE_MISMATCH:"
            f"{row['source_state']}:"
            f"{row['source_feature_index']}"
        )

    source_shape = shape(raw_geometry)
    if source_shape.is_valid:
        raise ValueError(
            "REPAIR_SOURCE_UNEXPECTEDLY_VALID:"
            f"{row['source_state']}:"
            f"{row['source_feature_index']}"
        )

    repaired = make_valid(source_shape)
    before_area = float(source_shape.area)
    after_area = float(repaired.area)
    relative_change = (
        abs(after_area - before_area) / before_area
        if before_area > 0
        else None
    )

    if (
        repaired.is_empty
        or not repaired.is_valid
        or repaired.geom_type not in {
            "Polygon",
            "MultiPolygon",
        }
        or relative_change is None
        or relative_change > 0.000001
        or geometry_hash(mapping(repaired))
        != row["source_geometry_hash"]
    ):
        raise ValueError(
            "GEOMETRY_REPAIR_RECONSTRUCTION_FAILED:"
            f"{row['source_state']}:"
            f"{row['source_feature_index']}"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rows",
        type=Path,
        default=DEFAULT_ROWS,
    )
    parser.add_argument(
        "--revalidation",
        type=Path,
        default=DEFAULT_REVALIDATION,
    )
    parser.add_argument(
        "--actionability",
        type=Path,
        default=DEFAULT_ACTIONABILITY,
    )
    parser.add_argument(
        "--manifest-output",
        type=Path,
        default=DEFAULT_MANIFEST,
    )
    parser.add_argument(
        "--proposal-output",
        type=Path,
        default=DEFAULT_PROPOSAL,
    )
    args = parser.parse_args()

    try:
        validate_pin(
            args.rows,
            ROWS_SHA256,
            "REVALIDATION_ROWS",
        )
        validate_pin(
            args.revalidation,
            REVALIDATION_SHA256,
            "REVALIDATION_SUMMARY",
        )
        validate_pin(
            args.actionability,
            ACTIONABILITY_SHA256,
            "ACTIONABILITY_AUDIT",
        )
        validate_pin(
            SELECTOR_SCRIPT,
            SELECTOR_SCRIPT_SHA256,
            "SELECTOR_SCRIPT",
        )

        revalidation = load_json(args.revalidation)
        actionability = load_json(args.actionability)
        rows = load_jsonl(args.rows)

        if (
            revalidation.get("healthy") is not True
            or actionability.get("healthy") is not True
        ):
            raise ValueError(
                "PINNED_INPUT_NOT_HEALTHY"
            )
        if (
            revalidation.get(
                "database_writes_attempted"
            ) is not False
            or actionability.get(
                "database_writes_attempted"
            ) is not False
        ):
            raise ValueError(
                "PINNED_INPUT_WRITE_FLAG"
            )

        by_state = Counter(
            row["source_state"]
            for row in rows
        )
        by_name = Counter(
            row["nwdp_name_disposition"]
            for row in rows
        )
        by_resolution = Counter(
            row["post_import_disposition"]
            for row in rows
        )

        repair_ids = {
            str(row["source_feature_id"])
            for row in rows
            if row.get("geometry_repair") is not None
        }

        identity_checks = {
            "row_count":
                len(rows) == EXPECTED_ROWS,
            "state_count":
                len(by_state) == EXPECTED_STATES,
            "state_counts":
                by_state
                == Counter(EXPECTED_BY_STATE),
            "name_counts":
                by_name
                == Counter(EXPECTED_BY_NAME),
            "resolution_counts":
                by_resolution
                == Counter(EXPECTED_BY_RESOLUTION),
            "candidate_identity_unique":
                len({
                    row["candidate_id"]
                    for row in rows
                }) == EXPECTED_ROWS,
            "source_feature_identity_unique":
                len({
                    row["source_feature_id"]
                    for row in rows
                }) == EXPECTED_ROWS,
            "target_village_identity_unique":
                len({
                    row["canonical_village_id"]
                    for row in rows
                }) == EXPECTED_ROWS,
            "repair_scope_exact":
                repair_ids == set(EXPECTED_REPAIRS),
            "runtime_features_absent":
                all(
                    not row["runtime_feature_exists"]
                    for row in rows
                ),
            "runtime_crosswalks_absent":
                all(
                    not row["runtime_crosswalk_exists"]
                    for row in rows
                ),
            "project_matches_absent":
                all(
                    not row["project_match_exists"]
                    for row in rows
                ),
            "not_authorized": True,
            "no_database_writes": True,
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
        national_hashes = []

        ordered_states = sorted(
            EXPECTED_BY_STATE,
            key=lambda state: int(
                STATE_SOURCE[state]["state_lgd_code"]
            ),
        )

        for sequence, state_name in enumerate(
            ordered_states,
            start=1,
        ):
            state_rows = grouped[state_name]
            state_rows.sort(
                key=lambda row: (
                    int(row["source_feature_index"]),
                    row["candidate_id"],
                )
            )

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

            import_batches = {
                row["import_batch_id"]
                for row in state_rows
            }
            if import_batches != {
                source_config["import_batch_id"]
            }:
                raise ValueError(
                    f"IMPORT_BATCH_MISMATCH:{state_name}"
                )

            source_hash = sha256_file(source_path)
            if source_hash != source_config["sha256"]:
                raise ValueError(
                    "SOURCE_FILE_HASH_MISMATCH:"
                    f"{state_name}:{source_hash}"
                )

            rows_by_index = {
                int(row["source_feature_index"]): row
                for row in state_rows
            }
            if len(rows_by_index) != len(state_rows):
                raise ValueError(
                    f"DUPLICATE_SOURCE_INDEX:{state_name}"
                )

            observed = set()

            for index, feature in stream_geojson_features(
                source_path
            ):
                row = rows_by_index.get(index)
                if row is None:
                    continue

                geometry = feature.get("geometry")
                if not isinstance(geometry, dict):
                    raise ValueError(
                        "SOURCE_GEOMETRY_MISSING:"
                        f"{state_name}:{index}"
                    )

                validate_repair(
                    row,
                    geometry,
                    geometry_hash(geometry),
                )
                observed.add(index)

            if observed != set(rows_by_index):
                missing = sorted(
                    set(rows_by_index) - observed
                )[:20]
                raise ValueError(
                    "SOURCE_INDEX_MISSING:"
                    f"{state_name}:{missing}"
                )

            runtime_geometries = (
                reconstruct_geometries(
                    source_path,
                    state_rows,
                )
            )

            manifest_rows = []
            for row in state_rows:
                index = int(
                    row["source_feature_index"]
                )
                item = manifest_row(
                    row,
                    runtime_geometries[index],
                )
                manifest_rows.append(item)
                national_hashes.append(
                    item["row_sha256"]
                )

            state_hash = canonical_checksum([
                row["row_sha256"]
                for row in manifest_rows
            ])

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
                    source_hash,
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

        manifest = {
            "schema_version": SCHEMA_VERSION,
            "mode": "READ_ONLY_MANIFEST",
            "status": "MANIFESTED_NOT_AUTHORIZED",
            "healthy": True,
            "authorized": False,
            "database_writes_attempted": False,
            "row_count": len(national_hashes),
            "state_count": len(state_manifests),
            "counts_by_state":
                dict(sorted(by_state.items())),
            "counts_by_name_disposition":
                dict(sorted(by_name.items())),
            "counts_by_resolution":
                dict(sorted(by_resolution.items())),
            "source_pins": {
                args.rows.name:
                    ROWS_SHA256,
                args.revalidation.name:
                    REVALIDATION_SHA256,
                args.actionability.name:
                    ACTIONABILITY_SHA256,
                SELECTOR_SCRIPT.name:
                    SELECTOR_SCRIPT_SHA256,
            },
            "geometry_hash_algorithm":
                "NWDP_GEOJSON_GEOMETRY_CANONICAL_V1",
            "runtime_geometry_reconstruction":
                "NATIONAL_RUNTIME_STATE_ENGINE_V1",
            "ordered_national_row_manifest_sha256":
                canonical_checksum(national_hashes),
            "checks": identity_checks,
            "guardrails": {
                "candidate_activation_changed":
                    False,
                "candidate_identity_changed":
                    False,
                "candidate_promotion_changed":
                    False,
                "canonical_geography_changed":
                    False,
                "runtime_activation_changed":
                    False,
                "lookup_changed": False,
                "project_matches_written": False,
                "source_files_written": False,
                "source_geometry_written": False,
                "android_changed": False,
            },
            "states": state_manifests,
        }
        manifest["manifest_checksum"] = (
            canonical_checksum(manifest)
        )
        atomic_write_json(
            args.manifest_output,
            manifest,
        )

        proposal = {
            "schema_version":
                PROPOSAL_SCHEMA_VERSION,
            "status": "PROPOSED_NOT_AUTHORIZED",
            "healthy": True,
            "authorized": False,
            "database_writes_attempted": False,
            "manifest_checksum":
                manifest["manifest_checksum"],
            "manifest_file_sha256":
                sha256_file(args.manifest_output),
            "ordered_national_row_manifest_sha256":
                manifest[
                    "ordered_national_row_manifest_sha256"
                ],
            "row_count": EXPECTED_ROWS,
            "state_count": EXPECTED_STATES,
            "counts_by_state":
                manifest["counts_by_state"],
            "excluded": {
                "name_review_rows": 2_867,
                "canonical_reparent_rows": 1_076,
                "absent_current_lgd_rows": 400,
                "other_structural_rows": 378,
            },
            "permissions": {
                "bounded_review_metadata_write_allowed":
                    False,
                "bounded_runtime_eligibility_write_allowed":
                    False,
                "inactive_runtime_feature_write_allowed":
                    False,
                "inactive_runtime_crosswalk_write_allowed":
                    False,
                "inactive_promotion_event_write_allowed":
                    False,
                "native_geometry_write_allowed":
                    False,
                "checkpoint_write_allowed":
                    False,
                "runtime_activation_change_allowed":
                    False,
                "lookup_scope_change_allowed":
                    False,
                "candidate_activation_allowed":
                    False,
                "candidate_identity_change_allowed":
                    False,
                "candidate_promotion_allowed":
                    False,
                "canonical_geography_write_allowed":
                    False,
                "project_match_write_allowed":
                    False,
                "source_file_write_allowed":
                    False,
                "source_geometry_write_allowed":
                    False,
                "android_behavior_change_allowed":
                    False,
            },
        }
        proposal["proposal_checksum"] = (
            canonical_checksum(proposal)
        )
        atomic_write_json(
            args.proposal_output,
            proposal,
        )

        print(json.dumps({
            "healthy": True,
            "authorized": False,
            "database_writes_attempted": False,
            "row_count": EXPECTED_ROWS,
            "state_count": EXPECTED_STATES,
            "manifest_checksum":
                manifest["manifest_checksum"],
            "manifest_file_sha256":
                sha256_file(args.manifest_output),
            "proposal_checksum":
                proposal["proposal_checksum"],
            "proposal_file_sha256":
                sha256_file(args.proposal_output),
            "ordered_national_row_manifest_sha256":
                manifest[
                    "ordered_national_row_manifest_sha256"
                ],
            "output_manifest":
                str(args.manifest_output.resolve()),
            "output_proposal":
                str(args.proposal_output.resolve()),
        }, indent=2, sort_keys=True))

        return 0

    except Exception as exc:
        print(json.dumps({
            "schema_version": SCHEMA_VERSION,
            "healthy": False,
            "fail_closed": True,
            "authorized": False,
            "database_writes_attempted": False,
            "error": f"{type(exc).__name__}:{exc}",
        }, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

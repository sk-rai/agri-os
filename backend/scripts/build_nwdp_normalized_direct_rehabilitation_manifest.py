from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from collections import defaultdict
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
from scripts.run_national_direct_village_runtime_state import (
    atomic_write_json,
    canonical_checksum,
    reconstruct_geometries,
    sha256_file,
    stream_geojson_features,
)

SCHEMA_VERSION = (
    "nwdp_normalized_direct_rehabilitation_manifest.v1"
)
AUDIT_SCRIPT = (
    BACKEND_ROOT
    / "scripts"
    / "audit_nwdp_deterministic_name_normalization.py"
)
AUDIT_SCRIPT_SHA256 = (
    "3dae5960f07d7eceea851cea0ae79d2b"
    "6ae4fa7008ee6e1a83ffac3ff430adf8"
)
AUDIT_REPORT = (
    PROJECT_ROOT
    / "data/staged/core_stack/promotion_review/"
    / "20260923-normalized-direct-village-rehabilitation-v1/"
    / "deterministic_name_normalization_audit.json"
)
AUDIT_REPORT_SHA256 = (
    "929f6a68ec9664f302f7d4f78ce6e0c"
    "8dcbe6b3368152bcd4772fdaab14640b8"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "data/staged/core_stack/promotion_review/"
    / "20260923-normalized-direct-village-rehabilitation-v1/"
    / "normalized_direct_rehabilitation_manifest.json"
)
EXPECTED_ROWS = 49_606
EXPECTED_STATES = 8

STATE_CONFIG = (
    {
        "sequence": 1,
        "state": "Delhi",
        "state_lgd_code": "7",
        "expected_rows": 33,
        "import_batch_id":
            "99077b8f-119d-5a00-9641-feadd2bb2e06",
        "file": "delhi.geojson",
        "sha256":
            "0411a0da45bb021ef95c82572a9d7966"
            "a0f11bd2ca45dbc7eb9cf909e0e507a9",
    },
    {
        "sequence": 2,
        "state": "Haryana",
        "state_lgd_code": "6",
        "expected_rows": 1_373,
        "import_batch_id":
            "3b5a631e-1c4f-5d24-b63b-7fdeaa1f1e22",
        "file": "haryana.geojson",
        "sha256":
            "d39dda744162fec3e20943ea6a5d67bb"
            "eddad82d102ee68f0567994ab7fdc54f",
    },
    {
        "sequence": 3,
        "state": "Himachal Pradesh",
        "state_lgd_code": "2",
        "expected_rows": 8_446,
        "import_batch_id":
            "c3d65ddc-ef3c-594f-99c9-044f475e1d40",
        "file": "himachal_pradesh.geojson",
        "sha256":
            "ef14c3c18e41a631ddb7014db9385959"
            "96c3836f65250f67d4a4cbd6b335bf5a",
    },
    {
        "sequence": 4,
        "state": "Jammu & Kashmir",
        "state_lgd_code": "1",
        "expected_rows": 3_595,
        "import_batch_id":
            "989f3796-a0c2-5dc6-9ef3-08f1e3dc7ba1",
        "file": "jammu_kashmir.geojson",
        "sha256":
            "bd1bcd4cec614cca521f09dc1160a752"
            "54f3120bee5dd0ad7f521280c3d9a155",
    },
    {
        "sequence": 5,
        "state": "Ladakh",
        "state_lgd_code": "37",
        "expected_rows": 59,
        "import_batch_id":
            "92302ea2-24bb-5d94-8420-7914b8ee34b1",
        "file": "ladakh.geojson",
        "sha256":
            "29a230f5a27e2ed423896272c540456b"
            "9c405b3e33f288f0b81c2249c2f233e5",
    },
    {
        "sequence": 6,
        "state": "Punjab",
        "state_lgd_code": "3",
        "expected_rows": 5_747,
        "import_batch_id":
            "fce1db5d-2c16-5a92-9f2a-86b1cd199ea9",
        "file": "punjab.geojson",
        "sha256":
            "37abcedd638eb93ad5c55b4a3b560048"
            "2f0b9834a7779021b92c9e5749393424",
    },
    {
        "sequence": 7,
        "state": "Rajasthan",
        "state_lgd_code": "8",
        "expected_rows": 19_458,
        "import_batch_id":
            "1739144c-184a-5dd3-a677-2f820a65adbd",
        "file": "rajasthan.geojson",
        "sha256":
            "fbfffeba1d6918adf882f95964bf25cd"
            "55e3adaf886138a044a4f1ad7dbd9364",
    },
    {
        "sequence": 8,
        "state": "Uttarakhand",
        "state_lgd_code": "5",
        "expected_rows": 10_895,
        "import_batch_id":
            "270e12e0-d49c-56d6-a6c7-7b9c06bad0d5",
        "file": "uttarakhand.geojson",
        "sha256":
            "5b3d40c3af0e711c31e0e9ff08013f19"
            "a7e162d15ff3dd785b4cb5293cba1ad6",
    },
)

SOURCE_ROOT = (
    PROJECT_ROOT
    / "data/raw/nwdp_boundary_all_state/20260824T110250Z"
)


REPAIR_PROPOSAL_CHECKSUM = (
    "560fcd926530ff694e139559b1ddf2ef"
    "070192f22e571678e195946d4907ba2a"
)
REPAIR_AUTHORIZATION_CHECKSUM = (
    "d3fe59a5650c6c8cbeacf9a827d0f7a"
    "e2ee69f6e9927c8d1089c9c59fcc2964b"
)
REPAIRED_ROWS = {
    "55fadfdb-d554-569e-b813-b11eb39764f3": {
        "state": "Himachal Pradesh",
        "index": 19236,
        "geometry_hash":
            "bfd61cfb40efec1056b29215be55d361"
            "ecbf71c042d759af315d838746d50483",
        "row_checksum":
            "6de5929775f1f69f4a094639ef8a0a319"
            "4d5525464cae2fbdf025b53b5913e90",
    },
    "ae819be5-73ae-5141-850e-b6f28e46363d": {
        "state": "Rajasthan",
        "index": 19314,
        "geometry_hash":
            "f2f8c03558b06b56845392b4f7cd7f0b"
            "eab655459cc3381b2cb2e9fd033705ef",
        "row_checksum":
            "ada5245190d9a233db47274c2cbed654e"
            "849591b0fbee4d6c4c2f649e4bdf96a",
    },
    "9b21eade-63ff-57d1-b7c8-88fc21c90bfc": {
        "state": "Uttarakhand",
        "index": 14918,
        "geometry_hash":
            "7ccbbd82f5af6281c2c9c7937fdcc872"
            "2cc3322a2ccc93d5259fab7a03c32df0",
        "row_checksum":
            "f3e4b3076a55435f0725940ab19d2b5c"
            "c7ee589f1489777c87b6e4f38fa2446a",
    },
}


def geometry_hash(value: dict[str, Any]) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


def extract_audit_cte() -> str:
    source = AUDIT_SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)

    audit_sql: str | None = None

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue

        if not any(
            isinstance(target, ast.Name)
            and target.id == "AUDIT_SQL"
            for target in node.targets
        ):
            continue

        if (
            isinstance(node.value, ast.Call)
            and node.value.args
            and isinstance(node.value.args[0], ast.Constant)
            and isinstance(node.value.args[0].value, str)
        ):
            audit_sql = node.value.args[0].value
            break

    if audit_sql is None:
        raise ValueError("AUDIT_SQL_NOT_FOUND")

    marker = "\nselect\n    source_state,\n    disposition,"

    if marker not in audit_sql:
        raise ValueError("AUDIT_SQL_FINAL_SELECT_NOT_FOUND")

    return audit_sql.rsplit(marker, 1)[0]


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
    )
    return parser.parse_args()


def selected_rows(connection: Any) -> list[dict[str, Any]]:
    sql = extract_audit_cte() + """
select
    classified.*,
    c.import_batch_id::text as import_batch_id,
    f.source_geometry_hash,
    f.geometry_validation_status,
    f.eligible_for_runtime_after_promotion,
    f.transformed_bbox,
    f.transformed_centroid,
    f.metadata->'geometry_repair'
      as geometry_repair,
    state.id::text as canonical_state_id,
    state.lgd_code::text as canonical_state_lgd_code,
    district.id::text as canonical_district_id,
    district.lgd_code::text as canonical_district_lgd_code,
    block.id::text as canonical_block_id,
    block.lgd_code::text as canonical_block_lgd_code
from classified
join geography_boundary_crosswalk_candidates c
  on c.id = classified.candidate_id
join geography_boundary_source_features f
  on f.id = classified.source_feature_id
join geography_villages village
  on village.id = classified.canonical_village_id
join geography_blocks block
  on block.id = village.block_id
join geography_districts district
  on district.id = village.district_id
join geography_states state
  on state.id = district.state_id
where classified.disposition in (
    'EXACT_OR_PUNCTUATION_MATCH',
    'TRAILING_NUMERIC_SUFFIX_ONLY'
)
order by
    state.lgd_code::bigint,
    classified.source_feature_index,
    classified.candidate_id
"""

    return [
        dict(row)
        for row in connection.execute(
            text(sql)
        ).mappings()
    ]


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "source_state",
        "source_feature_index",
        "candidate_id",
        "source_feature_id",
        "import_batch_id",
        "source_geometry_hash",
        "source_village_code",
        "source_village_name",
        "canonical_state_id",
        "canonical_state_lgd_code",
        "canonical_district_id",
        "canonical_district_lgd_code",
        "canonical_block_id",
        "canonical_block_lgd_code",
        "canonical_village_id",
        "canonical_village_code",
        "canonical_village_name",
        "disposition",
        "geometry_validation_status",
        "eligible_for_runtime_after_promotion",
        "transformed_bbox",
        "transformed_centroid",
        "geometry_repair",
    )

    result = {
        key: row.get(key)
        for key in keys
    }

    for key in (
        "candidate_id",
        "source_feature_id",
        "import_batch_id",
        "canonical_state_id",
        "canonical_district_id",
        "canonical_block_id",
        "canonical_village_id",
    ):
        if result[key] is not None:
            result[key] = str(result[key])

    return result


def main() -> int:
    options = arguments()

    if sha256_file(AUDIT_SCRIPT) != AUDIT_SCRIPT_SHA256:
        raise ValueError("AUDIT_SCRIPT_CHECKSUM_MISMATCH")

    if sha256_file(AUDIT_REPORT) != AUDIT_REPORT_SHA256:
        raise ValueError("AUDIT_REPORT_CHECKSUM_MISMATCH")

    audit_report = json.loads(
        AUDIT_REPORT.read_text(encoding="utf-8")
    )

    if (
        audit_report.get("healthy") is not True
        or audit_report.get(
            "strict_name_compatible_rows"
        ) != EXPECTED_ROWS
        or audit_report.get(
            "database_writes_attempted"
        ) is not False
    ):
        raise ValueError("AUDIT_REPORT_VALIDATION_FAILED")

    with engine.connect() as connection:
        transaction = connection.begin()

        connection.execute(text("""
            select set_config(
                'statement_timeout',
                '600000ms',
                true
            )
        """))

        rows = selected_rows(connection)

        candidate_ids = [
            str(row["candidate_id"])
            for row in rows
        ]
        source_feature_ids = [
            str(row["source_feature_id"])
            for row in rows
        ]

        collisions = dict(
            connection.execute(
                text("""
                    select
                      (
                        select count(*)
                        from geography_boundary_runtime_crosswalks
                        where source_candidate_id =
                          any(cast(:candidate_ids as uuid[]))
                      )::bigint as candidate_crosswalks,
                      (
                        select count(*)
                        from geography_boundary_runtime_features
                        where source_feature_id =
                          any(cast(:source_feature_ids as uuid[]))
                      )::bigint as source_features
                """),
                {
                    "candidate_ids": candidate_ids,
                    "source_feature_ids":
                        source_feature_ids,
                },
            ).mappings().one()
        )

        transaction.rollback()

    if len(rows) != EXPECTED_ROWS:
        raise ValueError(
            f"MANIFEST_ROW_COUNT_MISMATCH:{len(rows)}"
        )

    if any(int(value) != 0 for value in collisions.values()):
        raise ValueError(
            "EXISTING_RUNTIME_COLLISION:"
            + json.dumps(collisions, sort_keys=True)
        )

    grouped: dict[str, list[dict[str, Any]]] = (
        defaultdict(list)
    )

    for row in rows:
        grouped[row["source_state"]].append(row)

    states = []
    national_rows = []

    for config in STATE_CONFIG:
        state_name = config["state"]
        state_rows = grouped.get(state_name, [])

        if len(state_rows) != config["expected_rows"]:
            raise ValueError(
                "STATE_ROW_COUNT_MISMATCH:"
                f"{state_name}:{len(state_rows)}:"
                f"{config['expected_rows']}"
            )

        if {
            str(row["import_batch_id"])
            for row in state_rows
        } != {config["import_batch_id"]}:
            raise ValueError(
                f"IMPORT_BATCH_MISMATCH:{state_name}"
            )

        source_path = SOURCE_ROOT / config["file"]

        if sha256_file(source_path) != config["sha256"]:
            raise ValueError(
                f"SOURCE_FILE_CHECKSUM_MISMATCH:{state_name}"
            )

        rows_by_index = {
            int(row["source_feature_index"]): row
            for row in state_rows
        }
        expected_by_index = {
            index: row["source_geometry_hash"]
            for index, row in rows_by_index.items()
        }

        if len(rows_by_index) != len(state_rows):
            raise ValueError(
                f"DUPLICATE_SOURCE_INDEX:{state_name}"
            )

        observed_indexes = set()
        repaired_indexes = set()

        for index, feature in stream_geojson_features(
            source_path
        ):
            expected_hash = expected_by_index.get(index)

            if expected_hash is None:
                continue

            geometry = feature.get("geometry")

            if not isinstance(geometry, dict):
                raise ValueError(
                    f"SOURCE_GEOMETRY_MISSING:"
                    f"{state_name}:{index}"
                )

            actual_hash = geometry_hash(geometry)

            if actual_hash != expected_hash:
                row = rows_by_index[index]
                feature_id = str(row["source_feature_id"])
                expected_repair = REPAIRED_ROWS.get(
                    feature_id
                )
                repair = row.get("geometry_repair")

                if expected_repair is None:
                    raise ValueError(
                        "UNAUTHORIZED_GEOMETRY_REPAIR:"
                        f"{state_name}:{index}"
                    )

                if (
                    expected_repair["state"] != state_name
                    or expected_repair["index"] != index
                    or expected_repair["geometry_hash"]
                       != expected_hash
                    or not isinstance(repair, dict)
                    or repair.get("method")
                       != "SHAPELY_MAKE_VALID"
                    or repair.get("proposal_checksum")
                       != REPAIR_PROPOSAL_CHECKSUM
                    or repair.get("authorization_checksum")
                       != REPAIR_AUTHORIZATION_CHECKSUM
                    or repair.get("row_checksum")
                       != expected_repair["row_checksum"]
                ):
                    raise ValueError(
                        "GEOMETRY_REPAIR_EVIDENCE_MISMATCH:"
                        f"{state_name}:{index}"
                    )

                source_shape = shape(geometry)

                if source_shape.is_valid:
                    raise ValueError(
                        "REPAIR_SOURCE_UNEXPECTEDLY_VALID:"
                        f"{state_name}:{index}"
                    )

                repaired_shape = make_valid(source_shape)
                before_area = float(source_shape.area)
                after_area = float(repaired_shape.area)
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
                        "GEOMETRY_REPAIR_RECONSTRUCTION_FAILED:"
                        f"{state_name}:{index}"
                    )

                repaired_indexes.add(index)

            observed_indexes.add(index)

        if observed_indexes != set(expected_by_index):
            missing = sorted(
                set(expected_by_index) - observed_indexes
            )[:20]
            raise ValueError(
                f"SOURCE_INDEX_MISSING:"
                f"{state_name}:{missing}"
            )

        expected_repaired_indexes = {
            details["index"]
            for details in REPAIRED_ROWS.values()
            if details["state"] == state_name
        }

        if repaired_indexes != expected_repaired_indexes:
            raise ValueError(
                "REPAIRED_INDEX_RECONCILIATION_FAILED:"
                f"{state_name}:"
                f"{sorted(repaired_indexes)}:"
                f"{sorted(expected_repaired_indexes)}"
            )

        reconstructed = reconstruct_geometries(
            source_path,
            state_rows,
        )

        manifest_rows = []

        for row in state_rows:
            item = normalize_row(row)
            index = int(item["source_feature_index"])
            item["runtime_geometry_sha256"] = (
                canonical_checksum(reconstructed[index])
            )
            item["row_sha256"] = canonical_checksum(item)
            manifest_rows.append(item)
            national_rows.append(item["row_sha256"])

        state_manifest_sha256 = canonical_checksum(
            [row["row_sha256"] for row in manifest_rows]
        )

        states.append({
            **config,
            "source_file": str(source_path.resolve()),
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
                state_manifest_sha256,
            "rows": manifest_rows,
        })

        print(
            state_name,
            len(manifest_rows),
            state_manifest_sha256,
            file=sys.stderr,
            flush=True,
        )

    if len(states) != EXPECTED_STATES:
        raise ValueError("STATE_COUNT_MISMATCH")

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "mode": "READ_ONLY_MANIFEST",
        "healthy": True,
        "database_writes_attempted": False,
        "expected_row_count": EXPECTED_ROWS,
        "row_count": len(national_rows),
        "state_count": len(states),
        "audit_script_sha256":
            AUDIT_SCRIPT_SHA256,
        "audit_report_sha256":
            AUDIT_REPORT_SHA256,
        "geometry_hash_algorithm":
            "NWDP_GEOJSON_GEOMETRY_CANONICAL_V1",
        "runtime_geometry_reconstruction":
            "NATIONAL_RUNTIME_STATE_ENGINE_V1",
        "ordered_national_row_manifest_sha256":
            canonical_checksum(national_rows),
        "runtime_collisions": collisions,
        "guardrails": {
            "candidate_rows_changed": False,
            "source_rows_changed": False,
            "runtime_rows_changed": False,
            "project_matches_changed": False,
            "lookup_changed": False,
            "android_changed": False,
        },
        "states": states,
    }

    manifest["manifest_checksum"] = (
        canonical_checksum(manifest)
    )

    atomic_write_json(options.output, manifest)

    print(json.dumps({
        "healthy": True,
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
            "error": f"{type(exc).__name__}:{exc}",
        }, indent=2, sort_keys=True), file=sys.stderr)
        raise SystemExit(1)


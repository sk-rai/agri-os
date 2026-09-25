#!/usr/bin/env python3
"""Fail-closed NWDP parent-drift rehabilitation engine.

Permitted effects:
- approved direct-match review metadata;
- runtime eligibility;
- inactive promotion events, runtime features, and crosswalks;
- JSONB and native PostGIS runtime geometry;
- atomic state checkpoints.

Explicitly prohibited:
- runtime activation or lookup expansion;
- candidate activation or promotion;
- project-match writes;
- source geometry/file writes;
- Android behavior changes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from pyproj import CRS, Transformer
from shapely import make_valid
from shapely.geometry import mapping, shape
from shapely.ops import transform as transform_geometry
from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

CAMPAIGN_DIR = (
    ROOT
    / "data/staged/core_stack/promotion_review"
    / "20260924-nwdp-no-canonical-village-audit-v1"
)

DEFAULT_MANIFEST = (
    CAMPAIGN_DIR
    / "nwdp_district_drift_manifest.json"
)
DEFAULT_PROPOSAL = (
    CAMPAIGN_DIR
    / "nwdp_district_drift_proposal.json"
)
DEFAULT_AUTHORIZATION = (
    CAMPAIGN_DIR
    / "nwdp_district_drift_authorization.json"
)
DEFAULT_CHECKPOINT = (
    CAMPAIGN_DIR
    / "nwdp_district_drift_checkpoint.json"
)
DEFAULT_OUTPUT = (
    CAMPAIGN_DIR
    / "nwdp_district_drift_engine_report.json"
)

PROPOSAL_CHECKSUM = (
    "fabc768bab4eb8570251da9c2febf1b1"
    "5113bcff84f46b5187944c425b64724f"
)
AUTHORIZATION_CHECKSUM = (
    "3bf3f0a4dbeaec984c1d4db31d0d7283"
    "2cf205b78c097c5543d2eb46222add0e"
)
NATIONAL_MANIFEST_SHA256 = (
    "cfc95ce7d4da3b4a62367a6161037b65"
    "fe7df5b3630a5a35499ce3741d5f790e"
)
MANIFEST_CHECKSUM = (
    "cae4e558e34188cfebb950d43ec0dae9"
    "98761bdb1080f6bf5b28be6d2cedbb00"
)
MANIFEST_FILE_SHA256 = (
    "82d71abbb04c41aa46875669ea4e6888"
    "e48857762433f083df190475d9b490fb"
)
INITIAL_CHECKPOINT_CHECKSUM = (
    "cde9611420652423e5cd6ce628558d42"
    "4ecb694468dca86b9e44cff13afdb567"
)
RUNTIME_SET_ID = "e5f93e27-a0bd-5c8b-bef3-d97986e14c55"

EXPECTED_ROWS = 3_723
EXPECTED_STATES = 6
DEFAULT_BATCH_SIZE = 25_000
MAX_BATCH_SIZE = 25_000

SOURCE_CRS = "EPSG:7755"
TARGET_CRS = "EPSG:4326"

ADVISORY_LOCK_KEY = 7_621_092_023
MARKER = "nwdp_district_drift_rehabilitation"
SCHEMA_VERSION = (
    "nwdp_district_drift_state_engine.v1"
)

REVIEWER_ID = "nwdp-district-drift-rehabilitation"
REVIEWER_NOTES = (
    "Checksum-pinned district-drift village identity approved for "
    "inactive runtime staging; canonical district and hierarchy remain authoritative."
)

EXPECTED_PERMISSIONS = {
    "bounded_review_metadata_write_allowed": True,
    "bounded_runtime_eligibility_write_allowed": True,
    "inactive_runtime_crosswalk_write_allowed": True,
    "inactive_runtime_feature_write_allowed": True,
    "inactive_runtime_promotion_event_write_allowed": True,
    "native_geometry_write_allowed": True,
    "state_checkpoint_write_allowed": True,
    "android_behavior_change_allowed": False,
    "candidate_activation_allowed": False,
    "candidate_identity_change_allowed": False,
    "candidate_promotion_allowed": False,
    "canonical_geography_write_allowed": False,
    "lookup_scope_change_allowed": False,
    "project_match_write_allowed": False,
    "runtime_activation_change_allowed": False,
    "runtime_set_identity_change_allowed": False,
    "source_file_write_allowed": False,
    "source_geometry_write_allowed": False,
}

PROPOSAL_FILE_SHA256 = (
    "cedf89803883c1c0df5aea8e215d5cf"
    "7698cf3a835a80eb0c2e2813bab8f9c7e"
)
AUTHORIZATION_FILE_SHA256 = (
    "06e425badc096724ffb57da89b1fc675"
    "64b6beaffcb911ef47d0a0bf80a961bd"
)

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_checksum(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(
    path: Path,
    label: str,
) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(
            f"{label}_NOT_FOUND:{path}"
        )

    try:
        value = json.loads(
            path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"{label}_INVALID:{path}"
        ) from exc

    if not isinstance(value, dict):
        raise ValueError(
            f"{label}_INVALID:{path}"
        )

    return value


def atomic_write_json(
    path: Path,
    value: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    temporary = path.with_suffix(
        path.suffix + ".writing"
    )
    temporary.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def checkpoint_checksum(
    checkpoint: dict[str, Any],
) -> str:
    return canonical_checksum({
        key: value
        for key, value in checkpoint.items()
        if key != "checkpoint_checksum"
    })


def stable_uuid(
    kind: str,
    *parts: object,
) -> str:
    label = "|".join([
        "farmint",
        PROPOSAL_CHECKSUM,
        kind,
        *map(str, parts),
    ])
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            label,
        )
    )


def db_url() -> str:
    from app.core.config import settings

    return str(
        getattr(
            settings,
            "database_url",
            None,
        )
        or getattr(
            settings,
            "DATABASE_URL",
            None,
        )
        or (
            "postgresql+psycopg2://"
            "agri_os:agri_os_dev@localhost:5432/agri_os"
        )
    )


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--manifest-json",
        type=Path,
        default=DEFAULT_MANIFEST,
    )
    parser.add_argument(
        "--proposal-json",
        type=Path,
        default=DEFAULT_PROPOSAL,
    )
    parser.add_argument(
        "--authorization-json",
        type=Path,
        default=DEFAULT_AUTHORIZATION,
    )
    parser.add_argument(
        "--checkpoint-json",
        type=Path,
        default=DEFAULT_CHECKPOINT,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
    )
    parser.add_argument(
        "--proposal-checksum",
        default=PROPOSAL_CHECKSUM,
    )
    parser.add_argument(
        "--authorization-checksum",
        default=AUTHORIZATION_CHECKSUM,
    )
    parser.add_argument(
        "--national-manifest-sha256",
        default=NATIONAL_MANIFEST_SHA256,
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
    )
    parser.add_argument(
        "--operator",
        default=REVIEWER_ID,
    )

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--resume", action="store_true")
    mode.add_argument("--rollback", action="store_true")
    mode.add_argument(
        "--rollback-only-rehearsal",
        action="store_true",
    )

    parser.add_argument(
        "--enable-district-drift-rehabilitation-write",
        action="store_true",
    )
    parser.add_argument(
        "--authorization-reviewed",
        action="store_true",
    )
    parser.add_argument(
        "--rollback-procedure-reviewed",
        action="store_true",
    )
    parser.add_argument(
        "--admin-confirmation",
        action="store_true",
    )

    return parser.parse_args()


def validate_mutation_gates(
    options: argparse.Namespace,
) -> None:
    if not (
        1 <= options.batch_size <= MAX_BATCH_SIZE
    ):
        raise ValueError(
            "TRANSACTION_ROW_LIMIT_INVALID"
        )

    mutation_requested = (
        options.apply
        or options.resume
        or options.rollback
    )

    if not mutation_requested:
        return

    required = {
        "enable":
            options.enable_district_drift_rehabilitation_write,
        "authorization_reviewed":
            options.authorization_reviewed,
        "rollback_reviewed":
            options.rollback_procedure_reviewed,
        "admin_confirmation":
            options.admin_confirmation,
    }

    failed = sorted(
        key
        for key, value in required.items()
        if not value
    )

    if failed:
        raise ValueError(
            "MUTATION_GATES_NOT_SATISFIED:"
            + ",".join(failed)
        )


def validate_artifacts(
    options: argparse.Namespace,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    manifest = load_json(
        options.manifest_json,
        "MANIFEST_JSON",
    )
    proposal = load_json(
        options.proposal_json,
        "PROPOSAL_JSON",
    )
    authorization = load_json(
        options.authorization_json,
        "AUTHORIZATION_JSON",
    )
    checkpoint = load_json(
        options.checkpoint_json,
        "CHECKPOINT_JSON",
    )

    checks = {
        "manifest_schema":
            manifest.get("schema_version")
            == "nwdp_district_drift_manifest.v1",
        "manifest_healthy":
            manifest.get("healthy") is True,
        "manifest_unauthorized_source":
            manifest.get("authorized") is False,
        "manifest_read_only":
            manifest.get(
                "database_writes_attempted"
            ) is False,
        "manifest_file":
            sha256_file(options.manifest_json)
            == MANIFEST_FILE_SHA256,
        "manifest_checksum":
            manifest.get("manifest_checksum")
            == MANIFEST_CHECKSUM,
        "national_manifest":
            manifest.get(
                "ordered_national_row_manifest_sha256"
            )
            == options.national_manifest_sha256
            == NATIONAL_MANIFEST_SHA256,
        "proposal_schema":
            proposal.get("schema_version")
            == "nwdp_district_drift_proposal.v1",
        "proposal_status":
            proposal.get("status")
            == "PROPOSED_NOT_AUTHORIZED",
        "proposal_checksum":
            proposal.get("proposal_checksum")
            == options.proposal_checksum
            == PROPOSAL_CHECKSUM
            == canonical_checksum({
                key: value
                for key, value in proposal.items()
                if key != "proposal_checksum"
            }),
        "proposal_file":
            sha256_file(options.proposal_json)
            == PROPOSAL_FILE_SHA256,
        "proposal_manifest":
            proposal.get(
                "pinned_manifest", {}
            ).get("manifest_checksum")
            == MANIFEST_CHECKSUM,
        "proposal_manifest_file":
            proposal.get(
                "pinned_manifest", {}
            ).get("file_sha256")
            == MANIFEST_FILE_SHA256,
        "authorization_schema":
            authorization.get("schema_version")
            == "nwdp_district_drift_authorization.v1",
        "authorization_status":
            authorization.get("status")
            == "AUTHORIZED",
        "authorization_checksum":
            authorization.get(
                "authorization_checksum"
            )
            == options.authorization_checksum
            == AUTHORIZATION_CHECKSUM
            == canonical_checksum({
                key: value
                for key, value
                in authorization.items()
                if key != "authorization_checksum"
            }),
        "authorization_file":
            sha256_file(
                options.authorization_json
            )
            == AUTHORIZATION_FILE_SHA256,
        "authorization_proposal":
            authorization.get(
                "proposal_checksum"
            ) == PROPOSAL_CHECKSUM,
        "authorization_manifest":
            authorization.get(
                "manifest_checksum"
            ) == MANIFEST_CHECKSUM,
        "permissions_exact":
            authorization.get("permissions")
            == EXPECTED_PERMISSIONS,
        "row_count":
            manifest.get("row_count")
            == proposal.get(
                "proposal_scope", {}
            ).get("row_count")
            == authorization.get(
                "maximum_authorized_row_count"
            )
            == checkpoint.get(
                "authorized_row_count"
            )
            == EXPECTED_ROWS,
        "state_count":
            manifest.get("state_count")
            == proposal.get(
                "proposal_scope", {}
            ).get("state_count")
            == authorization.get(
                "authorized_state_count"
            )
            == checkpoint.get(
                "authorized_state_count"
            )
            == EXPECTED_STATES,
        "runtime_set":
            checkpoint.get("runtime_set_id")
            == RUNTIME_SET_ID,
        "checkpoint_schema":
            checkpoint.get("schema_version")
            == "nwdp_district_drift_checkpoint.v1",
        "checkpoint_manifest":
            checkpoint.get("manifest_checksum")
            == MANIFEST_CHECKSUM,
        "checkpoint_proposal":
            checkpoint.get("proposal_checksum")
            == PROPOSAL_CHECKSUM,
        "checkpoint_authorization":
            checkpoint.get(
                "authorization_checksum"
            ) == AUTHORIZATION_CHECKSUM,
        "checkpoint_national_manifest":
            checkpoint.get(
                "ordered_national_row_manifest_sha256"
            ) == NATIONAL_MANIFEST_SHA256,
        "checkpoint_checksum":
            checkpoint.get("checkpoint_checksum")
            == checkpoint_checksum(checkpoint),
        "checkpoint_state_count":
            len(checkpoint.get("states") or [])
            == EXPECTED_STATES,
        "transaction_limit":
            authorization.get(
                "execution_requirements", {}
            ).get("maximum_transaction_rows")
            == MAX_BATCH_SIZE,
        "single_writer":
            authorization.get(
                "execution_requirements", {}
            ).get("single_writer") is True,
    }

    if not checkpoint.get("execution_started"):
        checks["initial_checkpoint"] = (
            checkpoint.get("checkpoint_checksum")
            == INITIAL_CHECKPOINT_CHECKSUM
            and checkpoint.get("status") == "READY"
            and checkpoint.get(
                "database_writes_attempted"
            ) is False
            and checkpoint.get(
                "database_writes_committed"
            ) is False
        )
    else:
        checks["engine_checkpoint"] = (
            checkpoint.get(
                "state_engine_schema_version"
            )
            == SCHEMA_VERSION
        )

    manifest_states = manifest.get("states") or []
    proposal_states = (
        proposal.get("state_manifests") or []
    )
    checkpoint_states = (
        checkpoint.get("states") or []
    )

    checks["deterministic_sequence"] = (
        [
            state.get("sequence")
            for state in manifest_states
        ]
        == list(range(1, EXPECTED_STATES + 1))
        == [
            state.get("sequence")
            for state in proposal_states
        ]
        == [
            state.get("sequence")
            for state in checkpoint_states
        ]
    )

    manifest_by_sequence = {
        state["sequence"]: state
        for state in manifest_states
    }
    proposal_by_sequence = {
        state["sequence"]: state
        for state in proposal_states
    }

    checks["state_identity"] = all(
        sequence in manifest_by_sequence
        and sequence in proposal_by_sequence
        and state.get("state")
            == manifest_by_sequence[
                sequence
            ].get("state")
            == proposal_by_sequence[
                sequence
            ].get("state")
        and str(state.get("state_lgd_code"))
            == str(
                manifest_by_sequence[
                    sequence
                ].get("state_lgd_code")
            )
            == str(
                proposal_by_sequence[
                    sequence
                ].get("state_lgd_code")
            )
        and state.get("import_batch_id")
            == manifest_by_sequence[
                sequence
            ].get("import_batch_id")
            == proposal_by_sequence[
                sequence
            ].get("import_batch_id")
        and state.get("expected_row_count")
            == manifest_by_sequence[
                sequence
            ].get("row_count")
            == proposal_by_sequence[
                sequence
            ].get("row_count")
        and state.get(
                "ordered_row_manifest_sha256"
            )
            == manifest_by_sequence[
                sequence
            ].get(
                "ordered_row_manifest_sha256"
            )
            == proposal_by_sequence[
                sequence
            ].get(
                "ordered_row_manifest_sha256"
            )
        and state.get("source_file_sha256")
            == manifest_by_sequence[
                sequence
            ].get("source_file_sha256")
            == proposal_by_sequence[
                sequence
            ].get("source_file_sha256")
        for state in checkpoint_states
        for sequence in [state.get("sequence")]
    )

    checks["checkpoint_row_total"] = (
        sum(
            int(
                state.get(
                    "expected_row_count"
                ) or 0
            )
            for state in checkpoint_states
        )
        == EXPECTED_ROWS
    )

    failed = sorted(
        key
        for key, value in checks.items()
        if not value
    )
    if failed:
        raise ValueError(
            "DISTRICT_DRIFT_ARTIFACT_"
            "VALIDATION_FAILED:"
            + ",".join(failed)
        )

    return (
        manifest,
        proposal,
        authorization,
        checkpoint,
    )


def stream_geojson_features(
    path: Path,
) -> Iterator[tuple[int, dict[str, Any]]]:
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
                marker = buffer.find(
                    '"features"',
                    position,
                )

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
                    marker = buffer.find(
                        '"features"'
                    )

                if marker < 0:
                    raise ValueError(
                        "GEOJSON_FEATURES_ARRAY_NOT_FOUND"
                    )

                position = (
                    marker + len('"features"')
                )
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
                            raise ValueError(
                                "GEOJSON_FEATURES_COLON_MISSING"
                            )
                        position += 1
                        break

                    more = handle.read(1024 * 1024)
                    if not more:
                        raise ValueError(
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
                            raise ValueError(
                                "GEOJSON_FEATURES_ARRAY_INVALID"
                            )
                        position += 1
                        reached_array = True
                        break

                    more = handle.read(1024 * 1024)
                    if not more:
                        raise ValueError(
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
                    raise ValueError(
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
                    if not isinstance(feature, dict):
                        raise ValueError(
                            "GEOJSON_FEATURE_INVALID"
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
                        raise ValueError(
                            "INCOMPLETE_GEOJSON_FEATURE"
                        )
                    buffer += more


def reconstruct_geometries(
    source_path: Path,
    rows: list[dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    wanted = {
        int(row["source_feature_index"])
        for row in rows
    }

    transformer = Transformer.from_crs(
        CRS.from_user_input(SOURCE_CRS),
        CRS.from_user_input(TARGET_CRS),
        always_xy=True,
    )

    reconstructed: dict[
        int,
        dict[str, Any],
    ] = {}

    for index, feature in stream_geojson_features(
        source_path
    ):
        if index not in wanted:
            continue

        source_geometry = feature.get("geometry")
        if not isinstance(source_geometry, dict):
            raise ValueError(
                f"SOURCE_GEOMETRY_MISSING:{index}"
            )

        source_shape = shape(source_geometry)

        if source_shape.is_empty:
            raise ValueError(
                f"SOURCE_GEOMETRY_EMPTY:{index}"
            )

        candidate_shape = source_shape

        if not source_shape.is_valid:
            repaired_shape = make_valid(
                source_shape
            )
            before_area = float(
                source_shape.area
            )
            after_area = float(
                repaired_shape.area
            )
            relative_area_change = (
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
            ):
                raise ValueError(
                    "RUNTIME_GEOMETRY_REPAIR_UNSAFE:"
                    f"{index}:"
                    f"{repaired_shape.geom_type}"
                )

            if (
                relative_area_change is not None
                and relative_area_change
                > 0.000001
            ):
                raise ValueError(
                    "RUNTIME_GEOMETRY_REPAIR_"
                    "AREA_CHANGE:"
                    f"{index}:"
                    f"{relative_area_change:.12f}"
                )

            candidate_shape = repaired_shape

        transformed = transform_geometry(
            transformer.transform,
            candidate_shape,
        )

        if transformed.geom_type not in {
            "Polygon",
            "MultiPolygon",
        }:
            raise ValueError(
                "RUNTIME_GEOMETRY_TYPE_INVALID:"
                f"{index}:{transformed.geom_type}"
            )

        if (
            transformed.is_empty
            or not transformed.is_valid
        ):
            raise ValueError(
                f"RUNTIME_GEOMETRY_INVALID:{index}"
            )

        reconstructed[index] = mapping(
            transformed
        )

        if len(reconstructed) == len(wanted):
            break

    if set(reconstructed) != wanted:
        missing = sorted(
            wanted - set(reconstructed)
        )[:20]
        raise ValueError(
            f"SOURCE_GEOMETRY_INDEX_MISSING:{missing}"
        )

    return reconstructed


def preflight(connection) -> dict[str, Any]:
    snapshot = connection.execute(text("""
        select
          (
            select version_num
            from alembic_version
            limit 1
          ) as revision,
          to_regtype('geometry') is not null
            as postgis_geometry,
          exists (
            select 1
            from information_schema.columns
            where table_schema = current_schema()
              and table_name =
                'geography_boundary_runtime_features'
              and column_name =
                'geometry_wgs84_geom'
          ) as native_column,
          (
            select count(*)::bigint
            from geography_boundary_project_matches
          ) as project_matches,
          (
            select count(*)::bigint
            from geography_boundary_runtime_features
            where is_active = true
          ) as active_runtime_features,
          (
            select count(*)::bigint
            from geography_boundary_runtime_crosswalks
            where is_active = true
          ) as active_runtime_crosswalks,
          (
            select count(*)::bigint
            from geography_boundary_crosswalk_candidates
            where is_active = true
          ) as active_candidates,
          (
            select count(*)::bigint
            from geography_boundary_crosswalk_candidates
            where promotion_status = 'PROMOTED'
          ) as promoted_candidates
    """)).mappings().one()

    runtime_set = connection.execute(text("""
        select
          id::text as runtime_set_id,
          is_active,
          activation_status
        from geography_boundary_runtime_sets
        where id = cast(:runtime_set_id as uuid)
    """), {
        "runtime_set_id": RUNTIME_SET_ID,
    }).mappings().one_or_none()

    checks = {
        "schema_revision_059":
            str(snapshot["revision"]) == "059",
        "postgis_available":
            snapshot["postgis_geometry"] is True,
        "native_geometry_column":
            snapshot["native_column"] is True,
        "runtime_set_exists":
            runtime_set is not None,
        "runtime_set_identity":
            bool(
                runtime_set
                and runtime_set["runtime_set_id"]
                == RUNTIME_SET_ID
            ),
        "project_matches_zero":
            int(
                snapshot["project_matches"]
                or 0
            )
            == 0,
    }

    failed = sorted(
        key
        for key, value in checks.items()
        if not value
    )
    if failed:
        raise ValueError(
            "DATABASE_PREFLIGHT_FAILED:"
            + ",".join(failed)
        )

    return {
        "checks": checks,
        "snapshot": dict(snapshot),
        "runtime_set": dict(runtime_set),
    }


@contextmanager
def single_writer(connection):
    acquired = connection.execute(
        text(
            "select pg_try_advisory_lock(:key)"
        ),
        {"key": ADVISORY_LOCK_KEY},
    ).scalar_one()

    if acquired is not True:
        raise ValueError(
            "SINGLE_WRITER_LOCK_UNAVAILABLE"
        )

    # The session advisory lock survives commit. End
    # SQLAlchemy's implicit transaction before work begins.
    connection.commit()

    try:
        yield
    finally:
        if connection.in_transaction():
            connection.rollback()

        connection.execute(
            text(
                "select pg_advisory_unlock(:key)"
            ),
            {"key": ADVISORY_LOCK_KEY},
        )
        connection.commit()


def manifest_state_rows(
    manifest: dict[str, Any],
    state: dict[str, Any],
) -> list[dict[str, Any]]:
    matches = [
        item
        for item in manifest.get("states", [])
        if item.get("sequence") == state.get("sequence")
        and item.get("state") == state.get("state")
        and str(item.get("state_lgd_code"))
            == str(state.get("state_lgd_code"))
        and item.get("import_batch_id")
            == state.get("import_batch_id")
    ]

    if len(matches) != 1:
        raise ValueError(
            "MANIFEST_STATE_IDENTITY_MISMATCH:"
            f"{state.get('state')}"
        )

    manifest_state = matches[0]
    rows = manifest_state.get("rows") or []

    if (
        len(rows)
        != int(state["expected_row_count"])
        or len({
            row["candidate_id"]
            for row in rows
        }) != len(rows)
        or len({
            row["source_feature_id"]
            for row in rows
        }) != len(rows)
        or len({
            row["canonical_village_id"]
            for row in rows
        }) != len(rows)
    ):
        raise ValueError(
            "MANIFEST_STATE_ROW_IDENTITY_FAILED:"
            f"{state['state']}"
        )

    ordered = sorted(
        rows,
        key=lambda row: (
            int(row["source_feature_index"]),
            str(row["candidate_id"]),
        ),
    )

    if ordered != rows:
        raise ValueError(
            "MANIFEST_STATE_ORDER_INVALID:"
            f"{state['state']}"
        )

    return rows


def selected_rows(
    connection,
    manifest_rows: list[dict[str, Any]],
    cursor: int,
    limit: int,
) -> list[dict[str, Any]]:
    selected = [
        row
        for row in manifest_rows
        if int(row["source_feature_index"]) > cursor
    ][:limit]

    if not selected:
        return []

    rows = connection.execute(text(r"""
        with manifest_input as (
          select *
          from jsonb_to_recordset(
            cast(:rows as jsonb)
          ) as row(
            candidate_id uuid,
            import_batch_id uuid,
            source_feature_id uuid,
            source_feature_index integer,
            source_state text,
            source_village_code text,
            source_village_name text,
            source_geometry_hash text,
            geometry_validation_status text,
            eligible_for_runtime_after_promotion boolean,
            canonical_state_id uuid,
            canonical_state_lgd_code text,
            canonical_district_id uuid,
            canonical_district_lgd_code text,
            canonical_village_block_id uuid,
            canonical_village_block_code text,
            canonical_village_id uuid,
            canonical_village_code text,
            canonical_village_name text,
            name_disposition text,
            runtime_geometry_sha256 text,
            row_sha256 text,
            transformed_bbox jsonb,
            transformed_centroid jsonb,
            geometry_repair jsonb
          )
        )
        select
          candidate.id::text as candidate_id,
          candidate.import_batch_id::text
            as import_batch_id,
          candidate.source_feature_id::text
            as source_feature_id,
          candidate.source_feature_index,
          candidate.confidence,
          'village'::text as proposed_scope,
          input.canonical_state_id::text
            as proposed_state_id,
          input.canonical_district_id::text
            as proposed_district_id,
          input.canonical_village_block_id::text
            as proposed_block_id,
          input.canonical_village_id::text
            as proposed_village_id,
          input.canonical_state_lgd_code
            as proposed_state_lgd_code,
          input.canonical_district_lgd_code
            as proposed_district_lgd_code,
          input.canonical_village_block_code
            as proposed_block_lgd_code,
          input.canonical_village_code
            as proposed_village_lgd_code,
          candidate.source_codes,
          candidate.source_names,
          candidate.match_evidence,
          candidate.review_status,
          candidate.reviewer_decision,
          candidate.reviewer_id,
          candidate.reviewer_notes,
          candidate.reviewed_at,
          source.feature_category,
          source.source_geometry_hash,
          source.transformed_bbox,
          source.transformed_centroid,
          source.eligible_for_runtime_after_promotion,
          input.runtime_geometry_sha256,
          input.row_sha256,
          input.name_disposition,
          input.geometry_repair
        from manifest_input input
        join geography_boundary_crosswalk_candidates
          candidate
          on candidate.id = input.candidate_id
        join geography_boundary_source_features
          source
          on source.id = input.source_feature_id
        join geography_boundary_import_batches batch
          on batch.id = input.import_batch_id
        join geography_states canonical_state
          on canonical_state.id =
             input.canonical_state_id
        join geography_districts canonical_district
          on canonical_district.id =
             input.canonical_district_id
         and canonical_district.state_id =
             canonical_state.id
        join geography_blocks canonical_block
          on canonical_block.id =
             input.canonical_village_block_id
         and canonical_block.district_id =
             canonical_district.id
        join geography_villages canonical_village
          on canonical_village.id =
             input.canonical_village_id
         and canonical_village.district_id =
             canonical_district.id
         and canonical_village.block_id =
             canonical_block.id
        where candidate.import_batch_id =
                input.import_batch_id
          and candidate.source_feature_id =
                input.source_feature_id
          and candidate.source_feature_index =
                input.source_feature_index
          and candidate.candidate_bucket =
                'BLOCKED_SOURCE_CAVEAT'
          and candidate.review_status = 'BLOCKED'
          and candidate.promotion_status =
                'NOT_PROMOTED'
          and candidate.is_active = false
          and candidate.proposed_state_id is null
          and candidate.proposed_district_id is null
          and candidate.proposed_block_id is null
          and candidate.proposed_village_id is null
          and (
            candidate.proposed_scope is null
            or candidate.proposed_scope = ''
          )
          and not (
            coalesce(candidate.metadata, '{}'::jsonb)
            ? :marker
          )
          and source.import_batch_id =
                input.import_batch_id
          and source.source_feature_index =
                input.source_feature_index
          and source.source_geometry_hash =
                input.source_geometry_hash
          and source.geometry_validation_status =
                input.geometry_validation_status
          and source.geometry_validation_status =
                'VALIDATED'
          and source.eligible_for_runtime_after_promotion =
                input.eligible_for_runtime_after_promotion
          and input.eligible_for_runtime_after_promotion =
                false
          and batch.state_or_ut = input.source_state
          and canonical_state.lgd_code::text =
                input.canonical_state_lgd_code
          and canonical_district.lgd_code::text =
                input.canonical_district_lgd_code
          and canonical_block.lgd_code::text =
                input.canonical_village_block_code
          and canonical_village.lgd_code::text =
                input.canonical_village_code
          and canonical_village.canonical_name =
                input.canonical_village_name
          and input.name_disposition in (
            'EXACT_OR_PUNCTUATION_MATCH',
            'TRAILING_NUMERIC_SUFFIX_ONLY'
          )
          and not exists (
            select 1
            from geography_boundary_runtime_features
              existing_feature
            where existing_feature.runtime_set_id =
                    cast(:runtime_set_id as uuid)
              and existing_feature.source_feature_id =
                    input.source_feature_id
          )
          and not exists (
            select 1
            from geography_boundary_runtime_crosswalks
              existing_crosswalk
            where existing_crosswalk.runtime_set_id =
                    cast(:runtime_set_id as uuid)
              and (
                existing_crosswalk.source_candidate_id =
                  input.candidate_id
                or existing_crosswalk.village_id =
                  input.canonical_village_id
              )
          )
        order by
          candidate.source_feature_index,
          candidate.id
    """), {
        "rows": json.dumps(selected),
        "runtime_set_id": RUNTIME_SET_ID,
        "marker": MARKER,
    }).mappings().all()

    result = [
        dict(row)
        for row in rows
    ]

    if len(result) != len(selected):
        selected_ids = {
            str(row["candidate_id"])
            for row in selected
        }
        returned_ids = {
            str(row["candidate_id"])
            for row in result
        }
        missing = sorted(
            selected_ids - returned_ids
        )[:20]

        raise ValueError(
            "MANIFEST_DATABASE_SELECTION_MISMATCH:"
            f"{len(result)}:{len(selected)}:{missing}"
        )

    return result


def state_population_count(
    connection,
    manifest_rows: list[dict[str, Any]],
) -> int:
    if not manifest_rows:
        return 0

    rows = selected_rows(
        connection,
        manifest_rows,
        -1,
        len(manifest_rows),
    )
    return len(rows)


def campaign_metadata(
    state_code: str,
    transaction_id: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "proposal_checksum":
            PROPOSAL_CHECKSUM,
        "authorization_checksum":
            AUTHORIZATION_CHECKSUM,
        "manifest_checksum":
            MANIFEST_CHECKSUM,
        "ordered_national_row_manifest_sha256":
            NATIONAL_MANIFEST_SHA256,
        "state_lgd_code": state_code,
        "transaction_id": transaction_id,
        "runtime_activation_changed": False,
        "lookup_changed": False,
        "candidate_activation_changed": False,
        "candidate_promotion_changed": False,
        "candidate_identity_changed": False,
        "project_matches_written": False,
        "source_geometry_written": False,
        "source_files_written": False,
        "android_changed": False,
    }


def apply_batch(
    connection,
    state: dict[str, Any],
    rows: list[dict[str, Any]],
    geometries: dict[int, dict[str, Any]],
    operator: str,
) -> dict[str, Any]:
    state_code = str(state["state_lgd_code"])
    first_index = int(rows[0]["source_feature_index"])
    last_index = int(rows[-1]["source_feature_index"])

    transaction_id = stable_uuid(
        "transaction",
        state_code,
        first_index,
        last_index,
    )
    promotion_event_id = stable_uuid(
        "promotion-event",
        state_code,
        first_index,
        last_index,
    )
    base_metadata = campaign_metadata(
        state_code,
        transaction_id,
    )

    input_rows = []

    for row in rows:
        source_index = int(
            row["source_feature_index"]
        )
        geometry = geometries[source_index]
        calculated_geometry_hash = canonical_checksum(
            geometry
        )

        if (
            calculated_geometry_hash
            != row["runtime_geometry_sha256"]
        ):
            raise ValueError(
                "RUNTIME_GEOMETRY_CHECKSUM_MISMATCH:"
                f"{state['state']}:{source_index}"
            )

        row_metadata = {
            **base_metadata,
            "row_sha256": row["row_sha256"],
            "runtime_geometry_sha256":
                row["runtime_geometry_sha256"],
            "name_disposition": row["name_disposition"],
        }

        input_rows.append({
            **row,
            "runtime_feature_id": stable_uuid(
                "runtime-feature",
                row["source_feature_id"],
            ),
            "runtime_crosswalk_id": stable_uuid(
                "runtime-crosswalk",
                row["candidate_id"],
            ),
            "promotion_event_id":
                promotion_event_id,
            "geometry_wgs84": geometry,
            "campaign_metadata": row_metadata,
            "before_candidate": {
                "review_status":
                    row["review_status"],
                "reviewer_decision":
                    row["reviewer_decision"],
                "reviewer_id":
                    row["reviewer_id"],
                "reviewer_notes":
                    row["reviewer_notes"],
                "reviewed_at": (
                    row["reviewed_at"].isoformat()
                    if row["reviewed_at"]
                    else None
                ),
            },
            "before_runtime_eligible":
                bool(
                    row[
                        "eligible_for_runtime_after_promotion"
                    ]
                ),
        })

    params = {
        "rows": json.dumps(
            input_rows,
            default=str,
        ),
        "runtime_set_id": RUNTIME_SET_ID,
        "event_id": promotion_event_id,
        "operator": operator,
        "proposal_checksum":
            PROPOSAL_CHECKSUM,
        "metadata": json.dumps(base_metadata),
        "state_code": state_code,
        "marker": MARKER,
        "reviewer_notes": REVIEWER_NOTES,
    }

    connection.execute(
        text("set local lock_timeout = '10s'")
    )
    connection.execute(
        text(
            "set local statement_timeout = '30min'"
        )
    )

    connection.execute(text(r"""
        create temporary table
          rehabilitation_runtime_input
        on commit drop as
        select *
        from jsonb_to_recordset(
          cast(:rows as jsonb)
        ) as row(
          candidate_id uuid,
          import_batch_id uuid,
          source_feature_id uuid,
          source_feature_index integer,
          confidence text,
          proposed_scope text,
          proposed_state_id uuid,
          proposed_district_id uuid,
          proposed_block_id uuid,
          proposed_village_id uuid,
          proposed_state_lgd_code text,
          proposed_district_lgd_code text,
          proposed_block_lgd_code text,
          proposed_village_lgd_code text,
          source_codes jsonb,
          source_names jsonb,
          match_evidence jsonb,
          feature_category text,
          source_geometry_hash text,
          transformed_bbox jsonb,
          transformed_centroid jsonb,
          runtime_geometry_sha256 text,
          row_sha256 text,
          name_disposition text,
          geometry_repair jsonb,
          runtime_feature_id uuid,
          runtime_crosswalk_id uuid,
          promotion_event_id uuid,
          geometry_wgs84 jsonb,
          campaign_metadata jsonb,
          before_candidate jsonb,
          before_runtime_eligible boolean
        )
    """), params)

    locked_count = int(
        connection.execute(text(r"""
            select count(*)
            from (
              select candidate.id
              from rehabilitation_runtime_input input
              join geography_boundary_crosswalk_candidates
                candidate
                on candidate.id = input.candidate_id
              join geography_boundary_source_features
                source
                on source.id = input.source_feature_id
              join geography_states canonical_state
                on canonical_state.id =
                   input.proposed_state_id
              join geography_districts canonical_district
                on canonical_district.id =
                   input.proposed_district_id
               and canonical_district.state_id =
                   canonical_state.id
              join geography_blocks canonical_block
                on canonical_block.id =
                   input.proposed_block_id
               and canonical_block.district_id =
                   canonical_district.id
              join geography_villages canonical_village
                on canonical_village.id =
                   input.proposed_village_id
               and canonical_village.district_id =
                   canonical_district.id
               and canonical_village.block_id =
                   canonical_block.id
              where candidate.import_batch_id =
                      input.import_batch_id
                and candidate.source_feature_id =
                      input.source_feature_id
                and candidate.source_feature_index =
                      input.source_feature_index
                and candidate.candidate_bucket =
                      'BLOCKED_SOURCE_CAVEAT'
                and candidate.review_status = 'BLOCKED'
                and candidate.promotion_status =
                      'NOT_PROMOTED'
                and candidate.is_active = false
                and candidate.proposed_state_id is null
                and candidate.proposed_district_id is null
                and candidate.proposed_block_id is null
                and candidate.proposed_village_id is null
                and (
                  candidate.proposed_scope is null
                  or candidate.proposed_scope = ''
                )
                and not (
                  coalesce(
                    candidate.metadata,
                    '{}'::jsonb
                  ) ? :marker
                )
                and source.import_batch_id =
                      input.import_batch_id
                and source.source_feature_index =
                      input.source_feature_index
                and source.source_geometry_hash =
                      input.source_geometry_hash
                and source.geometry_validation_status =
                      'VALIDATED'
                and source.eligible_for_runtime_after_promotion =
                      false
                and canonical_state.lgd_code::text =
                      input.proposed_state_lgd_code
                and canonical_state.lgd_code::text =
                      :state_code
                and canonical_district.lgd_code::text =
                      input.proposed_district_lgd_code
                and canonical_block.lgd_code::text =
                      input.proposed_block_lgd_code
                and canonical_village.lgd_code::text =
                      input.proposed_village_lgd_code
                and not exists (
                  select 1
                  from geography_boundary_runtime_features
                    existing_feature
                  where existing_feature.runtime_set_id =
                          cast(:runtime_set_id as uuid)
                    and existing_feature.source_feature_id =
                          input.source_feature_id
                )
                and not exists (
                  select 1
                  from geography_boundary_runtime_crosswalks
                    existing_crosswalk
                  where existing_crosswalk.runtime_set_id =
                          cast(:runtime_set_id as uuid)
                    and (
                      existing_crosswalk.source_candidate_id =
                        input.candidate_id
                      or existing_crosswalk.village_id =
                        input.proposed_village_id
                    )
                )
              order by
                candidate.source_feature_index,
                candidate.id
              for update of candidate, source
            ) locked
        """), params).scalar_one()
    )

    if locked_count != len(rows):
        raise ValueError(
            "LOCKED_ROW_COUNT_MISMATCH:"
            f"{locked_count}:{len(rows)}"
        )

    promotion_events = connection.execute(text(r"""
        insert into
          geography_boundary_runtime_promotion_events (
            id,
            runtime_set_id,
            source_import_batch_id,
            promoted_by,
            promotion_mode,
            promotion_status,
            candidate_count,
            runtime_feature_count,
            runtime_crosswalk_count,
            dry_run_report,
            promotion_report,
            guardrail_metadata,
            metadata,
            is_active
          )
        select
          cast(:event_id as uuid),
          cast(:runtime_set_id as uuid),
          min(import_batch_id::text)::uuid,
          :operator,
          'REVIEWED_BATCH',
          'APPLIED',
          count(*),
          count(*),
          count(*),
          '{}'::jsonb,
          jsonb_build_object(
            'state_lgd_code', :state_code,
            'proposal_checksum',
              :proposal_checksum
          ),
          cast(:metadata as jsonb),
          cast(:metadata as jsonb),
          false
        from rehabilitation_runtime_input
        returning id
    """), params).rowcount

    if promotion_events != 1:
        raise ValueError(
            "PROMOTION_EVENT_INSERT_COUNT_MISMATCH"
        )

    review_rows = connection.execute(text(r"""
        update
          geography_boundary_crosswalk_candidates
            as candidate
        set
          review_status =
            'APPROVED_FOR_PROMOTION',
          reviewer_decision =
            'ACCEPT_DISTRICT_DRIFT_VILLAGE_MATCH',
          reviewer_id = :operator,
          reviewer_notes = :reviewer_notes,
          reviewed_at = now(),
          metadata =
            coalesce(
              candidate.metadata,
              '{}'::jsonb
            )
            || jsonb_build_object(
              :marker,
              jsonb_build_object(
                'proposal_checksum',
                  :proposal_checksum,
                'before',
                  input.before_candidate,
                'transaction_id',
                  input.campaign_metadata
                    ->>'transaction_id',
                'row_sha256',
                  input.row_sha256,
                'state_lgd_code',
                  input.proposed_state_lgd_code
              )
            ),
          updated_at = now()
        from rehabilitation_runtime_input input
        where candidate.id = input.candidate_id
        returning candidate.id
    """), params).rowcount

    eligibility_rows = connection.execute(text(r"""
        update
          geography_boundary_source_features
            as source
        set
          eligible_for_runtime_after_promotion =
            true,
          metadata =
            coalesce(
              source.metadata,
              '{}'::jsonb
            )
            || jsonb_build_object(
              :marker,
              jsonb_build_object(
                'proposal_checksum',
                  :proposal_checksum,
                'before_eligible',
                  input.before_runtime_eligible,
                'transaction_id',
                  input.campaign_metadata
                    ->>'transaction_id',
                'row_sha256',
                  input.row_sha256,
                'state_lgd_code',
                  input.proposed_state_lgd_code
              )
            ),
          updated_at = now()
        from rehabilitation_runtime_input input
        where source.id =
              input.source_feature_id
        returning source.id
    """), params).rowcount

    runtime_features = connection.execute(text(r"""
        insert into
          geography_boundary_runtime_features (
            id,
            runtime_set_id,
            source_feature_id,
            source_feature_index,
            source_codes,
            source_names,
            feature_category,
            geometry_wgs84,
            geometry_wgs84_geom,
            centroid_wgs84,
            bbox_wgs84,
            geometry_hash,
            geometry_validation_status,
            metadata,
            is_active
          )
        select
          input.runtime_feature_id,
          cast(:runtime_set_id as uuid),
          input.source_feature_id,
          input.source_feature_index,
          input.source_codes,
          input.source_names,
          input.feature_category,
          input.geometry_wgs84,
          ST_SetSRID(
            ST_GeomFromGeoJSON(
              input.geometry_wgs84::text
            ),
            4326
          ),
          coalesce(
            input.transformed_centroid,
            '{}'::jsonb
          ),
          coalesce(
            input.transformed_bbox,
            '[]'::jsonb
          ),
          input.source_geometry_hash,
          'VALIDATED',
          input.campaign_metadata,
          false
        from rehabilitation_runtime_input input
        order by
          input.source_feature_index,
          input.candidate_id
        returning id
    """), params).rowcount

    runtime_crosswalks = connection.execute(text(r"""
        insert into
          geography_boundary_runtime_crosswalks (
            id,
            runtime_set_id,
            runtime_feature_id,
            source_candidate_id,
            runtime_scope,
            state_id,
            district_id,
            block_id,
            village_id,
            state_lgd_code,
            district_lgd_code,
            block_lgd_code,
            village_lgd_code,
            confidence,
            reviewer_decision,
            promotion_event_id,
            metadata,
            is_active
          )
        select
          input.runtime_crosswalk_id,
          cast(:runtime_set_id as uuid),
          input.runtime_feature_id,
          input.candidate_id,
          'village',
          input.proposed_state_id,
          input.proposed_district_id,
          input.proposed_block_id,
          input.proposed_village_id,
          input.proposed_state_lgd_code,
          input.proposed_district_lgd_code,
          input.proposed_block_lgd_code,
          input.proposed_village_lgd_code,
          input.confidence,
          'ACCEPT_DISTRICT_DRIFT_VILLAGE_MATCH',
          input.promotion_event_id,
          input.campaign_metadata,
          false
        from rehabilitation_runtime_input input
        order by
          input.source_feature_index,
          input.candidate_id
        returning id
    """), params).rowcount

    counts = {
        "review_metadata": review_rows,
        "runtime_eligibility":
            eligibility_rows,
        "runtime_features":
            runtime_features,
        "runtime_crosswalks":
            runtime_crosswalks,
        "promotion_events":
            promotion_events,
    }

    expected = len(rows)

    if any(
        counts[key] != expected
        for key in (
            "review_metadata",
            "runtime_eligibility",
            "runtime_features",
            "runtime_crosswalks",
        )
    ):
        raise ValueError(
            "EXACT_RETURNED_ROW_RECONCILIATION_FAILED:"
            + json.dumps(counts, sort_keys=True)
        )

    guardrails = connection.execute(text(r"""
        select
          count(*) filter (
            where feature.is_active
          )::bigint as active_features,
          count(*) filter (
            where crosswalk.is_active
          )::bigint as active_crosswalks,
          count(*) filter (
            where event.is_active
          )::bigint as active_events,
          count(*) filter (
            where candidate.is_active
          )::bigint as active_candidates,
          count(*) filter (
            where candidate.promotion_status
                  <> 'NOT_PROMOTED'
          )::bigint as promoted_candidates,
          count(*) filter (
            where candidate.candidate_bucket
                  <> 'BLOCKED_SOURCE_CAVEAT'
          )::bigint as changed_candidate_buckets,
          count(*) filter (
            where candidate.proposed_state_id
                  is not null
               or candidate.proposed_district_id
                  is not null
               or candidate.proposed_block_id
                  is not null
               or candidate.proposed_village_id
                  is not null
               or nullif(
                    candidate.proposed_scope,
                    ''
                  ) is not null
          )::bigint as changed_candidate_identity,
          count(*) filter (
            where feature.geometry_wgs84_geom
                  is null
          )::bigint as missing_native_geometry,
          count(*) filter (
            where not ST_IsValid(
              feature.geometry_wgs84_geom
            )
          )::bigint as invalid_native_geometry,
          count(*) filter (
            where ST_SRID(
              feature.geometry_wgs84_geom
            ) <> 4326
          )::bigint as invalid_native_srid
        from rehabilitation_runtime_input input
        join geography_boundary_runtime_features
          feature
          on feature.id =
             input.runtime_feature_id
        join geography_boundary_runtime_crosswalks
          crosswalk
          on crosswalk.id =
             input.runtime_crosswalk_id
        join geography_boundary_runtime_promotion_events
          event
          on event.id =
             input.promotion_event_id
        join geography_boundary_crosswalk_candidates
          candidate
          on candidate.id =
             input.candidate_id
    """)).mappings().one()

    if any(
        int(value or 0) != 0
        for value in guardrails.values()
    ):
        raise ValueError(
            "FAIL_CLOSED_GUARDRAIL_VIOLATION:"
            + json.dumps(
                dict(guardrails),
                sort_keys=True,
            )
        )

    return {
        "transaction_id": transaction_id,
        "promotion_event_id":
            promotion_event_id,
        "first_source_feature_index":
            first_index,
        "last_source_feature_index":
            last_index,
        "row_count": expected,
        "counts": counts,
        "guardrails": dict(guardrails),
    }


def state_database_progress(
    connection,
    state: dict[str, Any],
) -> dict[str, int]:
    state_code = str(state["state_lgd_code"])

    row = connection.execute(text(r"""
        select
          (
            select count(*)::bigint
            from geography_boundary_runtime_crosswalks
              crosswalk
            join geography_boundary_crosswalk_candidates
              candidate
              on candidate.id =
                 crosswalk.source_candidate_id
            where crosswalk.runtime_set_id =
                    cast(:runtime_set_id as uuid)
              and crosswalk.metadata
                    ->>'proposal_checksum'
                  = :proposal_checksum
              and crosswalk.state_lgd_code =
                    :state_code
              and candidate.metadata
                    ->:marker
                    ->>'proposal_checksum'
                  = :proposal_checksum
          ) as review_metadata,
          (
            select count(*)::bigint
            from geography_boundary_runtime_features
              feature
            join geography_boundary_source_features
              source
              on source.id =
                 feature.source_feature_id
            where feature.runtime_set_id =
                    cast(:runtime_set_id as uuid)
              and feature.metadata
                    ->>'proposal_checksum'
                  = :proposal_checksum
              and feature.metadata
                    ->>'state_lgd_code'
                  = :state_code
              and source.metadata
                    ->:marker
                    ->>'proposal_checksum'
                  = :proposal_checksum
          ) as runtime_eligibility,
          (
            select count(*)::bigint
            from geography_boundary_runtime_features
              feature
            where feature.runtime_set_id =
                    cast(:runtime_set_id as uuid)
              and feature.metadata
                    ->>'proposal_checksum'
                  = :proposal_checksum
              and feature.metadata
                    ->>'state_lgd_code'
                  = :state_code
          ) as runtime_features,
          (
            select count(*)::bigint
            from geography_boundary_runtime_crosswalks
              crosswalk
            where crosswalk.runtime_set_id =
                    cast(:runtime_set_id as uuid)
              and crosswalk.metadata
                    ->>'proposal_checksum'
                  = :proposal_checksum
              and crosswalk.state_lgd_code =
                    :state_code
          ) as runtime_crosswalks,
          (
            select coalesce(
              max(feature.source_feature_index),
              -1
            )::bigint
            from geography_boundary_runtime_features
              feature
            where feature.runtime_set_id =
                    cast(:runtime_set_id as uuid)
              and feature.metadata
                    ->>'proposal_checksum'
                  = :proposal_checksum
              and feature.metadata
                    ->>'state_lgd_code'
                  = :state_code
          ) as maximum_source_feature_index
    """), {
        "marker": MARKER,
        "proposal_checksum":
            PROPOSAL_CHECKSUM,
        "runtime_set_id": RUNTIME_SET_ID,
        "state_code": state_code,
    }).mappings().one()

    return {
        key: int(value or 0)
        for key, value in row.items()
    }


def validate_state_progress(
    state: dict[str, Any],
    progress: dict[str, int],
    *,
    require_complete: bool,
) -> None:
    row_counts = {
        progress["review_metadata"],
        progress["runtime_eligibility"],
        progress["runtime_features"],
        progress["runtime_crosswalks"],
    }

    if len(row_counts) != 1:
        raise ValueError(
            "STATE_PROGRESS_COUNT_DIVERGENCE:"
            f"{state['state_lgd_code']}:"
            + json.dumps(progress, sort_keys=True)
        )

    completed = progress["runtime_features"]
    expected = int(state["expected_row_count"])

    if completed > expected:
        raise ValueError(
            "STATE_PROGRESS_EXCEEDS_AUTHORIZATION:"
            f"{state['state_lgd_code']}:"
            f"{completed}:{expected}"
        )

    if require_complete and completed != expected:
        raise ValueError(
            "STATE_RECONCILIATION_FAILED:"
            f"{state['state_lgd_code']}:"
            f"{completed}:{expected}"
        )


def recover_state_checkpoint(
    connection,
    state: dict[str, Any],
) -> dict[str, int]:
    progress = state_database_progress(
        connection,
        state,
    )
    validate_state_progress(
        state,
        progress,
        require_complete=False,
    )

    completed = progress["runtime_features"]

    state["completed_row_count"] = completed
    state["review_metadata_row_count"] = (
        progress["review_metadata"]
    )
    state["runtime_eligibility_row_count"] = (
        progress["runtime_eligibility"]
    )
    state["runtime_feature_row_count"] = (
        progress["runtime_features"]
    )
    state["runtime_crosswalk_row_count"] = (
        progress["runtime_crosswalks"]
    )
    state["cursor_source_feature_index"] = (
        progress["maximum_source_feature_index"]
    )

    if completed == int(
        state["expected_row_count"]
    ):
        state["status"] = "COMPLETED"
    elif completed:
        state["status"] = "IN_PROGRESS"
    else:
        state["status"] = "READY"

    return progress


def refresh_checkpoint(
    checkpoint: dict[str, Any],
) -> None:
    states = checkpoint["states"]

    checkpoint["completed_state_count"] = sum(
        state.get("status") == "COMPLETED"
        for state in states
    )
    checkpoint["completed_row_count"] = sum(
        int(state.get("completed_row_count") or 0)
        for state in states
    )
    checkpoint["completed_transaction_count"] = sum(
        int(
            state.get(
                "completed_transaction_count"
            )
            or 0
        )
        for state in states
    )

    checkpoint["execution_started"] = (
        checkpoint["completed_row_count"] > 0
    )
    checkpoint["execution_completed"] = (
        checkpoint["completed_row_count"]
        == EXPECTED_ROWS
        and checkpoint["completed_state_count"]
        == EXPECTED_STATES
    )
    checkpoint["database_writes_attempted"] = (
        checkpoint["execution_started"]
    )
    checkpoint["database_writes_committed"] = (
        checkpoint["execution_started"]
    )
    checkpoint["resume_required"] = (
        checkpoint["execution_started"]
        and not checkpoint["execution_completed"]
    )
    checkpoint["status"] = (
        "COMPLETED"
        if checkpoint["execution_completed"]
        else (
            "IN_PROGRESS"
            if checkpoint["execution_started"]
            else "READY"
        )
    )
    checkpoint["active_state"] = None
    checkpoint["active_transaction"] = None
    checkpoint["updated_at"] = now_iso()
    checkpoint[
        "state_engine_schema_version"
    ] = SCHEMA_VERSION
    checkpoint["checkpoint_checksum"] = (
        checkpoint_checksum(checkpoint)
    )


def reconcile_state(
    connection,
    state: dict[str, Any],
) -> dict[str, int]:
    progress = state_database_progress(
        connection,
        state,
    )
    validate_state_progress(
        state,
        progress,
        require_complete=True,
    )

    state_code = str(state["state_lgd_code"])

    guardrails = connection.execute(text(r"""
        select
          count(*) filter (
            where feature.is_active
          )::bigint as active_features,
          count(*) filter (
            where crosswalk.is_active
          )::bigint as active_crosswalks,
          count(*) filter (
            where event.is_active
          )::bigint as active_events,
          count(*) filter (
            where candidate.is_active
          )::bigint as active_candidates,
          count(*) filter (
            where candidate.promotion_status
                  <> 'NOT_PROMOTED'
          )::bigint as promoted_candidates,
          count(*) filter (
            where candidate.candidate_bucket
                  <> 'BLOCKED_SOURCE_CAVEAT'
          )::bigint as changed_candidate_buckets,
          count(*) filter (
            where candidate.proposed_state_id
                  is not null
               or candidate.proposed_district_id
                  is not null
               or candidate.proposed_block_id
                  is not null
               or candidate.proposed_village_id
                  is not null
               or nullif(
                    candidate.proposed_scope,
                    ''
                  ) is not null
          )::bigint as changed_candidate_identity,
          count(*) filter (
            where source.eligible_for_runtime_after_promotion
                  is not true
          )::bigint as missing_runtime_eligibility,
          count(*) filter (
            where feature.geometry_wgs84_geom
                  is null
          )::bigint as missing_native_geometry,
          count(*) filter (
            where not ST_IsValid(
              feature.geometry_wgs84_geom
            )
          )::bigint as invalid_native_geometry,
          count(*) filter (
            where ST_SRID(
              feature.geometry_wgs84_geom
            ) <> 4326
          )::bigint as invalid_srid,
          (
            count(*)
            - count(distinct crosswalk.village_id)
          )::bigint as duplicate_villages,
          count(*) filter (
            where feature.metadata
                    ->>'manifest_checksum'
                  <> :manifest_checksum
               or crosswalk.metadata
                    ->>'manifest_checksum'
                  <> :manifest_checksum
          )::bigint as manifest_pin_mismatches
        from geography_boundary_runtime_features
          feature
        join geography_boundary_runtime_crosswalks
          crosswalk
          on crosswalk.runtime_feature_id =
             feature.id
         and crosswalk.runtime_set_id =
             feature.runtime_set_id
        join geography_boundary_runtime_promotion_events
          event
          on event.id =
             crosswalk.promotion_event_id
        join geography_boundary_crosswalk_candidates
          candidate
          on candidate.id =
             crosswalk.source_candidate_id
        join geography_boundary_source_features
          source
          on source.id =
             feature.source_feature_id
        where feature.runtime_set_id =
                cast(:runtime_set_id as uuid)
          and feature.metadata
                ->>'proposal_checksum'
              = :proposal_checksum
          and feature.metadata
                ->>'state_lgd_code'
              = :state_code
    """), {
        "runtime_set_id": RUNTIME_SET_ID,
        "proposal_checksum":
            PROPOSAL_CHECKSUM,
        "manifest_checksum":
            MANIFEST_CHECKSUM,
        "state_code": state_code,
    }).mappings().one()

    if any(
        int(value or 0) != 0
        for value in guardrails.values()
    ):
        raise ValueError(
            "STATE_FAIL_CLOSED_RECONCILIATION_FAILED:"
            f"{state_code}:"
            + json.dumps(
                dict(guardrails),
                sort_keys=True,
            )
        )

    return {
        **progress,
        **{
            key: int(value or 0)
            for key, value in guardrails.items()
        },
    }


def run_apply(
    connection,
    options: argparse.Namespace,
    manifest: dict[str, Any],
    checkpoint: dict[str, Any],
) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []

    for state in checkpoint["states"]:
        state_code = str(
            state["state_lgd_code"]
        )
        rows_for_state = manifest_state_rows(
            manifest,
            state,
        )

        progress = recover_state_checkpoint(
            connection,
            state,
        )
        connection.commit()

        if state["status"] == "COMPLETED":
            reconciliation = reconcile_state(
                connection,
                state,
            )
            connection.commit()
            state["reconciliation"] = reconciliation
            reports.append({
                "state_lgd_code": state_code,
                "action":
                    "RESUME_VALIDATED_NO_REPLAY",
                "row_count":
                    progress["runtime_features"],
            })
            continue

        source_path = Path(state["source_file"])

        if not source_path.is_file():
            raise ValueError(
                "PINNED_STATE_SOURCE_NOT_FOUND:"
                f"{state_code}:{source_path}"
            )

        actual_source_checksum = sha256_file(
            source_path
        )
        if (
            actual_source_checksum
            != state["source_file_sha256"]
        ):
            raise ValueError(
                "PINNED_STATE_SOURCE_CHECKSUM_MISMATCH:"
                f"{state_code}:"
                f"expected={state['source_file_sha256']}:"
                f"actual={actual_source_checksum}"
            )

        cursor = int(
            state.get(
                "cursor_source_feature_index",
                -1,
            )
        )
        state["status"] = "IN_PROGRESS"

        while True:
            rows = selected_rows(
                connection,
                rows_for_state,
                cursor,
                options.batch_size,
            )
            connection.commit()

            if not rows:
                break

            geometries = reconstruct_geometries(
                source_path,
                rows,
            )

            first_index = int(
                rows[0]["source_feature_index"]
            )
            last_index = int(
                rows[-1]["source_feature_index"]
            )
            transaction_id = stable_uuid(
                "transaction",
                state_code,
                first_index,
                last_index,
            )

            active_transaction = {
                "transaction_id":
                    transaction_id,
                "first_source_feature_index":
                    first_index,
                "last_source_feature_index":
                    last_index,
                "row_count": len(rows),
            }
            checkpoint["active_state"] = state_code
            checkpoint["active_transaction"] = (
                active_transaction
            )
            state["active_transaction"] = (
                active_transaction
            )
            checkpoint["resume_required"] = True
            checkpoint[
                "state_engine_schema_version"
            ] = SCHEMA_VERSION
            checkpoint["updated_at"] = now_iso()
            checkpoint["checkpoint_checksum"] = (
                checkpoint_checksum(checkpoint)
            )
            atomic_write_json(
                options.checkpoint_json,
                checkpoint,
            )

            with connection.begin():
                batch_report = apply_batch(
                    connection,
                    state,
                    rows,
                    geometries,
                    options.operator,
                )

            progress = recover_state_checkpoint(
                connection,
                state,
            )
            connection.commit()

            state[
                "completed_transaction_count"
            ] = (
                int(
                    state.get(
                        "completed_transaction_count"
                    )
                    or 0
                )
                + 1
            )
            state["active_transaction"] = None
            cursor = progress[
                "maximum_source_feature_index"
            ]

            refresh_checkpoint(checkpoint)
            atomic_write_json(
                options.checkpoint_json,
                checkpoint,
            )

            reports.append({
                "state_lgd_code": state_code,
                **batch_report,
            })

        progress = recover_state_checkpoint(
            connection,
            state,
        )
        connection.commit()

        validate_state_progress(
            state,
            progress,
            require_complete=True,
        )

        reconciliation = reconcile_state(
            connection,
            state,
        )
        connection.commit()

        state["reconciliation"] = reconciliation
        state["status"] = "COMPLETED"
        state["active_transaction"] = None

        refresh_checkpoint(checkpoint)
        atomic_write_json(
            options.checkpoint_json,
            checkpoint,
        )

    refresh_checkpoint(checkpoint)

    if (
        checkpoint["completed_row_count"]
        != EXPECTED_ROWS
        or checkpoint["completed_state_count"]
        != EXPECTED_STATES
    ):
        raise ValueError(
            "REHABILITATION_COMPLETION_"
            "RECONCILIATION_FAILED:"
            + json.dumps({
                "completed_row_count":
                    checkpoint[
                        "completed_row_count"
                    ],
                "completed_state_count":
                    checkpoint[
                        "completed_state_count"
                    ],
            }, sort_keys=True)
        )

    atomic_write_json(
        options.checkpoint_json,
        checkpoint,
    )

    return reports


def rollback_state(
    connection,
    state: dict[str, Any],
    operator: str,
) -> dict[str, int]:
    state_code = str(state["state_lgd_code"])

    params = {
        "runtime_set_id": RUNTIME_SET_ID,
        "proposal_checksum":
            PROPOSAL_CHECKSUM,
        "marker": MARKER,
        "state_code": state_code,
        "operator": operator,
    }

    connection.execute(
        text("set local lock_timeout = '10s'")
    )
    connection.execute(
        text(
            "set local statement_timeout = '30min'"
        )
    )

    sources = connection.execute(text(r"""
        update geography_boundary_source_features
          source
        set
          eligible_for_runtime_after_promotion =
            cast(
              source.metadata
                ->:marker
                ->>'before_eligible'
              as boolean
            ),
          metadata =
            source.metadata - :marker,
          updated_at = now()
        from geography_boundary_runtime_features
          feature
        where feature.source_feature_id = source.id
          and feature.runtime_set_id =
                cast(:runtime_set_id as uuid)
          and feature.metadata
                ->>'proposal_checksum'
              = :proposal_checksum
          and feature.metadata
                ->>'state_lgd_code'
              = :state_code
          and feature.is_active = false
          and source.metadata
                ->:marker
                ->>'proposal_checksum'
              = :proposal_checksum
        returning source.id
    """), params).rowcount

    candidates = connection.execute(text(r"""
        update geography_boundary_crosswalk_candidates
          candidate
        set
          review_status =
            candidate.metadata
              ->:marker
              ->'before'
              ->>'review_status',
          reviewer_decision =
            nullif(
              candidate.metadata
                ->:marker
                ->'before'
                ->>'reviewer_decision',
              ''
            ),
          reviewer_id =
            nullif(
              candidate.metadata
                ->:marker
                ->'before'
                ->>'reviewer_id',
              ''
            ),
          reviewer_notes =
            nullif(
              candidate.metadata
                ->:marker
                ->'before'
                ->>'reviewer_notes',
              ''
            ),
          reviewed_at =
            nullif(
              candidate.metadata
                ->:marker
                ->'before'
                ->>'reviewed_at',
              ''
            )::timestamptz,
          metadata =
            candidate.metadata - :marker,
          updated_at = now()
        from geography_boundary_runtime_crosswalks
          crosswalk
        where crosswalk.source_candidate_id =
                candidate.id
          and crosswalk.runtime_set_id =
                cast(:runtime_set_id as uuid)
          and crosswalk.metadata
                ->>'proposal_checksum'
              = :proposal_checksum
          and crosswalk.state_lgd_code =
                :state_code
          and crosswalk.is_active = false
          and candidate.metadata
                ->:marker
                ->>'proposal_checksum'
              = :proposal_checksum
          and candidate.is_active = false
          and candidate.promotion_status =
                'NOT_PROMOTED'
        returning candidate.id
    """), params).rowcount

    crosswalks = connection.execute(text(r"""
        delete from
          geography_boundary_runtime_crosswalks
        where runtime_set_id =
                cast(:runtime_set_id as uuid)
          and metadata
                ->>'proposal_checksum'
              = :proposal_checksum
          and state_lgd_code = :state_code
          and is_active = false
        returning id
    """), params).rowcount

    features = connection.execute(text(r"""
        delete from
          geography_boundary_runtime_features
        where runtime_set_id =
                cast(:runtime_set_id as uuid)
          and metadata
                ->>'proposal_checksum'
              = :proposal_checksum
          and metadata
                ->>'state_lgd_code'
              = :state_code
          and is_active = false
        returning id
    """), params).rowcount

    events = connection.execute(text(r"""
        delete from
          geography_boundary_runtime_promotion_events
        where runtime_set_id =
                cast(:runtime_set_id as uuid)
          and metadata
                ->>'proposal_checksum'
              = :proposal_checksum
          and metadata
                ->>'state_lgd_code'
              = :state_code
          and is_active = false
        returning id
    """), params).rowcount

    counts = {
        "runtime_crosswalks_deleted":
            crosswalks,
        "runtime_features_deleted":
            features,
        "promotion_events_deleted":
            events,
        "source_rows_restored":
            sources,
        "candidate_rows_restored":
            candidates,
    }

    if len({
        crosswalks,
        features,
        sources,
        candidates,
    }) != 1:
        raise ValueError(
            "ROLLBACK_EXACT_RECONCILIATION_FAILED:"
            f"{state_code}:"
            + json.dumps(counts, sort_keys=True)
        )

    return counts


def reset_state_checkpoint(
    state: dict[str, Any],
) -> None:
    state.update({
        "active_transaction": None,
        "completed_row_count": 0,
        "completed_transaction_count": 0,
        "cursor_source_feature_index": -1,
        "review_metadata_row_count": 0,
        "runtime_crosswalk_row_count": 0,
        "runtime_eligibility_row_count": 0,
        "runtime_feature_row_count": 0,
        "status": "READY",
    })
    state.pop("reconciliation", None)


def run_rollback(
    connection,
    options: argparse.Namespace,
    checkpoint: dict[str, Any],
    *,
    rehearsal: bool,
) -> list[dict[str, Any]]:
    reports = []
    states = sorted(
        checkpoint["states"],
        key=lambda state: int(state["sequence"]),
        reverse=True,
    )

    if rehearsal:
        transaction = connection.begin()
        try:
            for state in states:
                progress = state_database_progress(
                    connection,
                    state,
                )
                if not progress["runtime_features"]:
                    continue

                counts = rollback_state(
                    connection,
                    state,
                    options.operator,
                )
                reports.append({
                    "state_lgd_code":
                        state["state_lgd_code"],
                    "rehearsal": True,
                    **counts,
                })
        finally:
            transaction.rollback()

        return reports

    checkpoint["rollback_started"] = True
    checkpoint["rollback_completed"] = False

    for state in states:
        progress = state_database_progress(
            connection,
            state,
        )
        connection.commit()

        if progress["runtime_features"]:
            with connection.begin():
                counts = rollback_state(
                    connection,
                    state,
                    options.operator,
                )

            remaining = state_database_progress(
                connection,
                state,
            )
            connection.commit()

            if any(
                remaining[key] != 0
                for key in (
                    "review_metadata",
                    "runtime_eligibility",
                    "runtime_features",
                    "runtime_crosswalks",
                )
            ):
                raise ValueError(
                    "ROLLBACK_STATE_NOT_EMPTY:"
                    f"{state['state_lgd_code']}:"
                    + json.dumps(
                        remaining,
                        sort_keys=True,
                    )
                )

            reports.append({
                "state_lgd_code":
                    state["state_lgd_code"],
                "rehearsal": False,
                **counts,
            })

        reset_state_checkpoint(state)
        refresh_checkpoint(checkpoint)
        checkpoint["rollback_started"] = True
        checkpoint["rollback_completed"] = False
        checkpoint["status"] = "ROLLING_BACK"
        checkpoint["checkpoint_checksum"] = (
            checkpoint_checksum(checkpoint)
        )
        atomic_write_json(
            options.checkpoint_json,
            checkpoint,
        )

    refresh_checkpoint(checkpoint)
    checkpoint["rollback_started"] = True
    checkpoint["rollback_completed"] = True
    checkpoint["status"] = "ROLLED_BACK"
    checkpoint["checkpoint_checksum"] = (
        checkpoint_checksum(checkpoint)
    )
    atomic_write_json(
        options.checkpoint_json,
        checkpoint,
    )

    return reports


def run_apply_rollback_rehearsal(
    connection,
    options: argparse.Namespace,
    manifest: dict[str, Any],
    checkpoint: dict[str, Any],
) -> dict[str, Any]:
    """Apply the first state and roll back the transaction."""
    state = checkpoint["states"][0]
    state_code = str(state["state_lgd_code"])
    expected = int(state["expected_row_count"])
    source_path = Path(state["source_file"])
    manifest_rows = manifest_state_rows(
        manifest,
        state,
    )

    if not source_path.is_file():
        raise ValueError(
            f"REHEARSAL_SOURCE_NOT_FOUND:{source_path}"
        )

    source_checksum = sha256_file(source_path)
    if source_checksum != state["source_file_sha256"]:
        raise ValueError(
            "REHEARSAL_SOURCE_CHECKSUM_MISMATCH"
        )

    before = state_database_progress(
        connection,
        state,
    )
    connection.commit()

    if any(
        before[key] != 0
        for key in (
            "review_metadata",
            "runtime_eligibility",
            "runtime_features",
            "runtime_crosswalks",
        )
    ):
        raise ValueError(
            "REHEARSAL_REQUIRES_PRISTINE_STATE:"
            + json.dumps(before, sort_keys=True)
        )

    rows = selected_rows(
        connection,
        manifest_rows,
        -1,
        expected,
    )
    connection.commit()

    if len(rows) != expected:
        raise ValueError(
            "REHEARSAL_SELECTION_COUNT_MISMATCH:"
            f"{len(rows)}:{expected}"
        )

    geometries = reconstruct_geometries(
        source_path,
        rows,
    )

    apply_report = None
    during = None
    rollback_report = None
    after_scoped_rollback = None
    transaction = connection.begin()

    try:
        apply_report = apply_batch(
            connection,
            state,
            rows,
            geometries,
            options.operator,
        )
        during = state_database_progress(
            connection,
            state,
        )
        validate_state_progress(
            state,
            during,
            require_complete=True,
        )

        rollback_report = rollback_state(
            connection,
            state,
            options.operator,
        )
        after_scoped_rollback = (
            state_database_progress(
                connection,
                state,
            )
        )

        if any(
            after_scoped_rollback[key] != 0
            for key in (
                "review_metadata",
                "runtime_eligibility",
                "runtime_features",
                "runtime_crosswalks",
            )
        ):
            raise ValueError(
                "REHEARSAL_SCOPED_ROLLBACK_NOT_EMPTY:"
                + json.dumps(
                    after_scoped_rollback,
                    sort_keys=True,
                )
            )
    finally:
        transaction.rollback()

    after = state_database_progress(
        connection,
        state,
    )
    connection.commit()

    if after != before:
        raise ValueError(
            "REHEARSAL_ROLLBACK_STATE_MISMATCH:"
            + json.dumps({
                "before": before,
                "after": after,
            }, sort_keys=True)
        )

    return {
        "state_lgd_code": state_code,
        "row_count": len(rows),
        "source_file": str(source_path),
        "source_file_sha256": source_checksum,
        "apply_report": apply_report,
        "during_transaction": during,
        "proposal_scoped_rollback_report":
            rollback_report,
        "after_proposal_scoped_rollback":
            after_scoped_rollback,
        "rollback_executed": True,
        "database_state_unchanged": True,
        "checkpoint_written": False,
        "before": before,
        "after": after,
    }


def dry_run_inventory(
    connection,
    manifest: dict[str, Any],
    checkpoint: dict[str, Any],
) -> dict[str, Any]:
    states = []
    total_remaining = 0
    total_completed = 0

    for state in checkpoint["states"]:
        state_code = str(state["state_lgd_code"])
        manifest_rows = manifest_state_rows(
            manifest,
            state,
        )
        remaining = state_population_count(
            connection,
            [
                row
                for row in manifest_rows
                if int(row["source_feature_index"])
                > int(
                    state.get(
                        "cursor_source_feature_index",
                        -1,
                    )
                )
            ],
        )
        progress = state_database_progress(
            connection,
            state,
        )
        connection.commit()

        validate_state_progress(
            state,
            progress,
            require_complete=False,
        )

        completed = progress["runtime_features"]
        expected = int(state["expected_row_count"])

        if remaining + completed != expected:
            raise ValueError(
                "DRY_RUN_STATE_ROW_COUNT_MISMATCH:"
                f"{state_code}:"
                f"remaining={remaining}:"
                f"completed={completed}:"
                f"expected={expected}"
            )

        total_remaining += remaining
        total_completed += completed

        states.append({
            "sequence": state["sequence"],
            "state": state["state"],
            "state_lgd_code": state_code,
            "expected_row_count": expected,
            "remaining_row_count": remaining,
            "completed_row_count": completed,
            "source_file": state["source_file"],
            "source_file_sha256":
                state["source_file_sha256"],
            "ordered_row_manifest_sha256":
                state[
                    "ordered_row_manifest_sha256"
                ],
        })

    if (
        total_remaining + total_completed
        != EXPECTED_ROWS
    ):
        raise ValueError(
            "DRY_RUN_REHABILITATION_ROW_COUNT_MISMATCH"
        )

    return {
        "remaining_row_count": total_remaining,
        "completed_row_count": total_completed,
        "authorized_row_count": EXPECTED_ROWS,
        "states": states,
    }


def main() -> int:
    options = arguments()
    validate_mutation_gates(options)

    (
        manifest,
        proposal,
        authorization,
        checkpoint,
    ) = validate_artifacts(options)

    if options.apply:
        mode = "APPLY"
    elif options.resume:
        mode = "RESUME"
    elif options.rollback:
        mode = "ROLLBACK"
    elif options.rollback_only_rehearsal:
        mode = "ROLLBACK_ONLY_REHEARSAL"
    else:
        mode = "DRY_RUN"

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "mode": mode,
        "healthy": False,
        "proposal_checksum": PROPOSAL_CHECKSUM,
        "authorization_checksum":
            AUTHORIZATION_CHECKSUM,
        "manifest_checksum": MANIFEST_CHECKSUM,
        "ordered_national_row_manifest_sha256":
            NATIONAL_MANIFEST_SHA256,
        "runtime_set_id": RUNTIME_SET_ID,
        "authorized_row_count": EXPECTED_ROWS,
        "authorized_state_count": EXPECTED_STATES,
        "batch_size": options.batch_size,
        "writer_count": 1,
        "single_writer": True,
        "guardrails": {
            "runtime_activation_changed": False,
            "lookup_changed": False,
            "candidate_activation_changed": False,
            "candidate_promotion_changed": False,
            "candidate_identity_changed": False,
            "project_matches_written": False,
            "source_geometry_written": False,
            "source_files_written": False,
            "android_changed": False,
        },
    }

    engine = create_engine(
        db_url(),
        future=True,
    )

    with engine.connect() as connection:
        report["preflight"] = preflight(connection)
        connection.commit()

        with single_writer(connection):
            if mode == "DRY_RUN":
                report["inventory"] = (
                    dry_run_inventory(
                        connection,
                        manifest,
                        checkpoint,
                    )
                )
                report["database_writes_attempted"] = False
                report["database_writes_committed"] = False

            elif mode == "ROLLBACK_ONLY_REHEARSAL":
                report["rollback_rehearsal"] = (
                    run_apply_rollback_rehearsal(
                        connection,
                        options,
                        manifest,
                        checkpoint,
                    )
                )
                report["database_writes_attempted"] = True
                report["database_writes_committed"] = False

            elif mode in {"APPLY", "RESUME"}:
                if (
                    mode == "APPLY"
                    and checkpoint.get(
                        "execution_started"
                    )
                ):
                    raise ValueError(
                        "APPLY_REQUIRES_PRISTINE_"
                        "CHECKPOINT_USE_RESUME"
                    )

                if (
                    mode == "RESUME"
                    and not checkpoint.get(
                        "execution_started"
                    )
                ):
                    recovered_rows = 0
                    for state in checkpoint["states"]:
                        progress = (
                            recover_state_checkpoint(
                                connection,
                                state,
                            )
                        )
                        recovered_rows += progress[
                            "runtime_features"
                        ]
                    connection.commit()

                    if recovered_rows == 0:
                        raise ValueError(
                            "RESUME_REQUIRES_STARTED_"
                            "CHECKPOINT_USE_APPLY"
                        )

                    refresh_checkpoint(checkpoint)
                    atomic_write_json(
                        options.checkpoint_json,
                        checkpoint,
                    )

                report["transactions"] = run_apply(
                    connection,
                    options,
                    manifest,
                    checkpoint,
                )
                report["database_writes_attempted"] = True
                report["database_writes_committed"] = True

            else:
                report["rollback"] = run_rollback(
                    connection,
                    options,
                    checkpoint,
                    rehearsal=False,
                )
                report["database_writes_attempted"] = True
                report["database_writes_committed"] = True

    report["healthy"] = True
    report["checkpoint_checksum"] = (
        checkpoint.get("checkpoint_checksum")
    )
    report["proposal_status"] = proposal.get("status")
    report["authorization_status"] = (
        authorization.get("status")
    )

    atomic_write_json(options.output, report)
    print(json.dumps(
        report,
        indent=2,
        sort_keys=True,
        default=str,
    ))

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        failure = {
            "schema_version":
                SCHEMA_VERSION,
            "healthy": False,
            "generated_at": now_iso(),
            "error":
                f"{type(exc).__name__}:{exc}",
            "fail_closed": True,
        }
        print(
            json.dumps(
                failure,
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        raise SystemExit(1)

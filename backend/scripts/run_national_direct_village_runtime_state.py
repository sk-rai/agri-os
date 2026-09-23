#!/usr/bin/env python3
"""Fail-closed national direct-village runtime campaign state engine.

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
    / "20260923-national-direct-village-runtime-campaign-v2"
)

DEFAULT_PROPOSAL = (
    CAMPAIGN_DIR
    / "national_direct_village_runtime_campaign_proposal.json"
)
DEFAULT_AUTHORIZATION = (
    CAMPAIGN_DIR
    / "national_direct_village_runtime_campaign_authorization.json"
)
DEFAULT_CHECKPOINT = (
    CAMPAIGN_DIR
    / "national_direct_village_runtime_campaign_checkpoint.json"
)
DEFAULT_OUTPUT = (
    CAMPAIGN_DIR
    / "national_direct_village_runtime_state_engine_report.json"
)

PROPOSAL_CHECKSUM = (
    "4040493550d62f4f2b4c380b404e80ff"
    "b8530c5c391f0497d022f2b638e2327e"
)
AUTHORIZATION_CHECKSUM = (
    "647bf08d951feae9adc27244c73cfa969"
    "3d6afaf7cbf48a01324eede4edd9ed0"
)
NATIONAL_MANIFEST_SHA256 = (
    "3fc6bbd0162abe635339df96c5b704dec"
    "734d8f7824c44933468ede5ecaeefc3"
)
INITIAL_CHECKPOINT_CHECKSUM = (
    "d40f510768fcfe8dbe528b0fa777f1b0"
    "102e9ebd5f83887e38af6e9a72aa7265"
)
RUNTIME_SET_ID = "e5f93e27-a0bd-5c8b-bef3-d97986e14c55"

EXPECTED_ROWS = 449_789
EXPECTED_STATES = 30
DEFAULT_BATCH_SIZE = 25_000
MAX_BATCH_SIZE = 25_000

SOURCE_CRS = "EPSG:7755"
TARGET_CRS = "EPSG:4326"

ADVISORY_LOCK_KEY = 7_621_092_021
MARKER = "national_direct_village_runtime_campaign"
SCHEMA_VERSION = "national_direct_village_runtime_state_engine.v1"

REVIEWER_ID = "national-direct-match-campaign"
REVIEWER_NOTES = (
    "National direct-code village boundary candidate approved by "
    "checksum-pinned campaign; runtime rows remain separately guarded."
)

REQUIRED_TRUE_PERMISSIONS = {
    "bounded_review_metadata_write_allowed",
    "bounded_runtime_eligibility_write_allowed",
    "inactive_runtime_crosswalk_write_allowed",
    "inactive_runtime_feature_write_allowed",
    "inactive_runtime_promotion_event_write_allowed",
    "native_geometry_write_allowed",
    "state_checkpoint_write_allowed",
}

REQUIRED_FALSE_PERMISSIONS = {
    "android_behavior_change_allowed",
    "candidate_activation_allowed",
    "candidate_promotion_allowed",
    "lookup_scope_change_allowed",
    "project_match_write_allowed",
    "runtime_activation_change_allowed",
    "source_file_write_allowed",
    "source_geometry_write_allowed",
}


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
    mode.add_argument(
        "--apply",
        action="store_true",
    )
    mode.add_argument(
        "--resume",
        action="store_true",
    )
    mode.add_argument(
        "--rollback",
        action="store_true",
    )
    mode.add_argument(
        "--rollback-only-rehearsal",
        action="store_true",
    )

    parser.add_argument(
        "--enable-national-direct-village-runtime-write",
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
        1
        <= options.batch_size
        <= MAX_BATCH_SIZE
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

    gates = {
        "enable":
            options.enable_national_direct_village_runtime_write,
        "authorization_reviewed":
            options.authorization_reviewed,
        "rollback_reviewed":
            options.rollback_procedure_reviewed,
        "admin_confirmation":
            options.admin_confirmation,
    }

    failed = sorted(
        key
        for key, value in gates.items()
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
]:
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
        "proposal_schema":
            proposal.get("schema_version")
            == (
                "national_direct_village_"
                "runtime_campaign_proposal.v1"
            ),
        "proposal_healthy":
            proposal.get("healthy") is True,
        "proposal_checksum":
            proposal.get("proposal_checksum")
            == options.proposal_checksum
            == PROPOSAL_CHECKSUM,
        "authorization_schema":
            authorization.get("schema_version")
            == (
                "national_direct_village_"
                "runtime_campaign_authorization.v1"
            ),
        "authorization_healthy":
            authorization.get("healthy") is True,
        "authorization_status":
            authorization.get("status")
            == "AUTHORIZED",
        "authorization_checksum":
            authorization.get(
                "authorization_checksum"
            )
            == options.authorization_checksum
            == AUTHORIZATION_CHECKSUM,
        "authorization_proposal":
            authorization.get(
                "proposal_checksum"
            )
            == PROPOSAL_CHECKSUM,
        "proposal_manifest":
            proposal.get(
                "ordered_national_row_manifest_sha256"
            )
            == options.national_manifest_sha256
            == NATIONAL_MANIFEST_SHA256,
        "authorization_manifest":
            authorization.get(
                "ordered_national_row_manifest_sha256"
            )
            == NATIONAL_MANIFEST_SHA256,
        "checkpoint_manifest":
            checkpoint.get(
                "national_row_manifest_sha256"
            )
            == NATIONAL_MANIFEST_SHA256,
        "runtime_set":
            proposal.get("runtime_set_id")
            == authorization.get(
                "runtime_set_id"
            )
            == RUNTIME_SET_ID,
        "row_count":
            int(
                proposal.get("row_count")
                or 0
            )
            == int(
                authorization.get(
                    "maximum_authorized_row_count"
                )
                or 0
            )
            == EXPECTED_ROWS,
        "state_count":
            int(
                proposal.get("state_count")
                or 0
            )
            == int(
                authorization.get(
                    "authorized_state_count"
                )
                or 0
            )
            == EXPECTED_STATES,
        "checkpoint_proposal":
            checkpoint.get(
                "proposal_checksum"
            )
            == PROPOSAL_CHECKSUM,
        "checkpoint_authorization":
            checkpoint.get(
                "authorization_checksum"
            )
            == AUTHORIZATION_CHECKSUM,
        "checkpoint_checksum":
            (
                (
                    not checkpoint.get(
                        "execution_started"
                    )
                    and checkpoint.get(
                        "checkpoint_checksum"
                    )
                    == INITIAL_CHECKPOINT_CHECKSUM
                )
                or (
                    checkpoint.get(
                        "state_engine_schema_version"
                    )
                    == SCHEMA_VERSION
                    and checkpoint.get(
                        "checkpoint_checksum"
                    )
                    == checkpoint_checksum(
                        checkpoint
                    )
                )
            ),
        "checkpoint_state_count":
            len(
                checkpoint.get("states")
                or []
            )
            == EXPECTED_STATES,
    }

    if not checkpoint.get(
        "execution_started"
    ):
        checks["initial_checkpoint"] = (
            checkpoint.get(
                "checkpoint_checksum"
            )
            == INITIAL_CHECKPOINT_CHECKSUM
        )

    permissions = (
        authorization.get("permissions")
        or {}
    )

    checks["allowed_permissions"] = all(
        permissions.get(key) is True
        for key in REQUIRED_TRUE_PERMISSIONS
    )
    checks["prohibited_permissions"] = all(
        permissions.get(key) is False
        for key in REQUIRED_FALSE_PERMISSIONS
    )

    states = (
        checkpoint.get("states")
        or []
    )
    state_codes = [
        int(state["state_lgd_code"])
        for state in states
    ]

    checks["deterministic_state_order"] = (
        state_codes == sorted(state_codes)
        and len(set(state_codes))
        == EXPECTED_STATES
    )
    checks["checkpoint_row_total"] = (
        sum(
            int(
                state.get(
                    "expected_row_count"
                )
                or 0
            )
            for state in states
        )
        == EXPECTED_ROWS
    )

    proposal_states = {
        str(state["state_lgd_code"]): state
        for state in (
            proposal.get("state_manifests")
            or []
        )
    }

    checks["state_artifact_identity"] = (
        len(proposal_states)
        == EXPECTED_STATES
        and all(
            code in proposal_states
            and int(
                proposal_states[code].get(
                    "row_count"
                )
                or 0
            )
            == int(
                state.get(
                    "expected_row_count"
                )
                or 0
            )
            and proposal_states[code].get(
                "ordered_row_manifest_sha256"
            )
            == state.get(
                "ordered_row_manifest_sha256"
            )
            and proposal_states[code].get(
                "source_file_sha256"
            )
            == state.get(
                "source_file_sha256"
            )
            for state in states
            for code in [
                str(state["state_lgd_code"])
            ]
        )
    )

    failed = sorted(
        key
        for key, value in checks.items()
        if not value
    )

    if failed:
        raise ValueError(
            "CAMPAIGN_ARTIFACT_VALIDATION_FAILED:"
            + ",".join(failed)
        )

    return proposal, authorization, checkpoint




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


SELECTION_FROM_SQL = """
    from geography_boundary_crosswalk_candidates c
    join geography_boundary_source_features f
      on f.id = c.source_feature_id
    join geography_boundary_import_batches
      source_batch
      on source_batch.id = c.import_batch_id
    join geography_villages canonical_village
      on canonical_village.id =
         c.proposed_village_id
    join geography_districts canonical_district
      on canonical_district.id =
         canonical_village.district_id
    join geography_states canonical_state
      on canonical_state.id =
         canonical_district.state_id
    left join geography_blocks canonical_block
      on canonical_block.id =
         canonical_village.block_id
    where c.candidate_bucket =
            'DIRECT_VLCODE_MATCH'
      and c.promotion_status = 'NOT_PROMOTED'
      and c.is_active = false
      and c.proposed_village_id is not null
      and canonical_state.lgd_code =
            :state_code
      and f.geometry_validation_status =
            'VALIDATED'
      and (
        case
          when canonical_state.lgd_code::text =
                 '1'
            then source_batch.state_or_ut =
                 'Jammu & Kashmir'
          when canonical_state.lgd_code::text =
                 '38'
            then source_batch.state_or_ut =
                 'Dadra and Nagar Haveli and Daman & Diu'
          else
            lower(
              regexp_replace(
                source_batch.state_or_ut,
                '[^a-zA-Z]+',
                '',
                'g'
              )
            )
            =
            lower(
              regexp_replace(
                canonical_state.canonical_name,
                '[^a-zA-Z]+',
                '',
                'g'
              )
            )
        end
      )
      and not exists (
        select 1
        from geography_boundary_crosswalk_candidates
          duplicate_candidate
        join geography_boundary_source_features
          duplicate_source
          on duplicate_source.id =
             duplicate_candidate.source_feature_id
        where duplicate_candidate.proposed_village_id =
                c.proposed_village_id
          and duplicate_candidate.id <> c.id
          and duplicate_candidate.candidate_bucket =
                'DIRECT_VLCODE_MATCH'
          and duplicate_candidate.promotion_status =
                'NOT_PROMOTED'
          and duplicate_candidate.is_active = false
          and duplicate_source.geometry_validation_status =
                'VALIDATED'
      )
      and not exists (
        select 1
        from geography_boundary_runtime_crosswalks rw
        where rw.runtime_set_id =
                cast(:runtime_set_id as uuid)
          and rw.source_candidate_id = c.id
      )
"""


def selected_rows(
    connection,
    state_code: str,
    cursor: int,
    limit: int,
) -> list[dict[str, Any]]:
    rows = connection.execute(text(
        """
        select
          c.id::text as candidate_id,
          c.import_batch_id::text,
          c.source_feature_id::text,
          c.source_feature_index,
          c.confidence,
          c.proposed_scope,
          canonical_state.id::text
            as proposed_state_id,
          canonical_district.id::text
            as proposed_district_id,
          canonical_block.id::text
            as proposed_block_id,
          canonical_village.id::text
            as proposed_village_id,
          canonical_state.lgd_code
            as proposed_state_lgd_code,
          canonical_district.lgd_code
            as proposed_district_lgd_code,
          canonical_block.lgd_code
            as proposed_block_lgd_code,
          canonical_village.lgd_code
            as proposed_village_lgd_code,
          c.source_codes,
          c.source_names,
          c.match_evidence,
          c.review_status,
          c.reviewer_decision,
          c.reviewer_id,
          c.reviewer_notes,
          c.reviewed_at,
          f.feature_category,
          f.source_geometry_hash,
          f.transformed_bbox,
          f.transformed_centroid,
          f.eligible_for_runtime_after_promotion
        """
        + SELECTION_FROM_SQL
        + """
          and c.source_feature_index > :cursor
        order by
          c.source_feature_index,
          c.id
        limit :limit
        """
    ), {
        "state_code": state_code,
        "cursor": cursor,
        "limit": limit,
        "runtime_set_id": RUNTIME_SET_ID,
    }).mappings().all()

    return [
        dict(row)
        for row in rows
    ]


def state_population_count(
    connection,
    state_code: str,
) -> int:
    return int(
        connection.execute(
            text(
                "select count(*) "
                + SELECTION_FROM_SQL
            ),
            {
                "state_code": state_code,
                "runtime_set_id":
                    RUNTIME_SET_ID,
            },
        ).scalar_one()
        or 0
    )


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
        "national_row_manifest_sha256":
            NATIONAL_MANIFEST_SHA256,
        "state_lgd_code": state_code,
        "transaction_id": transaction_id,
        "runtime_activation_changed": False,
        "lookup_scope_changed": False,
        "candidate_activation_changed": False,
        "candidate_promotion_changed": False,
        "project_matches_written": False,
        "source_geometry_written": False,
        "source_files_written": False,
        "android_behavior_changed": False,
    }


def apply_batch(
    connection,
    state: dict[str, Any],
    rows: list[dict[str, Any]],
    geometries: dict[int, dict[str, Any]],
    operator: str,
) -> dict[str, Any]:
    state_code = str(
        state["state_lgd_code"]
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
    promotion_event_id = stable_uuid(
        "promotion-event",
        state_code,
        first_index,
        last_index,
    )
    metadata = campaign_metadata(
        state_code,
        transaction_id,
    )

    input_rows = []

    for row in rows:
        source_index = int(
            row["source_feature_index"]
        )
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
            "geometry_wgs84":
                geometries[source_index],
            "campaign_metadata": metadata,
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
        "metadata": json.dumps(metadata),
        "state_code": state_code,
    }

    connection.execute(
        text(
            "set local lock_timeout = '10s'"
        )
    )
    connection.execute(
        text(
            "set local statement_timeout = '30min'"
        )
    )

    connection.execute(text("""
        create temporary table national_runtime_input
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
        connection.execute(text("""
            select count(*)
            from (
              select c.id
              from national_runtime_input input
              join geography_boundary_crosswalk_candidates c
                on c.id = input.candidate_id
              join geography_boundary_source_features f
                on f.id = input.source_feature_id
              join geography_villages canonical_village
                on canonical_village.id =
                   c.proposed_village_id
              join geography_districts canonical_district
                on canonical_district.id =
                   canonical_village.district_id
              join geography_states canonical_state
                on canonical_state.id =
                   canonical_district.state_id
              where c.source_feature_id =
                      input.source_feature_id
                and c.source_feature_index =
                      input.source_feature_index
                and c.candidate_bucket =
                      'DIRECT_VLCODE_MATCH'
                and c.promotion_status =
                      'NOT_PROMOTED'
                and c.is_active = false
                and c.proposed_village_id
                      is not null
                and canonical_state.lgd_code =
                      :state_code
                and f.geometry_validation_status =
                      'VALIDATED'
                and not exists (
                  select 1
                  from geography_boundary_crosswalk_candidates
                    duplicate_candidate
                  join geography_boundary_source_features
                    duplicate_source
                    on duplicate_source.id =
                       duplicate_candidate.source_feature_id
                  where duplicate_candidate.proposed_village_id =
                          c.proposed_village_id
                    and duplicate_candidate.id <> c.id
                    and duplicate_candidate.candidate_bucket =
                          'DIRECT_VLCODE_MATCH'
                    and duplicate_candidate.promotion_status =
                          'NOT_PROMOTED'
                    and duplicate_candidate.is_active = false
                    and duplicate_source.geometry_validation_status =
                          'VALIDATED'
                )
                and not exists (
                  select 1
                  from geography_boundary_runtime_crosswalks
                    existing_runtime
                  where existing_runtime.runtime_set_id =
                          cast(:runtime_set_id as uuid)
                    and existing_runtime.source_candidate_id =
                          c.id
                )
              order by
                c.source_feature_index,
                c.id
              for update of c, f
            ) locked
        """), params).scalar_one()
    )

    if locked_count != len(rows):
        raise ValueError(
            "LOCKED_ROW_COUNT_MISMATCH:"
            f"{locked_count}:{len(rows)}"
        )

    promotion_events = connection.execute(text("""
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
            'state_lgd_code',
              :state_code,
            'proposal_checksum',
              :proposal_checksum
          ),
          cast(:metadata as jsonb),
          cast(:metadata as jsonb),
          false
        from national_runtime_input
        on conflict (id) do nothing
        returning id
    """), params).rowcount

    if promotion_events != 1:
        raise ValueError(
            "PROMOTION_EVENT_INSERT_COUNT_MISMATCH"
        )

    review_rows = connection.execute(text("""
        update
          geography_boundary_crosswalk_candidates
            as candidate
        set
          review_status =
            'APPROVED_FOR_PROMOTION',
          reviewer_decision =
            'ACCEPT_DIRECT_CODE_MATCH',
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
                    ->>'transaction_id'
              )
            ),
          updated_at = now()
        from national_runtime_input input
        where candidate.id =
              input.candidate_id
        returning candidate.id
    """), {
        **params,
        "reviewer_notes": REVIEWER_NOTES,
        "marker": MARKER,
    }).rowcount

    eligibility_rows = connection.execute(text("""
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
                    ->>'transaction_id'
              )
            ),
          updated_at = now()
        from national_runtime_input input
        where source.id =
              input.source_feature_id
        returning source.id
    """), {
        **params,
        "marker": MARKER,
    }).rowcount

    runtime_features = connection.execute(text("""
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
        from national_runtime_input input
        order by
          input.source_feature_index,
          input.candidate_id
        returning id
    """), params).rowcount

    runtime_crosswalks = connection.execute(text("""
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
          input.proposed_scope,
          input.proposed_state_id,
          input.proposed_district_id,
          input.proposed_block_id,
          input.proposed_village_id,
          input.proposed_state_lgd_code,
          input.proposed_district_lgd_code,
          input.proposed_block_lgd_code,
          input.proposed_village_lgd_code,
          input.confidence,
          'ACCEPT_DIRECT_CODE_MATCH',
          input.promotion_event_id,
          input.campaign_metadata,
          false
        from national_runtime_input input
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
    exact_keys = (
        "review_metadata",
        "runtime_eligibility",
        "runtime_features",
        "runtime_crosswalks",
    )

    if any(
        counts[key] != expected
        for key in exact_keys
    ):
        raise ValueError(
            "EXACT_RETURNED_ROW_RECONCILIATION_FAILED:"
            + json.dumps(
                counts,
                sort_keys=True,
            )
        )

    guardrails = connection.execute(text("""
        select
          count(*) filter (
            where feature.is_active
          )::bigint as active_features,
          count(*) filter (
            where crosswalk.is_active
          )::bigint as active_crosswalks,
          count(*) filter (
            where candidate.is_active
          )::bigint as active_candidates,
          count(*) filter (
            where candidate.promotion_status
                  <> 'NOT_PROMOTED'
          )::bigint as promoted_candidates,
          count(*) filter (
            where feature.geometry_wgs84_geom
                  is null
          )::bigint as missing_native_geometry,
          count(*) filter (
            where not ST_IsValid(
              feature.geometry_wgs84_geom
            )
          )::bigint as invalid_native_geometry
        from national_runtime_input input
        join geography_boundary_runtime_features
          feature
          on feature.id =
             input.runtime_feature_id
        join geography_boundary_runtime_crosswalks
          crosswalk
          on crosswalk.id =
             input.runtime_crosswalk_id
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
    state_code = str(
        state["state_lgd_code"]
    )

    row = connection.execute(text("""
        select
          (
            select count(*)::bigint
            from geography_boundary_crosswalk_candidates
              candidate
            join geography_villages canonical_village
              on canonical_village.id =
                 candidate.proposed_village_id
            join geography_districts canonical_district
              on canonical_district.id =
                 canonical_village.district_id
            join geography_states canonical_state
              on canonical_state.id =
                 canonical_district.state_id
            where candidate.metadata
                    ->:marker
                    ->>'proposal_checksum'
                  = :proposal_checksum
              and canonical_state.lgd_code
                  = :state_code
          ) as review_metadata,
          (
            select count(distinct source.id)::bigint
            from geography_boundary_source_features
              source
            join geography_boundary_crosswalk_candidates
              candidate
              on candidate.source_feature_id =
                 source.id
            join geography_villages canonical_village
              on canonical_village.id =
                 candidate.proposed_village_id
            join geography_districts canonical_district
              on canonical_district.id =
                 canonical_village.district_id
            join geography_states canonical_state
              on canonical_state.id =
                 canonical_district.state_id
            where source.metadata
                    ->:marker
                    ->>'proposal_checksum'
                  = :proposal_checksum
              and canonical_state.lgd_code
                  = :state_code
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
            + json.dumps(
                progress,
                sort_keys=True,
            )
        )

    completed = progress[
        "runtime_features"
    ]
    expected = int(
        state["expected_row_count"]
    )

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

    completed = progress[
        "runtime_features"
    ]

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
    state[
        "cursor_after_source_feature_index"
    ] = progress[
        "maximum_source_feature_index"
    ]

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
        int(
            state.get("completed_row_count")
            or 0
        )
        for state in states
    )
    checkpoint[
        "completed_transaction_count"
    ] = sum(
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
    checkpoint["resume_required"] = (
        checkpoint["execution_started"]
        and checkpoint["completed_state_count"]
        < EXPECTED_STATES
    )
    checkpoint["active_state_lgd_code"] = None
    checkpoint["active_transaction"] = None
    checkpoint["generated_at"] = now_iso()
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

    state_code = str(
        state["state_lgd_code"]
    )

    guardrails = connection.execute(text("""
        select
          count(*) filter (
            where feature.is_active
          )::bigint as active_features,
          count(*) filter (
            where crosswalk.is_active
          )::bigint as active_crosswalks,
          count(*) filter (
            where candidate.is_active
          )::bigint as active_candidates,
          count(*) filter (
            where candidate.promotion_status
                  <> 'NOT_PROMOTED'
          )::bigint as promoted_candidates,
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
          )::bigint as invalid_srid
        from geography_boundary_runtime_features
          feature
        join geography_boundary_runtime_crosswalks
          crosswalk
          on crosswalk.runtime_feature_id =
             feature.id
         and crosswalk.runtime_set_id =
             feature.runtime_set_id
        join geography_boundary_crosswalk_candidates
          candidate
          on candidate.id =
             crosswalk.source_candidate_id
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
            for key, value
            in guardrails.items()
        },
    }


def run_apply(
    connection,
    options: argparse.Namespace,
    checkpoint: dict[str, Any],
) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []

    for state in checkpoint["states"]:
        state_code = str(
            state["state_lgd_code"]
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

            state["reconciliation"] = (
                reconciliation
            )
            reports.append({
                "state_lgd_code": state_code,
                "action":
                    "RESUME_VALIDATED_NO_REPLAY",
                "row_count":
                    progress["runtime_features"],
            })
            continue

        source_path = Path(
            state["source_file"]
        )

        if not source_path.is_file():
            raise ValueError(
                "PINNED_STATE_SOURCE_NOT_FOUND:"
                f"{state_code}:{source_path}"
            )

        actual_source_checksum = (
            sha256_file(source_path)
        )
        if (
            actual_source_checksum
            != state["source_file_sha256"]
        ):
            raise ValueError(
                "PINNED_STATE_SOURCE_CHECKSUM_MISMATCH:"
                f"{state_code}:"
                f"expected="
                f"{state['source_file_sha256']}:"
                f"actual={actual_source_checksum}"
            )

        cursor = int(
            state.get(
                "cursor_after_source_feature_index"
            )
            or -1
        )
        state["status"] = "IN_PROGRESS"
        state["last_error"] = None

        while True:
            rows = selected_rows(
                connection,
                state_code,
                cursor,
                options.batch_size,
            )

            # End the read transaction before starting
            # the bounded write transaction.
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

            checkpoint[
                "active_state_lgd_code"
            ] = state_code
            checkpoint["active_transaction"] = {
                "transaction_id":
                    transaction_id,
                "first_source_feature_index":
                    first_index,
                "last_source_feature_index":
                    last_index,
                "row_count": len(rows),
            }
            state["active_transaction"] = (
                checkpoint[
                    "active_transaction"
                ]
            )
            checkpoint[
                "resume_required"
            ] = True
            checkpoint[
                "checkpoint_checksum"
            ] = checkpoint_checksum(
                checkpoint
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

            # Recover committed truth from the database.
            # This also handles a prior commit followed by
            # interruption before checkpoint persistence.
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
                "state_lgd_code":
                    state_code,
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

        state["reconciliation"] = (
            reconciliation
        )
        state["status"] = "COMPLETED"
        state["active_transaction"] = None

        refresh_checkpoint(checkpoint)

        state_checkpoint_path = Path(
            state["checkpoint_json"]
        )
        state_audit_path = Path(
            state["audit_json"]
        )

        atomic_write_json(
            state_checkpoint_path,
            {
                "schema_version":
                    SCHEMA_VERSION,
                "status": "COMPLETED",
                "proposal_checksum":
                    PROPOSAL_CHECKSUM,
                "authorization_checksum":
                    AUTHORIZATION_CHECKSUM,
                "national_row_manifest_sha256":
                    NATIONAL_MANIFEST_SHA256,
                "state": state,
            },
        )
        atomic_write_json(
            state_audit_path,
            {
                "schema_version":
                    SCHEMA_VERSION,
                "healthy": True,
                "action":
                    "APPLIED_AND_RECONCILED",
                "generated_at": now_iso(),
                "proposal_checksum":
                    PROPOSAL_CHECKSUM,
                "authorization_checksum":
                    AUTHORIZATION_CHECKSUM,
                "state_lgd_code":
                    state_code,
                "expected_row_count":
                    state["expected_row_count"],
                "reconciliation":
                    reconciliation,
                "fail_closed_guardrails": {
                    "runtime_activation_changed":
                        False,
                    "lookup_scope_changed":
                        False,
                    "candidate_activation_changed":
                        False,
                    "candidate_promotion_changed":
                        False,
                    "project_matches_written":
                        False,
                    "source_geometry_written":
                        False,
                    "source_files_written":
                        False,
                    "android_behavior_changed":
                        False,
                },
            },
        )
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
            "NATIONAL_COMPLETION_RECONCILIATION_FAILED:"
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
    state_code = str(
        state["state_lgd_code"]
    )

    params = {
        "runtime_set_id": RUNTIME_SET_ID,
        "proposal_checksum":
            PROPOSAL_CHECKSUM,
        "marker": MARKER,
        "state_code": state_code,
        "operator": operator,
    }

    connection.execute(
        text(
            "set local lock_timeout = '10s'"
        )
    )
    connection.execute(
        text(
            "set local statement_timeout = '30min'"
        )
    )

    crosswalks = connection.execute(text("""
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

    features = connection.execute(text("""
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

    events = connection.execute(text("""
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

    sources = connection.execute(text("""
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
        from geography_boundary_crosswalk_candidates
          candidate,
          geography_villages canonical_village,
          geography_districts canonical_district,
          geography_states canonical_state
        where candidate.source_feature_id =
                source.id
          and canonical_village.id =
                candidate.proposed_village_id
          and canonical_district.id =
                canonical_village.district_id
          and canonical_state.id =
                canonical_district.state_id
          and canonical_state.lgd_code =
                :state_code
          and source.metadata
                ->:marker
                ->>'proposal_checksum'
              = :proposal_checksum
        returning source.id
    """), params).rowcount

    candidates = connection.execute(text("""
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
        from
          geography_villages canonical_village,
          geography_districts canonical_district,
          geography_states canonical_state
        where canonical_village.id =
                candidate.proposed_village_id
          and canonical_district.id =
                canonical_village.district_id
          and canonical_state.id =
                canonical_district.state_id
          and canonical_state.lgd_code =
                :state_code
          and candidate.metadata
                ->:marker
                ->>'proposal_checksum'
              = :proposal_checksum
          and candidate.is_active = false
          and candidate.promotion_status =
                'NOT_PROMOTED'
        returning candidate.id
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

    exact_counts = {
        crosswalks,
        features,
        sources,
        candidates,
    }
    if len(exact_counts) != 1:
        raise ValueError(
            "ROLLBACK_EXACT_RECONCILIATION_FAILED:"
            f"{state_code}:"
            + json.dumps(
                counts,
                sort_keys=True,
            )
        )

    return counts


def reset_state_checkpoint(
    state: dict[str, Any],
) -> None:
    state.update({
        "active_transaction": None,
        "completed_row_count": 0,
        "completed_transaction_count": 0,
        "cursor_after_source_feature_index":
            -1,
        "last_error": None,
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
        key=lambda state: int(
            state["sequence"]
        ),
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
                if not progress[
                    "runtime_features"
                ]:
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

    for state in states:
        progress = state_database_progress(
            connection,
            state,
        )
        connection.commit()

        if not progress["runtime_features"]:
            reset_state_checkpoint(state)
            refresh_checkpoint(checkpoint)
            atomic_write_json(
                options.checkpoint_json,
                checkpoint,
            )
            continue

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

        reset_state_checkpoint(state)
        refresh_checkpoint(checkpoint)
        atomic_write_json(
            options.checkpoint_json,
            checkpoint,
        )

        reports.append({
            "state_lgd_code":
                state["state_lgd_code"],
            "rehearsal": False,
            **counts,
        })

    refresh_checkpoint(checkpoint)
    atomic_write_json(
        options.checkpoint_json,
        checkpoint,
    )

    return reports




def run_apply_rollback_rehearsal(
    connection,
    options: argparse.Namespace,
    checkpoint: dict[str, Any],
) -> dict[str, Any]:
    """Apply the first authorized state and always roll it back."""

    state = checkpoint["states"][0]
    state_code = str(state["state_lgd_code"])
    expected = int(state["expected_row_count"])
    source_path = Path(state["source_file"])

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
        state_code,
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
            + json.dumps(
                {
                    "before": before,
                    "after": after,
                },
                sort_keys=True,
            )
        )

    return {
        "state_lgd_code": state_code,
        "row_count": len(rows),
        "source_file": str(source_path),
        "source_file_sha256": source_checksum,
        "apply_report": apply_report,
        "during_transaction": during,
        "rollback_executed": True,
        "database_state_unchanged": True,
        "checkpoint_written": False,
        "before": before,
        "after": after,
    }
def dry_run_inventory(
    connection,
    checkpoint: dict[str, Any],
) -> dict[str, Any]:
    states = []

    total_remaining = 0
    total_completed = 0

    for state in checkpoint["states"]:
        state_code = str(
            state["state_lgd_code"]
        )
        remaining = state_population_count(
            connection,
            state_code,
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

        completed = progress[
            "runtime_features"
        ]
        expected = int(
            state["expected_row_count"]
        )

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
            "state_lgd_code":
                state_code,
            "expected_row_count":
                expected,
            "remaining_row_count":
                remaining,
            "completed_row_count":
                completed,
            "source_file":
                state["source_file"],
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
            "DRY_RUN_NATIONAL_ROW_COUNT_MISMATCH"
        )

    return {
        "remaining_row_count":
            total_remaining,
        "completed_row_count":
            total_completed,
        "authorized_row_count":
            EXPECTED_ROWS,
        "states": states,
    }


def main() -> int:
    options = arguments()

    validate_mutation_gates(options)

    proposal, authorization, checkpoint = (
        validate_artifacts(options)
    )

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
        "proposal_checksum":
            PROPOSAL_CHECKSUM,
        "authorization_checksum":
            AUTHORIZATION_CHECKSUM,
        "national_row_manifest_sha256":
            NATIONAL_MANIFEST_SHA256,
        "runtime_set_id": RUNTIME_SET_ID,
        "authorized_row_count":
            EXPECTED_ROWS,
        "authorized_state_count":
            EXPECTED_STATES,
        "batch_size":
            options.batch_size,
        "writer_count": 1,
        "single_writer": True,
        "guardrails": {
            "runtime_activation_changed":
                False,
            "lookup_scope_changed":
                False,
            "candidate_activation_changed":
                False,
            "candidate_promotion_changed":
                False,
            "project_matches_written":
                False,
            "source_geometry_written":
                False,
            "source_files_written":
                False,
            "android_behavior_changed":
                False,
        },
    }

    engine = create_engine(
        db_url(),
        future=True,
    )

    with engine.connect() as connection:
        report["preflight"] = preflight(
            connection
        )
        connection.commit()

        with single_writer(connection):
            if mode == "DRY_RUN":
                report["inventory"] = (
                    dry_run_inventory(
                        connection,
                        checkpoint,
                    )
                )
                report[
                    "database_writes_attempted"
                ] = False
                report[
                    "database_writes_committed"
                ] = False

            elif mode == (
                "ROLLBACK_ONLY_REHEARSAL"
            ):
                report["rollback_rehearsal"] = (
                    run_apply_rollback_rehearsal(
                        connection,
                        options,
                        checkpoint,
                    )
                )
                report[
                    "database_writes_attempted"
                ] = True
                report[
                    "database_writes_committed"
                ] = False

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
                    # A DB commit may have occurred before
                    # checkpoint persistence. Recover DB truth.
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

                report["transactions"] = (
                    run_apply(
                        connection,
                        options,
                        checkpoint,
                    )
                )
                report[
                    "database_writes_attempted"
                ] = True
                report[
                    "database_writes_committed"
                ] = True

            else:
                report["rollback"] = (
                    run_rollback(
                        connection,
                        options,
                        checkpoint,
                        rehearsal=False,
                    )
                )
                report[
                    "database_writes_attempted"
                ] = True
                report[
                    "database_writes_committed"
                ] = True

    report["healthy"] = True
    report["checkpoint_checksum"] = (
        checkpoint.get(
            "checkpoint_checksum"
        )
    )
    report["proposal_status"] = (
        proposal.get("status")
    )
    report["authorization_status"] = (
        authorization.get("status")
    )

    atomic_write_json(
        options.output,
        report,
    )
    print(
        json.dumps(
            report,
            indent=2,
            sort_keys=True,
            default=str,
        )
    )

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

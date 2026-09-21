#!/usr/bin/env python3
"""Generate an unauthorized native runtime geometry backfill proposal."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.database import engine

RUNTIME_SET_ID = "e5f93e27-a0bd-5c8b-bef3-d97986e14c55"
EXPECTED_ROWS = 10


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fixture",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )
    return parser.parse_args()


def canonical_checksum(value) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()


def file_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    options = arguments()

    fixture = json.loads(
        options.fixture.read_text(encoding="utf-8")
    )
    features = fixture.get("features") or []

    if fixture.get("type") != "FeatureCollection":
        raise SystemExit(
            "BACKFILL_FIXTURE_NOT_FEATURE_COLLECTION"
        )
    if len(features) != EXPECTED_ROWS:
        raise SystemExit(
            "BACKFILL_FIXTURE_ROW_COUNT_MISMATCH"
        )

    feature_by_runtime_id = {}
    for feature in features:
        properties = feature.get("properties") or {}
        runtime_feature_id = properties.get(
            "runtime_feature_id"
        )
        geometry = feature.get("geometry") or {}

        if not runtime_feature_id:
            raise SystemExit(
                "BACKFILL_RUNTIME_FEATURE_ID_MISSING"
            )
        if runtime_feature_id in feature_by_runtime_id:
            raise SystemExit(
                "BACKFILL_RUNTIME_FEATURE_ID_DUPLICATE"
            )
        if geometry.get("type") not in {
            "Polygon",
            "MultiPolygon",
        }:
            raise SystemExit(
                "BACKFILL_GEOMETRY_TYPE_INVALID:"
                f"{runtime_feature_id}"
            )

        feature_by_runtime_id[
            runtime_feature_id
        ] = feature

    fixture_ids = sorted(feature_by_runtime_id)
    fixture_id_payload = json.dumps(
        fixture_ids,
        separators=(",", ":"),
    )

    with engine.connect() as connection:
        revision = str(
            connection.execute(text("""
                select version_num
                from alembic_version
            """)).scalar_one()
        )

        column_exists = bool(
            connection.execute(text("""
                select exists (
                  select 1
                  from information_schema.columns
                  where table_schema = current_schema()
                    and table_name =
                      'geography_boundary_runtime_features'
                    and column_name =
                      'geometry_wgs84_geom'
                )
            """)).scalar_one()
        )

        db_rows = [
            dict(row)
            for row in connection.execute(
                text("""
                    with expected as (
                      select value::uuid
                        as runtime_feature_id
                      from jsonb_array_elements_text(
                        cast(:feature_ids as jsonb)
                      )
                    )
                    select
                      rf.id::text
                        as runtime_feature_id,
                      rf.runtime_set_id::text
                        as runtime_set_id,
                      rf.source_feature_id::text
                        as source_feature_id,
                      rf.source_feature_index,
                      rf.geometry_hash
                        as runtime_archive_shape_hash,
                      rf.geometry_validation_status,
                      rf.is_active
                        as runtime_feature_active,
                      rf.geometry_wgs84_geom is null
                        as native_geometry_is_null,
                      rw.id::text
                        as runtime_crosswalk_id,
                      rw.village_id::text
                        as village_id,
                      rw.village_lgd_code,
                      rw.runtime_scope,
                      rw.is_active
                        as runtime_crosswalk_active,
                      sf.geometry_validation_status
                        as source_validation_status,
                      sf.eligible_for_runtime_after_promotion
                        as source_runtime_eligible
                    from expected e
                    join geography_boundary_runtime_features rf
                      on rf.id = e.runtime_feature_id
                    join geography_boundary_runtime_crosswalks rw
                      on rw.runtime_feature_id = rf.id
                     and rw.runtime_set_id = rf.runtime_set_id
                    join geography_boundary_source_features sf
                      on sf.id = rf.source_feature_id
                    order by rf.source_feature_index
                """),
                {"feature_ids": fixture_id_payload},
            ).mappings().all()
        ]

        counts = dict(
            connection.execute(text("""
                select
                  (
                    select count(*)::bigint
                    from geography_boundary_runtime_features
                    where runtime_set_id =
                      cast(:set_id as uuid)
                  ) as target_runtime_feature_rows,
                  (
                    select count(*)::bigint
                    from geography_boundary_runtime_features
                    where runtime_set_id =
                      cast(:set_id as uuid)
                      and geometry_wgs84_geom
                        is not null
                  ) as populated_native_geometry_rows,
                  (
                    select count(*)::bigint
                    from geography_boundary_runtime_crosswalks
                    where runtime_set_id =
                      cast(:set_id as uuid)
                  ) as target_runtime_crosswalk_rows,
                  (
                    select count(*)::bigint
                    from geography_boundary_crosswalk_candidates
                    where is_active = true
                  ) as active_candidate_rows,
                  (
                    select count(*)::bigint
                    from geography_boundary_crosswalk_candidates
                    where promotion_status = 'PROMOTED'
                  ) as promoted_candidate_rows,
                  (
                    select count(*)::bigint
                    from geography_boundary_project_matches
                  ) as project_match_rows
            """), {
                "set_id": RUNTIME_SET_ID,
            }).mappings().one()
        )

    counts = {
        key: int(value or 0)
        for key, value in counts.items()
    }

    if revision != "059":
        raise SystemExit(
            "BACKFILL_SCHEMA_REVISION_MISMATCH:"
            f"{revision}"
        )
    if not column_exists:
        raise SystemExit(
            "BACKFILL_NATIVE_GEOMETRY_COLUMN_MISSING"
        )
    if len(db_rows) != EXPECTED_ROWS:
        raise SystemExit(
            "BACKFILL_DATABASE_ROW_COUNT_MISMATCH"
        )

    proposal_rows = []

    for db_row in db_rows:
        runtime_feature_id = db_row[
            "runtime_feature_id"
        ]
        feature = feature_by_runtime_id[
            runtime_feature_id
        ]
        properties = feature["properties"]
        geometry = feature["geometry"]

        identity_checks = {
            "runtime_set_matches":
                db_row["runtime_set_id"]
                == RUNTIME_SET_ID,
            "runtime_crosswalk_matches":
                db_row["runtime_crosswalk_id"]
                == properties[
                    "runtime_crosswalk_id"
                ],
            "source_feature_index_matches":
                int(db_row["source_feature_index"])
                == int(properties[
                    "source_feature_index"
                ]),
            "village_id_matches":
                db_row["village_id"]
                == properties["village_id"],
            "village_lgd_code_matches":
                str(db_row["village_lgd_code"])
                == str(properties[
                    "village_lgd_code"
                ]),
            "runtime_archive_shape_hash_matches":
                db_row[
                    "runtime_archive_shape_hash"
                ]
                == properties[
                    "runtime_archive_shape_hash"
                ],
            "runtime_feature_active":
                db_row["runtime_feature_active"]
                is True,
            "runtime_crosswalk_active":
                db_row["runtime_crosswalk_active"]
                is True,
            "runtime_scope_is_village":
                db_row["runtime_scope"]
                == "village",
            "runtime_geometry_validated":
                db_row[
                    "geometry_validation_status"
                ] == "VALIDATED",
            "source_geometry_validated":
                db_row[
                    "source_validation_status"
                ] == "VALIDATED",
            "source_runtime_eligible":
                db_row["source_runtime_eligible"]
                is True,
            "native_geometry_is_null":
                db_row["native_geometry_is_null"]
                is True,
        }

        if not all(identity_checks.values()):
            raise SystemExit(
                "BACKFILL_IDENTITY_RECONCILIATION_FAILED:"
                f"{runtime_feature_id}:"
                + json.dumps(
                    identity_checks,
                    sort_keys=True,
                )
            )

        row_core = {
            "runtime_set_id":
                RUNTIME_SET_ID,
            "runtime_feature_id":
                runtime_feature_id,
            "runtime_crosswalk_id":
                db_row["runtime_crosswalk_id"],
            "source_feature_id":
                db_row["source_feature_id"],
            "source_feature_index":
                int(db_row["source_feature_index"]),
            "village_id":
                db_row["village_id"],
            "village_lgd_code":
                str(db_row["village_lgd_code"]),
            "runtime_scope":
                db_row["runtime_scope"],
            "runtime_archive_shape_hash":
                properties[
                    "runtime_archive_shape_hash"
                ],
            "normalized_geojson_geometry_hash":
                properties[
                    "normalized_geojson_geometry_hash"
                ],
            "native_geometry_before": None,
            "planned_geometry":
                geometry,
            "planned_srid": 4326,
            "planned_geometry_type":
                geometry["type"],
            "identity_checks":
                identity_checks,
        }

        row_core["planned_geometry_checksum"] = (
            canonical_checksum(geometry)
        )
        row_core["row_checksum"] = (
            canonical_checksum(row_core)
        )
        proposal_rows.append(row_core)

    proposal_rows.sort(
        key=lambda row: (
            row["source_feature_index"],
            row["runtime_feature_id"],
        )
    )

    proposal_core = {
        "schema_version":
            "nwdp_runtime_geometry_backfill_proposal.v1",
        "proposal_id":
            "20260921-karnataka-active-10-runtime-geometry",
        "status":
            "PROPOSED_NOT_AUTHORIZED",
        "runtime_set_id":
            RUNTIME_SET_ID,
        "schema_revision":
            revision,
        "fixture": {
            "path": str(options.fixture.resolve()),
            "sha256": file_checksum(options.fixture),
            "feature_count": len(features),
        },
        "row_count":
            len(proposal_rows),
        "rows":
            proposal_rows,
        "execution_policy": {
            "single_transaction": True,
            "single_writer": True,
            "idempotent_replay_required": True,
            "target_table":
                "geography_boundary_runtime_features",
            "target_column":
                "geometry_wgs84_geom",
            "spatial_constructor":
                "ST_SetSRID(ST_GeomFromGeoJSON(...),4326)",
            "required_before_value": None,
            "lookup_enablement_allowed": False,
            "runtime_activation_change_allowed": False,
            "candidate_activation_allowed": False,
            "candidate_promotion_allowed": False,
            "project_match_write_allowed": False,
            "source_feature_write_allowed": False,
            "source_file_write_allowed": False,
            "android_behavior_change_allowed": False,
        },
        "database_counts":
            counts,
        "guardrails": {
            "database_writes_attempted": False,
            "execution_started": False,
            "native_geometry_written": False,
            "lookup_api_enabled": False,
            "runtime_rows_activated": False,
            "project_matches_written": False,
            "candidate_activation_changed": False,
            "candidate_promotion_changed": False,
            "source_features_changed": False,
            "source_files_changed": False,
            "android_behavior_changed": False,
        },
    }

    proposal_checksum = canonical_checksum(
        proposal_core
    )
    confirmation = (
        "Authorize native runtime geometry backfill "
        f"{proposal_checksum} for exactly 10 active "
        "Karnataka pilot runtime features, with lookup "
        "enablement, runtime activation changes, candidate "
        "activation, candidate promotion, project match "
        "writes, source feature writes, source file writes, "
        "and Android behavior changes prohibited"
    )

    proposal = {
        **proposal_core,
        "proposal_checksum":
            proposal_checksum,
        "required_confirmation":
            confirmation,
        "generated_at":
            datetime.now(timezone.utc).isoformat(),
        "healthy": True,
        "readiness": {
            "ready_for_backfill_authorization":
                True,
            "ready_for_backfill_execution":
                False,
            "ready_for_lookup_enablement":
                False,
            "requires_exact_confirmation":
                True,
        },
    }

    options.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    options.output.write_text(
        json.dumps(
            proposal,
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )

    print(json.dumps({
        "healthy": proposal["healthy"],
        "status": proposal["status"],
        "proposal_id": proposal["proposal_id"],
        "proposal_checksum":
            proposal["proposal_checksum"],
        "row_count": proposal["row_count"],
        "runtime_set_id":
            proposal["runtime_set_id"],
        "database_counts":
            proposal["database_counts"],
        "required_confirmation":
            proposal["required_confirmation"],
        "output":
            str(options.output.resolve()),
        "guardrails":
            proposal["guardrails"],
    }, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

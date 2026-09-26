#!/usr/bin/env python3
"""Select and revalidate the post-LGD deterministic NWDP cohort.

This script is read-only. It does not authorize or perform staging,
activation, lookup exposure, candidate changes, project matching, canonical
geography changes, source writes, or Android changes.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from sqlalchemy import text

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
SCRIPT_DIR = Path(__file__).resolve().parent

for path in (BACKEND, SCRIPT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.core.database import engine
from lgd_priority_state_common import (
    DEFAULT_OUTPUT_DIR,
    atomic_write_json,
    atomic_write_jsonl,
    canonical_checksum,
    sha256_file,
)

SCHEMA_VERSION = "nwdp_post_lgd_staging_selector.v1"

DEFAULT_INPUT = (
    DEFAULT_OUTPUT_DIR
    / "nwdp_post_lgd_actionability_rows_v2.jsonl"
)
DEFAULT_AUDIT = (
    DEFAULT_OUTPUT_DIR
    / "nwdp_post_lgd_actionability_audit_v2.json"
)
DEFAULT_ROWS = (
    DEFAULT_OUTPUT_DIR
    / "nwdp_post_lgd_staging_revalidation.jsonl"
)
DEFAULT_SUMMARY = (
    DEFAULT_OUTPUT_DIR
    / "nwdp_post_lgd_staging_revalidation.json"
)

ACTIONABILITY_ROWS_SHA256 = (
    "65516c79d1ef1de7088c22880964e1cf"
    "9bd7b86154bec72075935696f83f3e1a"
)
ACTIONABILITY_AUDIT_SHA256 = (
    "cde548a919eaba5475c93942c9637e76"
    "5408a3d385d885f2cdaaee7c9e6a89ed"
)

RUNTIME_SET_ID = (
    "e5f93e27-a0bd-5c8b-bef3-d97986e14c55"
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

SELECT_SQL = text(r"""
with input as materialized (
  select *
  from jsonb_to_recordset(
    cast(:payload as jsonb)
  ) as item(
    candidate_id text,
    source_feature_id text,
    source_feature_index bigint,
    source_state text,
    source_village_code text,
    source_village_name text,
    expected_state_lgd_code text,
    expected_district_id text,
    post_import_disposition text,
    nwdp_name_disposition text,
    actionability text,
    canonical_village_id text,
    canonical_village_code text,
    canonical_village_name text,
    canonical_block_id text,
    canonical_block_code text,
    canonical_block_name text,
    canonical_district_id text,
    canonical_district_code text,
    canonical_district_name text,
    canonical_state_id text,
    canonical_state_code text,
    canonical_state_name text,
    input_row_checksum text
  )
)
select
  candidate.id::text as candidate_id,
  source.id::text as source_feature_id,
  source.source_feature_index,
  candidate.import_batch_id::text as import_batch_id,
  batch.state_or_ut as source_state,

  source.source_dtcode::text as source_district_code,
  source.source_sdcode::text as source_subdistrict_code,
  source.source_vlcode::text as source_village_code,

  nullif(
    trim(candidate.source_names->>'district'),
    ''
  ) as source_district_name,
  nullif(
    trim(candidate.source_names->>'subdistrict'),
    ''
  ) as source_subdistrict_name,
  nullif(
    trim(candidate.source_names->>'village'),
    ''
  ) as source_village_name,

  source.source_geometry_hash,
  source.geometry_validation_status,
  source.eligible_for_runtime_after_promotion,
  source.transformed_bbox,
  source.transformed_centroid,
  source.metadata->'geometry_repair' as geometry_repair,

  candidate.candidate_bucket,
  candidate.review_status,
  candidate.promotion_status,
  candidate.is_active as candidate_is_active,
  candidate.source_codes,
  candidate.source_names,
  candidate.match_evidence,
  candidate.confidence,
  candidate.proposed_scope,

  canonical_state.id::text as canonical_state_id,
  canonical_state.lgd_code::text
    as canonical_state_lgd_code,
  canonical_state.canonical_name
    as canonical_state_name,
  canonical_state.is_active
    as canonical_state_is_active,

  canonical_district.id::text
    as canonical_district_id,
  canonical_district.lgd_code::text
    as canonical_district_lgd_code,
  canonical_district.canonical_name
    as canonical_district_name,
  canonical_district.is_active
    as canonical_district_is_active,

  canonical_block.id::text as canonical_block_id,
  canonical_block.lgd_code::text
    as canonical_block_lgd_code,
  canonical_block.canonical_name
    as canonical_block_name,
  canonical_block.is_active
    as canonical_block_is_active,

  canonical_village.id::text
    as canonical_village_id,
  canonical_village.lgd_code::text
    as canonical_village_code,
  canonical_village.canonical_name
    as canonical_village_name,
  canonical_village.is_active
    as canonical_village_is_active,

  input.post_import_disposition,
  input.nwdp_name_disposition,
  input.actionability,
  input.input_row_checksum,

  exists (
    select 1
    from geography_boundary_runtime_features feature
    where feature.runtime_set_id =
          cast(:runtime_set_id as uuid)
      and feature.source_feature_id = source.id
  ) as runtime_feature_exists,

  exists (
    select 1
    from geography_boundary_runtime_crosswalks crosswalk
    where crosswalk.runtime_set_id =
          cast(:runtime_set_id as uuid)
      and (
        crosswalk.source_candidate_id = candidate.id
        or crosswalk.village_id = canonical_village.id
      )
  ) as runtime_crosswalk_exists,

  exists (
    select 1
    from geography_boundary_project_matches project_match
    where project_match.boundary_candidate_id =
          candidate.id
       or project_match.village_id =
          canonical_village.id
  ) as project_match_exists

from input
join geography_boundary_crosswalk_candidates candidate
  on candidate.id = cast(input.candidate_id as uuid)
join geography_boundary_source_features source
  on source.id = cast(input.source_feature_id as uuid)
 and source.id = candidate.source_feature_id
join geography_boundary_import_batches batch
  on batch.id = candidate.import_batch_id
join geography_villages canonical_village
  on canonical_village.id =
     cast(input.canonical_village_id as uuid)
join geography_blocks canonical_block
  on canonical_block.id =
     canonical_village.block_id
join geography_districts canonical_district
  on canonical_district.id =
     canonical_village.district_id
join geography_states canonical_state
  on canonical_state.id =
     canonical_district.state_id

where input.actionability =
        'DETERMINISTIC_INACTIVE_STAGING_CANDIDATE'
  and input.nwdp_name_disposition in (
        'EXACT_OR_PUNCTUATION_MATCH',
        'TRAILING_NUMERIC_SUFFIX_ONLY'
  )
  and input.post_import_disposition in (
        'RESOLVED_SAME_EXPECTED_DISTRICT',
        'RESOLVED_SAME_STATE_OTHER_DISTRICT'
  )
  and batch.state_or_ut = input.source_state
  and source.source_feature_index =
        input.source_feature_index
  and source.source_vlcode::bigint =
        input.source_village_code::bigint
  and canonical_village.lgd_code::bigint =
        input.canonical_village_code::bigint
  and canonical_village.canonical_name =
        input.canonical_village_name
  and canonical_block.id =
        cast(input.canonical_block_id as uuid)
  and canonical_district.id =
        cast(input.canonical_district_id as uuid)
  and canonical_state.id =
        cast(input.canonical_state_id as uuid)

order by
  canonical_state.lgd_code::bigint,
  source.source_feature_index,
  candidate.id
""")


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


def payload_row(row: dict[str, Any]) -> dict[str, Any]:
    matches = row.get("canonical_matches")
    if (
        not isinstance(matches, list)
        or len(matches) != 1
        or not isinstance(matches[0], dict)
    ):
        raise ValueError(
            "CANONICAL_MATCH_CARDINALITY:"
            f"{row.get('candidate_id')}"
        )

    match = matches[0]
    return {
        "candidate_id": row["candidate_id"],
        "source_feature_id":
            row["source_feature_id"],
        "source_feature_index":
            row["source_feature_index"],
        "source_state": row["source_state"],
        "source_village_code":
            row["source_village_code"],
        "source_village_name":
            row["source_village_name"],
        "expected_state_lgd_code":
            row["expected_state_lgd_code"],
        "expected_district_id":
            row["expected_district_id"],
        "post_import_disposition":
            row["post_import_disposition"],
        "nwdp_name_disposition":
            row["nwdp_name_disposition"],
        "actionability": row["actionability"],
        "canonical_village_id":
            match["village_id"],
        "canonical_village_code":
            match["village_code"],
        "canonical_village_name":
            match["village_name"],
        "canonical_block_id":
            match["block_id"],
        "canonical_block_code":
            match["block_code"],
        "canonical_block_name":
            match["block_name"],
        "canonical_district_id":
            match["district_id"],
        "canonical_district_code":
            match["district_code"],
        "canonical_district_name":
            match["district_name"],
        "canonical_state_id":
            match["state_id"],
        "canonical_state_code":
            match["state_code"],
        "canonical_state_name":
            match["state_name"],
        "input_row_checksum":
            row["row_checksum"],
    }


def normalized_output(row: dict[str, Any]) -> dict[str, Any]:
    value = dict(row)

    for boolean_key in (
        "candidate_is_active",
        "canonical_state_is_active",
        "canonical_district_is_active",
        "canonical_block_is_active",
        "canonical_village_is_active",
        "runtime_feature_exists",
        "runtime_crosswalk_exists",
        "project_match_exists",
        "eligible_for_runtime_after_promotion",
    ):
        value[boolean_key] = bool(
            value.get(boolean_key)
        )

    value["selector_row_checksum"] = (
        canonical_checksum(value)
    )
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
    )
    parser.add_argument(
        "--audit",
        type=Path,
        default=DEFAULT_AUDIT,
    )
    parser.add_argument(
        "--rows-output",
        type=Path,
        default=DEFAULT_ROWS,
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=DEFAULT_SUMMARY,
    )
    args = parser.parse_args()

    try:
        actual_rows_hash = sha256_file(args.input)
        actual_audit_hash = sha256_file(args.audit)

        if (
            actual_rows_hash
            != ACTIONABILITY_ROWS_SHA256
        ):
            raise ValueError(
                "ACTIONABILITY_ROWS_PIN_MISMATCH:"
                f"{actual_rows_hash}"
            )
        if (
            actual_audit_hash
            != ACTIONABILITY_AUDIT_SHA256
        ):
            raise ValueError(
                "ACTIONABILITY_AUDIT_PIN_MISMATCH:"
                f"{actual_audit_hash}"
            )

        audit = load_json(args.audit)
        all_rows = load_jsonl(args.input)

        if audit.get("healthy") is not True:
            raise ValueError(
                "ACTIONABILITY_AUDIT_NOT_HEALTHY"
            )
        if audit.get(
            "database_writes_attempted"
        ) is not False:
            raise ValueError(
                "ACTIONABILITY_AUDIT_WRITE_FLAG"
            )

        selected = [
            row for row in all_rows
            if row.get("actionability")
            == "DETERMINISTIC_INACTIVE_STAGING_CANDIDATE"
        ]

        if len(selected) != EXPECTED_ROWS:
            raise ValueError(
                f"SELECTED_ROW_COUNT:{len(selected)}"
            )

        payload = [
            payload_row(row)
            for row in selected
        ]

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
                database_rows = [
                    normalized_output(dict(row))
                    for row in connection.execute(
                        SELECT_SQL,
                        {
                            "payload": json.dumps(
                                payload,
                                ensure_ascii=False,
                                sort_keys=True,
                            ),
                            "runtime_set_id":
                                RUNTIME_SET_ID,
                        },
                    ).mappings()
                ]
            finally:
                transaction.rollback()

        by_state = Counter(
            row["source_state"]
            for row in database_rows
        )
        by_name = Counter(
            row["nwdp_name_disposition"]
            for row in database_rows
        )
        by_resolution = Counter(
            row["post_import_disposition"]
            for row in database_rows
        )

        checks = {
            "row_count":
                len(database_rows)
                == EXPECTED_ROWS,
            "state_count":
                len(by_state)
                == EXPECTED_STATES,
            "state_counts":
                by_state
                == Counter(EXPECTED_BY_STATE),
            "candidate_identity_unique":
                len({
                    row["candidate_id"]
                    for row in database_rows
                }) == EXPECTED_ROWS,
            "source_feature_identity_unique":
                len({
                    row["source_feature_id"]
                    for row in database_rows
                }) == EXPECTED_ROWS,
            "target_village_identity_unique":
                len({
                    row["canonical_village_id"]
                    for row in database_rows
                }) == EXPECTED_ROWS,
            "source_geometry_hash_present":
                all(
                    bool(row["source_geometry_hash"])
                    for row in database_rows
                ),
            "geometry_validated":
                all(
                    row["geometry_validation_status"]
                    == "VALIDATED"
                    for row in database_rows
                ),
            "canonical_hierarchy_active":
                all(
                    row["canonical_state_is_active"]
                    and row[
                        "canonical_district_is_active"
                    ]
                    and row[
                        "canonical_block_is_active"
                    ]
                    and row[
                        "canonical_village_is_active"
                    ]
                    for row in database_rows
                ),
            "candidate_not_active":
                all(
                    not row["candidate_is_active"]
                    for row in database_rows
                ),
            "candidate_not_promoted":
                all(
                    row["promotion_status"]
                    == "NOT_PROMOTED"
                    for row in database_rows
                ),
            "runtime_features_absent":
                all(
                    not row["runtime_feature_exists"]
                    for row in database_rows
                ),
            "runtime_crosswalks_absent":
                all(
                    not row[
                        "runtime_crosswalk_exists"
                    ]
                    for row in database_rows
                ),
            "project_matches_absent":
                all(
                    not row["project_match_exists"]
                    for row in database_rows
                ),
            "input_rows_pinned":
                len({
                    row["input_row_checksum"]
                    for row in database_rows
                }) == EXPECTED_ROWS,
            "no_database_writes": True,
            "not_authorized": True,
        }

        database_rows.sort(
            key=lambda row: (
                int(row["canonical_state_lgd_code"]),
                int(row["source_feature_index"]),
                row["candidate_id"],
            )
        )

        atomic_write_jsonl(
            args.rows_output,
            database_rows,
        )

        summary = {
            "schema_version": SCHEMA_VERSION,
            "status": "REVALIDATED_NOT_AUTHORIZED",
            "healthy": all(checks.values()),
            "authorized": False,
            "database_writes_attempted": False,
            "runtime_set_id": RUNTIME_SET_ID,
            "row_count": len(database_rows),
            "state_count": len(by_state),
            "checks": checks,
            "counts_by_state":
                dict(sorted(by_state.items())),
            "counts_by_name_disposition":
                dict(sorted(by_name.items())),
            "counts_by_resolution":
                dict(sorted(by_resolution.items())),
            "input_pins": {
                args.input.name:
                    actual_rows_hash,
                args.audit.name:
                    actual_audit_hash,
            },
            "rows": str(
                args.rows_output.resolve()
            ),
            "rows_sha256":
                sha256_file(args.rows_output),
            "ordered_row_manifest_sha256":
                canonical_checksum([
                    row["selector_row_checksum"]
                    for row in database_rows
                ]),
            "policy": {
                "runtime_staging_authorized":
                    False,
                "runtime_activation_authorized":
                    False,
                "lookup_change_authorized":
                    False,
                "candidate_change_authorized":
                    False,
                "canonical_change_authorized":
                    False,
                "project_matching_authorized":
                    False,
                "source_write_authorized":
                    False,
                "android_change_authorized":
                    False,
            },
        }
        summary["summary_checksum"] = (
            canonical_checksum(summary)
        )
        atomic_write_json(
            args.summary_output,
            summary,
        )

        print(json.dumps({
            "healthy": summary["healthy"],
            "authorized": False,
            "database_writes_attempted": False,
            "row_count": summary["row_count"],
            "state_count": summary["state_count"],
            "counts_by_state":
                summary["counts_by_state"],
            "counts_by_name_disposition":
                summary[
                    "counts_by_name_disposition"
                ],
            "counts_by_resolution":
                summary["counts_by_resolution"],
            "rows_sha256":
                summary["rows_sha256"],
            "ordered_row_manifest_sha256":
                summary[
                    "ordered_row_manifest_sha256"
                ],
            "summary_checksum":
                summary["summary_checksum"],
            "checks": checks,
        }, indent=2, sort_keys=True))

        return 0 if summary["healthy"] else 1

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

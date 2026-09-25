"""Read-only selector for deterministic NWDP district-drift rows.

The selector consumes checksum-pinned audit evidence and revalidates every
candidate, source feature, canonical target, review state, and runtime
collision against the current database. It performs no database writes and
does not authorize staging, activation, lookup, project matching, source
changes, canonical geography changes, or Android changes.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from sqlalchemy import text


SCHEMA_VERSION = "nwdp_district_drift_selector.v1"

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent

EVIDENCE_DIR = (
    PROJECT_ROOT
    / "data/staged/core_stack/promotion_review"
    / "20260924-nwdp-no-canonical-village-audit-v1"
)

PINNED_ROWS = (
    EVIDENCE_DIR
    / "nwdp_district_drift_runtime_revalidation.jsonl"
)

PINNED_ROWS_SHA256 = (
    "2e89584d5112e7d05a4ca2ba43c076a4"
    "5688afe31ae9ffd40bb22ad60f36c90b"
)

RUNTIME_SET_ID = (
    "e5f93e27-a0bd-5c8b-bef3-d97986e14c55"
)

EXPECTED_ROWS = 3_723
EXPECTED_STATES = 6

EXPECTED_BY_STATE = {
    "Delhi": 61,
    "Haryana": 30,
    "Jammu & Kashmir": 6,
    "Punjab": 112,
    "Rajasthan": 3_511,
    "Uttarakhand": 3,
}

EXPECTED_BY_NAME_DISPOSITION = {
    "EXACT_OR_PUNCTUATION_MATCH": 3_581,
    "TRAILING_NUMERIC_SUFFIX_ONLY": 142,
}

EXPECTED_BY_PARENT_ISSUE = {
    "CANONICAL_DISTRICT_DRIFT": 3_723,
}


SELECTED_ROWS_SQL = text(r"""
with input as materialized (
  select *
  from jsonb_to_recordset(
    cast(:payload as jsonb)
  ) as item(
    candidate_id text,
    source_feature_id text,
    source_state text,
    source_feature_index bigint,
    source_district_code text,
    source_district_name text,
    source_village_code text,
    source_village_name text,
    canonical_village_id text,
    canonical_village_code text,
    canonical_village_name text,
    canonical_district_code text,
    canonical_district_name text,
    canonical_block_code text,
    canonical_block_name text,
    name_disposition text,
    runtime_disposition text
  )
)

select
  candidate.id::text as candidate_id,
  source.id::text as source_feature_id,
  candidate.import_batch_id::text
    as import_batch_id,
  batch.state_or_ut as source_state,
  source.source_feature_index,
  source.source_geometry_hash,
  source.geometry_validation_status,
  source.eligible_for_runtime_after_promotion,
  source.transformed_bbox,
  source.transformed_centroid,
  source.metadata->'geometry_repair'
    as geometry_repair,
  source.source_dtcode::text
    as source_district_code,
  source.source_sdcode::text
    as source_subdistrict_code,
  source.source_vlcode::text
    as source_village_code,
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
  candidate.source_codes,
  candidate.source_names,
  candidate.match_evidence,
  candidate.confidence,
  candidate.proposed_scope,
  canonical_state.id::text
    as canonical_state_id,
  canonical_state.lgd_code::text
    as canonical_state_lgd_code,
  canonical_district.id::text
    as canonical_district_id,
  canonical_district.lgd_code::text
    as canonical_district_lgd_code,
  canonical_district.canonical_name
    as canonical_district_name,
  canonical_block.id::text
    as canonical_village_block_id,
  canonical_block.lgd_code::text
    as canonical_village_block_code,
  canonical_block.canonical_name
    as canonical_village_block_name,
  canonical_village.id::text
    as canonical_village_id,
  canonical_village.lgd_code::text
    as canonical_village_code,
  canonical_village.canonical_name
    as canonical_village_name,
  input.name_disposition,
  'CANONICAL_DISTRICT_DRIFT'
    as parent_issue,
  'ELIGIBLE_NO_RUNTIME_CONFLICT'
    as runtime_disposition,
  false as active_runtime_exists,
  false as inactive_runtime_exists
from input
join geography_boundary_crosswalk_candidates
  candidate
  on candidate.id =
     cast(input.candidate_id as uuid)
join geography_boundary_source_features
  source
  on source.id =
     cast(input.source_feature_id as uuid)
 and source.id = candidate.source_feature_id
join geography_boundary_import_batches batch
  on batch.id = candidate.import_batch_id
join geography_villages canonical_village
  on canonical_village.id =
     cast(input.canonical_village_id as uuid)
join geography_districts canonical_district
  on canonical_district.id =
     canonical_village.district_id
join geography_states canonical_state
  on canonical_state.id =
     canonical_district.state_id
join geography_blocks canonical_block
  on canonical_block.id =
     canonical_village.block_id
where candidate.candidate_bucket =
        'BLOCKED_SOURCE_CAVEAT'
  and candidate.review_status = 'BLOCKED'
  and candidate.promotion_status =
        'NOT_PROMOTED'
  and candidate.is_active = false
  and source.geometry_validation_status =
        'VALIDATED'
  and batch.state_or_ut = input.source_state
  and source.source_feature_index =
        input.source_feature_index
  and source.source_dtcode::text =
        input.source_district_code
  and source.source_vlcode::text =
        input.source_village_code
  and canonical_village.lgd_code::text =
        input.canonical_village_code
  and canonical_village.canonical_name =
        input.canonical_village_name
  and canonical_district.lgd_code::text =
        input.canonical_district_code
  and canonical_district.canonical_name =
        input.canonical_district_name
  and canonical_block.lgd_code::text =
        input.canonical_block_code
  and canonical_block.canonical_name =
        input.canonical_block_name
  and input.name_disposition in (
        'EXACT_OR_PUNCTUATION_MATCH',
        'TRAILING_NUMERIC_SUFFIX_ONLY'
  )
  and input.runtime_disposition =
        'ELIGIBLE_NO_RUNTIME_CONFLICT'
  and not exists (
    select 1
    from geography_boundary_runtime_features
      existing_feature
    where existing_feature.runtime_set_id =
          cast(:runtime_set_id as uuid)
      and existing_feature.source_feature_id =
          source.id
  )
  and not exists (
    select 1
    from geography_boundary_runtime_crosswalks
      existing_crosswalk
    where existing_crosswalk.runtime_set_id =
          cast(:runtime_set_id as uuid)
      and (
        existing_crosswalk.source_candidate_id =
          candidate.id
        or existing_crosswalk.village_id =
          canonical_village.id
      )
  )
order by
  canonical_state.lgd_code::bigint,
  source.source_feature_index,
  candidate.id
""")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)
    return digest.hexdigest()


def pinned_rows() -> list[dict[str, Any]]:
    actual = sha256_file(PINNED_ROWS)

    if actual != PINNED_ROWS_SHA256:
        raise ValueError(
            "PINNED_ROWS_CHECKSUM_MISMATCH:"
            f"expected={PINNED_ROWS_SHA256}:"
            f"actual={actual}"
        )

    rows: list[dict[str, Any]] = []

    with PINNED_ROWS.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)

            if (
                row.get("runtime_disposition")
                != "ELIGIBLE_NO_RUNTIME_CONFLICT"
            ):
                continue

            matches = row.get(
                "target_assessments"
            )

            if matches is None:
                matches = [{
                    "village_id":
                        row["canonical_village_id"],
                    "village_code":
                        row["canonical_village_code"],
                    "village_name":
                        row["canonical_village_name"],
                    "district_code":
                        row["canonical_district_code"],
                    "district_name":
                        row["canonical_district_name"],
                    "block_code":
                        row["canonical_block_code"],
                    "block_name":
                        row["canonical_block_name"],
                }]

            if len(matches) != 1:
                raise ValueError(
                    "PINNED_TARGET_NOT_UNIQUE:"
                    + row["candidate_id"]
                )

            target = matches[0]

            rows.append({
                "candidate_id":
                    row["candidate_id"],
                "source_feature_id":
                    row["source_feature_id"],
                "source_state":
                    row["source_state"],
                "source_feature_index":
                    row["source_feature_index"],
                "source_district_code":
                    row["source_district_code"],
                "source_district_name":
                    row.get(
                        "source_district_name"
                    ),
                "source_village_code":
                    row["source_village_code"],
                "source_village_name":
                    row["source_village_name"],
                "canonical_village_id":
                    target["village_id"],
                "canonical_village_code":
                    target["village_code"],
                "canonical_village_name":
                    target["village_name"],
                "canonical_district_code":
                    target["district_code"],
                "canonical_district_name":
                    target["district_name"],
                "canonical_block_code":
                    target["block_code"],
                "canonical_block_name":
                    target["block_name"],
                "name_disposition":
                    row["name_disposition"],
                "runtime_disposition":
                    row["runtime_disposition"],
            })

    return rows


def selected_rows(connection) -> list[dict[str, Any]]:
    evidence_rows = pinned_rows()

    payload = json.dumps(
        evidence_rows,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    return [
        dict(row)
        for row in connection.execute(
            SELECTED_ROWS_SQL,
            {
                "payload": payload,
                "runtime_set_id":
                    RUNTIME_SET_ID,
            },
        ).mappings()
    ]


def validate_rows(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    by_state = Counter(
        row["source_state"]
        for row in rows
    )
    by_name = Counter(
        row["name_disposition"]
        for row in rows
    )

    checks = {
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
        "states":
            dict(sorted(by_state.items()))
            == EXPECTED_BY_STATE,
        "state_count":
            len(by_state) == EXPECTED_STATES,
        "name_dispositions":
            dict(sorted(by_name.items()))
            == EXPECTED_BY_NAME_DISPOSITION,
        "geometry_validated":
            all(
                row["geometry_validation_status"]
                == "VALIDATED"
                for row in rows
            ),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "healthy": all(checks.values()),
        "row_count": len(rows),
        "state_count": len(by_state),
        "counts_by_state":
            dict(sorted(by_state.items())),
        "counts_by_name_disposition":
            dict(sorted(by_name.items())),
        "checks": checks,
        "database_writes_attempted": False,
    }

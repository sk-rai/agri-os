"""Read-only selector for deterministic NWDP parent-drift candidates.

This module selects identities only. It performs no database writes and grants
no authorization for mutation, staging, activation, lookup, project matching,
source writes, or Android changes.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text


SCHEMA_VERSION = "nwdp_parent_drift_selector.v1"

EXPECTED_ROWS = 11_676
EXPECTED_STATES = 8

EXPECTED_BY_STATE = {
    "Delhi": 76,
    "Haryana": 712,
    "Himachal Pradesh": 2_952,
    "Jammu & Kashmir": 224,
    "Ladakh": 60,
    "Punjab": 945,
    "Rajasthan": 3_086,
    "Uttarakhand": 3_621,
}

EXPECTED_BY_PARENT_ISSUE = {
    "CANONICAL_BLOCK_MISMATCH": 11_564,
    "SOURCE_SUBDISTRICT_MISMATCH": 112,
}

EXPECTED_BY_NAME_DISPOSITION = {
    "EXACT_OR_PUNCTUATION_MATCH": 7_095,
    "TRAILING_NUMERIC_SUFFIX_ONLY": 4_581,
}


SELECTED_ROWS_SQL = text(r"""
with
state_scope (
  source_state,
  state_lgd_code
) as (
  values
    ('Delhi', 7::bigint),
    ('Haryana', 6::bigint),
    ('Himachal Pradesh', 2::bigint),
    ('Jammu & Kashmir', 1::bigint),
    ('Ladakh', 37::bigint),
    ('Punjab', 3::bigint),
    ('Rajasthan', 8::bigint),
    ('Uttarakhand', 5::bigint)
),

structural as materialized (
  select
    candidate.id::text as candidate_id,
    candidate.source_feature_id::text
      as source_feature_id,
    candidate.import_batch_id::text
      as import_batch_id,
    batch.state_or_ut as source_state,
    scope.state_lgd_code::text
      as canonical_state_lgd_code,
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
    canonical_district.id::text
      as canonical_district_id,
    canonical_district.lgd_code::text
      as canonical_district_lgd_code,
    source_block.id::text
      as source_matched_block_id,
    source_block.lgd_code::text
      as source_matched_block_code,
    source_block.canonical_name
      as source_matched_block_name,
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
    case
      when source_block.id is null
        then 'SOURCE_SUBDISTRICT_MISMATCH'
      else 'CANONICAL_BLOCK_MISMATCH'
    end as parent_issue
  from geography_boundary_crosswalk_candidates
    candidate
  join geography_boundary_source_features
    source
    on source.id = candidate.source_feature_id
  join geography_boundary_import_batches
    batch
    on batch.id = candidate.import_batch_id
  join state_scope scope
    on scope.source_state = batch.state_or_ut
  join geography_states canonical_state
    on canonical_state.lgd_code::bigint =
       scope.state_lgd_code
  join geography_districts canonical_district
    on canonical_district.state_id =
       canonical_state.id
   and canonical_district.lgd_code::bigint =
       trim(source.source_dtcode::text)::bigint
  left join geography_blocks source_block
    on source_block.district_id =
       canonical_district.id
   and source_block.lgd_code::bigint =
       trim(source.source_sdcode::text)::bigint
  join geography_villages canonical_village
    on canonical_village.district_id =
       canonical_district.id
   and canonical_village.lgd_code::bigint =
       trim(source.source_vlcode::text)::bigint
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
    and trim(source.source_dtcode::text)
          ~ '^[0-9]+$'
    and trim(source.source_sdcode::text)
          ~ '^[0-9]+$'
    and trim(source.source_vlcode::text)
          ~ '^[0-9]+$'
    and (
      source_block.id is null
      or source_block.id <> canonical_block.id
    )
),

normalized as materialized (
  select
    structural.*,
    regexp_replace(
      lower(coalesce(source_village_name, '')),
      '[^a-z0-9]+',
      '',
      'g'
    ) as normalized_source,
    regexp_replace(
      lower(coalesce(canonical_village_name, '')),
      '[^a-z0-9]+',
      '',
      'g'
    ) as normalized_canonical,
    regexp_replace(
      lower(
        regexp_replace(
          coalesce(canonical_village_name, ''),
          '[[:space:]]*\([0-9][0-9/ -]*\)[[:space:]]*$',
          '',
          'g'
        )
      ),
      '[^a-z0-9]+',
      '',
      'g'
    ) as normalized_canonical_without_numeric_suffix
  from structural
),

classified as materialized (
  select
    normalized.*,
    case
      when normalized_source =
           normalized_canonical
        then 'EXACT_OR_PUNCTUATION_MATCH'
      when normalized_source =
           normalized_canonical_without_numeric_suffix
       and normalized_canonical <>
           normalized_canonical_without_numeric_suffix
        then 'TRAILING_NUMERIC_SUFFIX_ONLY'
      else 'NAME_MISMATCH_REVIEW_REQUIRED'
    end as name_disposition
  from normalized
),

with_guardrails as materialized (
  select
    classified.*,
    count(*) over (
      partition by canonical_village_id
    )::bigint as target_candidate_count,
    exists (
      select 1
      from geography_boundary_runtime_crosswalks
        runtime_crosswalk
      where runtime_crosswalk.village_id =
            cast(classified.canonical_village_id as uuid)
        and runtime_crosswalk.runtime_scope = 'village'
        and runtime_crosswalk.is_active = true
    ) as active_runtime_exists,
    exists (
      select 1
      from geography_boundary_runtime_crosswalks
        runtime_crosswalk
      where runtime_crosswalk.village_id =
            cast(classified.canonical_village_id as uuid)
        and runtime_crosswalk.runtime_scope = 'village'
        and runtime_crosswalk.is_active = false
    ) as inactive_runtime_exists
  from classified
)

select *
from with_guardrails
where name_disposition in (
        'EXACT_OR_PUNCTUATION_MATCH',
        'TRAILING_NUMERIC_SUFFIX_ONLY'
      )
  and target_candidate_count = 1
  and active_runtime_exists = false
  and inactive_runtime_exists = false
order by
  canonical_state_lgd_code::bigint,
  source_feature_index,
  candidate_id
""")


def selected_rows(connection: Any) -> list[dict[str, Any]]:
    """Return the deterministic, collision-free parent-drift cohort."""
    return [
        dict(row)
        for row in connection.execute(
            SELECTED_ROWS_SQL
        ).mappings()
    ]

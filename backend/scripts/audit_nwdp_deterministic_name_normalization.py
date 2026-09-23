from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


import json
import time

from sqlalchemy import text

from app.core.database import engine

AUDIT_SQL = text("""
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

eligible as materialized (
    select
        c.id as candidate_id,
        c.source_feature_id,
        b.state_or_ut as source_state,
        f.source_feature_index,
        f.source_vlcode::text
          as source_village_code,

        nullif(
          trim(c.source_names->>'village'),
          ''
        ) as source_village_name,

        village.id as canonical_village_id,
        village.lgd_code::text
          as canonical_village_code,
        village.canonical_name
          as canonical_village_name

    from geography_boundary_crosswalk_candidates c

    join geography_boundary_source_features f
      on f.id = c.source_feature_id

    join geography_boundary_import_batches b
      on b.id = c.import_batch_id

    join state_scope scope
      on scope.source_state =
         b.state_or_ut

    join geography_states state
      on state.lgd_code::bigint =
         scope.state_lgd_code

    join geography_districts district
      on district.state_id = state.id
     and district.lgd_code::bigint =
         trim(f.source_dtcode::text)::bigint

    join geography_blocks subdistrict
      on subdistrict.district_id =
         district.id
     and subdistrict.lgd_code::bigint =
         trim(f.source_sdcode::text)::bigint

    join geography_villages village
      on village.district_id = district.id
     and village.block_id = subdistrict.id
     and village.lgd_code::bigint =
         trim(f.source_vlcode::text)::bigint

    where c.candidate_bucket =
          'BLOCKED_SOURCE_CAVEAT'
      and c.review_status = 'BLOCKED'
      and c.promotion_status = 'NOT_PROMOTED'
      and c.is_active = false
      and f.geometry_validation_status =
          'VALIDATED'
      and trim(f.source_dtcode::text)
          ~ '^[0-9]+$'
      and trim(f.source_sdcode::text)
          ~ '^[0-9]+$'
      and trim(f.source_vlcode::text)
          ~ '^[0-9]+$'
      and not exists (
          select 1
          from geography_boundary_runtime_crosswalks rw
          join geography_boundary_runtime_features rf
            on rf.id = rw.runtime_feature_id
           and rf.runtime_set_id =
               rw.runtime_set_id
          join geography_boundary_runtime_sets rs
            on rs.id = rw.runtime_set_id
          where rw.village_id = village.id
            and rw.runtime_scope = 'village'
            and rw.is_active = true
            and rf.is_active = true
            and rs.is_active = true
      )
),

normalized as (
    select
        eligible.*,

        regexp_replace(
          lower(coalesce(
            source_village_name,
            ''
          )),
          '[^a-z0-9]+',
          '',
          'g'
        ) as normalized_source,

        regexp_replace(
          lower(coalesce(
            canonical_village_name,
            ''
          )),
          '[^a-z0-9]+',
          '',
          'g'
        ) as normalized_canonical,

        regexp_replace(
          lower(
            regexp_replace(
              coalesce(
                canonical_village_name,
                ''
              ),
              '[[:space:]]*\\([0-9][0-9/ -]*\\)[[:space:]]*$',
              '',
              'g'
            )
          ),
          '[^a-z0-9]+',
          '',
          'g'
        ) as normalized_canonical_without_numeric_suffix

    from eligible
),

classified as (
    select
        normalized.*,

        case
          when source_village_name is null
            then 'SOURCE_NAME_MISSING'

          when normalized_source =
               normalized_canonical
            then 'EXACT_OR_PUNCTUATION_MATCH'

          when normalized_source =
               normalized_canonical_without_numeric_suffix
           and normalized_canonical <>
               normalized_canonical_without_numeric_suffix
            then 'TRAILING_NUMERIC_SUFFIX_ONLY'

          else 'NAME_MISMATCH_REVIEW_REQUIRED'
        end as disposition

    from normalized
)

select
    source_state,
    disposition,
    count(*)::bigint as row_count,
    count(distinct candidate_id)::bigint
      as candidate_count,
    count(distinct canonical_village_id)::bigint
      as canonical_village_count

from classified

group by
    source_state,
    disposition

order by
    source_state,
    disposition
""")

SAMPLE_SQL = text("""
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

eligible as (
    select
        b.state_or_ut as source_state,
        f.source_feature_index,
        f.source_vlcode::text
          as source_village_code,
        c.source_names->>'village'
          as source_village_name,
        village.lgd_code::text
          as canonical_village_code,
        village.canonical_name
          as canonical_village_name

    from geography_boundary_crosswalk_candidates c

    join geography_boundary_source_features f
      on f.id = c.source_feature_id

    join geography_boundary_import_batches b
      on b.id = c.import_batch_id

    join state_scope scope
      on scope.source_state =
         b.state_or_ut

    join geography_states state
      on state.lgd_code::bigint =
         scope.state_lgd_code

    join geography_districts district
      on district.state_id = state.id
     and district.lgd_code::bigint =
         trim(f.source_dtcode::text)::bigint

    join geography_blocks subdistrict
      on subdistrict.district_id =
         district.id
     and subdistrict.lgd_code::bigint =
         trim(f.source_sdcode::text)::bigint

    join geography_villages village
      on village.district_id = district.id
     and village.block_id = subdistrict.id
     and village.lgd_code::bigint =
         trim(f.source_vlcode::text)::bigint

    where c.candidate_bucket =
          'BLOCKED_SOURCE_CAVEAT'
      and c.review_status = 'BLOCKED'
      and f.geometry_validation_status =
          'VALIDATED'
      and trim(f.source_dtcode::text)
          ~ '^[0-9]+$'
      and trim(f.source_sdcode::text)
          ~ '^[0-9]+$'
      and trim(f.source_vlcode::text)
          ~ '^[0-9]+$'
),

classified as (
    select
        eligible.*,

        regexp_replace(
          lower(coalesce(
            source_village_name,
            ''
          )),
          '[^a-z0-9]+',
          '',
          'g'
        ) as normalized_source,

        regexp_replace(
          lower(coalesce(
            canonical_village_name,
            ''
          )),
          '[^a-z0-9]+',
          '',
          'g'
        ) as normalized_canonical,

        regexp_replace(
          lower(
            regexp_replace(
              coalesce(
                canonical_village_name,
                ''
              ),
              '[[:space:]]*\\([0-9][0-9/ -]*\\)[[:space:]]*$',
              '',
              'g'
            )
          ),
          '[^a-z0-9]+',
          '',
          'g'
        ) as normalized_canonical_without_suffix

    from eligible
),

remaining as (
    select
        classified.*,
        row_number() over (
            partition by source_state
            order by source_feature_index
        ) as state_sample_number

    from classified

    where normalized_source <>
          normalized_canonical
      and normalized_source <>
          normalized_canonical_without_suffix
)

select
    source_state,
    source_feature_index,
    source_village_code,
    source_village_name,
    canonical_village_code,
    canonical_village_name

from remaining

where state_sample_number <= 10

order by
    source_state,
    source_feature_index
""")

started = time.perf_counter()

with engine.connect() as connection:
    transaction = connection.begin()

    connection.execute(text("""
        select set_config(
            'statement_timeout',
            '300000ms',
            true
        )
    """))

    classifications = [
        dict(row)
        for row in connection.execute(
            AUDIT_SQL,
        ).mappings()
    ]

    remaining_samples = [
        dict(row)
        for row in connection.execute(
            SAMPLE_SQL,
        ).mappings()
    ]

    transaction.rollback()

elapsed = time.perf_counter() - started

totals: dict[str, int] = {}

for row in classifications:
    disposition = row["disposition"]
    totals[disposition] = (
        totals.get(disposition, 0)
        + row["row_count"]
    )

total_rows = sum(totals.values())

strict_rows = (
    totals.get(
        "EXACT_OR_PUNCTUATION_MATCH",
        0,
    )
    + totals.get(
        "TRAILING_NUMERIC_SUFFIX_ONLY",
        0,
    )
)

report = {
    "schema_version":
        "nwdp_deterministic_name_normalization_audit.v1",
    "mode": "READ_ONLY",
    "database_writes_attempted": False,
    "elapsed_seconds": round(elapsed, 3),
    "expected_structural_rows": 57146,
    "actual_structural_rows": total_rows,
    "strict_name_compatible_rows": strict_rows,
    "totals_by_disposition": totals,
    "state_dispositions": classifications,
    "remaining_mismatch_samples":
        remaining_samples,
    "policy": {
        "fuzzy_matching_used": False,
        "trailing_numeric_suffix_rule":
            "PARENTHESIZED_NUMERIC_SLASH_SUFFIX_ONLY",
        "remaining_mismatch_auto_approved":
            False,
        "proposal_created": False,
        "database_writes_authorized": False,
    },
    "guardrails": {
        "candidate_rows_changed": False,
        "source_rows_changed": False,
        "runtime_rows_changed": False,
        "lookup_changed": False,
        "android_changed": False,
    },
}

report["healthy"] = (
    total_rows == 57146
)

print(json.dumps(report, indent=2))

if not report["healthy"]:
    raise SystemExit(
        "DETERMINISTIC_NAME_NORMALIZATION_AUDIT_FAILED"
    )

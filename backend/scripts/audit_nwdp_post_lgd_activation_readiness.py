#!/usr/bin/env python3
"""Re-audit activation readiness of the 17,498 post-LGD NWDP cohort.

Database behavior: read-only. This does not authorize activation, promotion,
lookup exposure, project matching, canonical changes, or Android changes.
"""

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.config import settings


SCHEMA_VERSION = "nwdp_post_lgd_activation_readiness_audit.v1"
RUNTIME_SET_ID = "e5f93e27-a0bd-5c8b-bef3-d97986e14c55"
PROPOSAL_CHECKSUM = (
    "80bbbe640c7675d9d9882c3489e53cc4"
    "81159eee222341e03d24a3121d7d0cae"
)
MANIFEST_CHECKSUM = (
    "72663edc2b5e27273d7d8516c40842f9"
    "7358842d4cde2a1a215353b3b281e16a"
)
EXPECTED_ROWS = 17_498
EXPECTED_EVENTS = 8
EXPECTED_BY_STATE = {
    "1": 821,
    "2": 2433,
    "3": 1625,
    "5": 1359,
    "6": 1922,
    "7": 8,
    "8": 9309,
    "37": 21,
}
DEFAULT_OUTPUT = (
    ROOT
    / "data/staged/core_stack/promotion_review"
    / "20260930-post-lgd-activation-readiness-reaudit-v1"
    / "nwdp_post_lgd_activation_readiness_audit.json"
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=settings.DATABASE_URL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


BASELINE_SQL = text("""
select
  (select count(*) from geography_states where is_active) as states,
  (select count(*) from geography_districts where is_active) as districts,
  (select count(*) from geography_blocks where is_active) as blocks,
  (select count(*) from geography_villages where is_active) as villages,
  (select count(*) from geography_boundary_source_features) as source_features,
  (select count(*) from geography_boundary_crosswalk_candidates) as candidates,
  (select count(*) from geography_boundary_runtime_features) as runtime_features,
  (select count(*) from geography_boundary_runtime_features
     where is_active) as active_runtime_features,
  (select count(*) from geography_boundary_runtime_crosswalks) as runtime_crosswalks,
  (select count(*) from geography_boundary_runtime_crosswalks
     where is_active) as active_runtime_crosswalks,
  (select count(*) from geography_boundary_project_matches) as project_matches
""")


AUDIT_SQL = text("""
with cohort as materialized (
  select
    feature.id as feature_id,
    feature.source_feature_id,
    feature.geometry_hash,
    feature.geometry_wgs84_geom,
    feature.geometry_validation_status,
    feature.is_active as feature_active,
    feature.metadata as feature_metadata,
    crosswalk.id as crosswalk_id,
    crosswalk.source_candidate_id,
    crosswalk.village_id,
    crosswalk.state_lgd_code,
    crosswalk.is_active as crosswalk_active,
    crosswalk.metadata as crosswalk_metadata,
    candidate.is_active as candidate_active,
    candidate.promotion_status,
    candidate.candidate_bucket,
    source.source_geometry_hash,
    source.geometry_validation_status as source_geometry_status,
    source.eligible_for_runtime_after_promotion,
    village.is_active as village_active,
    block.is_active as block_active,
    district.is_active as district_active,
    state.is_active as state_active
  from geography_boundary_runtime_features feature
  join geography_boundary_runtime_crosswalks crosswalk
    on crosswalk.runtime_feature_id = feature.id
   and crosswalk.runtime_set_id = feature.runtime_set_id
  join geography_boundary_crosswalk_candidates candidate
    on candidate.id = crosswalk.source_candidate_id
  join geography_boundary_source_features source
    on source.id = feature.source_feature_id
  join geography_villages village
    on village.id = crosswalk.village_id
  join geography_blocks block
    on block.id = village.block_id
  join geography_districts district
    on district.id = block.district_id
  join geography_states state
    on state.id = district.state_id
  where feature.runtime_set_id = cast(:runtime_set_id as uuid)
    and feature.metadata->>'proposal_checksum' = :proposal_checksum
)
select
  count(*)::bigint as row_count,
  count(distinct feature_id)::bigint as feature_count,
  count(distinct crosswalk_id)::bigint as crosswalk_count,
  count(distinct source_feature_id)::bigint as source_feature_count,
  count(distinct source_candidate_id)::bigint as candidate_count,
  count(distinct village_id)::bigint as village_count,
  count(*) filter (
    where feature_active or crosswalk_active
  )::bigint as already_active_count,
  count(*) filter (
    where candidate_active
       or promotion_status <> 'NOT_PROMOTED'
  )::bigint as candidate_state_mismatch_count,
  count(*) filter (
    where not eligible_for_runtime_after_promotion
  )::bigint as runtime_ineligible_source_count,
  count(*) filter (
    where geometry_wgs84_geom is null
       or not ST_IsValid(geometry_wgs84_geom)
       or ST_SRID(geometry_wgs84_geom) <> 4326
  )::bigint as invalid_native_geometry_count,
  count(*) filter (
    where geometry_hash is null
       or geometry_hash <> source_geometry_hash
       or geometry_validation_status <> 'VALIDATED'
       or source_geometry_status not in ('VALID', 'VALIDATED')
  )::bigint as geometry_evidence_mismatch_count,
  count(*) filter (
    where not village_active
       or not block_active
       or not district_active
       or not state_active
  )::bigint as inactive_canonical_hierarchy_count,
  count(*) filter (
    where feature_metadata->>'manifest_checksum' <> :manifest_checksum
       or crosswalk_metadata->>'manifest_checksum' <> :manifest_checksum
       or crosswalk_metadata->>'proposal_checksum' <> :proposal_checksum
  )::bigint as evidence_pin_mismatch_count,
  count(*) filter (
    where exists (
      select 1
      from geography_boundary_runtime_crosswalks active_crosswalk
      where active_crosswalk.village_id = cohort.village_id
        and active_crosswalk.is_active
        and active_crosswalk.id <> cohort.crosswalk_id
    )
  )::bigint as active_village_collision_count
from cohort
""")


STATE_SQL = text("""
select
  crosswalk.state_lgd_code,
  count(*)::bigint as row_count
from geography_boundary_runtime_features feature
join geography_boundary_runtime_crosswalks crosswalk
  on crosswalk.runtime_feature_id = feature.id
 and crosswalk.runtime_set_id = feature.runtime_set_id
where feature.runtime_set_id = cast(:runtime_set_id as uuid)
  and feature.metadata->>'proposal_checksum' = :proposal_checksum
group by crosswalk.state_lgd_code
order by crosswalk.state_lgd_code
""")


EVENT_SQL = text("""
select
  count(*)::bigint as event_count,
  count(*) filter (where is_active)::bigint as active_event_count
from geography_boundary_runtime_promotion_events
where runtime_set_id = cast(:runtime_set_id as uuid)
  and metadata->>'proposal_checksum' = :proposal_checksum
""")


SET_SQL = text("""
select
  id::text as runtime_set_id,
  status,
  activation_status,
  is_active
from geography_boundary_runtime_sets
where id = cast(:runtime_set_id as uuid)
""")


def integer_dict(row):
    return {
        key: int(value or 0)
        for key, value in dict(row).items()
    }


def main():
    args = parse_args()
    engine = create_engine(args.database_url)
    params = {
        "runtime_set_id": RUNTIME_SET_ID,
        "proposal_checksum": PROPOSAL_CHECKSUM,
        "manifest_checksum": MANIFEST_CHECKSUM,
    }

    with engine.connect() as connection:
        before = integer_dict(
            connection.execute(BASELINE_SQL).mappings().one()
        )
        cohort = integer_dict(
            connection.execute(
                AUDIT_SQL, params
            ).mappings().one()
        )
        states = {
            str(row["state_lgd_code"]): int(row["row_count"])
            for row in connection.execute(
                STATE_SQL, params
            ).mappings()
        }
        events = integer_dict(
            connection.execute(
                EVENT_SQL, params
            ).mappings().one()
        )
        runtime_set = connection.execute(
            SET_SQL, params
        ).mappings().one_or_none()
        after = integer_dict(
            connection.execute(BASELINE_SQL).mappings().one()
        )

    checks = {
        "database_counts_unchanged": before == after,
        "runtime_set_exists": runtime_set is not None,
        "cohort_row_count_exact":
            cohort["row_count"] == EXPECTED_ROWS,
        "feature_identity_unique":
            cohort["feature_count"] == EXPECTED_ROWS,
        "crosswalk_identity_unique":
            cohort["crosswalk_count"] == EXPECTED_ROWS,
        "source_identity_unique":
            cohort["source_feature_count"] == EXPECTED_ROWS,
        "candidate_identity_unique":
            cohort["candidate_count"] == EXPECTED_ROWS,
        "village_identity_unique":
            cohort["village_count"] == EXPECTED_ROWS,
        "all_rows_inactive":
            cohort["already_active_count"] == 0,
        "candidate_state_unchanged":
            cohort["candidate_state_mismatch_count"] == 0,
        "all_sources_runtime_eligible":
            cohort["runtime_ineligible_source_count"] == 0,
        "native_geometry_valid":
            cohort["invalid_native_geometry_count"] == 0,
        "geometry_evidence_aligned":
            cohort["geometry_evidence_mismatch_count"] == 0,
        "canonical_hierarchy_active":
            cohort["inactive_canonical_hierarchy_count"] == 0,
        "evidence_pins_exact":
            cohort["evidence_pin_mismatch_count"] == 0,
        "no_active_village_collisions":
            cohort["active_village_collision_count"] == 0,
        "state_partition_exact":
            states == EXPECTED_BY_STATE,
        "inactive_event_count_exact":
            events["event_count"] == EXPECTED_EVENTS
            and events["active_event_count"] == 0,
    }

    data_ready = all(checks.values())
    result = {
        "schema_version": SCHEMA_VERSION,
        "status": (
            "DATA_READY_ACTIVATION_NOT_AUTHORIZED"
            if data_ready
            else "ACTIVATION_READINESS_BLOCKED"
        ),
        "healthy": data_ready,
        "authorized": False,
        "runtime_set": dict(runtime_set) if runtime_set else None,
        "cohort": cohort,
        "counts_by_state_lgd_code": states,
        "promotion_events": events,
        "checks": checks,
        "database_before": before,
        "database_after": after,
        "activation_blockers": {
            "explicit_activation_authorization_missing": True,
            "shared_distributed_rate_limit_not_proven": True,
            "canary_apply_and_rollback_not_yet_designed": True,
        },
        "recommended_canary": {
            "state": "Jammu & Kashmir",
            "state_lgd_code": "1",
            "row_count": 821,
            "mode": "CHECKSUM_PINNED_STATE_SCOPED_APPLY_WITH_ROLLBACK",
        },
        "policy": {
            "database_writes_attempted": False,
            "activation_authorized": False,
            "lookup_exposure_authorized": False,
            "candidate_changes_authorized": False,
            "canonical_changes_authorized": False,
            "project_changes_authorized": False,
            "android_changes_authorized": False,
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))

    if not data_ready:
        failed = sorted(
            key for key, value in checks.items() if not value
        )
        raise SystemExit(
            "ACTIVATION_READINESS_FAILED:" + ",".join(failed)
        )

    print("NWDP POST-LGD ACTIVATION READINESS RE-AUDIT PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

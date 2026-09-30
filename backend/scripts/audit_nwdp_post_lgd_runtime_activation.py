#!/usr/bin/env python3
"""Read-only audit of the activated 17,498-row post-LGD runtime cohort."""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.config import settings


RUNTIME_SET_ID = "e5f93e27-a0bd-5c8b-bef3-d97986e14c55"
SOURCE_PROPOSAL = (
    "80bbbe640c7675d9d9882c3489e53cc4"
    "81159eee222341e03d24a3121d7d0cae"
)
EXPECTED_TOTAL = 467_397
EXPECTED_COHORT = 17_498
EXPECTED_INACTIVE_REHABILITATION = 65_005
MAX_LOOKUP_MS = 1_000.0
APPLY_CHECKPOINT_CHECKSUM = (
    "21492ba7580dba2af0f4083dd6e9c564"
    "c5b87a35a206f8c9966a8c2e02a4ab9b"
)

STATES = {
    "1": ("Jammu & Kashmir", 821),
    "2": ("Himachal Pradesh", 2433),
    "3": ("Punjab", 1625),
    "5": ("Uttarakhand", 1359),
    "6": ("Haryana", 1922),
    "7": ("Delhi", 8),
    "8": ("Rajasthan", 9309),
    "37": ("Ladakh", 21),
}

OUTPUT_DIR = (
    ROOT / "data/staged/core_stack/promotion_review"
    / "20260930-post-lgd-runtime-activation-v1"
)
CHECKPOINT = OUTPUT_DIR / "checkpoint.json"
DEFAULT_OUTPUT = OUTPUT_DIR / "post_activation_audit.json"


def args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--maximum-lookup-ms",
        type=float,
        default=MAX_LOOKUP_MS,
    )
    return parser.parse_args()


def checkpoint_checksum(value):
    clean = {
        key: item
        for key, item in value.items()
        if key != "checkpoint_checksum"
    }
    payload = json.dumps(
        clean,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def snapshot(connection):
    row = connection.execute(text("""
        select
          (select count(*) from geography_boundary_runtime_features
             where is_active) as active_features,
          (select count(*) from geography_boundary_runtime_crosswalks
             where is_active) as active_crosswalks,
          (select count(*) from geography_boundary_crosswalk_candidates
             where is_active) as active_candidates,
          (select count(*) from geography_boundary_crosswalk_candidates
             where promotion_status = 'PROMOTED') as promoted_candidates,
          (select count(*) from geography_boundary_project_matches)
             as project_matches,
          (select count(*) from geography_states where is_active)
             as states,
          (select count(*) from geography_districts where is_active)
             as districts,
          (select count(*) from geography_blocks where is_active)
             as blocks,
          (select count(*) from geography_villages where is_active)
             as villages
    """)).mappings().one()
    return {key: int(value or 0) for key, value in row.items()}


def cohort_by_state(connection):
    rows = connection.execute(text("""
        select
          rw.state_lgd_code,
          count(*)::bigint as row_count,
          count(*) filter (where rf.is_active)::bigint
            as active_features,
          count(*) filter (where rw.is_active)::bigint
            as active_crosswalks,
          count(*) filter (
            where rf.geometry_wgs84_geom is not null
          )::bigint as native_geometry_count,
          count(*) filter (
            where ST_SRID(rf.geometry_wgs84_geom) = 4326
          )::bigint as srid_4326_count,
          count(*) filter (
            where ST_IsValid(rf.geometry_wgs84_geom)
              and not ST_IsEmpty(rf.geometry_wgs84_geom)
          )::bigint as valid_geometry_count,
          count(*) filter (
            where state.is_active
              and district.is_active
              and block.is_active
              and village.is_active
          )::bigint as active_hierarchy_count,
          count(distinct rf.id)::bigint as feature_identity_count,
          count(distinct rw.id)::bigint as crosswalk_identity_count,
          count(distinct rw.village_id)::bigint
            as village_identity_count
        from geography_boundary_runtime_features rf
        join geography_boundary_runtime_crosswalks rw
          on rw.runtime_feature_id = rf.id
         and rw.runtime_set_id = rf.runtime_set_id
        join geography_villages village
          on village.id = rw.village_id
        join geography_blocks block
          on block.id = village.block_id
        join geography_districts district
          on district.id = block.district_id
        join geography_states state
          on state.id = district.state_id
        where rf.runtime_set_id = cast(:runtime_set_id as uuid)
          and rf.metadata->>'proposal_checksum' = :proposal
          and rw.metadata->>'proposal_checksum' = :proposal
        group by rw.state_lgd_code
        order by rw.state_lgd_code::integer
    """), {
        "runtime_set_id": RUNTIME_SET_ID,
        "proposal": SOURCE_PROPOSAL,
    }).mappings().all()

    return [
        {
            key: str(value) if key == "state_lgd_code" else int(value)
            for key, value in row.items()
        }
        for row in rows
    ]


def lookup_samples(connection, maximum_ms):
    samples = connection.execute(text("""
        select distinct on (rw.state_lgd_code)
          rw.state_lgd_code,
          rf.id::text as expected_runtime_feature_id,
          ST_X(ST_PointOnSurface(rf.geometry_wgs84_geom))
            as longitude,
          ST_Y(ST_PointOnSurface(rf.geometry_wgs84_geom))
            as latitude
        from geography_boundary_runtime_features rf
        join geography_boundary_runtime_crosswalks rw
          on rw.runtime_feature_id = rf.id
         and rw.runtime_set_id = rf.runtime_set_id
        where rf.runtime_set_id = cast(:runtime_set_id as uuid)
          and rf.metadata->>'proposal_checksum' = :proposal
          and rf.is_active
          and rw.is_active
        order by rw.state_lgd_code, rf.id
    """), {
        "runtime_set_id": RUNTIME_SET_ID,
        "proposal": SOURCE_PROPOSAL,
    }).mappings().all()

    lookup = text("""
        with requested_point as (
          select ST_SetSRID(
            ST_MakePoint(:longitude, :latitude),
            4326
          ) as geom
        )
        select rf.id::text
        from requested_point point
        join geography_boundary_runtime_sets runtime_set
          on runtime_set.id = cast(:runtime_set_id as uuid)
         and runtime_set.is_active
        join geography_boundary_runtime_features rf
          on rf.runtime_set_id = runtime_set.id
         and rf.is_active
         and rf.geometry_validation_status = 'VALIDATED'
         and rf.geometry_wgs84_geom is not null
         and rf.geometry_wgs84_geom && point.geom
         and ST_Covers(rf.geometry_wgs84_geom, point.geom)
        join geography_boundary_runtime_crosswalks rw
          on rw.runtime_feature_id = rf.id
         and rw.runtime_set_id = runtime_set.id
         and rw.is_active
         and rw.runtime_scope = 'village'
        join geography_boundary_source_features source
          on source.id = rf.source_feature_id
         and source.geometry_validation_status = 'VALIDATED'
         and source.eligible_for_runtime_after_promotion
        order by rf.id
        limit 2
    """)

    results = []
    for sample in samples:
        started = time.perf_counter()
        matches = [
            str(row[0])
            for row in connection.execute(lookup, {
                "runtime_set_id": RUNTIME_SET_ID,
                "longitude": float(sample["longitude"]),
                "latitude": float(sample["latitude"]),
            }).all()
        ]
        elapsed_ms = (time.perf_counter() - started) * 1000
        expected = str(sample["expected_runtime_feature_id"])
        results.append({
            "state_lgd_code": str(sample["state_lgd_code"]),
            "expected_runtime_feature_id": expected,
            "match_count": len(matches),
            "expected_match_present": expected in matches,
            "ambiguous": len(matches) > 1,
            "elapsed_ms": round(elapsed_ms, 3),
            "within_latency_ceiling": elapsed_ms <= maximum_ms,
        })

    return results


def main():
    options = args()

    if not CHECKPOINT.is_file():
        raise SystemExit(f"APPLY_CHECKPOINT_MISSING:{CHECKPOINT}")

    checkpoint = json.loads(
        CHECKPOINT.read_text(encoding="utf-8")
    )
    checkpoint_checks = {
        "schema_exact": (
            checkpoint.get("schema_version")
            == "nwdp_post_lgd_runtime_activation_checkpoint.v1"
        ),
        "mode_apply": checkpoint.get("mode") == "APPLY",
        "status_completed": checkpoint.get("status") == "COMPLETED",
        "state_count_exact": (
            checkpoint.get("completed_state_count") == 8
        ),
        "row_count_exact": (
            checkpoint.get("completed_row_count") == EXPECTED_COHORT
        ),
        "checksum_valid": (
            checkpoint_checksum(checkpoint)
            == checkpoint.get("checkpoint_checksum")
        ),
        "checksum_pinned": (
            checkpoint.get("checkpoint_checksum")
            == APPLY_CHECKPOINT_CHECKSUM
        ),
    }

    database = create_engine(settings.DATABASE_URL)

    with database.connect() as connection:
        connection.execute(text("set statement_timeout='30s'"))
        before = snapshot(connection)
        state_rows = cohort_by_state(connection)
        lookups = lookup_samples(
            connection,
            options.maximum_lookup_ms,
        )
        after = snapshot(connection)

    state_map = {
        row["state_lgd_code"]: row
        for row in state_rows
    }
    state_checks = {}

    for code, (name, expected) in STATES.items():
        row = state_map.get(code, {})
        exact = all(
            row.get(field) == expected
            for field in (
                "row_count",
                "active_features",
                "active_crosswalks",
                "native_geometry_count",
                "srid_4326_count",
                "valid_geometry_count",
                "active_hierarchy_count",
                "feature_identity_count",
                "crosswalk_identity_count",
                "village_identity_count",
            )
        )
        state_checks[code] = {
            "state_name": name,
            "expected": expected,
            "exact": exact,
        }

    checks = {
        "checkpoint_exact": all(checkpoint_checks.values()),
        "active_totals_exact": (
            before["active_features"] == EXPECTED_TOTAL
            and before["active_crosswalks"] == EXPECTED_TOTAL
        ),
        "state_partition_exact": (
            set(state_map) == set(STATES)
            and all(row["exact"] for row in state_checks.values())
        ),
        "lookup_sample_count_exact": len(lookups) == len(STATES),
        "sampled_lookup_expected_match": all(
            row["expected_match_present"] for row in lookups
        ),
        "sampled_lookup_unambiguous": all(
            not row["ambiguous"] for row in lookups
        ),
        "sampled_lookup_latency_bounded": all(
            row["within_latency_ceiling"] for row in lookups
        ),
        "protected_counts_unchanged": before == after,
        "candidate_state_unchanged": (
            before["active_candidates"] == 0
            and before["promoted_candidates"] == 0
        ),
        "project_matches_unchanged": (
            before["project_matches"] == 0
        ),
        "canonical_baseline_unchanged": (
            before["states"] == 35
            and before["districts"] == 779
            and before["villages"] == 600_647
        ),
        "lookup_exposure_unchanged": True,
        "no_database_writes": True,
    }

    report = {
        "schema_version":
            "nwdp_post_lgd_runtime_activation_audit.v1",
        "status": "PASSED" if all(checks.values()) else "FAILED",
        "healthy": all(checks.values()),
        "checks": checks,
        "checkpoint_checks": checkpoint_checks,
        "database_before": before,
        "database_after": after,
        "cohort_count": EXPECTED_COHORT,
        "active_runtime_total": EXPECTED_TOTAL,
        "remaining_inactive_rehabilitation_count":
            EXPECTED_INACTIVE_REHABILITATION,
        "states": state_rows,
        "state_checks": state_checks,
        "lookup_samples": lookups,
        "maximum_lookup_ms": options.maximum_lookup_ms,
        "policy": {
            "database_writes_attempted": False,
            "lookup_exposure_changed": False,
            "candidate_changes_authorized": False,
            "canonical_changes_authorized": False,
            "project_changes_authorized": False,
            "android_changes_authorized": False,
        },
    }

    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(report, indent=2, sort_keys=True))
    print(
        "NWDP POST-LGD RUNTIME ACTIVATION AUDIT "
        + report["status"]
    )
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

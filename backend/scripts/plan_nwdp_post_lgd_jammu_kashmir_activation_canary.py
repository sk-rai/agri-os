#!/usr/bin/env python3
"""Plan the 821-row Jammu & Kashmir post-LGD activation canary.

Database behavior: read-only. Output files are evidence only. This planner
does not authorize or perform activation, promotion, lookup exposure,
canonical changes, project changes, or Android changes.
"""

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.config import settings


SCHEMA_VERSION = "nwdp_post_lgd_activation_canary_plan.v1"
ROW_SCHEMA_VERSION = "nwdp_post_lgd_activation_canary_row.v1"
RUNTIME_SET_ID = "e5f93e27-a0bd-5c8b-bef3-d97986e14c55"
SOURCE_PROPOSAL = (
    "80bbbe640c7675d9d9882c3489e53cc4"
    "81159eee222341e03d24a3121d7d0cae"
)
SOURCE_MANIFEST = (
    "72663edc2b5e27273d7d8516c40842f9"
    "7358842d4cde2a1a215353b3b281e16a"
)
STATE_NAME = "Jammu & Kashmir"
STATE_LGD_CODE = "1"
EXPECTED_ROWS = 821
EXPECTED_ACTIVE_BASELINE = 449_899

DEFAULT_OUTPUT_DIR = (
    ROOT
    / "data/staged/core_stack/promotion_review"
    / "20260930-post-lgd-jammu-kashmir-activation-canary-v1"
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=settings.DATABASE_URL)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )
    return parser.parse_args()


def canonical_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def checksum(value):
    return hashlib.sha256(
        canonical_json(value).encode("utf-8")
    ).hexdigest()


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)
    return digest.hexdigest()


BASELINE_SQL = text("""
select
  (select count(*) from geography_boundary_runtime_features)
    as runtime_features,
  (select count(*) from geography_boundary_runtime_features
     where is_active) as active_runtime_features,
  (select count(*) from geography_boundary_runtime_crosswalks)
    as runtime_crosswalks,
  (select count(*) from geography_boundary_runtime_crosswalks
     where is_active) as active_runtime_crosswalks,
  (select count(*) from geography_boundary_crosswalk_candidates
     where is_active) as active_candidates,
  (select count(*) from geography_boundary_crosswalk_candidates
     where promotion_status = 'PROMOTED') as promoted_candidates,
  (select count(*) from geography_boundary_project_matches)
    as project_matches,
  (select count(*) from geography_villages where is_active)
    as active_villages
""")


ROWS_SQL = text("""
select
  feature.id::text as runtime_feature_id,
  feature.source_feature_id::text,
  feature.source_feature_index,
  feature.geometry_hash,
  feature.geometry_validation_status,
  feature.is_active as feature_is_active,
  feature.metadata->>'proposal_checksum'
    as feature_proposal_checksum,
  feature.metadata->>'manifest_checksum'
    as feature_manifest_checksum,

  crosswalk.id::text as runtime_crosswalk_id,
  crosswalk.source_candidate_id::text as candidate_id,
  crosswalk.promotion_event_id::text,
  crosswalk.village_id::text,
  crosswalk.state_id::text,
  crosswalk.district_id::text,
  crosswalk.block_id::text,
  crosswalk.state_lgd_code,
  crosswalk.district_lgd_code,
  crosswalk.block_lgd_code,
  crosswalk.village_lgd_code,
  crosswalk.runtime_scope,
  crosswalk.is_active as crosswalk_is_active,
  crosswalk.metadata->>'proposal_checksum'
    as crosswalk_proposal_checksum,
  crosswalk.metadata->>'manifest_checksum'
    as crosswalk_manifest_checksum,

  candidate.candidate_bucket,
  candidate.review_status,
  candidate.reviewer_decision,
  candidate.promotion_status,
  candidate.is_active as candidate_is_active,

  source.source_geometry_hash,
  source.geometry_validation_status
    as source_geometry_validation_status,
  source.eligible_for_runtime_after_promotion,

  village.canonical_name as village_name,
  village.is_active as village_is_active,
  block.canonical_name as block_name,
  block.is_active as block_is_active,
  district.canonical_name as district_name,
  district.is_active as district_is_active,
  state.canonical_name as state_name,
  state.is_active as state_is_active,

  exists (
    select 1
    from geography_boundary_runtime_crosswalks active_crosswalk
    where active_crosswalk.village_id = crosswalk.village_id
      and active_crosswalk.is_active
      and active_crosswalk.id <> crosswalk.id
  ) as has_active_village_collision,

  ST_IsValid(feature.geometry_wgs84_geom)
    as native_geometry_valid,
  ST_SRID(feature.geometry_wgs84_geom)
    as native_geometry_srid
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
  and feature.metadata->>'proposal_checksum' = :source_proposal
  and crosswalk.state_lgd_code = :state_lgd_code
order by
  feature.source_feature_index,
  feature.id
""")


EVENT_SQL = text("""
select
  id::text as promotion_event_id,
  promotion_mode,
  promotion_status,
  candidate_count,
  runtime_feature_count,
  runtime_crosswalk_count,
  is_active,
  metadata->>'proposal_checksum' as proposal_checksum,
  metadata->>'manifest_checksum' as manifest_checksum
from geography_boundary_runtime_promotion_events
where runtime_set_id = cast(:runtime_set_id as uuid)
  and metadata->>'proposal_checksum' = :source_proposal
  and metadata->>'state_lgd_code' = :state_lgd_code
order by id
""")


def baseline(connection):
    return {
        key: int(value or 0)
        for key, value in dict(
            connection.execute(
                BASELINE_SQL
            ).mappings().one()
        ).items()
    }


def main():
    args = parse_args()
    params = {
        "runtime_set_id": RUNTIME_SET_ID,
        "source_proposal": SOURCE_PROPOSAL,
        "state_lgd_code": STATE_LGD_CODE,
    }

    engine = create_engine(args.database_url)

    with engine.connect() as connection:
        before = baseline(connection)
        database_rows = [
            dict(row)
            for row in connection.execute(
                ROWS_SQL, params
            ).mappings()
        ]
        events = [
            dict(row)
            for row in connection.execute(
                EVENT_SQL, params
            ).mappings()
        ]
        after = baseline(connection)

    planned_rows = []
    for source in database_rows:
        row = {
            "schema_version": ROW_SCHEMA_VERSION,
            "plan_action": "ACTIVATE_RUNTIME_FEATURE_AND_CROSSWALK",
            "rollback_action":
                "DEACTIVATE_RUNTIME_CROSSWALK_AND_FEATURE",
            **source,
            "candidate_change_planned": False,
            "promotion_event_change_planned": False,
            "canonical_change_planned": False,
            "project_change_planned": False,
            "lookup_exposure_change_planned": False,
            "android_change_planned": False,
        }
        row["row_checksum"] = checksum(row)
        planned_rows.append(row)

    feature_ids = {
        row["runtime_feature_id"]
        for row in planned_rows
    }
    crosswalk_ids = {
        row["runtime_crosswalk_id"]
        for row in planned_rows
    }
    candidate_ids = {
        row["candidate_id"]
        for row in planned_rows
    }
    source_ids = {
        row["source_feature_id"]
        for row in planned_rows
    }
    village_ids = {
        row["village_id"]
        for row in planned_rows
    }

    blockers = Counter()
    for row in planned_rows:
        if row["feature_is_active"]:
            blockers["feature_already_active"] += 1
        if row["crosswalk_is_active"]:
            blockers["crosswalk_already_active"] += 1
        if row["candidate_is_active"]:
            blockers["candidate_active"] += 1
        if row["promotion_status"] != "NOT_PROMOTED":
            blockers["candidate_promoted"] += 1
        if not row["eligible_for_runtime_after_promotion"]:
            blockers["source_not_runtime_eligible"] += 1
        if not row["native_geometry_valid"]:
            blockers["native_geometry_invalid"] += 1
        if row["native_geometry_srid"] != 4326:
            blockers["native_geometry_wrong_srid"] += 1
        if row["geometry_hash"] != row["source_geometry_hash"]:
            blockers["geometry_hash_mismatch"] += 1
        if row["has_active_village_collision"]:
            blockers["active_village_collision"] += 1
        if not all([
            row["village_is_active"],
            row["block_is_active"],
            row["district_is_active"],
            row["state_is_active"],
        ]):
            blockers["inactive_canonical_hierarchy"] += 1
        if (
            row["feature_proposal_checksum"] != SOURCE_PROPOSAL
            or row["crosswalk_proposal_checksum"] != SOURCE_PROPOSAL
            or row["feature_manifest_checksum"] != SOURCE_MANIFEST
            or row["crosswalk_manifest_checksum"] != SOURCE_MANIFEST
        ):
            blockers["evidence_pin_mismatch"] += 1

    checks = {
        "database_counts_unchanged": before == after,
        "row_count_exact":
            len(planned_rows) == EXPECTED_ROWS,
        "feature_identity_unique":
            len(feature_ids) == EXPECTED_ROWS,
        "crosswalk_identity_unique":
            len(crosswalk_ids) == EXPECTED_ROWS,
        "candidate_identity_unique":
            len(candidate_ids) == EXPECTED_ROWS,
        "source_identity_unique":
            len(source_ids) == EXPECTED_ROWS,
        "village_identity_unique":
            len(village_ids) == EXPECTED_ROWS,
        "no_row_blockers": not blockers,
        "single_inactive_promotion_event":
            len(events) == 1
            and events[0]["is_active"] is False,
        "active_baseline_exact":
            before["active_runtime_features"]
            == EXPECTED_ACTIVE_BASELINE
            and before["active_runtime_crosswalks"]
            == EXPECTED_ACTIVE_BASELINE,
    }

    healthy = all(checks.values())

    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows_path = args.output_dir / "jammu_kashmir_canary_rows.jsonl"
    plan_path = args.output_dir / "jammu_kashmir_canary_plan.json"

    with rows_path.open("w", encoding="utf-8") as handle:
        for row in planned_rows:
            handle.write(canonical_json(row) + "\n")

    planned_active = EXPECTED_ACTIVE_BASELINE + EXPECTED_ROWS

    plan = {
        "schema_version": SCHEMA_VERSION,
        "status": (
            "CANARY_PLAN_READY_NOT_AUTHORIZED"
            if healthy
            else "CANARY_PLAN_BLOCKED"
        ),
        "healthy": healthy,
        "authorized": False,
        "state": {
            "state_name": STATE_NAME,
            "state_lgd_code": STATE_LGD_CODE,
        },
        "runtime_set_id": RUNTIME_SET_ID,
        "source_proposal_checksum": SOURCE_PROPOSAL,
        "source_manifest_checksum": SOURCE_MANIFEST,
        "row_count": len(planned_rows),
        "rows": str(rows_path.relative_to(ROOT)),
        "rows_sha256": file_sha256(rows_path),
        "ordered_row_manifest_sha256": checksum(
            [row["row_checksum"] for row in planned_rows]
        ),
        "promotion_events": events,
        "blocker_counts": dict(sorted(blockers.items())),
        "checks": checks,
        "database_before": before,
        "database_after": after,
        "expected_apply_delta": {
            "active_runtime_features": EXPECTED_ROWS,
            "active_runtime_crosswalks": EXPECTED_ROWS,
            "active_promotion_events": 0,
            "active_candidates": 0,
            "promoted_candidates": 0,
            "project_matches": 0,
            "expected_active_runtime_features_after":
                planned_active,
            "expected_active_runtime_crosswalks_after":
                planned_active,
        },
        "rollback_contract": {
            "deactivate_crosswalks_first": True,
            "deactivate_features_second": True,
            "expected_crosswalks_deactivated":
                EXPECTED_ROWS,
            "expected_features_deactivated":
                EXPECTED_ROWS,
            "expected_active_baseline_restored":
                EXPECTED_ACTIVE_BASELINE,
            "delete_runtime_rows": False,
            "mutate_promotion_event": False,
            "mutate_candidate": False,
            "mutate_source": False,
            "mutate_canonical_geography": False,
        },
        "required_apply_controls": [
            "explicit canary authorization",
            "reviewed plan and rows SHA256 pins",
            "PostgreSQL advisory lock",
            "single state-scoped transaction",
            "pre-commit exact reconciliation",
            "forced rollback rehearsal",
            "idempotent apply and rollback",
            "post-apply lookup correctness and ambiguity checks",
        ],
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
    plan["plan_checksum"] = checksum(plan)

    plan_path.write_text(
        json.dumps(plan, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )

    print(json.dumps(plan, indent=2, sort_keys=True, default=str))

    if not healthy:
        failed = sorted(
            key for key, value in checks.items() if not value
        )
        raise SystemExit(
            "CANARY_PLAN_FAILED:" + ",".join(failed)
        )

    print("NWDP POST-LGD JAMMU & KASHMIR CANARY PLAN PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

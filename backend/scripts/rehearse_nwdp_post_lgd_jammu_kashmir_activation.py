#!/usr/bin/env python3
"""Rollback-only rehearsal for the 821-row J&K activation canary."""

import hashlib
import json
import sys
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
PLAN_CHECKSUM = (
    "6d6adfe74b0bdd482c35f6cf7fe7006e"
    "5de8c9d7201982d1079a2d4a5f0caa05"
)
ROWS_SHA256 = (
    "c6338a7d6f10989ed0f380b06093bd28"
    "d63c52e6797f31a6e28fd3a08afe36a4"
)
STATE_LGD_CODE = "1"
EXPECTED_ROWS = 821
BASELINE = 449_899
TEMPORARY_ACTIVE = 450_720
ADVISORY_LOCK_KEY = 7_621_092_023

PLAN = (
    ROOT / "data/staged/core_stack/promotion_review"
    / "20260930-post-lgd-jammu-kashmir-activation-canary-v1"
    / "jammu_kashmir_canary_plan.json"
)
ROWS = PLAN.with_name("jammu_kashmir_canary_rows.jsonl")
OUTPUT = PLAN.with_name(
    "jammu_kashmir_canary_rollback_rehearsal.json"
)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024), b""
        ):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot(connection):
    row = connection.execute(text("""
        select
          (select count(*) from
             geography_boundary_runtime_features
             where is_active) as active_features,
          (select count(*) from
             geography_boundary_runtime_crosswalks
             where is_active) as active_crosswalks,
          (select count(*) from
             geography_boundary_crosswalk_candidates
             where is_active) as active_candidates,
          (select count(*) from
             geography_boundary_crosswalk_candidates
             where promotion_status = 'PROMOTED')
             as promoted_candidates,
          (select count(*) from
             geography_boundary_project_matches)
             as project_matches
    """)).mappings().one()
    return {
        key: int(value or 0)
        for key, value in row.items()
    }


def cohort_active(connection):
    row = connection.execute(text("""
        select
          count(*) filter (
            where feature.is_active
          )::bigint as active_features,
          count(*) filter (
            where crosswalk.is_active
          )::bigint as active_crosswalks
        from geography_boundary_runtime_features feature
        join geography_boundary_runtime_crosswalks crosswalk
          on crosswalk.runtime_feature_id = feature.id
         and crosswalk.runtime_set_id = feature.runtime_set_id
        where feature.runtime_set_id =
                cast(:runtime_set_id as uuid)
          and feature.metadata->>'proposal_checksum' =
                :proposal
          and crosswalk.state_lgd_code = :state_code
    """), {
        "runtime_set_id": RUNTIME_SET_ID,
        "proposal": SOURCE_PROPOSAL,
        "state_code": STATE_LGD_CODE,
    }).mappings().one()
    return {
        key: int(value or 0)
        for key, value in row.items()
    }


def main():
    plan = json.loads(PLAN.read_text(encoding="utf-8"))

    input_checks = {
        "plan_checksum_exact":
            plan["plan_checksum"] == PLAN_CHECKSUM,
        "rows_sha256_exact":
            sha256(ROWS) == ROWS_SHA256
            and plan["rows_sha256"] == ROWS_SHA256,
        "plan_status_exact":
            plan["status"]
            == "CANARY_PLAN_READY_NOT_AUTHORIZED",
        "plan_not_authorized":
            plan["authorized"] is False,
        "plan_row_count_exact":
            plan["row_count"] == EXPECTED_ROWS,
    }
    if not all(input_checks.values()):
        raise SystemExit(
            "REHEARSAL_INPUT_PIN_FAILURE:"
            + ",".join(
                key for key, value in input_checks.items()
                if not value
            )
        )

    engine = create_engine(settings.DATABASE_URL)
    connection = engine.connect()
    transaction = connection.begin()

    try:
        connection.execute(
            text("select pg_advisory_xact_lock(:key)"),
            {"key": ADVISORY_LOCK_KEY},
        )
        connection.execute(
            text("set local lock_timeout = '10s'")
        )
        connection.execute(
            text("set local statement_timeout = '5min'")
        )

        before = snapshot(connection)
        before_cohort = cohort_active(connection)

        features_changed = connection.execute(text("""
            update geography_boundary_runtime_features feature
            set is_active = true
            where feature.runtime_set_id =
                    cast(:runtime_set_id as uuid)
              and feature.metadata->>'proposal_checksum' =
                    :proposal
              and feature.metadata->>'state_lgd_code' =
                    :state_code
              and feature.is_active = false
        """), {
            "runtime_set_id": RUNTIME_SET_ID,
            "proposal": SOURCE_PROPOSAL,
            "state_code": STATE_LGD_CODE,
        }).rowcount

        crosswalks_changed = connection.execute(text("""
            update geography_boundary_runtime_crosswalks
            set is_active = true
            where runtime_set_id =
                    cast(:runtime_set_id as uuid)
              and metadata->>'proposal_checksum' =
                    :proposal
              and state_lgd_code = :state_code
              and is_active = false
        """), {
            "runtime_set_id": RUNTIME_SET_ID,
            "proposal": SOURCE_PROPOSAL,
            "state_code": STATE_LGD_CODE,
        }).rowcount

        temporary = snapshot(connection)
        temporary_cohort = cohort_active(connection)

        temporary_checks = {
            "features_changed_exact":
                features_changed == EXPECTED_ROWS,
            "crosswalks_changed_exact":
                crosswalks_changed == EXPECTED_ROWS,
            "temporary_feature_total_exact":
                temporary["active_features"]
                == TEMPORARY_ACTIVE,
            "temporary_crosswalk_total_exact":
                temporary["active_crosswalks"]
                == TEMPORARY_ACTIVE,
            "temporary_cohort_exact":
                temporary_cohort == {
                    "active_features": EXPECTED_ROWS,
                    "active_crosswalks": EXPECTED_ROWS,
                },
            "protected_counts_unchanged":
                all(
                    temporary[key] == before[key]
                    for key in (
                        "active_candidates",
                        "promoted_candidates",
                        "project_matches",
                    )
                ),
        }
        if not all(temporary_checks.values()):
            raise RuntimeError(
                "TEMPORARY_RECONCILIATION_FAILED"
            )

        transaction.rollback()

    except Exception:
        if transaction.is_active:
            transaction.rollback()
        connection.close()
        raise

    restored = snapshot(connection)
    restored_cohort = cohort_active(connection)
    connection.close()

    restoration_checks = {
        "baseline_started_exact":
            before["active_features"] == BASELINE
            and before["active_crosswalks"] == BASELINE,
        "cohort_started_inactive":
            before_cohort == {
                "active_features": 0,
                "active_crosswalks": 0,
            },
        "database_snapshot_restored":
            restored == before,
        "cohort_restored_inactive":
            restored_cohort == before_cohort,
        "rollback_executed": True,
        "commit_capability_absent": True,
    }

    healthy = (
        all(input_checks.values())
        and all(temporary_checks.values())
        and all(restoration_checks.values())
    )

    report = {
        "schema_version":
            "nwdp_post_lgd_activation_rollback_rehearsal.v1",
        "status": (
            "ROLLBACK_ONLY_REHEARSAL_PASSED"
            if healthy
            else "ROLLBACK_ONLY_REHEARSAL_FAILED"
        ),
        "healthy": healthy,
        "database_writes_committed": False,
        "input_checks": input_checks,
        "temporary_checks": temporary_checks,
        "restoration_checks": restoration_checks,
        "before": before,
        "temporary": temporary,
        "restored": restored,
        "before_cohort": before_cohort,
        "temporary_cohort": temporary_cohort,
        "restored_cohort": restored_cohort,
        "policy": {
            "activation_authorized": False,
            "commit_mode_available": False,
            "lookup_exposure_authorized": False,
            "candidate_changes_authorized": False,
            "canonical_changes_authorized": False,
            "project_changes_authorized": False,
            "android_changes_authorized": False,
        },
    }

    OUTPUT.write_text(
        json.dumps(report, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))

    if not healthy:
        return 1

    print(
        "NWDP POST-LGD JAMMU & KASHMIR "
        "ROLLBACK-ONLY REHEARSAL PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

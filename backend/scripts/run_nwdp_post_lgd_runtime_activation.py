#!/usr/bin/env python3
"""Checkpointed activation wrapper for 17,498 post-LGD runtime rows."""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.config import settings
import scripts.run_national_direct_village_runtime_activation as engine


RUNTIME_SET_ID = "e5f93e27-a0bd-5c8b-bef3-d97986e14c55"
SOURCE_PROPOSAL = (
    "80bbbe640c7675d9d9882c3489e53cc4"
    "81159eee222341e03d24a3121d7d0cae"
)
EXPECTED_ROWS = 17_498
BASELINE = 449_899
FINAL_TOTAL = 467_397
LOCK_KEY = 7_621_092_024

SOURCE_DIR = (
    ROOT / "data/staged/core_stack/promotion_review"
    / "20260925-lgd-priority-state-reconciliation-v1"
)
SOURCE_ARTIFACTS = {
    "nwdp_post_lgd_staging_manifest.json":
        "ce78c6ad48541069d3c949a1e8ae78cd4eb1af856014b361cfa1db7348191a76",
    "nwdp_post_lgd_staging_proposal.json":
        "1ebe99f17e952985c2db40991666bc1babbc1e17f2679ba8174126c75335f0f5",
    "nwdp_post_lgd_staging_checkpoint.json":
        "dd9b985c1181a6bfb2fb734b307f5f01c501171e1d92b76815b0324066b7534e",
    "nwdp_post_lgd_staging_authorization.json":
        "b786c1b6f8192d52560a2caca9f5044597c5f3d67ca19f7d9edf37874ef73112",
}
APPLY_CONFIRMATION = "APPLY_POST_LGD_RUNTIME_ACTIVATION"
ROLLBACK_CONFIRMATION = "ROLLBACK_POST_LGD_RUNTIME_ACTIVATION"

STATES = [
    {"state_lgd_code": "1", "state_name": "Jammu & Kashmir", "expected_row_count": 821},
    {"state_lgd_code": "2", "state_name": "Himachal Pradesh", "expected_row_count": 2433},
    {"state_lgd_code": "3", "state_name": "Punjab", "expected_row_count": 1625},
    {"state_lgd_code": "5", "state_name": "Uttarakhand", "expected_row_count": 1359},
    {"state_lgd_code": "6", "state_name": "Haryana", "expected_row_count": 1922},
    {"state_lgd_code": "7", "state_name": "Delhi", "expected_row_count": 8},
    {"state_lgd_code": "8", "state_name": "Rajasthan", "expected_row_count": 9309},
    {"state_lgd_code": "37", "state_name": "Ladakh", "expected_row_count": 21},
]

OUTPUT_DIR = (
    ROOT / "data/staged/core_stack/promotion_review"
    / "20260930-post-lgd-runtime-activation-v1"
)
CHECKPOINT = OUTPUT_DIR / "checkpoint.json"
REPORT = OUTPUT_DIR / "report.json"


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical_checksum(value):
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


def checkpoint_checksum(value):
    return canonical_checksum({
        key: item
        for key, item in value.items()
        if key != "checkpoint_checksum"
    })


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)
    return digest.hexdigest()


def validate_source_artifacts():
    results = {}
    for filename, expected_sha256 in SOURCE_ARTIFACTS.items():
        artifact = SOURCE_DIR / filename
        if not artifact.is_file():
            raise RuntimeError(
                f"SOURCE_ARTIFACT_MISSING:{artifact}"
            )

        actual_sha256 = sha256_file(artifact)
        results[filename] = {
            "path": str(artifact.relative_to(ROOT)),
            "expected_sha256": expected_sha256,
            "actual_sha256": actual_sha256,
            "valid": actual_sha256 == expected_sha256,
        }

    invalid = [
        filename
        for filename, result in results.items()
        if not result["valid"]
    ]
    if invalid:
        raise RuntimeError(
            "SOURCE_ARTIFACT_HASH_MISMATCH:"
            + ",".join(sorted(invalid))
        )

    return results


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--rollback", action="store_true")
    mode.add_argument("--rollback-only-rehearsal", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--admin-confirmation")
    return parser.parse_args()


def configure_reused_engine():
    engine.RUNTIME_SET_ID = RUNTIME_SET_ID
    engine.SOURCE_PROPOSAL = SOURCE_PROPOSAL
    engine.EXPECTED_ROWS = EXPECTED_ROWS
    engine.EXPECTED_STATES = len(STATES)
    engine.EXISTING_ACTIVE_ROWS = BASELINE


def counts(connection):
    row = connection.execute(text("""
        select
          (select count(*) from geography_boundary_runtime_features
             where is_active) as features,
          (select count(*) from geography_boundary_runtime_crosswalks
             where is_active) as crosswalks,
          (select count(*) from geography_boundary_crosswalk_candidates
             where is_active) as active_candidates,
          (select count(*) from geography_boundary_crosswalk_candidates
             where promotion_status = 'PROMOTED') as promoted_candidates,
          (select count(*) from geography_boundary_project_matches)
             as project_matches
    """)).mappings().one()
    return {key: int(value or 0) for key, value in row.items()}


def cohort_counts(connection):
    row = connection.execute(text("""
        select
          count(*)::bigint as rows,
          count(*) filter (where feature.is_active)::bigint
             as active_features,
          count(*) filter (where crosswalk.is_active)::bigint
             as active_crosswalks
        from geography_boundary_runtime_features feature
        join geography_boundary_runtime_crosswalks crosswalk
          on crosswalk.runtime_feature_id = feature.id
         and crosswalk.runtime_set_id = feature.runtime_set_id
        where feature.runtime_set_id = cast(:runtime_set as uuid)
          and feature.metadata->>'proposal_checksum' = :proposal
    """), {
        "runtime_set": RUNTIME_SET_ID,
        "proposal": SOURCE_PROPOSAL,
    }).mappings().one()
    return {key: int(value or 0) for key, value in row.items()}


def write_json(path, value):
    if path == CHECKPOINT:
        value = dict(value)
        value["checkpoint_checksum"] = (
            checkpoint_checksum(value)
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".writing")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def validate_protected(before, after):
    for key in (
        "active_candidates",
        "promoted_candidates",
        "project_matches",
    ):
        if before[key] != after[key]:
            raise RuntimeError(
                f"PROTECTED_COUNT_CHANGED:{key}"
            )


def requested_mode(args):
    if args.rollback_only_rehearsal:
        return "ROLLBACK_REHEARSAL"
    if args.rollback:
        return "ROLLBACK"
    if args.apply:
        return "APPLY"
    return "DRY_RUN"


def load_resume_checkpoint(mode):
    if not CHECKPOINT.is_file():
        raise RuntimeError(
            "RESUME_CHECKPOINT_MISSING"
        )

    checkpoint = json.loads(
        CHECKPOINT.read_text(encoding="utf-8")
    )
    expected_checksum = checkpoint.get(
        "checkpoint_checksum"
    )
    actual_checksum = checkpoint_checksum(checkpoint)

    checks = {
        "schema_exact":
            checkpoint.get("schema_version")
            == (
                "nwdp_post_lgd_runtime_"
                "activation_checkpoint.v1"
            ),
        "checksum_exact":
            expected_checksum == actual_checksum,
        "status_in_progress":
            checkpoint.get("status") == "IN_PROGRESS",
        "mode_exact":
            checkpoint.get("mode") == mode,
        "runtime_set_exact":
            checkpoint.get("runtime_set_id")
            == RUNTIME_SET_ID,
        "source_proposal_exact":
            checkpoint.get(
                "source_proposal_checksum"
            )
            == SOURCE_PROPOSAL,
        "row_count_exact":
            checkpoint.get("expected_row_count")
            == EXPECTED_ROWS,
        "state_count_exact":
            checkpoint.get("expected_state_count")
            == len(STATES),
        "baseline_exact":
            checkpoint.get(
                "expected_active_baseline"
            )
            == BASELINE,
        "final_total_exact":
            checkpoint.get("expected_active_final")
            == FINAL_TOTAL,
    }

    failed = sorted(
        key for key, value in checks.items()
        if not value
    )
    if failed:
        raise RuntimeError(
            "RESUME_CHECKPOINT_INVALID:"
            + ",".join(failed)
        )

    completed = checkpoint.get("completed")
    if not isinstance(completed, list):
        raise RuntimeError(
            "RESUME_COMPLETED_LIST_REQUIRED"
        )

    completed_codes = [
        str(item.get("state_lgd_code"))
        for item in completed
    ]
    expected_prefix = [
        state["state_lgd_code"]
        for state in STATES[:len(completed)]
    ]

    if completed_codes != expected_prefix:
        raise RuntimeError(
            "RESUME_STATE_PREFIX_INVALID"
        )

    expected_completed_rows = sum(
        state["expected_row_count"]
        for state in STATES[:len(completed)]
    )
    if (
        checkpoint.get("completed_state_count")
        != len(completed)
        or checkpoint.get("completed_row_count")
        != expected_completed_rows
    ):
        raise RuntimeError(
            "RESUME_PROGRESS_COUNT_INVALID"
        )

    return checkpoint, completed


def validate_execution_start(
    mode,
    before,
    cohort_before,
    completed,
):
    completed_rows = sum(
        item["expected_row_count"]
        for item in completed
    )

    if mode in {"APPLY", "ROLLBACK_REHEARSAL"}:
        expected_total = BASELINE + completed_rows
        expected_cohort_active = completed_rows
    elif mode == "ROLLBACK":
        expected_total = FINAL_TOTAL - completed_rows
        expected_cohort_active = (
            EXPECTED_ROWS - completed_rows
        )
    else:
        return

    checks = {
        "feature_total_exact":
            before["features"] == expected_total,
        "crosswalk_total_exact":
            before["crosswalks"] == expected_total,
        "cohort_feature_progress_exact":
            cohort_before["active_features"]
            == expected_cohort_active,
        "cohort_crosswalk_progress_exact":
            cohort_before["active_crosswalks"]
            == expected_cohort_active,
        "candidate_state_unchanged":
            before["active_candidates"] == 0
            and before["promoted_candidates"] == 0,
        "project_matches_unchanged":
            before["project_matches"] == 0,
    }

    failed = sorted(
        key for key, value in checks.items()
        if not value
    )
    if failed:
        raise RuntimeError(
            "EXECUTION_START_STATE_INVALID:"
            + ",".join(failed)
        )


def main():
    args = parse_args()
    source_artifacts = validate_source_artifacts()
    configure_reused_engine()

    if args.apply and args.admin_confirmation != APPLY_CONFIRMATION:
        raise SystemExit(f"APPLY_REQUIRES:{APPLY_CONFIRMATION}")
    if args.rollback and args.admin_confirmation != ROLLBACK_CONFIRMATION:
        raise SystemExit(f"ROLLBACK_REQUIRES:{ROLLBACK_CONFIRMATION}")

    db = create_engine(settings.DATABASE_URL)
    with db.connect() as connection:
        before = counts(connection)
        cohort_before = cohort_counts(connection)

    if cohort_before["rows"] != EXPECTED_ROWS:
        raise SystemExit("COHORT_COUNT_MISMATCH")

    if not (args.apply or args.rollback or args.rollback_only_rehearsal):
        report = {
            "schema_version": "nwdp_post_lgd_runtime_activation.v1",
            "status": "DRY_RUN_READY_NOT_AUTHORIZED",
            "database_writes_attempted": False,
            "before": before,
            "cohort": cohort_before,
            "states": STATES,
            "expected_final_total": FINAL_TOTAL,
            "source_artifacts": source_artifacts,
            "reused_engine":
                "run_national_direct_village_runtime_activation",
        }
        write_json(REPORT, report)
        print(json.dumps(report, indent=2))
        return 0

    rehearsal = args.rollback_only_rehearsal
    mode = requested_mode(args)

    if args.resume:
        if mode not in {"APPLY", "ROLLBACK"}:
            raise RuntimeError(
                "RESUME_REQUIRES_APPLY_OR_ROLLBACK"
            )
        checkpoint, completed = (
            load_resume_checkpoint(mode)
        )
        states_to_process = STATES[len(completed):]
    else:
        if (
            mode in {"APPLY", "ROLLBACK"}
            and CHECKPOINT.is_file()
        ):
            existing = json.loads(
                CHECKPOINT.read_text(encoding="utf-8")
            )
            if existing.get("status") == "IN_PROGRESS":
                raise RuntimeError(
                    "IN_PROGRESS_CHECKPOINT_REQUIRES_RESUME"
                )
        completed = []
        states_to_process = STATES

    if not states_to_process:
        raise RuntimeError(
            "NO_INCOMPLETE_STATES_TO_PROCESS"
        )

    validate_execution_start(
        mode,
        before,
        cohort_before,
        completed,
    )

    for state in states_to_process:
        with db.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(
                    text("select pg_advisory_xact_lock(:key)"),
                    {"key": LOCK_KEY},
                )
                connection.execute(text("set local lock_timeout='10s'"))
                connection.execute(text("set local statement_timeout='10min'"))

                if args.rollback:
                    result = engine.deactivate_state(connection, state)
                else:
                    result = engine.activate_state(connection, state)

                if rehearsal:
                    transaction.rollback()
                else:
                    transaction.commit()

                completed.append({
                    **state,
                    "result": result,
                    "committed": not rehearsal,
                })
                checkpoint_status = (
                    "COMPLETED"
                    if len(completed) == len(STATES)
                    else "IN_PROGRESS"
                )
                write_json(CHECKPOINT, {
                    "schema_version":
                        "nwdp_post_lgd_runtime_activation_checkpoint.v1",
                    "status": checkpoint_status,
                    "runtime_set_id": RUNTIME_SET_ID,
                    "source_proposal_checksum":
                        SOURCE_PROPOSAL,
                    "expected_row_count": EXPECTED_ROWS,
                    "expected_state_count": len(STATES),
                    "expected_active_baseline": BASELINE,
                    "expected_active_final": FINAL_TOTAL,
                    "mode": (
                        "ROLLBACK_REHEARSAL"
                        if rehearsal
                        else "ROLLBACK"
                        if args.rollback
                        else "APPLY"
                    ),
                    "completed_state_count":
                        len(completed),
                    "completed_row_count": sum(
                        item["expected_row_count"]
                        for item in completed
                    ),
                    "completed": completed,
                    "updated_at": now(),
                })
            except Exception:
                if transaction.is_active:
                    transaction.rollback()
                raise

    with db.connect() as connection:
        after = counts(connection)
        cohort_after = cohort_counts(connection)

    validate_protected(before, after)

    if rehearsal:
        if after != before or cohort_after != cohort_before:
            raise RuntimeError("REHEARSAL_DID_NOT_RESTORE_BASELINE")
        status = "FULL_COHORT_ROLLBACK_REHEARSAL_PASSED"
    elif args.apply:
        if (
            after["features"] != FINAL_TOTAL
            or after["crosswalks"] != FINAL_TOTAL
            or cohort_after["active_features"] != EXPECTED_ROWS
            or cohort_after["active_crosswalks"] != EXPECTED_ROWS
        ):
            raise RuntimeError("APPLY_RECONCILIATION_FAILED")
        status = "POST_LGD_RUNTIME_ACTIVATION_APPLIED"
    else:
        if (
            after["features"] != BASELINE
            or after["crosswalks"] != BASELINE
            or cohort_after["active_features"] != 0
            or cohort_after["active_crosswalks"] != 0
        ):
            raise RuntimeError("ROLLBACK_RECONCILIATION_FAILED")
        status = "POST_LGD_RUNTIME_ACTIVATION_ROLLED_BACK"

    report = {
        "schema_version": "nwdp_post_lgd_runtime_activation.v1",
        "status": status,
        "database_writes_attempted": not rehearsal,
        "database_writes_committed": not rehearsal,
        "before": before,
        "after": after,
        "cohort_before": cohort_before,
        "cohort_after": cohort_after,
        "states": completed,
        "source_artifacts": source_artifacts,
        "lookup_exposure_changed": False,
        "candidate_changes": False,
        "canonical_changes": False,
        "project_changes": False,
        "android_changes": False,
    }
    write_json(REPORT, report)
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

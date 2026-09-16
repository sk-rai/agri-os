#!/usr/bin/env python3
"""Forced-failure rollback regression for the generic state-batch engine."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.database import SessionLocal  # noqa: E402
from scripts import (  # noqa: E402
    apply_boundary_geometry_validation_metadata_authorized_state_batch
    as apply_engine,
)

RUN_ROOT = (
    ROOT / "data/staged/core_stack/"
    "boundary_validation_metadata_rollout_runs"
)
FIXTURE_ROOT = (
    RUN_ROOT / "_generic_engine_dynamic_regression"
)
PLAN_DIR = FIXTURE_ROOT / "plan"
STATE_SLUG = "bihar"
OUTPUT_DIR = FIXTURE_ROOT / "execution"
PLANNER = (
    ROOT / "backend/scripts/"
    "plan_boundary_geometry_validation_metadata_national_rollout.py"
)
ENGINE = (
    ROOT / "backend/scripts/"
    "apply_boundary_geometry_validation_metadata_authorized_state_batch.py"
)


def check(condition: bool, label: str, detail=None) -> None:
    if not condition:
        print(f"FAIL {label}")
        if detail is not None:
            print(json.dumps(detail, indent=2, default=str))
        raise AssertionError(label)
    print(f"PASS {label}")


def database_snapshot(
    feature_ids: list[str],
    rollback_token: str,
) -> dict:
    with SessionLocal() as db:
        counts = dict(db.execute(text("""
            select
              (select count(*)
               from geography_boundary_source_features)
                as source_feature_rows,
              (select count(*)
               from geography_boundary_source_features
               where geometry_validation_status = 'NOT_VALIDATED')
                as not_validated_rows,
              (select count(*)
               from geography_boundary_source_features
               where geometry_validation_status = 'VALIDATED')
                as validated_rows,
              (select count(*)
               from geography_boundary_source_features
               where eligible_for_runtime_after_promotion = true)
                as runtime_eligible_source_rows,
              (select count(*)
               from geography_boundary_validation_metadata_events)
                as validation_event_rows,
              (select count(*)
               from geography_boundary_validation_metadata_events
               where is_active = true)
                as active_validation_event_rows,
              (select count(*)
               from geography_boundary_crosswalk_candidates)
                as candidate_rows,
              (select count(*)
               from geography_boundary_crosswalk_candidates
               where is_active = true)
                as active_candidate_rows,
              (select count(*)
               from geography_boundary_crosswalk_candidates
               where promotion_status = 'PROMOTED')
                as promoted_candidate_rows,
              (select count(*)
               from geography_boundary_runtime_sets)
                as runtime_set_rows,
              (select count(*)
               from geography_boundary_runtime_features)
                as runtime_feature_rows,
              (select count(*)
               from geography_boundary_runtime_crosswalks)
                as runtime_crosswalk_rows
        """)).mappings().one())

        rows = [
            dict(row)
            for row in db.execute(text("""
                select
                  id::text as source_feature_id,
                  source_feature_index,
                  geometry_validation_status,
                  eligible_for_runtime_after_promotion,
                  metadata
                from geography_boundary_source_features
                where id = any(cast(:ids as uuid[]))
                order by source_feature_index
            """), {"ids": feature_ids}).mappings()
        ]

        event_count = int(db.execute(text("""
            select count(*)
            from geography_boundary_validation_metadata_events
            where rollback_token = :rollback_token
        """), {
            "rollback_token": rollback_token,
        }).scalar_one())

        db.rollback()

    return {
        "counts": {
            key: int(value or 0)
            for key, value in counts.items()
        },
        "rows": rows,
        "event_count_for_token": event_count,
    }


def main() -> int:
    shutil.rmtree(FIXTURE_ROOT, ignore_errors=True)
    PLAN_DIR.mkdir(parents=True)

    plan_process = subprocess.run(
        [
            sys.executable,
            str(PLANNER),
            "--output-dir",
            str(PLAN_DIR),
            "--states",
            STATE_SLUG,
            "--batch-limit",
            "500",
            "--workers",
            "1",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    check(
        plan_process.returncode == 0,
        "Fresh transaction fixture plan succeeds",
        {
            "stdout": plan_process.stdout,
            "stderr": plan_process.stderr,
        },
    )

    national = json.loads(
        (
            PLAN_DIR /
            "national_validation_metadata_wave_plan.json"
        ).read_text(encoding="utf-8")
    )
    state = next(
        row for row in national["states"]
        if row["state_slug"] == STATE_SLUG
    )
    plan_path = Path(state["plan_json"])
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    rows = plan["rows"]
    feature_ids = [
        row["source_feature_id"] for row in rows
    ]

    check(
        len(rows) == 500,
        "Dynamic Bihar fixture contains exactly 500 rows",
        {"row_count": len(rows)},
    )
    check(
        all(
            row["classification"] == "VALIDATED_NO_REPAIR"
            and row["current_geometry_validation_status"] ==
                "NOT_VALIDATED"
            and row["planned_geometry_validation_status"] ==
                "VALIDATED"
            and row["runtime_eligibility_change_planned"] is False
            for row in rows
        ),
        "Fixture contains only safe metadata transitions",
    )

    rollback_token = (
        "fixture-generic-state-batch-forced-failure-"
        f"{plan['batch']['batch_id']}"
    )
    authorization = {
        "schema_version": (
            "boundary_geometry_validation_metadata_"
            "state_batch_authorization.v1"
        ),
        "status": "AUTHORIZED",
        "national_plan_checksum":
            national["national_plan_checksum"],
        "state": {
            "state_slug": STATE_SLUG,
            "state_or_ut": state["state_or_ut"],
            "import_batch_id": state["import_batch_id"],
            "source_sha256": state["source_sha256"],
            "batch_id": state["batch_id"],
            "plan_checksum": state["plan_checksum"],
            "selected_row_count": len(rows),
            "first_source_feature_index":
                plan["batch"]["first_source_feature_index"],
            "last_source_feature_index":
                plan["batch"]["last_source_feature_index"],
            "rollback_token": rollback_token,
        },
        "approval": {
            "operator": "generic-engine-regression",
            "approver": "generic-engine-regression",
            "approval_reference":
                "forced-failure-transaction-regression",
        },
        "permissions": {
            "apply_authorized": True,
            "rollback_authorized": True,
            "maximum_row_count": 500,
            "validated_without_repair_only": True,
            "geometry_repair_allowed": False,
            "runtime_eligibility_change_allowed": False,
            "candidate_write_allowed": False,
            "runtime_table_write_allowed": False,
            "runtime_lookup_enablement_allowed": False,
            "android_behavior_change_allowed": False,
        },
    }
    authorization["authorization_checksum"] = (
        apply_engine.authorization_checksum(authorization)
    )

    shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
    OUTPUT_DIR.mkdir(parents=True)
    authorization_path = OUTPUT_DIR / "authorization.json"
    authorization_path.write_text(
        json.dumps(authorization, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    before = database_snapshot(feature_ids, rollback_token)
    check(
        before["event_count_for_token"] == 0,
        "Fixture rollback token is unused",
        before,
    )
    check(
        len(before["rows"]) == len(rows)
        and all(
            row["geometry_validation_status"] ==
                "NOT_VALIDATED"
            and row[
                "eligible_for_runtime_after_promotion"
            ] is False
            for row in before["rows"]
        ),
        "Fixture rows begin in the expected safe state",
        before["rows"],
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(ENGINE),
            "--authorization-json", str(authorization_path),
            "--authorization-checksum",
            authorization["authorization_checksum"],
            "--national-plan-checksum",
            national["national_plan_checksum"],
            "--plan-json", str(plan_path),
            "--plan-checksum", state["plan_checksum"],
            "--source-sha256", state["source_sha256"],
            "--rollback-token", rollback_token,
            "--output-dir", str(OUTPUT_DIR),
            "--operator", "generic-engine-regression",
            "--approver", "generic-engine-regression",
            "--approval-reference",
            "forced-failure-transaction-regression",
            "--apply",
            "--enable-validation-metadata-write",
            "--dry-run-reviewed",
            "--event-schema-reviewed",
            "--admin-confirmation",
            "--force-failure-after", "2",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    audit_path = (
        OUTPUT_DIR /
        "boundary_validation_metadata_authorized_state_batch_audit.json"
    )
    check(
        audit_path.is_file(),
        "Forced failure writes a durable audit report",
        {"stdout": proc.stdout, "stderr": proc.stderr},
    )
    audit = json.loads(audit_path.read_text(encoding="utf-8"))

    check(
        proc.returncode != 0
        and audit["healthy"] is False
        and audit["action"] == "ROLLED_BACK_TRANSACTION"
        and audit["error"] == "FORCED_MID_BATCH_FAILURE",
        "Forced mid-batch failure is surfaced",
        audit,
    )

    after = database_snapshot(feature_ids, rollback_token)
    check(
        after == before,
        "Forced failure rolls back source and event writes atomically",
        {"before": before, "after": after},
    )
    check(
        audit["final_counts"] == before["counts"]
        and audit["changed_source_row_count"] == 0
        and audit["changed_event_row_count"] == 0,
        "Failure audit reports no persisted transaction changes",
        audit,
    )
    check(
        audit["guardrails"]["transaction_changes_persisted"] is False
        and audit["guardrails"]["runtime_tables_written"] is False
        and audit["guardrails"]["runtime_lookup_enabled"] is False
        and audit["guardrails"]["android_behavior_changed"] is False,
        "Runtime and Android guardrails remain closed",
        audit["guardrails"],
    )

    apply_engine.configure_authorization(
        authorization,
        rollback=False,
    )
    apply_engine.FIXTURE_IDS = feature_ids
    apply_engine.FIXTURE_INDEXES = [
        row["source_feature_index"] for row in rows
    ]

    direct_args = Namespace(
        apply=True,
        rollback=False,
        enable_validation_metadata_write=True,
        dry_run_reviewed=True,
        event_schema_reviewed=True,
        admin_confirmation=True,
        operator="generic-engine-regression",
        approver="generic-engine-regression",
        approval_reference=(
            "forced-failure-transaction-regression"
        ),
        rollback_token=rollback_token,
        source_sha256=state["source_sha256"],
        plan_checksum=state["plan_checksum"],
        force_failure_after=0,
    )
    apply_engine.validate(direct_args, plan)

    with apply_engine.engine.connect() as connection:
        transaction = connection.begin()
        try:
            transactional_before = apply_engine.counts(connection)

            apply_action, applied_rows, applied_events = (
                apply_engine.apply_rows(
                    connection,
                    plan,
                    direct_args,
                )
            )
            applied_counts = apply_engine.counts(connection)

            check(
                apply_action == "APPLIED"
                and applied_rows == len(rows)
                and applied_events == len(rows),
                "Generic engine applies the exact authorized batch",
                {
                    "action": apply_action,
                    "rows": applied_rows,
                    "events": applied_events,
                },
            )
            check(
                applied_counts["not_validated_rows"] ==
                    transactional_before[
                        "not_validated_rows"
                    ] - len(rows)
                and applied_counts["validated_rows"] ==
                    transactional_before["validated_rows"] +
                    len(rows)
                and applied_counts["validation_event_rows"] ==
                    transactional_before[
                        "validation_event_rows"
                    ] + len(rows)
                and applied_counts[
                    "active_validation_event_rows"
                ] == transactional_before[
                    "active_validation_event_rows"
                ] + len(rows),
                "Authorized apply changes only validation metadata counts",
                {
                    "before": transactional_before,
                    "applied": applied_counts,
                },
            )

            retry_action, retry_rows, retry_events = (
                apply_engine.apply_rows(
                    connection,
                    plan,
                    direct_args,
                )
            )
            retry_counts = apply_engine.counts(connection)
            check(
                retry_action == "IDEMPOTENT_NO_OP"
                and retry_rows == 0
                and retry_events == 0
                and retry_counts == applied_counts,
                "Repeated authorized apply is idempotent",
                {
                    "action": retry_action,
                    "rows": retry_rows,
                    "events": retry_events,
                    "counts": retry_counts,
                },
            )

            applied_state_rows = [
                apply_engine.load_source(
                    connection,
                    feature_id,
                )
                for feature_id in feature_ids
            ]
            check(
                all(
                    row["geometry_validation_status"] ==
                        "VALIDATED"
                    and row[
                        "eligible_for_runtime_after_promotion"
                    ] is False
                    and row["metadata"].get(
                        apply_engine.MARKER
                    )
                    for row in applied_state_rows
                ),
                "Authorized rows carry reversible event evidence",
            )

            rollback_action, rolled_rows, rolled_events = (
                apply_engine.rollback_rows(
                    connection,
                    direct_args,
                )
            )
            rolled_counts = apply_engine.counts(connection)

            check(
                rollback_action == "ROLLED_BACK"
                and rolled_rows == len(rows)
                and rolled_events == len(rows),
                "Generic engine rolls back the exact authorized batch",
                {
                    "action": rollback_action,
                    "rows": rolled_rows,
                    "events": rolled_events,
                },
            )
            check(
                rolled_counts["not_validated_rows"] ==
                    transactional_before["not_validated_rows"]
                and rolled_counts["validated_rows"] ==
                    transactional_before["validated_rows"]
                and rolled_counts[
                    "active_validation_event_rows"
                ] == transactional_before[
                    "active_validation_event_rows"
                ]
                and rolled_counts["validation_event_rows"] ==
                    transactional_before[
                        "validation_event_rows"
                    ] + len(rows),
                "Rollback restores source counts and deactivates events",
                {
                    "before": transactional_before,
                    "rolled_back": rolled_counts,
                },
            )

            (
                retry_rollback_action,
                retry_rollback_rows,
                retry_rollback_events,
            ) = apply_engine.rollback_rows(
                connection,
                direct_args,
            )
            retry_rollback_counts = apply_engine.counts(connection)
            check(
                retry_rollback_action ==
                    "IDEMPOTENT_ROLLBACK_NO_OP"
                and retry_rollback_rows == 0
                and retry_rollback_events == 0
                and retry_rollback_counts == rolled_counts,
                "Repeated authorized rollback is idempotent",
                {
                    "action": retry_rollback_action,
                    "rows": retry_rollback_rows,
                    "events": retry_rollback_events,
                    "counts": retry_rollback_counts,
                },
            )

            restored_rows = [
                apply_engine.load_source(
                    connection,
                    feature_id,
                )
                for feature_id in feature_ids
            ]
            check(
                all(
                    row["geometry_validation_status"] ==
                        "NOT_VALIDATED"
                    and row[
                        "eligible_for_runtime_after_promotion"
                    ] is False
                    and apply_engine.MARKER not in
                        (row["metadata"] or {})
                    for row in restored_rows
                ),
                "Rollback restores exact pre-apply row state",
            )

            event_rows = apply_engine.active_events(
                connection,
                rollback_token,
            )
            check(
                len(event_rows) == len(rows)
                and all(
                    event["apply_status"] == "ROLLED_BACK"
                    and event["is_active"] is False
                    and event["rolled_back_by"] ==
                        "generic-engine-regression"
                    for event in event_rows
                ),
                "Rollback preserves immutable inactive evidence",
                event_rows,
            )
        finally:
            transaction.rollback()

    final = database_snapshot(feature_ids, rollback_token)
    check(
        final == before,
        "Outer fixture transaction leaves no persistent changes",
        {"before": before, "final": final},
    )

    print("=" * 72)
    print(
        "AUTHORIZED STATE-BATCH TRANSACTION AND ROLLBACK "
        "REGRESSION PASSED"
    )
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

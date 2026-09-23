#!/usr/bin/env python3
"""Guarded national direct-village runtime activation engine."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.config import settings  # noqa: E402


CAMPAIGN_DIR = (
    ROOT
    / "data/staged/core_stack/promotion_review"
    / "20260923-national-direct-village-runtime-activation-v1"
)

PROPOSAL_PATH = (
    CAMPAIGN_DIR
    / "national_direct_village_runtime_activation_proposal.json"
)

AUTHORIZATION_PATH = (
    CAMPAIGN_DIR
    / "national_direct_village_runtime_activation_authorization.json"
)

CHECKPOINT_PATH = (
    CAMPAIGN_DIR
    / "national_direct_village_runtime_activation_checkpoint.json"
)

DEFAULT_OUTPUT = (
    CAMPAIGN_DIR
    / "national_direct_village_runtime_activation_report.json"
)

ACTIVATION_PROPOSAL = (
    "09397c171a408f3ac12acb0c0a429f0f"
    "81d6a6841b3616f1f760e12b94f7c3d3"
)

ACTIVATION_AUTHORIZATION = (
    "e446de344a08dddd7cf46bc4a52aee8e"
    "06c6d49937187214d62ec0d35e1e35a7"
)

INITIAL_CHECKPOINT = (
    "2edd2a721663c789676d97e7ef71dc0b"
    "f4aaae6b44027322ee522f0ac06debff"
)

SOURCE_PROPOSAL = (
    "4040493550d62f4f2b4c380b404e80ff"
    "b8530c5c391f0497d022f2b638e2327e"
)

SOURCE_MANIFEST = (
    "3fc6bbd0162abe635339df96c5b704dec"
    "734d8f7824c44933468ede5ecaeefc3"
)

SOURCE_CHECKPOINT = (
    "a026f553c3157c5e32da425d2412c68d"
    "7fee32fb906734947f1a09bbfe68ad45"
)

RUNTIME_SET_ID = (
    "e5f93e27-a0bd-5c8b-bef3-d97986e14c55"
)

EXPECTED_ROWS = 449_789
EXPECTED_STATES = 30
EXISTING_ACTIVE_ROWS = 110
ADVISORY_LOCK_KEY = 7_621_092_022

SCHEMA_VERSION = (
    "national_direct_village_runtime_activation_engine.v1"
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_checksum(value: Any) -> str:
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


def checkpoint_checksum(value: dict[str, Any]) -> str:
    return canonical_checksum({
        key: item
        for key, item in value.items()
        if key != "checkpoint_checksum"
    })


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(value, dict):
        raise ValueError(f"INVALID_JSON_OBJECT:{path}")

    return value


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary = path.with_suffix(
        path.suffix + ".writing"
    )

    temporary.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )

    os.replace(temporary, path)


def db_url() -> str:
    return str(settings.DATABASE_URL)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
    )

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--resume", action="store_true")
    mode.add_argument("--rollback", action="store_true")
    mode.add_argument(
        "--rollback-only-rehearsal",
        action="store_true",
    )

    parser.add_argument(
        "--enable-national-runtime-activation",
        action="store_true",
    )
    parser.add_argument(
        "--authorization-reviewed",
        action="store_true",
    )
    parser.add_argument(
        "--rollback-procedure-reviewed",
        action="store_true",
    )
    parser.add_argument(
        "--admin-confirmation",
        action="store_true",
    )

    return parser.parse_args()


def validate_mutation_gates(options: argparse.Namespace) -> None:
    mutation = (
        options.apply
        or options.resume
        or options.rollback
    )

    if not mutation:
        return

    gates = {
        "enable":
            options.enable_national_runtime_activation,
        "authorization":
            options.authorization_reviewed,
        "rollback":
            options.rollback_procedure_reviewed,
        "admin":
            options.admin_confirmation,
    }

    failed = sorted(
        key
        for key, value in gates.items()
        if not value
    )

    if failed:
        raise ValueError(
            "MUTATION_GATES_NOT_SATISFIED:"
            + ",".join(failed)
        )


def validate_artifacts() -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    proposal = load_json(PROPOSAL_PATH)
    authorization = load_json(AUTHORIZATION_PATH)
    checkpoint = load_json(CHECKPOINT_PATH)

    checks = {
        "proposal":
            proposal.get(
                "activation_proposal_checksum"
            )
            == ACTIVATION_PROPOSAL,
        "proposal_healthy":
            proposal.get("healthy") is True,
        "authorization":
            authorization.get(
                "authorization_checksum"
            )
            == ACTIVATION_AUTHORIZATION,
        "authorization_status":
            authorization.get("status")
            == "AUTHORIZED",
        "authorization_proposal":
            authorization.get(
                "activation_proposal_checksum"
            )
            == ACTIVATION_PROPOSAL,
        "source_proposal":
            checkpoint.get(
                "source_proposal_checksum"
            )
            == SOURCE_PROPOSAL,
        "source_manifest":
            checkpoint.get(
                "source_manifest_sha256"
            )
            == SOURCE_MANIFEST,
        "source_checkpoint":
            checkpoint.get(
                "source_checkpoint_checksum"
            )
            == SOURCE_CHECKPOINT,
        "runtime_set":
            checkpoint.get("runtime_set_id")
            == RUNTIME_SET_ID,
        "rows":
            checkpoint.get("expected_row_count")
            == EXPECTED_ROWS,
        "states":
            checkpoint.get("expected_state_count")
            == EXPECTED_STATES
            and len(checkpoint.get("states") or [])
            == EXPECTED_STATES,
        "checkpoint":
            checkpoint.get("checkpoint_checksum")
            == checkpoint_checksum(checkpoint),
    }

    if not checkpoint.get("execution_started"):
        checks["initial_checkpoint"] = (
            checkpoint.get("checkpoint_checksum")
            == INITIAL_CHECKPOINT
        )

    permissions = authorization.get("permissions") or {}

    checks["allowed_permissions"] = (
        permissions.get(
            "campaign_runtime_feature_activation_allowed"
        )
        is True
        and permissions.get(
            "campaign_runtime_crosswalk_activation_allowed"
        )
        is True
        and permissions.get(
            "proposal_scoped_deactivation_allowed"
        )
        is True
    )

    prohibited = (
        "runtime_set_identity_change_allowed",
        "candidate_activation_allowed",
        "candidate_promotion_allowed",
        "promotion_event_activation_allowed",
        "project_match_write_allowed",
        "source_write_allowed",
        "android_behavior_change_allowed",
        "lookup_reenablement_allowed",
    )

    checks["prohibited_permissions"] = all(
        permissions.get(key) is False
        for key in prohibited
    )

    failed = sorted(
        key
        for key, value in checks.items()
        if not value
    )

    if failed:
        raise ValueError(
            "ACTIVATION_ARTIFACT_VALIDATION_FAILED:"
            + ",".join(failed)
        )

    return proposal, authorization, checkpoint


@contextmanager
def single_writer(connection):
    acquired = connection.execute(
        text("select pg_try_advisory_lock(:key)"),
        {"key": ADVISORY_LOCK_KEY},
    ).scalar_one()

    connection.commit()

    if acquired is not True:
        raise ValueError(
            "ACTIVATION_SINGLE_WRITER_LOCK_UNAVAILABLE"
        )

    try:
        yield
    finally:
        if connection.in_transaction():
            connection.rollback()

        connection.execute(
            text("select pg_advisory_unlock(:key)"),
            {"key": ADVISORY_LOCK_KEY},
        )
        connection.commit()


def state_counts(connection, state_code: str) -> dict[str, int]:
    row = connection.execute(
        text("""
            select
              count(distinct feature.id)::bigint
                as feature_count,
              count(distinct feature.id)
                filter (where feature.is_active)::bigint
                as active_feature_count,
              count(distinct crosswalk.id)::bigint
                as crosswalk_count,
              count(distinct crosswalk.id)
                filter (where crosswalk.is_active)::bigint
                as active_crosswalk_count
            from geography_boundary_runtime_crosswalks
              crosswalk
            join geography_boundary_runtime_features feature
              on feature.id =
                 crosswalk.runtime_feature_id
            where crosswalk.runtime_set_id =
                    cast(:runtime_set_id as uuid)
              and feature.runtime_set_id =
                    cast(:runtime_set_id as uuid)
              and crosswalk.metadata
                    ->>'proposal_checksum' =
                    :source_proposal
              and feature.metadata
                    ->>'proposal_checksum' =
                    :source_proposal
              and crosswalk.state_lgd_code =
                    :state_code
        """),
        {
            "runtime_set_id": RUNTIME_SET_ID,
            "source_proposal": SOURCE_PROPOSAL,
            "state_code": state_code,
        },
    ).mappings().one()

    return {
        key: int(value or 0)
        for key, value in row.items()
    }


def global_snapshot(connection) -> dict[str, int]:
    row = connection.execute(
        text("""
            select
              (
                select count(*)
                from geography_boundary_runtime_features
                where runtime_set_id =
                      cast(:runtime_set_id as uuid)
                  and metadata->>'proposal_checksum' =
                      :source_proposal
              )::bigint as campaign_features,
              (
                select count(*)
                from geography_boundary_runtime_features
                where runtime_set_id =
                      cast(:runtime_set_id as uuid)
                  and metadata->>'proposal_checksum' =
                      :source_proposal
                  and is_active
              )::bigint as active_campaign_features,
              (
                select count(*)
                from geography_boundary_runtime_crosswalks
                where runtime_set_id =
                      cast(:runtime_set_id as uuid)
                  and metadata->>'proposal_checksum' =
                      :source_proposal
              )::bigint as campaign_crosswalks,
              (
                select count(*)
                from geography_boundary_runtime_crosswalks
                where runtime_set_id =
                      cast(:runtime_set_id as uuid)
                  and metadata->>'proposal_checksum' =
                      :source_proposal
                  and is_active
              )::bigint as active_campaign_crosswalks,
              (
                select count(*)
                from geography_boundary_runtime_features
                where runtime_set_id =
                      cast(:runtime_set_id as uuid)
                  and metadata->>'proposal_checksum'
                        is distinct from
                        :source_proposal
                  and is_active
              )::bigint as preserved_active_features,
              (
                select count(*)
                from geography_boundary_runtime_crosswalks
                where runtime_set_id =
                      cast(:runtime_set_id as uuid)
                  and metadata->>'proposal_checksum'
                        is distinct from
                        :source_proposal
                  and is_active
              )::bigint as preserved_active_crosswalks,
              (
                select count(*)
                from geography_boundary_runtime_promotion_events
                where metadata->>'proposal_checksum' =
                      :source_proposal
                  and is_active
              )::bigint as active_campaign_events,
              (
                select count(*)
                from geography_boundary_crosswalk_candidates
                where is_active
              )::bigint as active_candidates,
              (
                select count(*)
                from geography_boundary_crosswalk_candidates
                where promotion_status = 'PROMOTED'
              )::bigint as promoted_candidates,
              (
                select count(*)
                from geography_boundary_project_matches
              )::bigint as project_matches
        """),
        {
            "runtime_set_id": RUNTIME_SET_ID,
            "source_proposal": SOURCE_PROPOSAL,
        },
    ).mappings().one()

    return {
        key: int(value or 0)
        for key, value in row.items()
    }


def validate_snapshot(
    snapshot: dict[str, int],
    expected_active: int | None = None,
) -> None:
    checks = {
        "campaign_features":
            snapshot["campaign_features"]
            == EXPECTED_ROWS,
        "campaign_crosswalks":
            snapshot["campaign_crosswalks"]
            == EXPECTED_ROWS,
        "preserved_features":
            snapshot["preserved_active_features"]
            == EXISTING_ACTIVE_ROWS,
        "preserved_crosswalks":
            snapshot["preserved_active_crosswalks"]
            == EXISTING_ACTIVE_ROWS,
        "events_inactive":
            snapshot["active_campaign_events"] == 0,
        "candidates_inactive":
            snapshot["active_candidates"] == 0,
        "candidates_unpromoted":
            snapshot["promoted_candidates"] == 0,
        "project_matches":
            snapshot["project_matches"] == 0,
    }

    if expected_active is not None:
        checks["active_features"] = (
            snapshot["active_campaign_features"]
            == expected_active
        )
        checks["active_crosswalks"] = (
            snapshot["active_campaign_crosswalks"]
            == expected_active
        )

    failed = sorted(
        key
        for key, value in checks.items()
        if not value
    )

    if failed:
        raise ValueError(
            "ACTIVATION_SNAPSHOT_FAILED:"
            + ",".join(failed)
        )


def activate_state(
    connection,
    state: dict[str, Any],
) -> dict[str, Any]:
    code = str(state["state_lgd_code"])
    expected = int(state["expected_row_count"])

    features = connection.execute(
        text("""
            update geography_boundary_runtime_features
              as feature
            set is_active = true
            where feature.runtime_set_id =
                    cast(:runtime_set_id as uuid)
              and feature.metadata
                    ->>'proposal_checksum' =
                    :source_proposal
              and feature.is_active = false
              and exists (
                select 1
                from geography_boundary_runtime_crosswalks
                  crosswalk
                where crosswalk.runtime_feature_id =
                        feature.id
                  and crosswalk.runtime_set_id =
                        cast(:runtime_set_id as uuid)
                  and crosswalk.metadata
                        ->>'proposal_checksum' =
                        :source_proposal
                  and crosswalk.state_lgd_code =
                        :state_code
              )
        """),
        {
            "runtime_set_id": RUNTIME_SET_ID,
            "source_proposal": SOURCE_PROPOSAL,
            "state_code": code,
        },
    ).rowcount

    crosswalks = connection.execute(
        text("""
            update geography_boundary_runtime_crosswalks
            set is_active = true
            where runtime_set_id =
                    cast(:runtime_set_id as uuid)
              and metadata->>'proposal_checksum' =
                    :source_proposal
              and state_lgd_code = :state_code
              and is_active = false
        """),
        {
            "runtime_set_id": RUNTIME_SET_ID,
            "source_proposal": SOURCE_PROPOSAL,
            "state_code": code,
        },
    ).rowcount

    counts = state_counts(connection, code)

    if (
        counts["feature_count"] != expected
        or counts["crosswalk_count"] != expected
        or counts["active_feature_count"] != expected
        or counts["active_crosswalk_count"] != expected
    ):
        raise ValueError(
            f"STATE_ACTIVATION_RECONCILIATION_FAILED:{code}"
        )

    return {
        "state_lgd_code": code,
        "features_changed": int(features or 0),
        "crosswalks_changed": int(crosswalks or 0),
        **counts,
    }


def deactivate_state(
    connection,
    state: dict[str, Any],
) -> dict[str, Any]:
    code = str(state["state_lgd_code"])

    crosswalks = connection.execute(
        text("""
            update geography_boundary_runtime_crosswalks
            set is_active = false
            where runtime_set_id =
                    cast(:runtime_set_id as uuid)
              and metadata->>'proposal_checksum' =
                    :source_proposal
              and state_lgd_code = :state_code
              and is_active = true
        """),
        {
            "runtime_set_id": RUNTIME_SET_ID,
            "source_proposal": SOURCE_PROPOSAL,
            "state_code": code,
        },
    ).rowcount

    features = connection.execute(
        text("""
            update geography_boundary_runtime_features
              as feature
            set is_active = false
            where feature.runtime_set_id =
                    cast(:runtime_set_id as uuid)
              and feature.metadata
                    ->>'proposal_checksum' =
                    :source_proposal
              and feature.is_active = true
              and exists (
                select 1
                from geography_boundary_runtime_crosswalks
                  crosswalk
                where crosswalk.runtime_feature_id =
                        feature.id
                  and crosswalk.runtime_set_id =
                        cast(:runtime_set_id as uuid)
                  and crosswalk.metadata
                        ->>'proposal_checksum' =
                        :source_proposal
                  and crosswalk.state_lgd_code =
                        :state_code
              )
        """),
        {
            "runtime_set_id": RUNTIME_SET_ID,
            "source_proposal": SOURCE_PROPOSAL,
            "state_code": code,
        },
    ).rowcount

    counts = state_counts(connection, code)

    if (
        counts["active_feature_count"] != 0
        or counts["active_crosswalk_count"] != 0
    ):
        raise ValueError(
            f"STATE_DEACTIVATION_RECONCILIATION_FAILED:{code}"
        )

    return {
        "state_lgd_code": code,
        "features_changed": int(features or 0),
        "crosswalks_changed": int(crosswalks or 0),
        **counts,
    }


def refresh_checkpoint(checkpoint: dict[str, Any]) -> None:
    checkpoint["completed_state_count"] = sum(
        state["status"] == "COMPLETED"
        for state in checkpoint["states"]
    )

    checkpoint["completed_row_count"] = sum(
        int(state["expected_row_count"])
        for state in checkpoint["states"]
        if state["status"] == "COMPLETED"
    )

    checkpoint["completed_transaction_count"] = (
        checkpoint["completed_state_count"]
    )

    checkpoint["generated_at"] = now_iso()
    checkpoint["checkpoint_checksum"] = (
        checkpoint_checksum(checkpoint)
    )


def run() -> int:
    options = arguments()
    validate_mutation_gates(options)

    proposal, authorization, checkpoint = (
        validate_artifacts()
    )

    if settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED:
        raise ValueError(
            "LOOKUP_MUST_REMAIN_DISABLED"
        )

    if options.apply:
        mode = "APPLY"
    elif options.resume:
        mode = "RESUME"
    elif options.rollback:
        mode = "ROLLBACK"
    elif options.rollback_only_rehearsal:
        mode = "ROLLBACK_ONLY_REHEARSAL"
    else:
        mode = "DRY_RUN"

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "healthy": False,
        "mode": mode,
        "activation_proposal_checksum":
            ACTIVATION_PROPOSAL,
        "authorization_checksum":
            ACTIVATION_AUTHORIZATION,
        "source_proposal_checksum":
            SOURCE_PROPOSAL,
        "source_manifest_sha256":
            SOURCE_MANIFEST,
        "runtime_set_id":
            RUNTIME_SET_ID,
        "authorized_row_count":
            EXPECTED_ROWS,
        "authorized_state_count":
            EXPECTED_STATES,
        "lookup_enabled": False,
        "guardrails": {
            "runtime_set_identity_changed": False,
            "candidate_activation_changed": False,
            "candidate_promotion_changed": False,
            "promotion_event_activation_changed": False,
            "project_matches_written": False,
            "source_written": False,
            "android_behavior_changed": False,
            "lookup_reenabled": False,
        },
    }

    engine = create_engine(db_url(), future=True)

    with engine.connect() as connection:
        with single_writer(connection):
            before = global_snapshot(connection)
            connection.commit()

            validate_snapshot(before)

            report["before"] = before

            if mode == "DRY_RUN":
                report["database_writes_attempted"] = False
                report["database_writes_committed"] = False

            elif mode == "ROLLBACK_ONLY_REHEARSAL":
                state = checkpoint["states"][0]

                rehearsal_before = state_counts(
                    connection,
                    state["state_lgd_code"],
                )
                connection.commit()

                apply_report = activate_state(
                    connection,
                    state,
                )
                rehearsal_during = state_counts(
                    connection,
                    state["state_lgd_code"],
                )

                connection.rollback()

                rehearsal_after = state_counts(
                    connection,
                    state["state_lgd_code"],
                )
                connection.commit()

                if rehearsal_after != rehearsal_before:
                    raise ValueError(
                        "ACTIVATION_REHEARSAL_STATE_CHANGED"
                    )

                report["rehearsal"] = {
                    "state_lgd_code":
                        state["state_lgd_code"],
                    "row_count":
                        state["expected_row_count"],
                    "before": rehearsal_before,
                    "during": rehearsal_during,
                    "after": rehearsal_after,
                    "apply_report": apply_report,
                    "rollback_executed": True,
                    "database_state_unchanged": True,
                    "checkpoint_written": False,
                }

                report["database_writes_attempted"] = True
                report["database_writes_committed"] = False

            elif mode in {"APPLY", "RESUME"}:
                if (
                    mode == "APPLY"
                    and checkpoint["execution_started"]
                ):
                    raise ValueError(
                        "APPLY_REQUIRES_PRISTINE_CHECKPOINT"
                    )

                checkpoint["execution_started"] = True
                checkpoint["status"] = "RUNNING"
                checkpoint["resume_required"] = True
                refresh_checkpoint(checkpoint)
                atomic_write(CHECKPOINT_PATH, checkpoint)

                state_reports = []

                for state in checkpoint["states"]:
                    counts = state_counts(
                        connection,
                        state["state_lgd_code"],
                    )
                    connection.commit()

                    expected = int(
                        state["expected_row_count"]
                    )

                    if (
                        counts["active_feature_count"]
                        == expected
                        and counts["active_crosswalk_count"]
                        == expected
                    ):
                        state["status"] = "COMPLETED"
                        state["active_feature_count"] = expected
                        state["active_crosswalk_count"] = expected
                        refresh_checkpoint(checkpoint)
                        atomic_write(
                            CHECKPOINT_PATH,
                            checkpoint,
                        )
                        continue

                    checkpoint["active_state_lgd_code"] = (
                        state["state_lgd_code"]
                    )
                    state["status"] = "RUNNING"
                    refresh_checkpoint(checkpoint)
                    atomic_write(CHECKPOINT_PATH, checkpoint)

                    try:
                        state_report = activate_state(
                            connection,
                            state,
                        )
                        connection.commit()
                    except Exception:
                        connection.rollback()
                        state["status"] = "FAILED"
                        state["last_error"] = (
                            "STATE_ACTIVATION_FAILED"
                        )
                        refresh_checkpoint(checkpoint)
                        atomic_write(
                            CHECKPOINT_PATH,
                            checkpoint,
                        )
                        raise

                    state["status"] = "COMPLETED"
                    state["features_activated"] = (
                        state_report["features_changed"]
                    )
                    state["crosswalks_activated"] = (
                        state_report["crosswalks_changed"]
                    )
                    state["active_feature_count"] = expected
                    state["active_crosswalk_count"] = expected
                    state["completed_at"] = now_iso()
                    state["last_error"] = None

                    checkpoint["active_state_lgd_code"] = None
                    refresh_checkpoint(checkpoint)
                    atomic_write(CHECKPOINT_PATH, checkpoint)

                    state_reports.append(state_report)

                checkpoint["status"] = "COMPLETED"
                checkpoint["resume_required"] = False
                checkpoint["active_state_lgd_code"] = None
                refresh_checkpoint(checkpoint)
                atomic_write(CHECKPOINT_PATH, checkpoint)

                after = global_snapshot(connection)
                connection.commit()

                validate_snapshot(
                    after,
                    expected_active=EXPECTED_ROWS,
                )

                report["states"] = state_reports
                report["after"] = after
                report["checkpoint_checksum"] = (
                    checkpoint["checkpoint_checksum"]
                )
                report["database_writes_attempted"] = True
                report["database_writes_committed"] = True

            elif mode == "ROLLBACK":
                rollback_reports = []

                for state in reversed(
                    checkpoint["states"]
                ):
                    rollback_reports.append(
                        deactivate_state(
                            connection,
                            state,
                        )
                    )
                    connection.commit()

                    state["status"] = "ROLLED_BACK"
                    state["active_feature_count"] = 0
                    state["active_crosswalk_count"] = 0
                    state["completed_at"] = now_iso()
                    refresh_checkpoint(checkpoint)
                    atomic_write(
                        CHECKPOINT_PATH,
                        checkpoint,
                    )

                checkpoint["status"] = "ROLLED_BACK"
                checkpoint["resume_required"] = False
                checkpoint["active_state_lgd_code"] = None
                refresh_checkpoint(checkpoint)
                atomic_write(CHECKPOINT_PATH, checkpoint)

                after = global_snapshot(connection)
                connection.commit()

                validate_snapshot(
                    after,
                    expected_active=0,
                )

                report["rollback"] = rollback_reports
                report["after"] = after
                report["checkpoint_checksum"] = (
                    checkpoint["checkpoint_checksum"]
                )
                report["database_writes_attempted"] = True
                report["database_writes_committed"] = True

            report["healthy"] = True
            report["generated_at"] = now_iso()

    atomic_write(options.output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def main() -> int:
    options = None

    try:
        return run()
    except Exception as exc:
        report = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": now_iso(),
            "healthy": False,
            "fail_closed": True,
            "error": (
                f"{type(exc).__name__}:{exc}"
            ),
        }

        output = (
            options.output
            if options is not None
            else DEFAULT_OUTPUT
        )

        atomic_write(output, report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

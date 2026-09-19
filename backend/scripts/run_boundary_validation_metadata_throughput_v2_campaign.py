#!/usr/bin/env python3
"""Guarded single-step operational runner for throughput V2 campaigns."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))

from app.core.database import engine  # noqa: E402
from boundary_validation_metadata_throughput_v2 import (  # noqa: E402
    EVENT_TABLE,
    execute_apply_transaction,
)
from plan_boundary_geometry_validation_metadata_bounded_state import (  # noqa: E402
    SCHEMA_VERSION as PLAN_SCHEMA_VERSION,
    canonical_checksum as plan_checksum_for,
)
from plan_boundary_geometry_validation_metadata_dry_run import (  # noqa: E402
    HASH_ALGORITHM,
)
from boundary_validation_metadata_throughput_v2_controller import (  # noqa: E402
    advance_committed_transaction,
    complete_empty_state,
    next_ready_state,
    preflight,
    stage_transaction,
)

MARKER = "authorized_state_batch_validation_metadata_apply"
DEFAULT_RAW_DIR = (
    ROOT
    / "data/raw/nwdp_boundary_all_state"
    / "20260824T110250Z"
)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"V2_JSON_OBJECT_REQUIRED:{path}")
    return value


def atomic_write_json(
    path: Path,
    value: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(
        path.suffix + ".writing"
    )
    temporary.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def proposal_state(
    proposal: dict[str, Any],
    state_slug: str,
) -> dict[str, Any]:
    matches = [
        state
        for state in proposal["states"]
        if state["state_slug"] == state_slug
    ]
    if len(matches) != 1:
        raise ValueError(
            "V2_PROPOSAL_STATE_IDENTITY_INVALID"
        )
    return matches[0]


def transaction_id(
    campaign_checksum: str,
    plan_checksum: str,
) -> str:
    return str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        (
            "agri-os:throughput-v2:"
            f"{campaign_checksum}:{plan_checksum}"
        ),
    ))


def rollback_token(
    campaign_checksum: str,
    plan_checksum: str,
) -> str:
    return str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        (
            "agri-os:throughput-v2:rollback:"
            f"{campaign_checksum}:{plan_checksum}"
        ),
    ))


def validate_plan_identity(
    *,
    plan: dict[str, Any],
    state: dict[str, Any],
    proposal_identity: dict[str, Any],
) -> None:
    if (
        plan.get("healthy") is not True
        or plan.get("mode")
        != "READ_ONLY_BOUNDED_STATE_VALIDATION_METADATA_PLAN"
    ):
        raise ValueError(
            "V2_PREPARED_PLAN_NOT_HEALTHY"
        )

    scope = plan.get("scope") or {}
    source = plan.get("source") or {}
    batch = plan.get("batch") or {}

    checksum_payload = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "state_slug": scope.get("state_slug"),
        "state_or_ut": scope.get("state_or_ut"),
        "import_batch_id":
            scope.get("import_batch_id"),
        "source_sha256": source.get("sha256"),
        "geometry_hash_algorithm":
            source.get(
                "geometry_hash_algorithm"
            ),
        "cursor_after_index":
            scope.get("cursor_after_index"),
        "limit": scope.get("limit"),
        "rows": plan.get("rows") or [],
    }
    recomputed_checksum = plan_checksum_for(
        checksum_payload
    )

    if (
        batch.get("plan_checksum")
        != recomputed_checksum
        or source.get(
            "geometry_hash_algorithm"
        ) != HASH_ALGORITHM
        or scope.get("state_slug")
        != state["state_slug"]
        or scope.get("state_or_ut")
        != state["state_or_ut"]
        or scope.get("import_batch_id")
        != proposal_identity["import_batch_id"]
        or int(
            scope.get("cursor_after_index", -2)
        )
        != int(state["cursor_after_index"])
        or scope.get("throughput_v2") is not True
        or source.get("sha256")
        != proposal_identity["source_sha256"]
        or not batch.get("plan_checksum")
    ):
        raise ValueError(
            "V2_PREPARED_PLAN_IDENTITY_INVALID"
        )

    rows = plan.get("rows") or []
    if len(rows) != int(
        batch.get("selected_row_count") or 0
    ):
        raise ValueError(
            "V2_PREPARED_PLAN_ROW_COUNT_MISMATCH"
        )


def prepare_next(
    *,
    proposal: dict[str, Any],
    authorization: dict[str, Any],
    checkpoint: dict[str, Any],
    expected_checksum: str,
    checkpoint_path: Path,
    campaign_dir: Path,
    raw_dir: Path,
) -> dict[str, Any]:
    preflight(
        proposal=proposal,
        authorization=authorization,
        checkpoint=checkpoint,
        expected_campaign_checksum=
            expected_checksum,
    )

    if checkpoint["status"] != "READY":
        raise ValueError(
            "V2_PREPARE_CHECKPOINT_NOT_READY"
        )

    state = next_ready_state(checkpoint)
    if state is None:
        raise ValueError(
            "V2_PREPARE_NO_READY_STATE"
        )

    identity = proposal_state(
        proposal,
        state["state_slug"],
    )

    transaction_number = (
        int(
            checkpoint[
                "completed_transaction_count"
            ]
        )
        + 1
    )
    output_dir = (
        campaign_dir
        / "transactions"
        / (
            f"{transaction_number:04d}-"
            f"{state['state_slug']}"
        )
    )

    planner_command = [
        str(ROOT / "venv/bin/python"),
        str(
            BACKEND
            / "scripts"
            / (
                "plan_boundary_geometry_validation_"
                "metadata_bounded_state.py"
            )
        ),
        "--state-slug",
        state["state_slug"],
        "--state-or-ut",
        state["state_or_ut"],
        "--expected-source-sha256",
        identity["source_sha256"],
        "--cursor-after-index",
        str(state["cursor_after_index"]),
        "--limit",
        str(
            proposal["limits"][
                "default_rows_per_state_transaction"
            ]
        ),
        "--throughput-v2",
        "--raw-dir",
        str(raw_dir),
        "--output-dir",
        str(output_dir),
    ]

    subprocess.run(
        planner_command,
        check=True,
    )

    plan_path = output_dir / (
        f"{state['state_slug']}"
        "_bounded_validation_metadata_plan.json"
    )
    plan = load_json(plan_path)

    validate_plan_identity(
        plan=plan,
        state=state,
        proposal_identity=identity,
    )

    batch = plan["batch"]
    selected_rows = int(
        batch["selected_row_count"]
    )

    if selected_rows == 0:
        updated = complete_empty_state(
            checkpoint=checkpoint,
            proposal=proposal,
            state_slug=state["state_slug"],
            final_cursor_after_index=int(
                batch["next_cursor_after_index"]
            ),
        )
        atomic_write_json(
            checkpoint_path,
            updated,
        )
        return {
            "status": "EMPTY_STATE_COMPLETE",
            "state_slug": state["state_slug"],
            "checkpoint_status":
                updated["status"],
        }

    plan_checksum = batch["plan_checksum"]

    prepared = {
        "transaction_id": transaction_id(
            expected_checksum,
            plan_checksum,
        ),
        "state_slug": state["state_slug"],
        "state_or_ut": state["state_or_ut"],
        "plan_checksum": plan_checksum,
        "plan_json": str(plan_path),
        "source_sha256":
            identity["source_sha256"],
        "import_batch_id":
            identity["import_batch_id"],
        "rollback_token": rollback_token(
            expected_checksum,
            plan_checksum,
        ),
        "selected_row_count": selected_rows,
        "first_source_feature_index": int(
            batch["first_source_feature_index"]
        ),
        "last_source_feature_index": int(
            batch["last_source_feature_index"]
        ),
        "next_cursor_after_index": int(
            batch["next_cursor_after_index"]
        ),
        "has_more": bool(batch["has_more"]),
    }

    updated = stage_transaction(
        checkpoint=checkpoint,
        proposal=proposal,
        prepared_transaction=prepared,
    )
    atomic_write_json(
        checkpoint_path,
        updated,
    )

    return {
        "status": "READY_TO_EXECUTE",
        **prepared,
    }


def execution_rows(
    plan: dict[str, Any],
    plan_checksum: str,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []

    for planned in plan["rows"]:
        row = dict(planned)
        row["event_id"] = str(uuid.uuid5(
            uuid.NAMESPACE_URL,
            (
                "agri-os:"
                "validation-metadata-throughput-v2:"
                f"{plan_checksum}:"
                f"{planned['source_feature_id']}"
            ),
        ))
        output.append(row)

    return output


def reconcile_committed_events(
    connection: Any,
    prepared: dict[str, Any],
) -> dict[str, int]:
    result = connection.execute(text(f"""
        select
          count(*) as event_count,
          count(distinct source_feature_id)
            as source_feature_count,
          count(*) filter (
            where apply_status = 'APPLIED'
              and is_active = true
          ) as active_applied_count
        from {EVENT_TABLE}
        where plan_checksum = :plan_checksum
          and rollback_token = :rollback_token
    """), {
        "plan_checksum":
            prepared["plan_checksum"],
        "rollback_token":
            prepared["rollback_token"],
    }).mappings().one()

    return {
        key: int(value or 0)
        for key, value in result.items()
    }


def execute_prepared(
    *,
    proposal: dict[str, Any],
    authorization: dict[str, Any],
    checkpoint: dict[str, Any],
    expected_checksum: str,
    checkpoint_path: Path,
) -> dict[str, Any]:
    preflight(
        proposal=proposal,
        authorization=authorization,
        checkpoint=checkpoint,
        expected_campaign_checksum=
            expected_checksum,
    )

    if checkpoint["status"] != (
        "READY_TO_EXECUTE"
    ):
        raise ValueError(
            "V2_EXECUTE_CHECKPOINT_NOT_READY"
        )

    prepared = checkpoint[
        "prepared_transaction"
    ]
    plan = load_json(
        Path(prepared["plan_json"])
    )
    state = next(
        item
        for item in checkpoint["states"]
        if item["state_slug"]
        == prepared["state_slug"]
    )
    identity = proposal_state(
        proposal,
        prepared["state_slug"],
    )

    validate_plan_identity(
        plan=plan,
        state={
            **state,
            "state_or_ut":
                prepared["state_or_ut"],
        },
        proposal_identity=identity,
    )

    if (
        plan["batch"]["plan_checksum"]
        != prepared["plan_checksum"]
        or len(plan["rows"])
        != int(
            prepared["selected_row_count"]
        )
    ):
        raise ValueError(
            "V2_EXECUTION_PLAN_IDENTITY_MISMATCH"
        )

    rows = execution_rows(
        plan,
        prepared["plan_checksum"],
    )
    approval = authorization["approval"]

    parameters = {
        "state_or_ut":
            prepared["state_or_ut"],
        "source_sha256":
            prepared["source_sha256"],
        "plan_checksum":
            prepared["plan_checksum"],
        "rollback_token":
            prepared["rollback_token"],
        "import_batch_id":
            prepared["import_batch_id"],
        "marker": MARKER,
        "event_metadata": json.dumps({
            "schema_version":
                "boundary_validation_metadata_"
                "throughput_v2_execution.v1",
            "campaign_id":
                proposal["campaign_id"],
            "transaction_id":
                prepared["transaction_id"],
            "approval_reference":
                approval[
                    "approval_reference"
                ],
        }),
        "applied_by": approval["operator"],
        "apply_report": json.dumps({
            "result": "APPLIED",
            "throughput_v2": True,
        }),
    }

    with engine.begin() as connection:
        apply_result = (
            execute_apply_transaction(
                connection,
                rows=rows,
                authorized_row_count=int(
                    prepared[
                        "selected_row_count"
                    ]
                ),
                parameters=parameters,
            )
        )

    with engine.connect() as connection:
        reconciliation = (
            reconcile_committed_events(
                connection,
                prepared,
            )
        )

    expected_rows = int(
        prepared["selected_row_count"]
    )
    if any(
        reconciliation[key] != expected_rows
        for key in (
            "event_count",
            "source_feature_count",
            "active_applied_count",
        )
    ):
        raise RuntimeError(
            "V2_POST_COMMIT_RECONCILIATION_MISMATCH"
        )

    execution_result = {
        "transaction_id":
            prepared["transaction_id"],
        "state_slug":
            prepared["state_slug"],
        "plan_checksum":
            prepared["plan_checksum"],
        "rollback_token":
            prepared["rollback_token"],
        "committed_row_count":
            expected_rows,
        "status": "COMMITTED",
        "apply_status":
            apply_result["status"],
        "committed_at":
            datetime.now(
                timezone.utc
            ).isoformat(),
        "reconciliation": reconciliation,
    }

    updated = advance_committed_transaction(
        checkpoint=checkpoint,
        proposal=proposal,
        execution_result=execution_result,
    )
    atomic_write_json(
        checkpoint_path,
        updated,
    )

    return execution_result


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--proposal",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--authorization",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--campaign-checksum",
        required=True,
    )
    parser.add_argument(
        "--campaign-dir",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=DEFAULT_RAW_DIR,
    )
    parser.add_argument(
        "--confirm-execute-prepared",
        action="store_true",
    )
    parser.add_argument(
        "command",
        choices=(
            "status",
            "prepare-next",
            "execute-prepared",
        ),
    )
    return parser.parse_args()


def main() -> int:
    options = arguments()

    proposal = load_json(options.proposal)
    authorization = load_json(
        options.authorization
    )
    checkpoint = load_json(
        options.checkpoint
    )

    preflight(
        proposal=proposal,
        authorization=authorization,
        checkpoint=checkpoint,
        expected_campaign_checksum=
            options.campaign_checksum,
    )

    if options.command == "status":
        result = checkpoint
    elif options.command == "prepare-next":
        result = prepare_next(
            proposal=proposal,
            authorization=authorization,
            checkpoint=checkpoint,
            expected_checksum=
                options.campaign_checksum,
            checkpoint_path=
                options.checkpoint,
            campaign_dir=
                options.campaign_dir,
            raw_dir=options.raw_dir,
        )
    else:
        if not (
            options.confirm_execute_prepared
        ):
            raise SystemExit(
                "V2_EXECUTE_PREPARED_CONFIRMATION_REQUIRED"
            )
        result = execute_prepared(
            proposal=proposal,
            authorization=authorization,
            checkpoint=checkpoint,
            expected_checksum=
                options.campaign_checksum,
            checkpoint_path=
                options.checkpoint,
        )

    print(json.dumps(
        result,
        indent=2,
        sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

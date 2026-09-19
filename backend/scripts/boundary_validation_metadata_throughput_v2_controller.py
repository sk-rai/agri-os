#!/usr/bin/env python3
"""Pure checkpoint state machine for throughput V2 campaigns.

No filesystem, planner, or database execution is performed here.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from boundary_validation_metadata_throughput_v2_campaign import (
    CHECKPOINT_SCHEMA,
    validate_authorization,
    validate_proposal,
)


STATE_STATUSES = {
    "READY",
    "READY_TO_EXECUTE",
    "COMPLETE",
}
CHECKPOINT_STATUSES = {
    "READY",
    "READY_TO_EXECUTE",
    "COMPLETE",
}


def validate_checkpoint(
    *,
    checkpoint: dict[str, Any],
    proposal: dict[str, Any],
) -> None:
    if (
        checkpoint.get("schema_version")
        != CHECKPOINT_SCHEMA
    ):
        raise ValueError(
            "V2_CHECKPOINT_SCHEMA_MISMATCH"
        )
    if (
        checkpoint.get("campaign_id")
        != proposal["campaign_id"]
        or checkpoint.get("campaign_checksum")
        != proposal["campaign_checksum"]
    ):
        raise ValueError(
            "V2_CHECKPOINT_IDENTITY_MISMATCH"
        )
    if (
        checkpoint.get("status")
        not in CHECKPOINT_STATUSES
    ):
        raise ValueError(
            "V2_CHECKPOINT_STATUS_INVALID"
        )

    states = checkpoint.get("states") or []
    proposal_states = proposal["states"]

    if len(states) != len(proposal_states):
        raise ValueError(
            "V2_CHECKPOINT_STATE_COUNT_MISMATCH"
        )
    if [
        state["state_slug"]
        for state in states
    ] != [
        state["state_slug"]
        for state in proposal_states
    ]:
        raise ValueError(
            "V2_CHECKPOINT_STATE_ORDER_MISMATCH"
        )

    if any(
        state.get("status")
        not in STATE_STATUSES
        for state in states
    ):
        raise ValueError(
            "V2_CHECKPOINT_STATE_STATUS_INVALID"
        )

    completed_rows = sum(
        int(state.get("completed_row_count") or 0)
        for state in states
    )
    completed_transactions = sum(
        int(
            state.get(
                "completed_transaction_count"
            ) or 0
        )
        for state in states
    )

    if (
        completed_rows
        != int(
            checkpoint.get(
                "completed_row_count"
            ) or 0
        )
    ):
        raise ValueError(
            "V2_CHECKPOINT_COMPLETED_ROW_COUNT_MISMATCH"
        )
    if (
        completed_transactions
        != int(
            checkpoint.get(
                "completed_transaction_count"
            ) or 0
        )
    ):
        raise ValueError(
            "V2_CHECKPOINT_TRANSACTION_COUNT_MISMATCH"
        )

    prepared = checkpoint.get(
        "prepared_transaction"
    )
    ready_states = [
        state
        for state in states
        if state["status"] == "READY_TO_EXECUTE"
    ]

    if checkpoint["status"] == "READY_TO_EXECUTE":
        if (
            not isinstance(prepared, dict)
            or len(ready_states) != 1
            or checkpoint.get(
                "active_state_slug"
            )
            != ready_states[0]["state_slug"]
            or prepared.get("state_slug")
            != ready_states[0]["state_slug"]
        ):
            raise ValueError(
                "V2_CHECKPOINT_PREPARED_TRANSACTION_INVALID"
            )
    elif (
        prepared is not None
        or ready_states
        or checkpoint.get(
            "active_state_slug"
        ) is not None
    ):
        raise ValueError(
            "V2_CHECKPOINT_UNEXPECTED_PREPARED_TRANSACTION"
        )

    transaction_records = (
        checkpoint.get("transactions") or []
    )
    if len(transaction_records) != int(
        checkpoint.get(
            "completed_transaction_count"
        ) or 0
    ):
        raise ValueError(
            "V2_CHECKPOINT_TRANSACTION_RECORD_COUNT_MISMATCH"
        )

    maximum_rows = int(
        proposal["limits"][
            "maximum_campaign_row_count"
        ]
    )
    if completed_rows > maximum_rows:
        raise ValueError(
            "V2_CHECKPOINT_CAMPAIGN_ROW_LIMIT_EXCEEDED"
        )


def preflight(
    *,
    proposal: dict[str, Any],
    authorization: dict[str, Any],
    checkpoint: dict[str, Any],
    expected_campaign_checksum: str,
) -> None:
    validate_proposal(
        proposal,
        expected_campaign_checksum,
    )
    validate_authorization(
        authorization=authorization,
        proposal=proposal,
        expected_campaign_checksum=
            expected_campaign_checksum,
    )
    validate_checkpoint(
        checkpoint=checkpoint,
        proposal=proposal,
    )


def next_ready_state(
    checkpoint: dict[str, Any],
) -> dict[str, Any] | None:
    if checkpoint.get("status") != "READY":
        raise ValueError(
            "V2_CHECKPOINT_NOT_READY"
        )

    for state in checkpoint["states"]:
        if state["status"] == "READY":
            return deepcopy(state)

    return None


def stage_transaction(
    *,
    checkpoint: dict[str, Any],
    proposal: dict[str, Any],
    prepared_transaction: dict[str, Any],
) -> dict[str, Any]:
    validate_checkpoint(
        checkpoint=checkpoint,
        proposal=proposal,
    )

    if checkpoint["status"] != "READY":
        raise ValueError(
            "V2_CHECKPOINT_NOT_READY"
        )

    required = (
        "transaction_id",
        "state_slug",
        "state_or_ut",
        "plan_checksum",
        "plan_json",
        "source_sha256",
        "import_batch_id",
        "rollback_token",
        "selected_row_count",
        "first_source_feature_index",
        "last_source_feature_index",
        "next_cursor_after_index",
        "has_more",
    )
    if any(
        prepared_transaction.get(key)
        in (None, "")
        for key in required
    ):
        raise ValueError(
            "V2_PREPARED_TRANSACTION_IDENTITY_INCOMPLETE"
        )

    selected_rows = int(
        prepared_transaction[
            "selected_row_count"
        ]
    )
    default_rows = int(
        proposal["limits"][
            "default_rows_per_state_transaction"
        ]
    )
    maximum_rows = int(
        proposal["limits"][
            "maximum_rows_per_state_transaction"
        ]
    )
    remaining_budget = (
        int(
            proposal["limits"][
                "maximum_campaign_row_count"
            ]
        )
        - int(
            checkpoint["completed_row_count"]
        )
    )

    if (
        selected_rows < 1
        or selected_rows > default_rows
        or selected_rows > maximum_rows
        or selected_rows > remaining_budget
    ):
        raise ValueError(
            "V2_PREPARED_TRANSACTION_ROW_LIMIT_INVALID"
        )

    output = deepcopy(checkpoint)

    state = next(
        (
            item
            for item in output["states"]
            if item["state_slug"]
            == prepared_transaction[
                "state_slug"
            ]
        ),
        None,
    )
    if state is None:
        raise ValueError(
            "V2_PREPARED_TRANSACTION_STATE_UNKNOWN"
        )
    if state["status"] != "READY":
        raise ValueError(
            "V2_PREPARED_TRANSACTION_STATE_NOT_READY"
        )
    if (
        state["state_or_ut"]
        != prepared_transaction[
            "state_or_ut"
        ]
    ):
        raise ValueError(
            "V2_PREPARED_TRANSACTION_STATE_IDENTITY_MISMATCH"
        )
    if (
        int(
            prepared_transaction[
                "first_source_feature_index"
            ]
        )
        <= int(state["cursor_after_index"])
        or int(
            prepared_transaction[
                "last_source_feature_index"
            ]
        )
        < int(
            prepared_transaction[
                "first_source_feature_index"
            ]
        )
        or int(
            prepared_transaction[
                "next_cursor_after_index"
            ]
        )
        < int(
            prepared_transaction[
                "last_source_feature_index"
            ]
        )
    ):
        raise ValueError(
            "V2_PREPARED_TRANSACTION_CURSOR_INVALID"
        )

    state["status"] = "READY_TO_EXECUTE"
    output["status"] = "READY_TO_EXECUTE"
    output["active_state_slug"] = (
        state["state_slug"]
    )
    output["prepared_transaction"] = deepcopy(
        prepared_transaction
    )

    validate_checkpoint(
        checkpoint=output,
        proposal=proposal,
    )
    return output


def advance_committed_transaction(
    *,
    checkpoint: dict[str, Any],
    proposal: dict[str, Any],
    execution_result: dict[str, Any],
) -> dict[str, Any]:
    validate_checkpoint(
        checkpoint=checkpoint,
        proposal=proposal,
    )

    if checkpoint["status"] != "READY_TO_EXECUTE":
        raise ValueError(
            "V2_CHECKPOINT_NOT_READY_TO_EXECUTE"
        )

    prepared = checkpoint[
        "prepared_transaction"
    ]
    if (
        execution_result.get("transaction_id")
        != prepared["transaction_id"]
        or execution_result.get("plan_checksum")
        != prepared["plan_checksum"]
        or execution_result.get("rollback_token")
        != prepared["rollback_token"]
        or int(
            execution_result.get(
                "committed_row_count"
            ) or 0
        )
        != int(prepared["selected_row_count"])
    ):
        raise ValueError(
            "V2_EXECUTION_RESULT_IDENTITY_MISMATCH"
        )

    output = deepcopy(checkpoint)
    state = next(
        item
        for item in output["states"]
        if item["state_slug"]
        == prepared["state_slug"]
    )

    committed_rows = int(
        prepared["selected_row_count"]
    )
    state["completed_row_count"] = (
        int(state["completed_row_count"])
        + committed_rows
    )
    state["completed_transaction_count"] = (
        int(
            state[
                "completed_transaction_count"
            ]
        )
        + 1
    )
    state["cursor_after_index"] = int(
        prepared["next_cursor_after_index"]
    )
    state["status"] = (
        "READY"
        if prepared["has_more"]
        else "COMPLETE"
    )

    output["completed_row_count"] = (
        int(output["completed_row_count"])
        + committed_rows
    )
    output["completed_transaction_count"] = (
        int(
            output[
                "completed_transaction_count"
            ]
        )
        + 1
    )
    output["transactions"].append(
        deepcopy(execution_result)
    )
    output["active_state_slug"] = None
    output["prepared_transaction"] = None

    has_ready = any(
        item["status"] == "READY"
        for item in output["states"]
    )
    output["status"] = (
        "READY"
        if has_ready
        else "COMPLETE"
    )

    validate_checkpoint(
        checkpoint=output,
        proposal=proposal,
    )
    return output


def complete_empty_state(
    *,
    checkpoint: dict[str, Any],
    proposal: dict[str, Any],
    state_slug: str,
    final_cursor_after_index: int,
) -> dict[str, Any]:
    validate_checkpoint(
        checkpoint=checkpoint,
        proposal=proposal,
    )
    if checkpoint["status"] != "READY":
        raise ValueError(
            "V2_CHECKPOINT_NOT_READY"
        )

    output = deepcopy(checkpoint)
    state = next(
        (
            item
            for item in output["states"]
            if item["state_slug"] == state_slug
        ),
        None,
    )
    if state is None:
        raise ValueError(
            "V2_EMPTY_STATE_UNKNOWN"
        )
    if state["status"] != "READY":
        raise ValueError(
            "V2_EMPTY_STATE_NOT_READY"
        )

    state["cursor_after_index"] = int(
        final_cursor_after_index
    )
    state["status"] = "COMPLETE"

    if not any(
        item["status"] == "READY"
        for item in output["states"]
    ):
        output["status"] = "COMPLETE"

    validate_checkpoint(
        checkpoint=output,
        proposal=proposal,
    )
    return output

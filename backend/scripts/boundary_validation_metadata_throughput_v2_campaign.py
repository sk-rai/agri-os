#!/usr/bin/env python3
"""Proposal and authorization contracts for throughput V2 campaigns.

This module does not execute plans or perform database writes.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from boundary_validation_metadata_throughput_v2 import (
    DEFAULT_ROWS_PER_STATE_TRANSACTION,
    DEFAULT_WRITER_COUNT,
    MAXIMUM_ROWS_PER_STATE_TRANSACTION,
    MAXIMUM_WRITER_COUNT,
)


PROPOSAL_SCHEMA = (
    "boundary_validation_metadata_throughput_v2_campaign_proposal.v1"
)
AUTHORIZATION_SCHEMA = (
    "boundary_validation_metadata_throughput_v2_campaign_authorization.v1"
)
CHECKPOINT_SCHEMA = (
    "boundary_validation_metadata_throughput_v2_campaign_checkpoint.v1"
)

PROHIBITED_CHANGES = (
    "geometry_repair_allowed",
    "runtime_eligibility_change_allowed",
    "candidate_write_allowed",
    "candidate_activation_allowed",
    "candidate_promotion_allowed",
    "runtime_table_write_allowed",
    "runtime_lookup_enablement_allowed",
    "android_behavior_change_allowed",
)


def canonical_checksum(value: dict[str, Any]) -> str:
    payload = {
        key: item
        for key, item in value.items()
        if key not in {
            "campaign_checksum",
            "authorization_checksum",
            "generated_at",
            "authorized_at",
            "output_json",
        }
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_proposal(
    *,
    campaign_id: str,
    start_database_counts: dict[str, int],
    states: list[dict[str, Any]],
) -> dict[str, Any]:
    if not campaign_id.strip():
        raise ValueError("V2_CAMPAIGN_ID_REQUIRED")
    if not states:
        raise ValueError("V2_CAMPAIGN_STATES_REQUIRED")

    normalized_states: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()
    seen_batches: set[str] = set()

    for state in states:
        required = (
            "state_slug",
            "state_or_ut",
            "import_batch_id",
            "source_sha256",
            "not_validated_count",
        )
        if any(
            state.get(key) in (None, "")
            for key in required
        ):
            raise ValueError(
                "V2_CAMPAIGN_STATE_IDENTITY_INCOMPLETE"
            )

        slug = str(state["state_slug"])
        batch = str(state["import_batch_id"])

        if slug in seen_slugs:
            raise ValueError(
                "V2_CAMPAIGN_STATE_SLUG_NOT_UNIQUE"
            )
        if batch in seen_batches:
            raise ValueError(
                "V2_CAMPAIGN_IMPORT_BATCH_NOT_UNIQUE"
            )

        seen_slugs.add(slug)
        seen_batches.add(batch)

        remaining = int(
            state["not_validated_count"]
        )
        if remaining < 0:
            raise ValueError(
                "V2_CAMPAIGN_STATE_COUNT_INVALID"
            )

        normalized_states.append({
            "state_slug": slug,
            "state_or_ut": str(
                state["state_or_ut"]
            ),
            "import_batch_id": batch,
            "source_sha256": str(
                state["source_sha256"]
            ),
            "start_not_validated_count": remaining,
            "initial_cursor_after_index": -1,
        })

    normalized_states.sort(
        key=lambda item: (
            item["start_not_validated_count"],
            item["state_slug"],
        )
    )

    maximum_campaign_rows = sum(
        state["start_not_validated_count"]
        for state in normalized_states
    )

    proposal: dict[str, Any] = {
        "schema_version": PROPOSAL_SCHEMA,
        "status": "PROPOSED_NOT_AUTHORIZED",
        "campaign_id": campaign_id,
        "generated_at":
            datetime.now(timezone.utc).isoformat(),
        "start_database_counts": {
            key: int(value or 0)
            for key, value
            in start_database_counts.items()
        },
        "limits": {
            "maximum_campaign_row_count":
                maximum_campaign_rows,
            "default_rows_per_state_transaction":
                DEFAULT_ROWS_PER_STATE_TRANSACTION,
            "maximum_rows_per_state_transaction":
                MAXIMUM_ROWS_PER_STATE_TRANSACTION,
            "default_writer_count":
                DEFAULT_WRITER_COUNT,
            "maximum_writer_count":
                MAXIMUM_WRITER_COUNT,
        },
        "execution_policy": {
            "state_order":
                "REMAINING_ROWS_ASCENDING_THEN_SLUG",
            "continuous_state_drain": True,
            "checkpoint_after_each_transaction": True,
            "one_active_transaction_per_state": True,
            "set_based_apply_required": True,
            "exact_returned_row_counts_required": True,
            "validated_without_repair_only": True,
        },
        "prohibited_changes": {
            key: False
            for key in PROHIBITED_CHANGES
        },
        "authorization": {
            "campaign_execution_authorized": False,
        },
        "states": normalized_states,
    }
    proposal["campaign_checksum"] = (
        canonical_checksum(proposal)
    )
    return proposal


def validate_proposal(
    proposal: dict[str, Any],
    expected_checksum: str,
) -> None:
    if proposal.get("schema_version") != PROPOSAL_SCHEMA:
        raise ValueError(
            "V2_CAMPAIGN_PROPOSAL_SCHEMA_MISMATCH"
        )
    if (
        proposal.get("status")
        != "PROPOSED_NOT_AUTHORIZED"
    ):
        raise ValueError(
            "V2_CAMPAIGN_PROPOSAL_STATUS_INVALID"
        )
    if (
        proposal.get("campaign_checksum")
        != expected_checksum
    ):
        raise ValueError(
            "V2_CAMPAIGN_EXPECTED_CHECKSUM_MISMATCH"
        )
    if canonical_checksum(proposal) != expected_checksum:
        raise ValueError(
            "V2_CAMPAIGN_CONTENT_CHECKSUM_MISMATCH"
        )

    limits = proposal.get("limits") or {}
    if (
        int(
            limits.get(
                "default_rows_per_state_transaction"
            ) or 0
        ) != DEFAULT_ROWS_PER_STATE_TRANSACTION
        or int(
            limits.get(
                "maximum_rows_per_state_transaction"
            ) or 0
        ) != MAXIMUM_ROWS_PER_STATE_TRANSACTION
        or int(
            limits.get("default_writer_count") or 0
        ) != DEFAULT_WRITER_COUNT
        or int(
            limits.get("maximum_writer_count") or 0
        ) != MAXIMUM_WRITER_COUNT
    ):
        raise ValueError(
            "V2_CAMPAIGN_LIMITS_INVALID"
        )

    states = proposal.get("states") or []
    ordered = sorted(
        states,
        key=lambda item: (
            int(item["start_not_validated_count"]),
            item["state_slug"],
        ),
    )
    if states != ordered:
        raise ValueError(
            "V2_CAMPAIGN_STATE_ORDER_INVALID"
        )

    maximum_rows = sum(
        int(state["start_not_validated_count"])
        for state in states
    )
    if int(
        limits.get("maximum_campaign_row_count")
        or -1
    ) != maximum_rows:
        raise ValueError(
            "V2_CAMPAIGN_ROW_BUDGET_INVALID"
        )

    if (
        proposal.get("authorization") or {}
    ).get(
        "campaign_execution_authorized"
    ) is not False:
        raise ValueError(
            "V2_CAMPAIGN_PROPOSAL_MUST_NOT_AUTHORIZE"
        )

    prohibited = (
        proposal.get("prohibited_changes") or {}
    )
    if (
        set(prohibited) != set(PROHIBITED_CHANGES)
        or any(
            prohibited.get(key) is not False
            for key in PROHIBITED_CHANGES
        )
    ):
        raise ValueError(
            "V2_CAMPAIGN_PROHIBITED_PERMISSION_ENABLED"
        )


def required_confirmation(
    proposal: dict[str, Any],
) -> str:
    limits = proposal["limits"]
    return (
        "Authorize throughput V2 campaign "
        f"{proposal['campaign_checksum']} for up to "
        f"{limits['maximum_campaign_row_count']} rows with "
        f"{limits['default_rows_per_state_transaction']}-row "
        "default state transactions and "
        f"{limits['default_writer_count']} writer"
    )


def build_authorization(
    *,
    proposal: dict[str, Any],
    expected_checksum: str,
    confirmation: str,
    operator: str,
    approver: str,
    approval_reference: str,
) -> dict[str, Any]:
    validate_proposal(
        proposal,
        expected_checksum,
    )

    if confirmation != required_confirmation(proposal):
        raise ValueError(
            "V2_CAMPAIGN_CONFIRMATION_MISMATCH"
        )
    if not operator or not approver or not approval_reference:
        raise ValueError(
            "V2_CAMPAIGN_APPROVAL_IDENTITY_INCOMPLETE"
        )

    authorization: dict[str, Any] = {
        "schema_version": AUTHORIZATION_SCHEMA,
        "status": "AUTHORIZED",
        "campaign_id": proposal["campaign_id"],
        "campaign_checksum": expected_checksum,
        "authorized_at":
            datetime.now(timezone.utc).isoformat(),
        "approval": {
            "operator": operator,
            "approver": approver,
            "approval_reference": approval_reference,
            "confirmation": confirmation,
        },
        "permissions": {
            "campaign_execution_authorized": True,
            "maximum_campaign_row_count":
                proposal["limits"][
                    "maximum_campaign_row_count"
                ],
            "default_rows_per_state_transaction":
                DEFAULT_ROWS_PER_STATE_TRANSACTION,
            "maximum_rows_per_state_transaction":
                MAXIMUM_ROWS_PER_STATE_TRANSACTION,
            "writer_count": DEFAULT_WRITER_COUNT,
            "validated_without_repair_only": True,
            **{
                key: False
                for key in PROHIBITED_CHANGES
            },
        },
    }
    authorization["authorization_checksum"] = (
        canonical_checksum(authorization)
    )
    return authorization


def validate_authorization(
    *,
    authorization: dict[str, Any],
    proposal: dict[str, Any],
    expected_campaign_checksum: str,
) -> None:
    validate_proposal(
        proposal,
        expected_campaign_checksum,
    )

    if (
        authorization.get("schema_version")
        != AUTHORIZATION_SCHEMA
    ):
        raise ValueError(
            "V2_CAMPAIGN_AUTHORIZATION_SCHEMA_MISMATCH"
        )
    if authorization.get("status") != "AUTHORIZED":
        raise ValueError(
            "V2_CAMPAIGN_NOT_AUTHORIZED"
        )
    if (
        authorization.get("campaign_id")
        != proposal["campaign_id"]
        or authorization.get("campaign_checksum")
        != expected_campaign_checksum
    ):
        raise ValueError(
            "V2_CAMPAIGN_AUTHORIZATION_IDENTITY_MISMATCH"
        )
    if (
        canonical_checksum(authorization)
        != authorization.get(
            "authorization_checksum"
        )
    ):
        raise ValueError(
            "V2_CAMPAIGN_AUTHORIZATION_CHECKSUM_MISMATCH"
        )

    permissions = (
        authorization.get("permissions") or {}
    )
    if (
        permissions.get(
            "campaign_execution_authorized"
        ) is not True
        or int(
            permissions.get(
                "maximum_campaign_row_count"
            ) or -1
        ) != int(
            proposal["limits"][
                "maximum_campaign_row_count"
            ]
        )
        or int(
            permissions.get(
                "default_rows_per_state_transaction"
            ) or 0
        ) != DEFAULT_ROWS_PER_STATE_TRANSACTION
        or int(
            permissions.get(
                "maximum_rows_per_state_transaction"
            ) or 0
        ) != MAXIMUM_ROWS_PER_STATE_TRANSACTION
        or int(
            permissions.get("writer_count") or 0
        ) != DEFAULT_WRITER_COUNT
        or permissions.get(
            "validated_without_repair_only"
        ) is not True
    ):
        raise ValueError(
            "V2_CAMPAIGN_AUTHORIZATION_LIMITS_INVALID"
        )

    if any(
        permissions.get(key) is not False
        for key in PROHIBITED_CHANGES
    ):
        raise ValueError(
            "V2_CAMPAIGN_AUTHORIZATION_PROHIBITED"
        )


def initial_checkpoint(
    proposal: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": CHECKPOINT_SCHEMA,
        "campaign_id": proposal["campaign_id"],
        "campaign_checksum":
            proposal["campaign_checksum"],
        "status": "READY",
        "completed_row_count": 0,
        "completed_transaction_count": 0,
        "active_state_slug": None,
        "states": [
            {
                "state_slug": state["state_slug"],
                "state_or_ut": state["state_or_ut"],
                "cursor_after_index":
                    state["initial_cursor_after_index"],
                "completed_row_count": 0,
                "completed_transaction_count": 0,
                "status": (
                    "READY"
                    if state[
                        "start_not_validated_count"
                    ] > 0
                    else "COMPLETE"
                ),
            }
            for state in proposal["states"]
        ],
        "transactions": [],
    }

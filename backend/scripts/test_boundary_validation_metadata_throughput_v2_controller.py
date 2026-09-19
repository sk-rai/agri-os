#!/usr/bin/env python3
"""Regression for the pure throughput V2 controller state machine."""

from __future__ import annotations

from boundary_validation_metadata_throughput_v2_campaign import (
    build_authorization,
    build_proposal,
    initial_checkpoint,
    required_confirmation,
)
from boundary_validation_metadata_throughput_v2_controller import (
    advance_committed_transaction,
    complete_empty_state,
    next_ready_state,
    preflight,
    stage_transaction,
    validate_checkpoint,
)


def fixture():
    proposal = build_proposal(
        campaign_id="controller-fixture",
        start_database_counts={
            "source_feature_rows": 100,
            "not_validated_rows": 30_000,
            "validated_rows": 70_000,
        },
        states=[
            {
                "state_slug": "empty",
                "state_or_ut": "Empty",
                "import_batch_id": "batch-empty",
                "source_sha256": "a" * 64,
                "not_validated_count": 0,
            },
            {
                "state_slug": "small",
                "state_or_ut": "Small",
                "import_batch_id": "batch-small",
                "source_sha256": "b" * 64,
                "not_validated_count": 5_000,
            },
            {
                "state_slug": "large",
                "state_or_ut": "Large",
                "import_batch_id": "batch-large",
                "source_sha256": "c" * 64,
                "not_validated_count": 25_000,
            },
        ],
    )
    authorization = build_authorization(
        proposal=proposal,
        expected_checksum=
            proposal["campaign_checksum"],
        confirmation=
            required_confirmation(proposal),
        operator="fixture",
        approver="fixture",
        approval_reference="fixture",
    )
    checkpoint = initial_checkpoint(proposal)
    return proposal, authorization, checkpoint


def main() -> int:
    proposal, authorization, checkpoint = fixture()

    preflight(
        proposal=proposal,
        authorization=authorization,
        checkpoint=checkpoint,
        expected_campaign_checksum=
            proposal["campaign_checksum"],
    )

    assert (
        next_ready_state(checkpoint)[
            "state_slug"
        ]
        == "small"
    )

    prepared = {
        "transaction_id": "transaction-1",
        "state_slug": "small",
        "state_or_ut": "Small",
        "plan_checksum": "d" * 64,
        "plan_json": "/tmp/plan.json",
        "source_sha256": "b" * 64,
        "import_batch_id": "batch-small",
        "rollback_token": "rollback-1",
        "selected_row_count": 5_000,
        "first_source_feature_index": 1,
        "last_source_feature_index": 5_000,
        "next_cursor_after_index": 5_000,
        "has_more": False,
    }

    staged = stage_transaction(
        checkpoint=checkpoint,
        proposal=proposal,
        prepared_transaction=prepared,
    )
    assert staged["status"] == "READY_TO_EXECUTE"
    assert (
        staged["active_state_slug"]
        == "small"
    )

    replay = {
        "transaction_id": "transaction-1",
        "plan_checksum": "d" * 64,
        "rollback_token": "rollback-1",
        "committed_row_count": 5_000,
        "status": "COMMITTED",
    }
    advanced = advance_committed_transaction(
        checkpoint=staged,
        proposal=proposal,
        execution_result=replay,
    )

    assert advanced["status"] == "READY"
    assert advanced["completed_row_count"] == 5_000
    assert (
        advanced["completed_transaction_count"]
        == 1
    )
    assert (
        next_ready_state(advanced)[
            "state_slug"
        ]
        == "large"
    )

    completed = complete_empty_state(
        checkpoint=advanced,
        proposal=proposal,
        state_slug="large",
        final_cursor_after_index=99_999,
    )
    assert completed["status"] == "COMPLETE"

    validate_checkpoint(
        checkpoint=completed,
        proposal=proposal,
    )

    print("PASS authorization and checkpoint preflight")
    print("PASS zero-row states start complete")
    print("PASS smallest ready state is selected first")
    print("PASS prepared transaction is identity-pinned")
    print("PASS committed transaction advances counts")
    print("PASS empty terminal state completes safely")
    print(
        "# VALIDATION METADATA THROUGHPUT V2 "
        "CONTROLLER REGRESSION PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

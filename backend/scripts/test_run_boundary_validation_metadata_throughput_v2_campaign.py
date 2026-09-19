#!/usr/bin/env python3
"""Regression for guarded throughput V2 operational runner."""

from __future__ import annotations

import tempfile
from pathlib import Path

from boundary_validation_metadata_throughput_v2_campaign import (
    build_authorization,
    build_proposal,
    initial_checkpoint,
    required_confirmation,
)
from boundary_validation_metadata_throughput_v2_controller import (
    advance_committed_transaction,
    stage_transaction,
    validate_checkpoint,
)
from run_boundary_validation_metadata_throughput_v2_campaign import (
    atomic_write_json,
    execution_rows,
    rollback_token,
    transaction_id,
    validate_plan_identity,
)


def fixture():
    proposal = build_proposal(
        campaign_id="runner-fixture",
        start_database_counts={
            "not_validated_rows": 2,
        },
        states=[{
            "state_slug": "small",
            "state_or_ut": "Small",
            "import_batch_id": "batch-small",
            "source_sha256": "a" * 64,
            "not_validated_count": 2,
        }],
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
    return proposal, authorization


def main() -> int:
    proposal, authorization = fixture()
    assert authorization["status"] == "AUTHORIZED"

    plan_checksum = "b" * 64
    campaign_checksum = (
        proposal["campaign_checksum"]
    )

    first_transaction_id = transaction_id(
        campaign_checksum,
        plan_checksum,
    )
    first_rollback_token = rollback_token(
        campaign_checksum,
        plan_checksum,
    )

    assert first_transaction_id == transaction_id(
        campaign_checksum,
        plan_checksum,
    )
    assert first_rollback_token == rollback_token(
        campaign_checksum,
        plan_checksum,
    )
    assert (
        first_transaction_id
        != first_rollback_token
    )

    prepared = {
        "transaction_id":
            first_transaction_id,
        "state_slug": "small",
        "state_or_ut": "Small",
        "plan_checksum": plan_checksum,
        "plan_json": "/tmp/fixture-plan.json",
        "source_sha256": "a" * 64,
        "import_batch_id": "batch-small",
        "rollback_token":
            first_rollback_token,
        "selected_row_count": 2,
        "first_source_feature_index": 1,
        "last_source_feature_index": 2,
        "next_cursor_after_index": 2,
        "has_more": False,
    }

    staged = stage_transaction(
        checkpoint=initial_checkpoint(
            proposal
        ),
        proposal=proposal,
        prepared_transaction=prepared,
    )
    assert (
        staged["status"]
        == "READY_TO_EXECUTE"
    )

    plan = {
        "rows": [
            {
                "source_feature_id":
                    "source-1",
                "source_feature_index": 1,
            },
            {
                "source_feature_id":
                    "source-2",
                "source_feature_index": 2,
            },
        ],
    }

    rows = execution_rows(
        plan,
        plan_checksum,
    )
    replay_rows = execution_rows(
        plan,
        plan_checksum,
    )

    assert rows == replay_rows
    assert len({
        row["event_id"]
        for row in rows
    }) == 2

    tampered_plan = {
        "healthy": True,
        "mode":
            "READ_ONLY_BOUNDED_STATE_VALIDATION_METADATA_PLAN",
        "scope": {
            "state_slug": "small",
            "state_or_ut": "Small",
            "import_batch_id": "batch-small",
            "cursor_after_index": -1,
            "limit": 2,
            "throughput_v2": True,
        },
        "source": {
            "sha256": "a" * 64,
            "geometry_hash_algorithm":
                "NWDP_GEOJSON_GEOMETRY_CANONICAL_V1",
        },
        "batch": {
            "plan_checksum": "c" * 64,
            "selected_row_count": 2,
        },
        "rows": plan["rows"],
    }
    checksum_rejected = False
    try:
        validate_plan_identity(
            plan=tampered_plan,
            state={
                "state_slug": "small",
                "state_or_ut": "Small",
                "cursor_after_index": -1,
            },
            proposal_identity={
                "import_batch_id": "batch-small",
                "source_sha256": "a" * 64,
            },
        )
    except ValueError as exc:
        checksum_rejected = (
            str(exc)
            == "V2_PREPARED_PLAN_IDENTITY_INVALID"
        )
    assert checksum_rejected

    execution_result = {
        "transaction_id":
            first_transaction_id,
        "state_slug": "small",
        "plan_checksum": plan_checksum,
        "rollback_token":
            first_rollback_token,
        "committed_row_count": 2,
        "status": "COMMITTED",
        "apply_status":
            "IDEMPOTENT_NO_OP",
    }

    recovered = advance_committed_transaction(
        checkpoint=staged,
        proposal=proposal,
        execution_result=execution_result,
    )

    assert recovered["status"] == "COMPLETE"
    assert recovered["completed_row_count"] == 2
    assert (
        recovered[
            "completed_transaction_count"
        ]
        == 1
    )
    validate_checkpoint(
        checkpoint=recovered,
        proposal=proposal,
    )

    with tempfile.TemporaryDirectory(
        prefix="throughput-v2-runner-"
    ) as temporary:
        checkpoint_path = (
            Path(temporary)
            / "checkpoint.json"
        )
        atomic_write_json(
            checkpoint_path,
            staged,
        )
        assert checkpoint_path.is_file()
        assert not checkpoint_path.with_suffix(
            ".json.writing"
        ).exists()

    print(
        "PASS deterministic transaction and "
        "rollback identities"
    )
    print(
        "PASS deterministic event identities "
        "support idempotent replay"
    )
    print("PASS tampered plan checksum is rejected")
    print(
        "PASS post-commit interruption can "
        "advance the staged checkpoint"
    )
    print("PASS checkpoint writes are atomic")
    print(
        "# VALIDATION METADATA THROUGHPUT "
        "V2 RUNNER REGRESSION PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

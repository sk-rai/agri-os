#!/usr/bin/env python3
"""Contract regression for throughput V2 campaigns."""

from __future__ import annotations

from copy import deepcopy

from boundary_validation_metadata_throughput_v2_campaign import (
    build_authorization,
    build_proposal,
    initial_checkpoint,
    required_confirmation,
    validate_authorization,
    validate_proposal,
)


def rejected(function, expected: str) -> None:
    try:
        function()
    except ValueError as exc:
        assert str(exc) == expected
        return
    raise AssertionError(
        f"Expected rejection: {expected}"
    )


def fixture_proposal():
    return build_proposal(
        campaign_id="throughput-v2-fixture",
        start_database_counts={
            "source_feature_rows": 100,
            "not_validated_rows": 60,
            "validated_rows": 40,
            "runtime_eligible_source_rows": 0,
        },
        states=[
            {
                "state_slug": "large",
                "state_or_ut": "Large",
                "import_batch_id": "batch-large",
                "source_sha256": "a" * 64,
                "not_validated_count": 50,
            },
            {
                "state_slug": "small",
                "state_or_ut": "Small",
                "import_batch_id": "batch-small",
                "source_sha256": "b" * 64,
                "not_validated_count": 10,
            },
        ],
    )


def main() -> int:
    proposal = fixture_proposal()
    checksum = proposal["campaign_checksum"]

    validate_proposal(proposal, checksum)

    assert [
        state["state_slug"]
        for state in proposal["states"]
    ] == ["small", "large"]
    assert (
        proposal["limits"][
            "maximum_campaign_row_count"
        ]
        == 60
    )
    assert (
        proposal["limits"][
            "default_rows_per_state_transaction"
        ]
        == 25_000
    )
    assert (
        proposal["limits"][
            "maximum_rows_per_state_transaction"
        ]
        == 50_000
    )
    assert (
        proposal["limits"]["default_writer_count"]
        == 1
    )

    tampered = deepcopy(proposal)
    tampered["states"][0][
        "start_not_validated_count"
    ] = 11
    rejected(
        lambda: validate_proposal(
            tampered,
            checksum,
        ),
        "V2_CAMPAIGN_CONTENT_CHECKSUM_MISMATCH",
    )

    unordered = deepcopy(proposal)
    unordered["states"].reverse()
    unordered["campaign_checksum"] = (
        __import__(
            "boundary_validation_metadata_throughput_v2_campaign"
        ).canonical_checksum(unordered)
    )
    rejected(
        lambda: validate_proposal(
            unordered,
            unordered["campaign_checksum"],
        ),
        "V2_CAMPAIGN_STATE_ORDER_INVALID",
    )

    confirmation = required_confirmation(proposal)
    authorization = build_authorization(
        proposal=proposal,
        expected_checksum=checksum,
        confirmation=confirmation,
        operator="fixture-operator",
        approver="fixture-approver",
        approval_reference="fixture-reference",
    )
    validate_authorization(
        authorization=authorization,
        proposal=proposal,
        expected_campaign_checksum=checksum,
    )

    wrong_confirmation = confirmation + " altered"
    rejected(
        lambda: build_authorization(
            proposal=proposal,
            expected_checksum=checksum,
            confirmation=wrong_confirmation,
            operator="fixture-operator",
            approver="fixture-approver",
            approval_reference="fixture-reference",
        ),
        "V2_CAMPAIGN_CONFIRMATION_MISMATCH",
    )

    unsafe = deepcopy(authorization)
    unsafe["permissions"][
        "runtime_table_write_allowed"
    ] = True
    unsafe["authorization_checksum"] = (
        __import__(
            "boundary_validation_metadata_throughput_v2_campaign"
        ).canonical_checksum(unsafe)
    )
    rejected(
        lambda: validate_authorization(
            authorization=unsafe,
            proposal=proposal,
            expected_campaign_checksum=checksum,
        ),
        "V2_CAMPAIGN_AUTHORIZATION_PROHIBITED",
    )

    checkpoint = initial_checkpoint(proposal)
    assert checkpoint["status"] == "READY"
    assert checkpoint["completed_row_count"] == 0
    assert [
        state["state_slug"]
        for state in checkpoint["states"]
    ] == ["small", "large"]

    print("PASS V2 campaign proposal is deterministic")
    print("PASS states are ordered from smallest to largest")
    print("PASS 25000 default and 50000 ceiling are pinned")
    print("PASS authorization requires exact confirmation")
    print("PASS prohibited permissions remain closed")
    print("PASS checkpoint starts empty and deterministic")
    print(
        "# VALIDATION METADATA THROUGHPUT V2 "
        "CAMPAIGN CONTRACT REGRESSION PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

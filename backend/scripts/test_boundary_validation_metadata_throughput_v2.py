#!/usr/bin/env python3
"""Static regression checks for the disconnected V2 throughput path."""

from boundary_validation_metadata_throughput_v2 import (
    DEFAULT_ROWS_PER_STATE_TRANSACTION,
    DEFAULT_WRITER_COUNT,
    MAXIMUM_ROWS_PER_STATE_TRANSACTION,
    MAXIMUM_WRITER_COUNT,
    ThroughputProfile,
    apply_statements,
    rollback_statements,
    validate_authorized_rows,
)


def rejected(
    profile: ThroughputProfile,
    expected: str,
) -> None:
    try:
        profile.validate()
    except ValueError as exc:
        assert str(exc) == expected
        return
    raise AssertionError(
        f"Expected rejection: {expected}"
    )


def main() -> int:
    assert DEFAULT_ROWS_PER_STATE_TRANSACTION == 25_000
    assert MAXIMUM_ROWS_PER_STATE_TRANSACTION == 50_000
    assert DEFAULT_WRITER_COUNT == 1
    assert MAXIMUM_WRITER_COUNT == 2

    ThroughputProfile().validate()
    ThroughputProfile(50_000, 2).validate()

    rejected(
        ThroughputProfile(0, 1),
        "V2_TRANSACTION_ROW_LIMIT_INVALID",
    )
    rejected(
        ThroughputProfile(50_001, 1),
        "V2_TRANSACTION_ROW_LIMIT_INVALID",
    )
    rejected(
        ThroughputProfile(25_000, 0),
        "V2_WRITER_COUNT_INVALID",
    )
    rejected(
        ThroughputProfile(25_000, 3),
        "V2_WRITER_COUNT_INVALID",
    )

    valid_rows = [
        {
            "event_id": "event-1",
            "source_feature_id": "source-1",
            "source_feature_index": 1,
        },
        {
            "event_id": "event-2",
            "source_feature_id": "source-2",
            "source_feature_index": 2,
        },
    ]
    validate_authorized_rows(valid_rows, 2)

    try:
        validate_authorized_rows(valid_rows, 3)
    except ValueError as exc:
        assert str(exc) == (
            "V2_AUTHORIZED_ROW_COUNT_MISMATCH"
        )
    else:
        raise AssertionError(
            "Mismatched authorized count was accepted"
        )

    duplicate_rows = [
        valid_rows[0],
        {
            "event_id": "event-2",
            "source_feature_id": "source-1",
            "source_feature_index": 2,
        },
    ]
    try:
        validate_authorized_rows(
            duplicate_rows,
            2,
        )
    except ValueError as exc:
        assert str(exc) == (
            "V2_ROW_IDENTITY_NOT_UNIQUE:"
            "source_feature_id"
        )
    else:
        raise AssertionError(
            "Duplicate source identity was accepted"
        )

    apply_sql = "\n".join(
        apply_statements()
    ).lower()
    rollback_sql = "\n".join(
        rollback_statements()
    ).lower()

    assert "jsonb_to_recordset" in apply_sql
    assert "for update of source" in apply_sql
    assert "returning source.id" in apply_sql
    assert (
        "eligible_for_runtime_after_promotion ="
        in apply_sql
    )
    assert (
        "geography_boundary_crosswalk_candidates"
        not in apply_sql
    )
    assert "geography_boundary_runtime_" not in apply_sql

    assert (
        "apply_status = 'rolled_back'"
        in rollback_sql
    )
    assert "returning source.id" in rollback_sql

    print(
        "PASS V2 throughput envelope is bounded"
    )
    print(
        "PASS V2 apply and rollback are set-based"
    )
    print(
        "PASS V2 authorization count and identity checks"
    )
    print(
        "PASS runtime and candidate tables remain disconnected"
    )
    print(
        "# VALIDATION METADATA THROUGHPUT V2 "
        "REGRESSION PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

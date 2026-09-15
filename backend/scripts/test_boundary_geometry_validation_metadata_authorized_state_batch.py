#!/usr/bin/env python3
"""Regression for generic state-batch authorization validation."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from scripts import (  # noqa: E402
    apply_boundary_geometry_validation_metadata_authorized_state_batch
    as engine,
)


def check(condition: bool, label: str, detail=None) -> None:
    if not condition:
        print(f"FAIL {label}")
        if detail is not None:
            print(json.dumps(detail, indent=2, default=str))
        raise AssertionError(label)
    print(f"PASS {label}")


def authorization() -> dict:
    value = {
        "schema_version": (
            "boundary_geometry_validation_metadata_"
            "state_batch_authorization.v1"
        ),
        "status": "AUTHORIZED",
        "national_plan_checksum": "1" * 64,
        "state": {
            "state_slug": "fixture_state",
            "state_or_ut": "Fixture State",
            "import_batch_id":
                "00000000-0000-0000-0000-000000000001",
            "source_sha256": "2" * 64,
            "batch_id":
                "00000000-0000-0000-0000-000000000002",
            "plan_checksum": "3" * 64,
            "selected_row_count": 2,
            "first_source_feature_index": 10,
            "last_source_feature_index": 11,
            "rollback_token":
                "fixture-validation-metadata-batch-1",
        },
        "approval": {
            "operator": "fixture-operator",
            "approver": "fixture-approver",
            "approval_reference": "fixture-approval-reference",
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
    value["authorization_checksum"] = (
        engine.authorization_checksum(value)
    )
    return value


def rejected(
    value: dict,
    expected: str,
    *,
    rollback: bool = False,
) -> None:
    try:
        engine.configure_authorization(
            value,
            rollback=rollback,
        )
    except ValueError as exc:
        check(
            str(exc) == expected,
            f"Authorization rejects {expected}",
            {"actual": str(exc), "expected": expected},
        )
        return
    raise AssertionError(f"Expected rejection: {expected}")


def main() -> int:
    valid = authorization()

    check(
        len(valid["authorization_checksum"]) == 64,
        "Authorization exposes deterministic SHA-256 checksum",
    )
    check(
        engine.authorization_checksum(valid) ==
            valid["authorization_checksum"],
        "Authorization checksum is stable",
    )

    wrong_schema = copy.deepcopy(valid)
    wrong_schema["schema_version"] = "wrong.v1"
    rejected(wrong_schema, "AUTHORIZATION_SCHEMA_MISMATCH")

    proposed = copy.deepcopy(valid)
    proposed["status"] = "PROPOSED_NOT_AUTHORIZED"
    rejected(proposed, "STATE_BATCH_NOT_AUTHORIZED")

    tampered = copy.deepcopy(valid)
    tampered["state"]["selected_row_count"] = 3
    rejected(tampered, "AUTHORIZATION_CHECKSUM_MISMATCH")

    missing_approval = copy.deepcopy(valid)
    missing_approval["approval"]["approver"] = ""
    missing_approval["authorization_checksum"] = (
        engine.authorization_checksum(missing_approval)
    )
    rejected(
        missing_approval,
        "AUTHORIZATION_APPROVAL_INCOMPLETE",
    )

    no_apply = copy.deepcopy(valid)
    no_apply["permissions"]["apply_authorized"] = False
    no_apply["authorization_checksum"] = (
        engine.authorization_checksum(no_apply)
    )
    rejected(no_apply, "APPLY_NOT_AUTHORIZED")

    no_rollback = copy.deepcopy(valid)
    no_rollback["permissions"]["rollback_authorized"] = False
    no_rollback["authorization_checksum"] = (
        engine.authorization_checksum(no_rollback)
    )
    rejected(
        no_rollback,
        "ROLLBACK_NOT_AUTHORIZED",
        rollback=True,
    )

    oversized = copy.deepcopy(valid)
    oversized["permissions"]["maximum_row_count"] = 501
    oversized["authorization_checksum"] = (
        engine.authorization_checksum(oversized)
    )
    rejected(oversized, "AUTHORIZATION_ROW_LIMIT_INVALID")

    excessive_selection = copy.deepcopy(valid)
    excessive_selection["state"]["selected_row_count"] = 501
    excessive_selection["authorization_checksum"] = (
        engine.authorization_checksum(excessive_selection)
    )
    rejected(
        excessive_selection,
        "AUTHORIZATION_ROW_LIMIT_INVALID",
    )

    unsafe_classification = copy.deepcopy(valid)
    unsafe_classification["permissions"][
        "validated_without_repair_only"
    ] = False
    unsafe_classification["authorization_checksum"] = (
        engine.authorization_checksum(unsafe_classification)
    )
    rejected(
        unsafe_classification,
        "SAFE_CLASSIFICATION_POLICY_REQUIRED",
    )

    for key in [
        "geometry_repair_allowed",
        "runtime_eligibility_change_allowed",
        "candidate_write_allowed",
        "runtime_table_write_allowed",
        "runtime_lookup_enablement_allowed",
        "android_behavior_change_allowed",
    ]:
        prohibited = copy.deepcopy(valid)
        prohibited["permissions"][key] = True
        prohibited["authorization_checksum"] = (
            engine.authorization_checksum(prohibited)
        )
        rejected(
            prohibited,
            "PROHIBITED_PERMISSION_ENABLED",
        )

    engine.configure_authorization(valid, rollback=False)
    engine.validate_invocation_checksums(
        valid["authorization_checksum"],
        valid["national_plan_checksum"],
    )
    check(
        True,
        "Matching external invocation checksums are accepted",
    )

    try:
        engine.validate_invocation_checksums(
            "0" * 64,
            valid["national_plan_checksum"],
        )
    except ValueError as exc:
        check(
            str(exc) ==
                "EXPECTED_AUTHORIZATION_CHECKSUM_MISMATCH",
            "Wrong external authorization checksum is rejected",
        )
    else:
        raise AssertionError(
            "Wrong external authorization checksum was accepted"
        )

    try:
        engine.validate_invocation_checksums(
            valid["authorization_checksum"],
            "0" * 64,
        )
    except ValueError as exc:
        check(
            str(exc) ==
                "EXPECTED_NATIONAL_PLAN_CHECKSUM_MISMATCH",
            "Wrong external national checksum is rejected",
        )
    else:
        raise AssertionError(
            "Wrong external national checksum was accepted"
        )

    check(
        engine.STATE_SLUG == "fixture_state"
        and engine.STATE_NAME == "Fixture State"
        and engine.IMPORT_BATCH_ID ==
            "00000000-0000-0000-0000-000000000001"
        and engine.SOURCE_SHA256 == "2" * 64
        and engine.PLAN_CHECKSUM == "3" * 64
        and engine.NATIONAL_PLAN_CHECKSUM == "1" * 64
        and engine.APPROVED_ROW_COUNT == 2
        and engine.APPROVED_FIRST_INDEX == 10
        and engine.APPROVED_LAST_INDEX == 11
        and engine.APPROVED_OPERATOR == "fixture-operator"
        and engine.APPROVED_APPROVER == "fixture-approver"
        and engine.APPROVED_ROLLBACK_TOKEN ==
            "fixture-validation-metadata-batch-1",
        "Valid authorization configures generic state identity",
    )

    check(
        "andaman" not in Path(
            engine.__file__
        ).read_text(encoding="utf-8").lower(),
        "Generic engine contains no embedded Andaman identity",
    )

    print("=" * 72)
    print(
        "AUTHORIZED STATE-BATCH VALIDATION METADATA "
        "CONTRACT REGRESSION PASSED"
    )
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

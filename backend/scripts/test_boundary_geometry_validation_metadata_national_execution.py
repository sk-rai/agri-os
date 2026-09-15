#!/usr/bin/env python3
"""Regression for fail-closed national metadata execution authorization."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from scripts import (  # noqa: E402
    run_boundary_geometry_validation_metadata_national_execution
    as orchestrator,
)


def check(condition: bool, label: str, detail=None) -> None:
    if not condition:
        print(f"FAIL {label}")
        if detail is not None:
            print(json.dumps(detail, indent=2, default=str))
        raise AssertionError(label)
    print(f"PASS {label}")


def states(authorized: bool = False) -> list[dict]:
    return [
        {
            "sequence": sequence,
            "state_or_ut": f"Fixture State {sequence:02d}",
            "state_slug": f"fixture_state_{sequence:02d}",
            "import_batch_id":
                f"00000000-0000-0000-0000-{sequence:012d}",
            "source_sha256": f"{sequence:064x}",
            "batch_id":
                f"10000000-0000-0000-0000-{sequence:012d}",
            "plan_checksum": f"{sequence + 100:064x}",
            "selected_row_count": 1,
            "first_source_feature_index": sequence - 1,
            "last_source_feature_index": sequence - 1,
            "rollback_token":
                f"fixture-state-{sequence:02d}-rollback",
            "plan_json":
                f"/fixture/state-{sequence:02d}/plan.json",
            "checkpoint_json":
                f"/fixture/state-{sequence:02d}/checkpoint.json",
            "apply_authorized": authorized,
            "rollback_authorized": authorized,
        }
        for sequence in range(1, 37)
    ]


def safe_policy() -> dict:
    return {
        "stop_on_first_failure": True,
        "maximum_rows_per_transaction": 500,
        "one_state_batch_per_transaction": True,
        "exact_plan_checksum_required": True,
        "exact_source_checksum_required": True,
        "exact_import_batch_required": True,
        "exact_rollback_token_required": True,
        "validated_without_repair_only": True,
        "geometry_repair_allowed": False,
        "runtime_eligibility_change_allowed": False,
        "candidate_activation_allowed": False,
        "candidate_promotion_allowed": False,
        "runtime_table_write_allowed": False,
        "runtime_lookup_enablement_allowed": False,
        "android_behavior_change_allowed": False,
    }


def proposal() -> dict:
    value = {
        "schema_version": orchestrator.PROPOSAL_SCHEMA,
        "status": "PROPOSED_NOT_AUTHORIZED",
        "national_plan_checksum": "a" * 64,
        "batch_limit": 500,
        "evidence": {
            "national_plan_healthy": True,
            "integrity_audit_healthy": True,
            "disabled_apply_guard_healthy": True,
        },
        "authorization": {
            "apply_authorized": False,
            "rollback_authorized": False,
            "operator": None,
            "approver": None,
            "approval_reference": None,
            "approved_at": None,
        },
        "execution_policy": safe_policy(),
        "states": states(False),
        "readiness": {
            "ready_for_national_apply": False,
            "ready_for_runtime_promotion": False,
            "ready_for_android_behavior_change": False,
        },
    }
    value["manifest_checksum"] = (
        orchestrator.manifest_checksum(value)
    )
    return value


def authorized() -> dict:
    value = proposal()
    value["schema_version"] = orchestrator.AUTHORIZED_SCHEMA
    value["status"] = "AUTHORIZED"
    value["authorization"] = {
        "apply_authorized": True,
        "rollback_authorized": True,
        "operator": "fixture-operator",
        "approver": "fixture-approver",
        "approval_reference": "fixture-approval",
        "approved_at": "2026-09-15T00:00:00+00:00",
    }
    value["states"] = states(True)
    value["readiness"]["ready_for_national_apply"] = True
    value["manifest_checksum"] = (
        orchestrator.manifest_checksum(value)
    )
    return value


def args_for(value: dict, **changes) -> Namespace:
    values = {
        "apply": True,
        "rollback": False,
        "manifest_checksum": value["manifest_checksum"],
        "national_plan_checksum":
            value["national_plan_checksum"],
        "enable_national_validation_metadata_write": True,
        "plan_reviewed": True,
        "integrity_audit_reviewed": True,
        "rollback_procedure_reviewed": True,
        "admin_confirmation": True,
    }
    values.update(changes)
    return Namespace(**values)


def expect(
    value: dict,
    expected: str,
    **changes,
) -> None:
    actual = orchestrator.authorization_error(
        args_for(value, **changes),
        value,
    )
    check(
        actual == expected,
        f"Orchestrator rejects {expected}",
        {"actual": actual, "expected": expected},
    )


def main() -> int:
    proposed = proposal()

    check(
        orchestrator.structural_error(
            args_for(proposed),
            proposed,
        ) is None,
        "Proposed manifest is structurally valid",
    )
    expect(
        proposed,
        "NATIONAL_EXECUTION_NOT_AUTHORIZED",
    )

    tampered_status = copy.deepcopy(proposed)
    tampered_status["status"] = "AUTHORIZED"
    expect(
        tampered_status,
        "MANIFEST_CONTENT_CHECKSUM_MISMATCH",
    )

    tampered_authorization = copy.deepcopy(proposed)
    tampered_authorization["authorization"][
        "apply_authorized"
    ] = True
    expect(
        tampered_authorization,
        "MANIFEST_CONTENT_CHECKSUM_MISMATCH",
    )

    expect(
        proposed,
        "EXPECTED_MANIFEST_CHECKSUM_MISMATCH",
        manifest_checksum="0" * 64,
    )
    expect(
        proposed,
        "EXPECTED_NATIONAL_PLAN_CHECKSUM_MISMATCH",
        national_plan_checksum="0" * 64,
    )
    expect(
        proposed,
        "EXACTLY_ONE_OF_APPLY_OR_ROLLBACK_REQUIRED",
        apply=False,
        rollback=False,
    )

    approved = authorized()
    check(
        orchestrator.structural_error(
            args_for(approved),
            approved,
        ) is None,
        "Authorized fixture manifest is structurally valid",
    )
    expect(
        approved,
        "NATIONAL_EXECUTION_ENGINE_NOT_ENABLED",
    )

    derived = [
        orchestrator.state_authorization_document(
            approved,
            state,
        )
        for state in approved["states"]
    ]
    check(
        len(derived) == 36
        and len({
            item["authorization_checksum"]
            for item in derived
        }) == 36,
        "Orchestrator derives 36 unique state authorizations",
    )
    check(
        all(
            item["schema_version"] ==
                orchestrator.state_engine.AUTHORIZATION_SCHEMA
            and item["status"] == "AUTHORIZED"
            and item["national_plan_checksum"] ==
                approved["national_plan_checksum"]
            and item["permissions"]["apply_authorized"]
                is True
            and item["permissions"]["rollback_authorized"]
                is True
            and orchestrator.state_engine.authorization_checksum(
                item
            ) == item["authorization_checksum"]
            for item in derived
        ),
        "Derived state authorizations satisfy engine contract",
        derived,
    )

    altered = copy.deepcopy(derived[0])
    altered["state"]["selected_row_count"] = 2
    check(
        orchestrator.state_engine.authorization_checksum(
            altered
        ) != altered["authorization_checksum"],
        "Derived authorization detects state-batch tampering",
    )

    with tempfile.TemporaryDirectory(
        prefix="national-execution-artifact-"
    ) as temporary:
        fixture_dir = Path(temporary)
        source_path = fixture_dir / "fixture_state.geojson"
        source_path.write_bytes(b"fixture-source")
        source_sha256 = orchestrator.sha256_file(source_path)

        row = {
            "sequence": 1,
            "source_feature_id":
                "20000000-0000-0000-0000-000000000001",
            "source_feature_index": 0,
            "source_vlcode": "000001",
            "current_geometry_validation_status":
                "NOT_VALIDATED",
            "planned_geometry_validation_status":
                "VALIDATED",
            "classification": "VALIDATED_NO_REPAIR",
            "source_geometry_hash": "b" * 64,
            "source_bbox": [0, 0, 1, 1],
            "transformed_bbox": [0, 0, 1, 1],
            "transformed_centroid": {
                "type": "Point",
                "coordinates": [0.5, 0.5],
            },
            "runtime_eligibility_change_planned": False,
        }
        import_batch_id = (
            "30000000-0000-0000-0000-000000000001"
        )
        batch_id = (
            "40000000-0000-0000-0000-000000000001"
        )
        plan = {
            "schema_version": (
                "boundary_geometry_validation_metadata_"
                "bounded_state_plan.v1"
            ),
            "healthy": True,
            "scope": {
                "state_slug": "fixture_state",
                "state_or_ut": "Fixture State",
                "import_batch_id": import_batch_id,
                "cursor_after_index": -1,
                "limit": 500,
            },
            "source": {
                "path": str(source_path),
                "sha256": source_sha256,
                "feature_count": 1,
                "geometry_hash_algorithm":
                    "NWDP_GEOJSON_GEOMETRY_CANONICAL_V1",
            },
            "batch": {
                "batch_id": batch_id,
                "plan_checksum": "",
                "selected_row_count": 1,
                "first_source_feature_index": 0,
                "last_source_feature_index": 0,
            },
            "rows": [row],
            "database_counts": {
                "before": {},
                "after": {},
                "unchanged": True,
            },
        }
        plan["batch"]["plan_checksum"] = (
            orchestrator.state_engine.recompute_plan_checksum(
                plan
            )
        )

        plan_path = fixture_dir / "plan.json"
        checkpoint_path = fixture_dir / "checkpoint.json"
        plan_path.write_text(
            json.dumps(plan, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        checkpoint = {
            "schema_version": (
                "boundary_geometry_validation_metadata_"
                "national_state_checkpoint.v1"
            ),
            "identity": {
                "state_slug": "fixture_state",
                "state_or_ut": "Fixture State",
                "import_batch_id": import_batch_id,
                "source_sha256": source_sha256,
                "source_feature_count": 1,
                "database_not_validated_count": 1,
                "database_validated_count": 0,
                "batch_limit": 500,
            },
            "batch_id": batch_id,
            "plan_checksum":
                plan["batch"]["plan_checksum"],
        }
        checkpoint_path.write_text(
            json.dumps(
                checkpoint,
                indent=2,
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )

        state = {
            "state_slug": "fixture_state",
            "state_or_ut": "Fixture State",
            "import_batch_id": import_batch_id,
            "source_sha256": source_sha256,
            "source_feature_count": 1,
            "database_not_validated_count": 1,
            "database_validated_count": 0,
            "batch_id": batch_id,
            "plan_checksum":
                plan["batch"]["plan_checksum"],
            "selected_row_count": 1,
            "first_source_feature_index": 0,
            "last_source_feature_index": 0,
            "rollback_token": "fixture-rollback-token",
            "plan_json": str(plan_path),
            "checkpoint_json": str(checkpoint_path),
            "apply_authorized": True,
            "rollback_authorized": True,
        }

        check(
            orchestrator.state_artifact_error(state) is None,
            "Valid state plan and checkpoint artifacts are accepted",
        )

        incomplete = copy.deepcopy(state)
        del incomplete["source_feature_count"]
        check(
            "MANIFEST_STATE_ARTIFACT_IDENTITY_INCOMPLETE"
            in (
                orchestrator.state_artifact_error(incomplete)
                or ""
            ),
            "Missing manifest artifact identity is rejected",
        )

        tampered_plan = copy.deepcopy(plan)
        tampered_plan["rows"][0][
            "current_geometry_validation_status"
        ] = "VALIDATED"
        plan_path.write_text(
            json.dumps(
                tampered_plan,
                indent=2,
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )
        check(
            "STATE_PLAN_CONTENT_CHECKSUM_MISMATCH"
            in (
                orchestrator.state_artifact_error(state)
                or ""
            ),
            "Tampered state plan is rejected",
        )

        plan_path.write_text(
            json.dumps(plan, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        source_path.write_bytes(b"changed-fixture-source")
        check(
            "CURRENT_SOURCE_CHECKSUM_MISMATCH"
            in (
                orchestrator.state_artifact_error(state)
                or ""
            ),
            "Changed source file is rejected immediately",
        )

    missing_global_apply = copy.deepcopy(approved)
    missing_global_apply["authorization"][
        "apply_authorized"
    ] = False
    missing_global_apply["manifest_checksum"] = (
        orchestrator.manifest_checksum(
            missing_global_apply
        )
    )
    expect(
        missing_global_apply,
        "NATIONAL_APPLY_NOT_AUTHORIZED",
    )

    missing_state_apply = copy.deepcopy(approved)
    missing_state_apply["states"][5][
        "apply_authorized"
    ] = False
    missing_state_apply["manifest_checksum"] = (
        orchestrator.manifest_checksum(
            missing_state_apply
        )
    )
    expect(
        missing_state_apply,
        "STATE_BATCH_APPLY_NOT_AUTHORIZED",
    )

    unsafe_policy = copy.deepcopy(approved)
    unsafe_policy["execution_policy"][
        "runtime_lookup_enablement_allowed"
    ] = True
    unsafe_policy["manifest_checksum"] = (
        orchestrator.manifest_checksum(unsafe_policy)
    )
    expect(
        unsafe_policy,
        "PROHIBITED_NATIONAL_EXECUTION_POLICY_ENABLED",
    )

    incomplete_policy = copy.deepcopy(approved)
    incomplete_policy["execution_policy"][
        "stop_on_first_failure"
    ] = False
    incomplete_policy["manifest_checksum"] = (
        orchestrator.manifest_checksum(
            incomplete_policy
        )
    )
    expect(
        incomplete_policy,
        "NATIONAL_EXECUTION_POLICY_INCOMPLETE",
    )

    expect(
        approved,
        "NATIONAL_METADATA_WRITE_FLAG_REQUIRED",
        enable_national_validation_metadata_write=False,
    )
    expect(
        approved,
        "NATIONAL_PLAN_REVIEW_REQUIRED",
        plan_reviewed=False,
    )
    expect(
        approved,
        "NATIONAL_INTEGRITY_AUDIT_REVIEW_REQUIRED",
        integrity_audit_reviewed=False,
    )
    expect(
        approved,
        "ROLLBACK_PROCEDURE_REVIEW_REQUIRED",
        rollback_procedure_reviewed=False,
    )
    expect(
        approved,
        "ADMIN_CONFIRMATION_REQUIRED",
        admin_confirmation=False,
    )

    rollback = args_for(
        approved,
        apply=False,
        rollback=True,
    )
    check(
        orchestrator.authorization_error(
            rollback,
            approved,
        ) == "NATIONAL_EXECUTION_ENGINE_NOT_ENABLED",
        "Authorized rollback reaches final disabled gate",
    )

    print("=" * 72)
    print(
        "NATIONAL VALIDATION METADATA EXECUTION "
        "AUTHORIZATION REGRESSION PASSED"
    )
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

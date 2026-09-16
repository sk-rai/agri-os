#!/usr/bin/env python3
"""Regression for national execution manifest authorization."""

from __future__ import annotations

import copy
import json
import sys
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

import importlib

authorizer = importlib.import_module(
    "scripts.authorize_boundary_geometry_validation_metadata_"
    "national_execution_manifest"
)
orchestrator = importlib.import_module(
    "scripts.run_boundary_geometry_validation_metadata_"
    "national_execution"
)

def check(condition: bool, label: str, detail=None) -> None:
    if not condition:
        print(f"FAIL {label}")
        if detail is not None:
            print(json.dumps(detail, indent=2, default=str))
        raise AssertionError(label)
    print(f"PASS {label}")


def fixture_states() -> list[dict]:
    return [
        {
            "sequence": sequence,
            "state_or_ut": f"Fixture State {sequence:02d}",
            "state_slug": f"fixture_state_{sequence:02d}",
            "import_batch_id":
                f"00000000-0000-0000-0000-{sequence:012d}",
            "source_sha256": f"{sequence:064x}",
            "source_feature_count": 1,
            "database_not_validated_count": 1,
            "database_validated_count": 0,
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
            "apply_authorized": False,
            "rollback_authorized": False,
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
        "states": fixture_states(),
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


def execution_args(
    manifest: dict,
    *,
    rollback: bool,
) -> Namespace:
    return Namespace(
        apply=not rollback,
        rollback=rollback,
        manifest_checksum=manifest["manifest_checksum"],
        national_plan_checksum=
            manifest["national_plan_checksum"],
        enable_national_validation_metadata_write=True,
        plan_reviewed=True,
        integrity_audit_reviewed=True,
        rollback_procedure_reviewed=True,
        admin_confirmation=True,
    )


def main() -> int:
    source = proposal()

    check(
        authorizer.proposal_error(
            source,
            proposal_manifest_checksum=
                source["manifest_checksum"],
            national_plan_checksum=
                source["national_plan_checksum"],
        ) is None,
        "Valid proposal is accepted for separate authorization",
    )

    reduced_source = copy.deepcopy(source)
    reduced_source["states"] = reduced_source["states"][:2]
    reduced_source["manifest_checksum"] = (
        orchestrator.manifest_checksum(reduced_source)
    )
    check(
        authorizer.proposal_error(
            reduced_source,
            proposal_manifest_checksum=
                reduced_source["manifest_checksum"],
            national_plan_checksum=
                reduced_source["national_plan_checksum"],
        ) is None,
        "Reduced-state proposal is accepted",
    )

    apply_one = authorizer.authorize_manifest(
        source,
        mode="APPLY",
        operator="fixture-operator",
        approver="fixture-approver",
        approval_reference="fixture-apply-approval",
        approved_at="2026-09-15T00:00:00+00:00",
    )
    apply_two = authorizer.authorize_manifest(
        source,
        mode="APPLY",
        operator="fixture-operator",
        approver="fixture-approver",
        approval_reference="fixture-apply-approval",
        approved_at="2026-09-15T00:00:00+00:00",
    )
    check(
        apply_one["manifest_checksum"] ==
            apply_two["manifest_checksum"]
        and orchestrator.manifest_checksum(apply_one) ==
            apply_one["manifest_checksum"],
        "Apply authorization checksum is deterministic",
    )
    check(
        apply_one["authorization"]["apply_authorized"]
            is True
        and apply_one["authorization"][
            "rollback_authorized"
        ] is False
        and all(
            state["apply_authorized"] is True
            and state["rollback_authorized"] is False
            for state in apply_one["states"]
        ),
        "Apply authorization grants only apply permission",
    )
    check(
        orchestrator.authorization_error(
            execution_args(apply_one, rollback=False),
            apply_one,
        ) is None,
        "Apply manifest satisfies national execution gate",
    )
    check(
        orchestrator.authorization_error(
            execution_args(apply_one, rollback=True),
            apply_one,
        ) == "NATIONAL_ROLLBACK_NOT_AUTHORIZED",
        "Apply manifest cannot authorize rollback",
    )

    rollback = authorizer.authorize_manifest(
        source,
        mode="ROLLBACK",
        operator="fixture-operator",
        approver="fixture-approver",
        approval_reference="fixture-rollback-approval",
        approved_at="2026-09-15T00:00:00+00:00",
    )
    check(
        rollback["authorization"]["apply_authorized"]
            is False
        and rollback["authorization"][
            "rollback_authorized"
        ] is True
        and all(
            state["apply_authorized"] is False
            and state["rollback_authorized"] is True
            for state in rollback["states"]
        ),
        "Rollback authorization grants only rollback permission",
    )
    check(
        orchestrator.authorization_error(
            execution_args(rollback, rollback=True),
            rollback,
        ) is None,
        "Rollback manifest satisfies national execution gate",
    )
    check(
        orchestrator.authorization_error(
            execution_args(rollback, rollback=False),
            rollback,
        ) == "NATIONAL_APPLY_NOT_AUTHORIZED",
        "Rollback manifest cannot authorize apply",
    )

    tampered = copy.deepcopy(source)
    tampered["states"][0]["selected_row_count"] = 2
    check(
        authorizer.proposal_error(
            tampered,
            proposal_manifest_checksum=
                source["manifest_checksum"],
            national_plan_checksum=
                source["national_plan_checksum"],
        ) == "PROPOSAL_CONTENT_CHECKSUM_MISMATCH",
        "Modified proposal content is rejected",
    )

    wrong_checksum = authorizer.proposal_error(
        source,
        proposal_manifest_checksum="0" * 64,
        national_plan_checksum=
            source["national_plan_checksum"],
    )
    check(
        wrong_checksum == "EXPECTED_PROPOSAL_CHECKSUM_MISMATCH",
        "Wrong external proposal checksum is rejected",
    )

    wrong_national = authorizer.proposal_error(
        source,
        proposal_manifest_checksum=
            source["manifest_checksum"],
        national_plan_checksum="0" * 64,
    )
    check(
        wrong_national ==
            "EXPECTED_NATIONAL_PLAN_CHECKSUM_MISMATCH",
        "Wrong external national checksum is rejected",
    )

    already_authorized = copy.deepcopy(source)
    already_authorized["authorization"][
        "apply_authorized"
    ] = True
    already_authorized["manifest_checksum"] = (
        orchestrator.manifest_checksum(already_authorized)
    )
    check(
        authorizer.proposal_error(
            already_authorized,
            proposal_manifest_checksum=
                already_authorized["manifest_checksum"],
            national_plan_checksum=
                already_authorized[
                    "national_plan_checksum"
                ],
        ) == "PROPOSAL_ALREADY_AUTHORIZES_EXECUTION",
        "Proposal carrying execution permission is rejected",
    )

    print("=" * 67)
    print()
    print(
        "# NATIONAL EXECUTION MANIFEST AUTHORIZATION "
        "REGRESSION PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

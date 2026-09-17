#!/usr/bin/env python3
"""Regression for the bounded validation-metadata campaign controller."""

from __future__ import annotations

import copy
import importlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

campaign = importlib.import_module(
    "scripts.run_boundary_geometry_validation_metadata_campaign"
)


def check(condition: bool, label: str, detail=None) -> None:
    if not condition:
        print(f"FAIL {label}")
        if detail is not None:
            print(json.dumps(detail, indent=2, default=str))
        raise AssertionError(label)
    print(f"PASS {label}")


def expect_error(value: dict, expected: str) -> None:
    try:
        campaign.validate_proposal(
            value,
            value.get("campaign_checksum") or "",
        )
    except ValueError as exc:
        check(
            expected in str(exc),
            f"Campaign rejects {expected}",
            str(exc),
        )
        return
    raise AssertionError(f"Expected {expected}")


def proposal() -> dict:
    value = {
        "schema_version": campaign.CAMPAIGN_SCHEMA,
        "status": "PROPOSED_NOT_AUTHORIZED",
        "campaign_id": "fixture-campaign",
        "generated_at": "2026-09-16T00:00:00+00:00",
        "start_database_counts": {
            "source_feature_rows": 654285,
            "not_validated_rows": 625171,
            "validated_rows": 29114,
        },
        "remaining_eligible_row_count": 625171,
        "limits": {
            "maximum_wave_count": campaign.MAXIMUM_WAVE_COUNT,
            "maximum_campaign_row_count":
                campaign.MAXIMUM_CAMPAIGN_ROW_COUNT,
            "maximum_rows_per_state_transaction":
                campaign.MAXIMUM_ROWS_PER_STATE_TRANSACTION,
            "maximum_states_per_wave": 36,
            "maximum_parallel_state_transactions": 1,
        },
        "execution_policy": {
            "stop_on_first_failure": True,
            "reconcile_after_every_wave": True,
            "next_wave_requires_previous_reconciliation": True,
            "one_state_batch_per_transaction": True,
        },
        "prohibited_changes": {
            "geometry_repair_allowed": False,
            "runtime_eligibility_change_allowed": False,
            "candidate_activation_allowed": False,
            "candidate_promotion_allowed": False,
            "runtime_table_write_allowed": False,
            "runtime_lookup_enablement_allowed": False,
            "lgd_geography_overwrite_allowed": False,
            "android_behavior_change_allowed": False,
        },
        "authorization": {
            "campaign_execution_authorized": False,
            "operator": None,
            "approver": None,
            "approval_reference": None,
            "approved_at": None,
        },
        "readiness": {
            "ready_for_campaign_review": True,
            "ready_for_campaign_execution": False,
            "database_writes_attempted": False,
            "execution_started": False,
        },
        "wave_template": {
            "planner_batch_limit": 500,
            "planner_workers": 4,
        },
    }
    value["campaign_checksum"] = (
        campaign.canonical_checksum(value)
    )
    return value


def main() -> int:
    source = proposal()

    campaign.validate_proposal(
        source,
        source["campaign_checksum"],
    )
    check(
        True,
        "Valid bounded campaign proposal is accepted",
    )

    initial = campaign.initial_checkpoint(source)
    check(
        initial["status"] == "READY"
        and initial["completed_wave_count"] == 0
        and initial["completed_row_count"] == 0
        and initial["waves"] == [],
        "Initial campaign checkpoint is empty and deterministic",
    )

    altered = copy.deepcopy(source)
    altered["limits"]["maximum_wave_count"] = 17
    expect_error(altered, "CAMPAIGN_CONTENT_CHECKSUM_MISMATCH")

    oversized = copy.deepcopy(source)
    oversized["limits"]["maximum_campaign_row_count"] = 175001
    oversized["campaign_checksum"] = (
        campaign.canonical_checksum(oversized)
    )
    expect_error(oversized, "CAMPAIGN_LIMITS_INVALID")

    transaction = copy.deepcopy(source)
    transaction["limits"][
        "maximum_rows_per_state_transaction"
    ] = 501
    transaction["campaign_checksum"] = (
        campaign.canonical_checksum(transaction)
    )
    expect_error(transaction, "CAMPAIGN_LIMITS_INVALID")

    parallel = copy.deepcopy(source)
    parallel["limits"][
        "maximum_parallel_state_transactions"
    ] = 2
    parallel["campaign_checksum"] = (
        campaign.canonical_checksum(parallel)
    )
    expect_error(parallel, "CAMPAIGN_LIMITS_INVALID")

    unsafe = copy.deepcopy(source)
    unsafe["prohibited_changes"][
        "runtime_lookup_enablement_allowed"
    ] = True
    unsafe["campaign_checksum"] = (
        campaign.canonical_checksum(unsafe)
    )
    expect_error(
        unsafe,
        "CAMPAIGN_PROHIBITED_PERMISSION_ENABLED",
    )

    authorized = copy.deepcopy(source)
    authorized["authorization"][
        "campaign_execution_authorized"
    ] = True
    authorized["campaign_checksum"] = (
        campaign.canonical_checksum(authorized)
    )
    expect_error(
        authorized,
        "CAMPAIGN_PROPOSAL_MUST_NOT_AUTHORIZE",
    )

    campaign_authorization = copy.deepcopy(source)
    campaign_authorization["schema_version"] = (
        "national_validation_metadata_"
        "campaign_authorization.v1"
    )
    campaign_authorization["status"] = "AUTHORIZED"
    campaign_authorization[
        "proposal_campaign_checksum"
    ] = source["campaign_checksum"]
    campaign_authorization.pop("campaign_checksum", None)
    campaign_authorization["authorization"] = {
        "campaign_execution_authorized": True,
        "operator": "admin-regression",
        "approver": "admin-regression",
        "approval_reference": "fixture-campaign-approval",
        "approved_at": "2026-09-17T00:00:00+00:00",
        "confirmation": (
            "Authorize fixture campaign for bounded execution"
        ),
    }
    campaign_authorization["authorization_checksum"] = (
        campaign.campaign_authorization_checksum(
            campaign_authorization
        )
    )

    campaign.validate_campaign_authorization(
        source,
        campaign_authorization,
    )
    check(
        True,
        "Valid campaign authorization is accepted",
    )

    tampered_authorization = copy.deepcopy(
        campaign_authorization
    )
    tampered_authorization["limits"][
        "maximum_campaign_row_count"
    ] = 150001
    try:
        campaign.validate_campaign_authorization(
            source,
            tampered_authorization,
        )
    except ValueError as exc:
        check(
            "CAMPAIGN_AUTHORIZATION_CHECKSUM_MISMATCH"
            in str(exc),
            "Tampered campaign authorization is rejected",
            str(exc),
        )
    else:
        raise AssertionError(
            "Tampered campaign authorization was accepted"
        )

    wrong_identity = copy.deepcopy(
        campaign_authorization
    )
    wrong_identity["authorization"]["operator"] = (
        "unexpected-operator"
    )
    wrong_identity["authorization_checksum"] = (
        campaign.campaign_authorization_checksum(
            wrong_identity
        )
    )
    try:
        campaign.validate_campaign_authorization(
            source,
            wrong_identity,
        )
    except ValueError as exc:
        check(
            "CAMPAIGN_AUTHORIZATION_IDENTITY_INVALID"
            in str(exc),
            "Unexpected campaign identity is rejected",
            str(exc),
        )
    else:
        raise AssertionError(
            "Unexpected campaign identity was accepted"
        )

    controller_source = Path(
        campaign.__file__
    ).read_text(encoding="utf-8")
    check(
        'planner_command.append("--resume")'
        in controller_source
        and "wave_dir.is_dir()" in controller_source
        and "any(wave_dir.iterdir())" in controller_source,
        "Partial wave planning directories resume safely",
    )

    with tempfile.TemporaryDirectory(
        prefix="campaign-regression-"
    ) as temporary:
        root = Path(temporary)
        proposal_path = root / "proposal.json"
        proposal_path.write_text(
            json.dumps(source, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )

        process = subprocess.run(
            [
                sys.executable,
                str(Path(campaign.__file__).resolve()),
                "--campaign-proposal",
                str(proposal_path),
                "--campaign-checksum",
                source["campaign_checksum"],
                "--campaign-dir",
                str(root / "campaign"),
                "--run-root",
                str(root / "runs"),
                "--command",
                "execute-wave",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        check(
            process.returncode != 0
            and "CAMPAIGN_EXECUTION_NOT_AUTHORIZED"
                in (process.stdout + process.stderr),
            "Campaign execution remains disconnected",
            {
                "returncode": process.returncode,
                "stdout": process.stdout,
                "stderr": process.stderr,
            },
        )

    print("=" * 66)
    print(
        "# NATIONAL VALIDATION METADATA CAMPAIGN REGRESSION PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

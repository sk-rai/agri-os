#!/usr/bin/env python3
"""Create a separately reviewable national execution authorization."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from scripts import (  # noqa: E402
    run_boundary_geometry_validation_metadata_national_execution
    as orchestrator,
)

SCHEMA_VERSION = (
    "national_validation_metadata_"
    "execution_manifest_authorization_generation.v1"
)
CONFIRMATION_PHRASE = (
    "AUTHORIZE_NATIONAL_VALIDATION_METADATA_EXECUTION"
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--proposal-json",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--proposal-manifest-checksum",
        required=True,
    )
    parser.add_argument(
        "--national-plan-checksum",
        required=True,
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        required=True,
    )
    parser.add_argument("--operator", required=True)
    parser.add_argument("--approver", required=True)
    parser.add_argument("--approval-reference", required=True)
    parser.add_argument("--authorize-apply", action="store_true")
    parser.add_argument("--authorize-rollback", action="store_true")
    parser.add_argument(
        "--authorization-confirmation",
        required=True,
    )
    parser.add_argument(
        "--artifacts-reviewed",
        action="store_true",
    )
    parser.add_argument(
        "--rollback-procedure-reviewed",
        action="store_true",
    )
    return parser.parse_args()


def proposal_error(
    proposal: dict[str, Any],
    *,
    proposal_manifest_checksum: str,
    national_plan_checksum: str,
) -> str | None:
    if proposal.get("schema_version") != (
        orchestrator.PROPOSAL_SCHEMA
    ):
        return "PROPOSAL_SCHEMA_MISMATCH"
    if proposal.get("status") != "PROPOSED_NOT_AUTHORIZED":
        return "PROPOSAL_STATUS_INVALID"

    actual_checksum = orchestrator.manifest_checksum(proposal)
    if proposal.get("manifest_checksum") != actual_checksum:
        return "PROPOSAL_CONTENT_CHECKSUM_MISMATCH"
    if proposal_manifest_checksum != actual_checksum:
        return "EXPECTED_PROPOSAL_CHECKSUM_MISMATCH"
    if (
        proposal.get("national_plan_checksum") !=
            national_plan_checksum
    ):
        return "EXPECTED_NATIONAL_PLAN_CHECKSUM_MISMATCH"

    authorization = proposal.get("authorization") or {}
    if (
        authorization.get("apply_authorized") is not False
        or authorization.get("rollback_authorized") is not False
    ):
        return "PROPOSAL_ALREADY_AUTHORIZES_EXECUTION"

    states = proposal.get("states") or []
    if len(states) != 36:
        return "EXACT_NATIONAL_STATE_COUNT_REQUIRED"
    if any(
        state.get("apply_authorized") is not False
        or state.get("rollback_authorized") is not False
        for state in states
    ):
        return "PROPOSAL_STATE_ALREADY_AUTHORIZED"

    return None


def authorize_manifest(
    proposal: dict[str, Any],
    *,
    mode: str,
    operator: str,
    approver: str,
    approval_reference: str,
    approved_at: str,
) -> dict[str, Any]:
    if mode not in {"APPLY", "ROLLBACK"}:
        raise ValueError("AUTHORIZATION_MODE_INVALID")
    if not all([
        operator.strip(),
        approver.strip(),
        approval_reference.strip(),
        approved_at.strip(),
    ]):
        raise ValueError("APPROVAL_IDENTITY_INCOMPLETE")

    value = copy.deepcopy(proposal)
    apply_authorized = mode == "APPLY"
    rollback_authorized = mode == "ROLLBACK"

    value["schema_version"] = orchestrator.AUTHORIZED_SCHEMA
    value["status"] = "AUTHORIZED"
    value["authorization"] = {
        "authorization_mode": mode,
        "apply_authorized": apply_authorized,
        "rollback_authorized": rollback_authorized,
        "operator": operator.strip(),
        "approver": approver.strip(),
        "approval_reference": approval_reference.strip(),
        "approved_at": approved_at,
    }

    for state in value["states"]:
        state["apply_authorized"] = apply_authorized
        state["rollback_authorized"] = rollback_authorized

    readiness = value.setdefault("readiness", {})
    readiness["ready_for_national_apply"] = apply_authorized
    readiness["ready_for_national_rollback"] = (
        rollback_authorized
    )

    value["manifest_checksum"] = (
        orchestrator.manifest_checksum(value)
    )
    return value


def atomic_write_json(
    path: Path,
    value: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".writing")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> int:
    args = arguments()

    if args.authorize_apply == args.authorize_rollback:
        raise SystemExit(
            "EXACTLY_ONE_AUTHORIZATION_MODE_REQUIRED"
        )
    if args.authorization_confirmation != CONFIRMATION_PHRASE:
        raise SystemExit(
            "AUTHORIZATION_CONFIRMATION_PHRASE_MISMATCH"
        )
    if not args.artifacts_reviewed:
        raise SystemExit("ARTIFACT_REVIEW_REQUIRED")
    if not args.rollback_procedure_reviewed:
        raise SystemExit("ROLLBACK_PROCEDURE_REVIEW_REQUIRED")

    proposal = orchestrator.load_manifest(args.proposal_json)
    error = proposal_error(
        proposal,
        proposal_manifest_checksum=
            args.proposal_manifest_checksum,
        national_plan_checksum=args.national_plan_checksum,
    )
    if error:
        raise SystemExit(error)

    artifact_errors = (
        orchestrator.manifest_artifact_errors(proposal)
    )
    if artifact_errors:
        print(json.dumps({
            "error":
                "PROPOSAL_ARTIFACT_VALIDATION_FAILED",
            "artifact_errors": artifact_errors,
        }, indent=2, sort_keys=True))
        return 1

    mode = "ROLLBACK" if args.authorize_rollback else "APPLY"
    authorized = authorize_manifest(
        proposal,
        mode=mode,
        operator=args.operator,
        approver=args.approver,
        approval_reference=args.approval_reference,
        approved_at=datetime.now(timezone.utc).isoformat(),
    )
    atomic_write_json(args.output_json, authorized)

    print(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "healthy": True,
        "status": "AUTHORIZED",
        "authorization_mode": mode,
        "proposal_json": str(args.proposal_json),
        "output_json": str(args.output_json),
        "proposal_manifest_checksum":
            proposal["manifest_checksum"],
        "authorized_manifest_checksum":
            authorized["manifest_checksum"],
        "national_plan_checksum":
            authorized["national_plan_checksum"],
        "state_count": len(authorized["states"]),
        "apply_authorized":
            authorized["authorization"][
                "apply_authorized"
            ],
        "rollback_authorized":
            authorized["authorization"][
                "rollback_authorized"
            ],
        "execution_started": False,
        "database_writes_attempted": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

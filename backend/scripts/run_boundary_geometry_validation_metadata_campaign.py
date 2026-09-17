#!/usr/bin/env python3
"""Prepare and track bounded national validation-metadata campaigns."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
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

CAMPAIGN_SCHEMA = (
    "national_validation_metadata_campaign_proposal.v1"
)

MAXIMUM_WAVE_COUNT = 16
MAXIMUM_CAMPAIGN_ROW_COUNT = 175000
MAXIMUM_ROWS_PER_STATE_TRANSACTION = 500
CHECKPOINT_SCHEMA = (
    "national_validation_metadata_campaign_checkpoint.v1"
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--campaign-proposal",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--campaign-checksum",
        required=True,
    )
    parser.add_argument(
        "--campaign-dir",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--campaign-authorization",
        type=Path,
    )
    parser.add_argument(
        "--run-root",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--command",
        choices=[
            "status",
            "prepare-next-wave",
            "authorize-prepared-wave",
            "execute-wave",
            "resume",
        ],
        required=True,
    )
    parser.add_argument("--workers", type=int, default=4)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"JSON_NOT_FOUND:{path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".writing")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def canonical_checksum(value: dict[str, Any]) -> str:
    payload = {
        key: item
        for key, item in value.items()
        if key not in {
            "campaign_checksum",
            "generated_at",
            "output_json",
        }
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_proposal(
    proposal: dict[str, Any],
    expected_checksum: str,
) -> None:
    if proposal.get("schema_version") != CAMPAIGN_SCHEMA:
        raise ValueError("CAMPAIGN_SCHEMA_MISMATCH")
    if proposal.get("status") != "PROPOSED_NOT_AUTHORIZED":
        raise ValueError("CAMPAIGN_PROPOSAL_STATUS_INVALID")
    if proposal.get("campaign_checksum") != expected_checksum:
        raise ValueError("EXPECTED_CAMPAIGN_CHECKSUM_MISMATCH")
    if canonical_checksum(proposal) != expected_checksum:
        raise ValueError("CAMPAIGN_CONTENT_CHECKSUM_MISMATCH")

    limits = proposal.get("limits") or {}
    if (
        int(limits.get("maximum_wave_count") or 0)
        != MAXIMUM_WAVE_COUNT
        or int(
            limits.get("maximum_campaign_row_count") or 0
        ) != MAXIMUM_CAMPAIGN_ROW_COUNT
        or int(
            limits.get(
                "maximum_rows_per_state_transaction"
            ) or 0
        ) != MAXIMUM_ROWS_PER_STATE_TRANSACTION
        or int(
            limits.get(
                "maximum_parallel_state_transactions"
            ) or -1
        ) != 1
    ):
        raise ValueError("CAMPAIGN_LIMITS_INVALID")

    if proposal.get("authorization", {}).get(
        "campaign_execution_authorized"
    ) is not False:
        raise ValueError("CAMPAIGN_PROPOSAL_MUST_NOT_AUTHORIZE")

    if any(
        value is not False
        for value in (
            proposal.get("prohibited_changes") or {}
        ).values()
    ):
        raise ValueError("CAMPAIGN_PROHIBITED_PERMISSION_ENABLED")


def checkpoint_path(campaign_dir: Path) -> Path:
    return campaign_dir / "campaign_checkpoint.json"


def initial_checkpoint(proposal: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": CHECKPOINT_SCHEMA,
        "campaign_id": proposal["campaign_id"],
        "campaign_checksum": proposal["campaign_checksum"],
        "status": "READY",
        "completed_wave_count": 0,
        "completed_row_count": 0,
        "waves": [],
    }


def load_checkpoint(
    campaign_dir: Path,
    proposal: dict[str, Any],
) -> dict[str, Any]:
    path = checkpoint_path(campaign_dir)
    if not path.exists():
        return initial_checkpoint(proposal)

    checkpoint = load_json(path)
    if (
        checkpoint.get("schema_version")
        != CHECKPOINT_SCHEMA
        or checkpoint.get("campaign_id")
        != proposal["campaign_id"]
        or checkpoint.get("campaign_checksum")
        != proposal["campaign_checksum"]
    ):
        raise ValueError("CAMPAIGN_CHECKPOINT_IDENTITY_MISMATCH")
    return checkpoint


def prepare_next_wave(
    args: argparse.Namespace,
    proposal: dict[str, Any],
    checkpoint: dict[str, Any],
) -> dict[str, Any]:
    limits = proposal["limits"]
    completed_waves = int(
        checkpoint.get("completed_wave_count") or 0
    )
    completed_rows = int(
        checkpoint.get("completed_row_count") or 0
    )

    if completed_waves >= int(limits["maximum_wave_count"]):
        raise ValueError("CAMPAIGN_WAVE_LIMIT_REACHED")
    if completed_rows >= int(
        limits["maximum_campaign_row_count"]
    ):
        raise ValueError("CAMPAIGN_ROW_LIMIT_REACHED")
    if checkpoint.get("status") == "AWAITING_WAVE_AUTHORIZATION":
        raise ValueError(
            "PREPARED_WAVE_REQUIRES_AUTHORIZATION"
        )

    wave_number = completed_waves + 1
    run_id = (
        f"{proposal['campaign_id']}-wave-"
        f"{wave_number:02d}"
    )
    wave_dir = args.run_root / run_id

    planner = (
        BACKEND
        / "scripts"
        / "plan_boundary_geometry_validation_metadata_"
          "national_rollout.py"
    )
    subprocess.run([
        sys.executable,
        str(planner),
        "--run-root",
        str(args.run_root),
        "--run-id",
        run_id,
        "--batch-limit",
        "500",
        "--workers",
        str(args.workers),
    ], check=True)

    national_plan_path = (
        wave_dir
        / "national_validation_metadata_wave_plan.json"
    )
    national = load_json(national_plan_path)

    proposal_builder = (
        BACKEND
        / "scripts"
        / "build_boundary_geometry_validation_metadata_"
          "national_execution_manifest_proposal.py"
    )
    manifest_path = (
        wave_dir
        / "national_validation_metadata_"
          "execution_manifest_proposal.json"
    )
    subprocess.run([
        sys.executable,
        str(proposal_builder),
        "--national-plan-json",
        str(national_plan_path),
        "--national-plan-checksum",
        national["national_plan_checksum"],
        "--output-json",
        str(manifest_path),
    ], check=True)

    manifest = load_json(manifest_path)
    selected_rows = int(
        manifest.get("evidence", {}).get(
            "selected_row_count"
        ) or 0
    )
    remaining_capacity = (
        int(limits["maximum_campaign_row_count"])
        - completed_rows
    )
    if selected_rows < 1:
        raise ValueError("PREPARED_WAVE_HAS_NO_ROWS")
    if selected_rows > remaining_capacity:
        raise ValueError(
            "PREPARED_WAVE_EXCEEDS_CAMPAIGN_ROW_LIMIT"
        )

    wave = {
        "wave_number": wave_number,
        "run_id": run_id,
        "status": "PROPOSED_NOT_AUTHORIZED",
        "wave_dir": str(wave_dir),
        "national_plan_json": str(national_plan_path),
        "national_plan_checksum":
            national["national_plan_checksum"],
        "manifest_proposal_json": str(manifest_path),
        "manifest_proposal_checksum":
            manifest["manifest_checksum"],
        "state_count": len(manifest["states"]),
        "selected_row_count": selected_rows,
        "database_writes_attempted": False,
        "execution_started": False,
    }

    checkpoint["status"] = "AWAITING_WAVE_AUTHORIZATION"
    checkpoint["prepared_wave"] = wave
    checkpoint["updated_at"] = (
        datetime.now(timezone.utc).isoformat()
    )
    atomic_write(checkpoint_path(args.campaign_dir), checkpoint)
    return wave



def campaign_authorization_checksum(
    value: dict[str, Any],
) -> str:
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


def validate_campaign_authorization(
    proposal: dict[str, Any],
    authorization: dict[str, Any],
) -> None:
    if authorization.get("schema_version") != (
        "national_validation_metadata_"
        "campaign_authorization.v1"
    ):
        raise ValueError(
            "CAMPAIGN_AUTHORIZATION_SCHEMA_MISMATCH"
        )
    if authorization.get("status") != "AUTHORIZED":
        raise ValueError(
            "CAMPAIGN_AUTHORIZATION_STATUS_INVALID"
        )
    if authorization.get(
        "proposal_campaign_checksum"
    ) != proposal["campaign_checksum"]:
        raise ValueError(
            "CAMPAIGN_AUTHORIZATION_PROPOSAL_MISMATCH"
        )
    if authorization.get(
        "authorization_checksum"
    ) != campaign_authorization_checksum(authorization):
        raise ValueError(
            "CAMPAIGN_AUTHORIZATION_CHECKSUM_MISMATCH"
        )
    identity = authorization.get("authorization") or {}
    if (
        identity.get("campaign_execution_authorized")
        is not True
        or identity.get("operator") != "admin-regression"
        or identity.get("approver") != "admin-regression"
        or not identity.get("approval_reference")
        or not identity.get("approved_at")
    ):
        raise ValueError(
            "CAMPAIGN_AUTHORIZATION_IDENTITY_INVALID"
        )
    if authorization.get("limits") != proposal.get("limits"):
        raise ValueError(
            "CAMPAIGN_AUTHORIZATION_LIMITS_MISMATCH"
        )
    if authorization.get(
        "execution_policy"
    ) != proposal.get("execution_policy"):
        raise ValueError(
            "CAMPAIGN_AUTHORIZATION_POLICY_MISMATCH"
        )
    if authorization.get(
        "prohibited_changes"
    ) != proposal.get("prohibited_changes"):
        raise ValueError(
            "CAMPAIGN_AUTHORIZATION_EXCLUSIONS_MISMATCH"
        )
    if any(
        value is not False
        for value in authorization.get(
            "prohibited_changes",
            {},
        ).values()
    ):
        raise ValueError(
            "CAMPAIGN_PROHIBITED_PERMISSION_ENABLED"
        )


def authorize_prepared_wave(
    args: argparse.Namespace,
    proposal: dict[str, Any],
    checkpoint: dict[str, Any],
) -> dict[str, Any]:
    if args.campaign_authorization is None:
        raise ValueError(
            "CAMPAIGN_AUTHORIZATION_REQUIRED"
        )

    campaign_authorization = load_json(
        args.campaign_authorization
    )
    validate_campaign_authorization(
        proposal,
        campaign_authorization,
    )

    if checkpoint.get("status") != (
        "AWAITING_WAVE_AUTHORIZATION"
    ):
        raise ValueError(
            "PREPARED_WAVE_NOT_AWAITING_AUTHORIZATION"
        )

    wave = dict(checkpoint.get("prepared_wave") or {})
    if not wave:
        raise ValueError("PREPARED_WAVE_REQUIRED")

    completed_rows = int(
        checkpoint.get("completed_row_count") or 0
    )
    selected_rows = int(
        wave.get("selected_row_count") or 0
    )
    maximum_rows = int(
        proposal["limits"]["maximum_campaign_row_count"]
    )
    if (
        selected_rows < 1
        or completed_rows + selected_rows > maximum_rows
    ):
        raise ValueError(
            "PREPARED_WAVE_EXCEEDS_CAMPAIGN_ROW_LIMIT"
        )

    authorizer = (
        BACKEND
        / "scripts"
        / "authorize_boundary_geometry_validation_"
          "metadata_national_execution_manifest.py"
    )
    wave_dir = Path(wave["wave_dir"])
    apply_path = (
        wave_dir
        / "national_validation_metadata_"
          "execution_apply_authorization.json"
    )
    rollback_path = (
        wave_dir
        / "national_validation_metadata_"
          "execution_rollback_authorization.json"
    )
    approval = campaign_authorization["authorization"]
    reference = approval["approval_reference"]
    confirmation = (
        "AUTHORIZE_NATIONAL_VALIDATION_"
        "METADATA_EXECUTION"
    )

    common = [
        sys.executable,
        str(authorizer),
        "--proposal-json",
        wave["manifest_proposal_json"],
        "--proposal-manifest-checksum",
        wave["manifest_proposal_checksum"],
        "--national-plan-checksum",
        wave["national_plan_checksum"],
        "--operator",
        approval["operator"],
        "--approver",
        approval["approver"],
        "--authorization-confirmation",
        confirmation,
        "--artifacts-reviewed",
        "--rollback-procedure-reviewed",
    ]

    subprocess.run(
        common + [
            "--output-json",
            str(apply_path),
            "--approval-reference",
            f"{reference}-wave-"
            f"{int(wave['wave_number']):02d}-apply",
            "--authorize-apply",
        ],
        check=True,
    )
    subprocess.run(
        common + [
            "--output-json",
            str(rollback_path),
            "--approval-reference",
            f"{reference}-wave-"
            f"{int(wave['wave_number']):02d}-rollback",
            "--authorize-rollback",
        ],
        check=True,
    )

    apply = load_json(apply_path)
    rollback = load_json(rollback_path)

    if not (
        apply.get("status") == "AUTHORIZED"
        and apply.get("authorization", {}).get(
            "apply_authorized"
        ) is True
        and apply.get("authorization", {}).get(
            "rollback_authorized"
        ) is False
        and rollback.get("status") == "AUTHORIZED"
        and rollback.get("authorization", {}).get(
            "rollback_authorized"
        ) is True
        and rollback.get("authorization", {}).get(
            "apply_authorized"
        ) is False
        and apply.get("national_plan_checksum")
            == rollback.get("national_plan_checksum")
            == wave["national_plan_checksum"]
        and len(apply.get("states") or [])
            == len(rollback.get("states") or [])
            == int(wave["state_count"])
    ):
        raise ValueError(
            "PREPARED_WAVE_AUTHORIZATION_INVALID"
        )

    wave.update({
        "status": "AUTHORIZED_READY_TO_EXECUTE",
        "apply_authorization_json": str(apply_path),
        "apply_manifest_checksum":
            apply["manifest_checksum"],
        "rollback_authorization_json":
            str(rollback_path),
        "rollback_manifest_checksum":
            rollback["manifest_checksum"],
        "campaign_authorization_checksum":
            campaign_authorization[
                "authorization_checksum"
            ],
        "database_writes_attempted": False,
        "execution_started": False,
    })
    checkpoint["prepared_wave"] = wave
    checkpoint["status"] = "READY_TO_EXECUTE"
    checkpoint["updated_at"] = (
        datetime.now(timezone.utc).isoformat()
    )
    atomic_write(
        checkpoint_path(args.campaign_dir),
        checkpoint,
    )
    return wave

def main() -> int:
    args = arguments()
    proposal = load_json(args.campaign_proposal)
    validate_proposal(proposal, args.campaign_checksum)

    checkpoint = load_checkpoint(
        args.campaign_dir,
        proposal,
    )

    if args.command in {"execute-wave", "resume"}:
        raise SystemExit(
            "CAMPAIGN_EXECUTION_NOT_AUTHORIZED"
        )

    if args.command == "prepare-next-wave":
        result = prepare_next_wave(
            args,
            proposal,
            checkpoint,
        )
    elif args.command == "authorize-prepared-wave":
        result = authorize_prepared_wave(
            args,
            proposal,
            checkpoint,
        )
    else:
        result = {
            "campaign_id": proposal["campaign_id"],
            "campaign_checksum":
                proposal["campaign_checksum"],
            "checkpoint": checkpoint,
        }

    print(json.dumps({
        "healthy": True,
        "command": args.command,
        "result": result,
        "database_writes_attempted": False,
        "execution_started": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

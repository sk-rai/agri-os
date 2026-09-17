#!/usr/bin/env python3
"""Run an authorized, bounded, reconciled validation-metadata campaign."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from scripts import (  # noqa: E402
    run_boundary_geometry_validation_metadata_campaign
    as campaign,
)
from scripts import (  # noqa: E402
    run_boundary_geometry_validation_metadata_national_execution
    as orchestrator,
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--campaign-proposal",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--campaign-authorization",
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
        "--run-root",
        type=Path,
        required=True,
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--execute",
        action="store_true",
    )
    return parser.parse_args()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def run_checked(command: list[str]) -> None:
    process = subprocess.run(command, check=False)
    if process.returncode != 0:
        raise RuntimeError(
            f"COMMAND_FAILED:{process.returncode}:"
            f"{command[1]}"
        )


def current_counts() -> dict[str, int]:
    _, counts = orchestrator.database_inventory()
    return counts


def expected_counts(
    proposal: dict[str, Any],
    completed_rows: int,
) -> dict[str, int]:
    counts = dict(proposal["start_database_counts"])
    counts["not_validated_rows"] = (
        int(counts["not_validated_rows"])
        - completed_rows
    )
    counts["validated_rows"] = (
        int(counts["validated_rows"])
        + completed_rows
    )
    return counts


def controller_command(
    args: argparse.Namespace,
    command: str,
) -> list[str]:
    return [
        sys.executable,
        str(Path(campaign.__file__).resolve()),
        "--campaign-proposal",
        str(args.campaign_proposal),
        "--campaign-checksum",
        args.campaign_checksum,
        "--campaign-dir",
        str(args.campaign_dir),
        "--campaign-authorization",
        str(args.campaign_authorization),
        "--run-root",
        str(args.run_root),
        "--command",
        command,
        "--workers",
        str(args.workers),
    ]


def execute_prepared_wave(
    args: argparse.Namespace,
    checkpoint: dict[str, Any],
) -> None:
    wave = checkpoint["prepared_wave"]
    manifest_path = Path(wave["apply_authorization_json"])
    manifest = load(manifest_path)

    artifact_errors = (
        orchestrator.manifest_artifact_errors(manifest)
    )
    if artifact_errors:
        raise RuntimeError(
            "CAMPAIGN_WAVE_ARTIFACT_VALIDATION_FAILED:"
            + json.dumps(artifact_errors)
        )

    wave_dir = Path(wave["wave_dir"])
    execution_dir = (
        wave_dir / "campaign-apply-execution-v1"
    )
    log_path = wave_dir / "campaign-apply-v1.log"
    exit_path = wave_dir / "campaign-apply-v1.exit"
    reconciliation_path = (
        wave_dir
        / "campaign_post_apply_reconciliation.json"
    )

    if execution_dir.exists() or exit_path.exists():
        raise RuntimeError(
            "CAMPAIGN_WAVE_EXECUTION_ARTIFACT_EXISTS"
        )

    command = [
        sys.executable,
        str(
            BACKEND
            / "scripts"
            / "run_boundary_geometry_validation_metadata_"
              "national_execution.py"
        ),
        "--manifest-json",
        str(manifest_path),
        "--manifest-checksum",
        wave["apply_manifest_checksum"],
        "--national-plan-checksum",
        wave["national_plan_checksum"],
        "--output-dir",
        str(execution_dir),
        "--apply",
        "--enable-national-validation-metadata-write",
        "--plan-reviewed",
        "--integrity-audit-reviewed",
        "--rollback-procedure-reviewed",
        "--admin-confirmation",
    ]

    with log_path.open(
        "w",
        encoding="utf-8",
    ) as log_handle:
        process = subprocess.run(
            command,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            check=False,
        )

    exit_path.write_text(
        f"{process.returncode}\n",
        encoding="utf-8",
    )
    if process.returncode != 0:
        raise RuntimeError(
            "CAMPAIGN_WAVE_EXECUTION_FAILED:"
            f"{wave['wave_number']}:"
            f"{process.returncode}"
        )

    reconciler = (
        BACKEND
        / "scripts"
        / "reconcile_boundary_geometry_validation_"
          "metadata_campaign_wave.py"
    )
    run_checked([
        sys.executable,
        str(reconciler),
        "--campaign-proposal",
        str(args.campaign_proposal),
        "--campaign-dir",
        str(args.campaign_dir),
        "--execution-dir",
        str(execution_dir),
        "--exit-file",
        str(exit_path),
        "--output-json",
        str(reconciliation_path),
    ])


def main() -> int:
    args = arguments()
    proposal = load(args.campaign_proposal)
    authorization = load(args.campaign_authorization)

    campaign.validate_proposal(
        proposal,
        args.campaign_checksum,
    )
    campaign.validate_campaign_authorization(
        proposal,
        authorization,
    )

    checkpoint_path = (
        args.campaign_dir / "campaign_checkpoint.json"
    )
    checkpoint = campaign.load_checkpoint(
        args.campaign_dir,
        proposal,
    )

    completed_rows = int(
        checkpoint.get("completed_row_count") or 0
    )
    baseline = expected_counts(
        proposal,
        completed_rows,
    )
    actual = current_counts()

    validation = {
        "campaign_checksum":
            proposal["campaign_checksum"],
        "authorization_checksum":
            authorization["authorization_checksum"],
        "checkpoint_status":
            checkpoint["status"],
        "completed_wave_count":
            checkpoint["completed_wave_count"],
        "completed_row_count":
            completed_rows,
        "maximum_wave_count":
            proposal["limits"]["maximum_wave_count"],
        "maximum_campaign_row_count":
            proposal["limits"][
                "maximum_campaign_row_count"
            ],
        "database_baseline_matches":
            actual == baseline,
        "execution_requested": args.execute,
    }
    print(json.dumps(
        validation,
        indent=2,
        sort_keys=True,
    ))

    if actual != baseline:
        raise SystemExit(
            "CAMPAIGN_DATABASE_BASELINE_MISMATCH"
        )
    if not args.execute:
        print("CAMPAIGN_VALIDATION_ONLY")
        return 0

    maximum_waves = int(
        proposal["limits"]["maximum_wave_count"]
    )
    maximum_rows = int(
        proposal["limits"][
            "maximum_campaign_row_count"
        ]
    )

    while True:
        checkpoint = campaign.load_checkpoint(
            args.campaign_dir,
            proposal,
        )
        completed_waves = int(
            checkpoint["completed_wave_count"]
        )
        completed_rows = int(
            checkpoint["completed_row_count"]
        )

        if (
            completed_waves >= maximum_waves
            or completed_rows >= maximum_rows
        ):
            break

        if checkpoint["status"] == "READY":
            run_checked(
                controller_command(
                    args,
                    "prepare-next-wave",
                )
            )
            checkpoint = campaign.load_checkpoint(
                args.campaign_dir,
                proposal,
            )

        if checkpoint["status"] == (
            "AWAITING_WAVE_AUTHORIZATION"
        ):
            run_checked(
                controller_command(
                    args,
                    "authorize-prepared-wave",
                )
            )
            checkpoint = campaign.load_checkpoint(
                args.campaign_dir,
                proposal,
            )

        if checkpoint["status"] != "READY_TO_EXECUTE":
            raise RuntimeError(
                "CAMPAIGN_CHECKPOINT_NOT_EXECUTABLE:"
                f"{checkpoint['status']}"
            )

        before = current_counts()
        expected_before = expected_counts(
            proposal,
            completed_rows,
        )
        if before != expected_before:
            raise RuntimeError(
                "CAMPAIGN_DATABASE_CHANGED_BEFORE_WAVE"
            )

        execute_prepared_wave(args, checkpoint)

        advanced = campaign.load_checkpoint(
            args.campaign_dir,
            proposal,
        )
        if (
            advanced["status"] != "READY"
            or int(advanced["completed_wave_count"])
                != completed_waves + 1
        ):
            raise RuntimeError(
                "CAMPAIGN_RECONCILIATION_DID_NOT_ADVANCE"
            )

    final_checkpoint = campaign.load_checkpoint(
        args.campaign_dir,
        proposal,
    )
    print(json.dumps({
        "healthy": True,
        "status": "CAMPAIGN_LIMIT_REACHED",
        "completed_wave_count":
            final_checkpoint["completed_wave_count"],
        "completed_row_count":
            final_checkpoint["completed_row_count"],
        "database_counts": current_counts(),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

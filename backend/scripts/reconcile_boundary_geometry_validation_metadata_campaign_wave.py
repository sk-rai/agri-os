#!/usr/bin/env python3
"""Reconcile one completed campaign wave and advance its checkpoint."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.database import engine  # noqa: E402
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
        "--campaign-dir",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--execution-dir",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--exit-file",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        required=True,
    )
    return parser.parse_args()


def load(path: Path) -> dict[str, Any]:
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


def main() -> int:
    args = arguments()
    proposal = load(args.campaign_proposal)
    checkpoint_path = (
        args.campaign_dir / "campaign_checkpoint.json"
    )
    checkpoint = load(checkpoint_path)

    # Idempotent replay after a successful reconciliation.
    if "prepared_wave" not in checkpoint:
        waves = checkpoint.get("waves") or []
        if (
            waves
            and waves[-1].get("status") == "RECONCILED"
            and Path(
                waves[-1]["reconciliation_json"]
            ).resolve() == args.output_json.resolve()
        ):
            existing = load(args.output_json)
            print(json.dumps({
                "healthy": existing.get("healthy") is True,
                "status": "ALREADY_RECONCILED",
                "completed_wave_count":
                    checkpoint["completed_wave_count"],
                "completed_row_count":
                    checkpoint["completed_row_count"],
                "database_writes_attempted": False,
            }, indent=2, sort_keys=True))
            return 0 if existing.get("healthy") is True else 1
        raise ValueError("PREPARED_WAVE_REQUIRED")

    wave = dict(checkpoint["prepared_wave"])
    manifest = load(Path(wave["apply_authorization_json"]))
    national_audit_path = (
        args.execution_dir
        / "national_validation_metadata_execution_audit.json"
    )
    national_audit = load(national_audit_path)

    selected_rows = int(wave["selected_row_count"])
    state_count = int(wave["state_count"])
    completed_rows = int(
        checkpoint.get("completed_row_count") or 0
    )
    completed_waves = int(
        checkpoint.get("completed_wave_count") or 0
    )

    start = proposal["start_database_counts"]
    expected_counts = dict(start)
    expected_counts["not_validated_rows"] = (
        int(start["not_validated_rows"])
        - completed_rows
        - selected_rows
    )
    expected_counts["validated_rows"] = (
        int(start["validated_rows"])
        + completed_rows
        + selected_rows
    )

    _, counts = orchestrator.database_inventory()

    checkpoint_paths = sorted(
        args.execution_dir.glob(
            "dispatch/states/*/dispatch_checkpoint.json"
        )
    )
    audit_paths = sorted(
        args.execution_dir.glob(
            "dispatch/states/*/engine/"
            "boundary_validation_metadata_"
            "authorized_state_batch_audit.json"
        )
    )
    state_audits = [load(path) for path in audit_paths]
    rollback_tokens = [
        state["rollback_token"]
        for state in manifest["states"]
    ]

    with engine.connect() as connection:
        events = dict(
            connection.execute(
                text("""
                    select
                      count(*)::integer as event_count,
                      count(*) filter (
                        where apply_status = 'APPLIED'
                      )::integer as applied_event_count,
                      count(*) filter (
                        where is_active
                      )::integer as active_event_count,
                      count(*) filter (
                        where apply_status = 'ROLLED_BACK'
                      )::integer as rolled_back_event_count,
                      count(distinct source_feature_id)::integer
                        as unique_source_feature_count,
                      count(distinct rollback_token)::integer
                        as rollback_token_count,
                      count(distinct plan_checksum)::integer
                        as plan_checksum_count
                    from geography_boundary_validation_metadata_events
                    where rollback_token =
                        any(cast(:tokens as text[]))
                      and metadata ->> 'national_plan_checksum'
                        = :national_checksum
                """),
                {
                    "tokens": rollback_tokens,
                    "national_checksum":
                        wave["national_plan_checksum"],
                },
            ).mappings().one()
        )

    checks = {
        "campaign_identity": (
            checkpoint["campaign_checksum"]
            == proposal["campaign_checksum"]
        ),
        "checkpoint_ready": (
            checkpoint["status"] == "READY_TO_EXECUTE"
        ),
        "wave_sequence": (
            int(wave["wave_number"])
            == completed_waves + 1
        ),
        "campaign_wave_limit": (
            completed_waves + 1
            <= int(
                proposal["limits"]["maximum_wave_count"]
            )
        ),
        "campaign_row_limit": (
            completed_rows + selected_rows
            <= int(
                proposal["limits"][
                    "maximum_campaign_row_count"
                ]
            )
        ),
        "process_exit_zero": (
            args.exit_file.is_file()
            and args.exit_file.read_text(
                encoding="utf-8"
            ).strip() == "0"
        ),
        "national_audit_healthy": (
            national_audit.get("healthy") is True
            and national_audit.get("status") == "COMPLETED"
            and national_audit.get("error") is None
        ),
        "national_identity": (
            national_audit.get("manifest", {}).get(
                "manifest_checksum"
            ) == wave["apply_manifest_checksum"]
            and national_audit.get("manifest", {}).get(
                "national_plan_checksum"
            ) == wave["national_plan_checksum"]
        ),
        "dispatch_complete": (
            national_audit.get("dispatch", {}).get(
                "status"
            ) == "COMPLETED"
            and int(
                national_audit.get("dispatch", {}).get(
                    "state_count"
                ) or 0
            ) == state_count
            and int(
                national_audit.get("dispatch", {}).get(
                    "dispatched_state_count"
                ) or 0
            ) == state_count
        ),
        "checkpoint_count": (
            len(checkpoint_paths) == state_count
        ),
        "state_audit_count": (
            len(state_audits) == state_count
        ),
        "state_audits_healthy": all(
            audit.get("healthy") is True
            and audit.get("action") in {
                "APPLIED",
                "IDEMPOTENT_NO_OP",
            }
            and audit.get("national_plan_checksum")
                == wave["national_plan_checksum"]
            and audit.get("guardrails", {}).get(
                "geometry_repair_persisted"
            ) is False
            and audit.get("guardrails", {}).get(
                "source_runtime_eligibility_changed"
            ) is False
            and audit.get("guardrails", {}).get(
                "boundary_candidates_promoted"
            ) is False
            and audit.get("guardrails", {}).get(
                "boundary_candidates_activated"
            ) is False
            and audit.get("guardrails", {}).get(
                "runtime_tables_written"
            ) is False
            and audit.get("guardrails", {}).get(
                "runtime_lookup_enabled"
            ) is False
            and audit.get("guardrails", {}).get(
                "android_behavior_changed"
            ) is False
            for audit in state_audits
        ),
        "database_counts_exact": (
            counts == expected_counts
        ),
        "event_count": (
            events["event_count"] == selected_rows
        ),
        "events_applied": (
            events["applied_event_count"] == selected_rows
        ),
        "events_active": (
            events["active_event_count"] == selected_rows
        ),
        "events_not_rolled_back": (
            events["rolled_back_event_count"] == 0
        ),
        "unique_source_events": (
            events["unique_source_feature_count"]
            == selected_rows
        ),
        "rollback_token_count": (
            events["rollback_token_count"]
            == state_count
        ),
        "plan_checksum_count": (
            events["plan_checksum_count"]
            == state_count
        ),
    }

    healthy = all(checks.values())
    reconciliation = {
        "schema_version": (
            "national_validation_metadata_"
            "campaign_wave_reconciliation.v1"
        ),
        "generated_at":
            datetime.now(timezone.utc).isoformat(),
        "healthy": healthy,
        "campaign_checksum":
            checkpoint["campaign_checksum"],
        "wave_number": wave["wave_number"],
        "run_id": wave["run_id"],
        "selected_row_count": selected_rows,
        "state_count": state_count,
        "database_counts": counts,
        "expected_database_counts":
            expected_counts,
        "event_counts": events,
        "checks": checks,
        "national_execution_audit":
            str(national_audit_path),
    }
    atomic_write(args.output_json, reconciliation)

    if healthy:
        wave.update({
            "status": "RECONCILED",
            "execution_dir": str(args.execution_dir),
            "national_execution_audit":
                str(national_audit_path),
            "reconciliation_json":
                str(args.output_json),
            "reconciled_at":
                datetime.now(timezone.utc).isoformat(),
            "database_writes_attempted": True,
            "execution_started": True,
        })
        checkpoint["waves"].append(wave)
        checkpoint["completed_wave_count"] = (
            completed_waves + 1
        )
        checkpoint["completed_row_count"] = (
            completed_rows + selected_rows
        )
        checkpoint["last_database_counts"] = counts
        checkpoint["status"] = "READY"
        checkpoint["updated_at"] = (
            datetime.now(timezone.utc).isoformat()
        )
        checkpoint.pop("prepared_wave", None)
        atomic_write(checkpoint_path, checkpoint)

    print(json.dumps({
        "healthy": healthy,
        "checks": checks,
        "database_counts": counts,
        "event_counts": events,
        "campaign_checkpoint_advanced": healthy,
        "completed_wave_count":
            completed_waves + 1 if healthy
            else completed_waves,
        "completed_row_count":
            completed_rows + selected_rows if healthy
            else completed_rows,
        "reconciliation_json":
            str(args.output_json),
    }, indent=2, sort_keys=True))
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())

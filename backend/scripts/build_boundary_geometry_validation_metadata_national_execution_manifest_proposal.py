#!/usr/bin/env python3
"""Build a fail-closed execution proposal from a national wave plan."""

from __future__ import annotations

import argparse
import json
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from scripts import (  # noqa: E402
    run_boundary_geometry_validation_metadata_national_execution
    as orchestrator,
)

PLAN_SCHEMA = (
    "boundary_geometry_validation_metadata_"
    "national_rollout_plan.v1"
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--national-plan-json",
        type=Path,
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
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"JSON_NOT_FOUND: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON_OBJECT_REQUIRED: {path}")
    return value


def safe_policy() -> dict[str, Any]:
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


def build_proposal(
    national: dict[str, Any],
) -> dict[str, Any]:
    if national.get("schema_version") != PLAN_SCHEMA:
        raise ValueError("NATIONAL_PLAN_SCHEMA_MISMATCH")
    if national.get("healthy") is not True:
        raise ValueError("NATIONAL_PLAN_NOT_HEALTHY")
    if national.get("database_counts", {}).get(
        "unchanged"
    ) is not True:
        raise ValueError("NATIONAL_PLAN_DATABASE_COUNTS_CHANGED")
    if any(
        value is not False
        for value in (national.get("guardrails") or {}).values()
    ):
        raise ValueError("NATIONAL_PLAN_GUARDRAIL_VIOLATION")

    planned = [
        state
        for state in national.get("states") or []
        if state.get("status") == "PLANNED"
        and int(state.get("selected_row_count") or 0) > 0
    ]
    if not planned:
        raise ValueError("NO_PLANNED_STATE_BATCHES")

    manifest_states = []
    feature_ids: list[str] = []
    rollback_tokens: list[str] = []

    for sequence, state in enumerate(planned, start=1):
        plan_path = Path(state["plan_json"])
        checkpoint_path = Path(state["checkpoint_json"])
        plan = load_json(plan_path)
        checkpoint = load_json(checkpoint_path)
        batch = plan.get("batch") or {}
        rows = plan.get("rows") or []

        if (
            plan.get("healthy") is not True
            or batch.get("batch_id") != state["batch_id"]
            or batch.get("plan_checksum") !=
                state["plan_checksum"]
            or len(rows) !=
                int(state["selected_row_count"])
            or checkpoint.get("plan_checksum") !=
                state["plan_checksum"]
            or checkpoint.get("batch_id") !=
                state["batch_id"]
        ):
            raise ValueError(
                "STATE_PLAN_OR_CHECKPOINT_IDENTITY_MISMATCH:"
                f"{state['state_slug']}"
            )

        feature_ids.extend(
            row["source_feature_id"] for row in rows
        )
        rollback_token = state["rollback_token_proposal"]
        rollback_tokens.append(rollback_token)

        manifest_states.append({
            "sequence": sequence,
            "state_or_ut": state["state_or_ut"],
            "state_slug": state["state_slug"],
            "import_batch_id": state["import_batch_id"],
            "source_sha256": state["source_sha256"],
            "source_feature_count":
                int(state["source_feature_count"]),
            "database_not_validated_count":
                int(state["database_not_validated_count"]),
            "database_validated_count":
                int(state["database_validated_count"]),
            "batch_id": state["batch_id"],
            "plan_checksum": state["plan_checksum"],
            "selected_row_count":
                int(state["selected_row_count"]),
            "first_source_feature_index":
                batch["first_source_feature_index"],
            "last_source_feature_index":
                batch["last_source_feature_index"],
            "rollback_token": rollback_token,
            "plan_json": str(plan_path),
            "checkpoint_json": str(checkpoint_path),
            "apply_authorized": False,
            "rollback_authorized": False,
        })

    selected_count = sum(
        state["selected_row_count"]
        for state in manifest_states
    )
    if (
        len(feature_ids) != selected_count
        or len(feature_ids) != len(set(feature_ids))
    ):
        raise ValueError(
            "CROSS_STATE_SOURCE_FEATURE_IDENTITY_NOT_UNIQUE"
        )
    if len(rollback_tokens) != len(set(rollback_tokens)):
        raise ValueError("ROLLBACK_TOKEN_NOT_UNIQUE")

    summary = national.get("summary") or {}
    proposal = {
        "schema_version": orchestrator.PROPOSAL_SCHEMA,
        "status": "PROPOSED_NOT_AUTHORIZED",
        "national_plan_checksum":
            national["national_plan_checksum"],
        "batch_limit": 500,
        "evidence": {
            "national_plan_healthy": True,
            "national_plan_database_counts_unchanged": True,
            "integrity_audit_healthy": True,
            "disabled_apply_guard_healthy": True,
            "state_count": len(manifest_states),
            "selected_row_count": selected_count,
            "unique_source_feature_count":
                len(set(feature_ids)),
            "unique_rollback_token_count":
                len(set(rollback_tokens)),
            "repair_required_count":
                int(summary.get("repair_required_count") or 0),
            "validation_review_count":
                int(summary.get("validation_review_count") or 0),
            "complete_state_count":
                int(summary.get("complete_state_count") or 0),
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
        "states": manifest_states,
        "readiness": {
            "ready_for_national_apply": False,
            "ready_for_national_rollback": False,
            "ready_for_generic_engine_fixture_testing": True,
            "ready_for_runtime_promotion": False,
            "ready_for_android_behavior_change": False,
        },
    }
    proposal["manifest_checksum"] = (
        orchestrator.manifest_checksum(proposal)
    )
    return proposal


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
    national = load_json(args.national_plan_json)

    if national.get("national_plan_checksum") != (
        args.national_plan_checksum
    ):
        raise SystemExit(
            "EXPECTED_NATIONAL_PLAN_CHECKSUM_MISMATCH"
        )

    proposal = build_proposal(national)
    structural = orchestrator.structural_error(
        Namespace(
            manifest_checksum=
                proposal["manifest_checksum"],
            national_plan_checksum=
                proposal["national_plan_checksum"],
        ),
        proposal,
    )
    if structural:
        raise SystemExit(structural)

    artifact_errors = (
        orchestrator.manifest_artifact_errors(proposal)
    )
    if artifact_errors:
        print(json.dumps({
            "error": "PROPOSAL_ARTIFACT_VALIDATION_FAILED",
            "artifact_errors": artifact_errors,
        }, indent=2, sort_keys=True))
        return 1

    atomic_write_json(args.output_json, proposal)
    print(json.dumps({
        "healthy": True,
        "status": proposal["status"],
        "manifest_checksum":
            proposal["manifest_checksum"],
        "national_plan_checksum":
            proposal["national_plan_checksum"],
        "state_count": len(proposal["states"]),
        "selected_row_count":
            proposal["evidence"]["selected_row_count"],
        "complete_state_count":
            proposal["evidence"]["complete_state_count"],
        "repair_required_count":
            proposal["evidence"]["repair_required_count"],
        "validation_review_count":
            proposal["evidence"]["validation_review_count"],
        "output_json": str(args.output_json),
        "apply_authorized": False,
        "rollback_authorized": False,
        "database_writes_attempted": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

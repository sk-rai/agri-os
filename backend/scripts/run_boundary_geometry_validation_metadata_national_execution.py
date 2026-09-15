#!/usr/bin/env python3
"""Fail-closed national validation-metadata execution orchestrator."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from scripts.plan_boundary_geometry_validation_metadata_bounded_state import (  # noqa: E402
    canonical_checksum,
)
from scripts.plan_boundary_geometry_validation_metadata_national_rollout import (  # noqa: E402
    database_inventory,
)

SCHEMA_VERSION = (
    "boundary_geometry_validation_metadata_"
    "national_execution_orchestrator.v1"
)
PROPOSAL_SCHEMA = (
    "national_validation_metadata_"
    "execution_manifest_proposal.v1"
)
AUTHORIZED_SCHEMA = (
    "national_validation_metadata_"
    "execution_manifest_authorization.v1"
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest-json",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--manifest-checksum",
        required=True,
    )
    parser.add_argument(
        "--national-plan-checksum",
        required=True,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--enable-national-validation-metadata-write",
        action="store_true",
    )
    parser.add_argument("--plan-reviewed", action="store_true")
    parser.add_argument("--integrity-audit-reviewed", action="store_true")
    parser.add_argument("--rollback-procedure-reviewed", action="store_true")
    parser.add_argument("--admin-confirmation", action="store_true")
    return parser.parse_args()


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError("MANIFEST_JSON_NOT_FOUND")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("MANIFEST_JSON_INVALID") from exc
    if not isinstance(value, dict):
        raise ValueError("MANIFEST_JSON_INVALID")
    return value


def manifest_checksum(manifest: dict[str, Any]) -> str:
    states = manifest.get("states") or []
    payload = {
        "schema_version": manifest.get("schema_version"),
        "status": manifest.get("status"),
        "national_plan_checksum":
            manifest.get("national_plan_checksum"),
        "batch_limit": manifest.get("batch_limit"),
        "evidence": manifest.get("evidence") or {},
        "authorization":
            manifest.get("authorization") or {},
        "execution_policy":
            manifest.get("execution_policy") or {},
        "readiness": manifest.get("readiness") or {},
        "states": [
            {
                key: value
                for key, value in state.items()
                if key not in {"plan_json", "checkpoint_json"}
            }
            for state in states
        ],
    }
    return canonical_checksum(payload)


def structural_error(
    args: argparse.Namespace,
    manifest: dict[str, Any],
) -> str | None:
    schema = manifest.get("schema_version")
    if schema not in {PROPOSAL_SCHEMA, AUTHORIZED_SCHEMA}:
        return "MANIFEST_SCHEMA_MISMATCH"

    checksum = manifest_checksum(manifest)
    if manifest.get("manifest_checksum") != checksum:
        return "MANIFEST_CONTENT_CHECKSUM_MISMATCH"
    if args.manifest_checksum != checksum:
        return "EXPECTED_MANIFEST_CHECKSUM_MISMATCH"

    national_checksum = manifest.get("national_plan_checksum")
    if not national_checksum:
        return "NATIONAL_PLAN_CHECKSUM_REQUIRED"
    if args.national_plan_checksum != national_checksum:
        return "EXPECTED_NATIONAL_PLAN_CHECKSUM_MISMATCH"

    if int(manifest.get("batch_limit") or 0) != 500:
        return "MANIFEST_BATCH_LIMIT_MISMATCH"

    states = manifest.get("states") or []
    if len(states) != 36:
        return "EXACT_NATIONAL_STATE_COUNT_REQUIRED"

    slugs = [state.get("state_slug") for state in states]
    batches = [state.get("batch_id") for state in states]
    plans = [state.get("plan_checksum") for state in states]
    tokens = [state.get("rollback_token") for state in states]

    if (
        any(not value for value in slugs + batches + plans + tokens)
        or len(set(slugs)) != 36
        or len(set(batches)) != 36
        or len(set(plans)) != 36
        or len(set(tokens)) != 36
    ):
        return "MANIFEST_STATE_IDENTITY_NOT_UNIQUE"

    if any(
        int(state.get("selected_row_count") or 0) < 1
        or int(state.get("selected_row_count") or 0) > 500
        for state in states
    ):
        return "MANIFEST_STATE_ROW_COUNT_INVALID"

    return None


def authorization_error(
    args: argparse.Namespace,
    manifest: dict[str, Any],
) -> str:
    if args.apply == args.rollback:
        return "EXACTLY_ONE_OF_APPLY_OR_ROLLBACK_REQUIRED"

    structural = structural_error(args, manifest)
    if structural:
        return structural

    if (
        manifest.get("schema_version") == PROPOSAL_SCHEMA
        or manifest.get("status") != "AUTHORIZED"
    ):
        return "NATIONAL_EXECUTION_NOT_AUTHORIZED"

    authorization = manifest.get("authorization") or {}
    requested = (
        "rollback_authorized"
        if args.rollback
        else "apply_authorized"
    )
    if authorization.get(requested) is not True:
        return (
            "NATIONAL_ROLLBACK_NOT_AUTHORIZED"
            if args.rollback
            else "NATIONAL_APPLY_NOT_AUTHORIZED"
        )

    if not all(
        authorization.get(key)
        for key in [
            "operator",
            "approver",
            "approval_reference",
            "approved_at",
        ]
    ):
        return "NATIONAL_APPROVAL_IDENTITY_INCOMPLETE"

    state_permission = (
        "rollback_authorized"
        if args.rollback
        else "apply_authorized"
    )
    if not all(
        state.get(state_permission) is True
        for state in manifest["states"]
    ):
        return (
            "STATE_BATCH_ROLLBACK_NOT_AUTHORIZED"
            if args.rollback
            else "STATE_BATCH_APPLY_NOT_AUTHORIZED"
        )

    policy = manifest.get("execution_policy") or {}
    required_true = [
        "stop_on_first_failure",
        "one_state_batch_per_transaction",
        "exact_plan_checksum_required",
        "exact_source_checksum_required",
        "exact_import_batch_required",
        "exact_rollback_token_required",
        "validated_without_repair_only",
    ]
    if (
        any(policy.get(key) is not True for key in required_true)
        or int(policy.get("maximum_rows_per_transaction") or 0)
            != 500
    ):
        return "NATIONAL_EXECUTION_POLICY_INCOMPLETE"

    prohibited = [
        "geometry_repair_allowed",
        "runtime_eligibility_change_allowed",
        "candidate_activation_allowed",
        "candidate_promotion_allowed",
        "runtime_table_write_allowed",
        "runtime_lookup_enablement_allowed",
        "android_behavior_change_allowed",
    ]
    if any(policy.get(key) is not False for key in prohibited):
        return "PROHIBITED_NATIONAL_EXECUTION_POLICY_ENABLED"

    if not args.enable_national_validation_metadata_write:
        return "NATIONAL_METADATA_WRITE_FLAG_REQUIRED"
    if not args.plan_reviewed:
        return "NATIONAL_PLAN_REVIEW_REQUIRED"
    if not args.integrity_audit_reviewed:
        return "NATIONAL_INTEGRITY_AUDIT_REVIEW_REQUIRED"
    if not args.rollback_procedure_reviewed:
        return "ROLLBACK_PROCEDURE_REVIEW_REQUIRED"
    if not args.admin_confirmation:
        return "ADMIN_CONFIRMATION_REQUIRED"

    return "NATIONAL_EXECUTION_ENGINE_NOT_ENABLED"


def guardrails() -> dict[str, bool]:
    return {
        "database_writes_attempted": False,
        "validation_metadata_written": False,
        "validation_events_written": False,
        "geometry_repair_persisted": False,
        "runtime_eligibility_changed": False,
        "candidate_activation_changed": False,
        "candidate_promotion_changed": False,
        "runtime_tables_written": False,
        "runtime_lookup_enabled": False,
        "lgd_geography_overwritten": False,
        "android_behavior_changed": False,
    }


def write_audit(
    output_dir: Path,
    audit: dict[str, Any],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = (
        output_dir /
        "national_validation_metadata_execution_audit.json"
    )
    temporary = path.with_suffix(".json.writing")
    temporary.write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def main() -> int:
    args = arguments()
    _, before = database_inventory()

    try:
        manifest = load_manifest(args.manifest_json)
        error = authorization_error(args, manifest)
    except ValueError as exc:
        manifest = {}
        error = str(exc)

    _, after = database_inventory()

    audit = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": False,
        "mode": (
            "NATIONAL_VALIDATION_METADATA_ROLLBACK"
            if args.rollback
            else "NATIONAL_VALIDATION_METADATA_APPLY"
        ),
        "status": "REJECTED",
        "error": error,
        "manifest": {
            "path": str(args.manifest_json),
            "schema_version": manifest.get("schema_version"),
            "status": manifest.get("status"),
            "manifest_checksum":
                manifest.get("manifest_checksum"),
            "national_plan_checksum":
                manifest.get("national_plan_checksum"),
            "state_count":
                len(manifest.get("states") or []),
        },
        "expected": {
            "manifest_checksum": args.manifest_checksum,
            "national_plan_checksum":
                args.national_plan_checksum,
        },
        "confirmations": {
            "explicit_apply_requested": args.apply,
            "explicit_rollback_requested": args.rollback,
            "resume_requested": args.resume,
            "national_write_flag_enabled":
                args.enable_national_validation_metadata_write,
            "plan_reviewed": args.plan_reviewed,
            "integrity_audit_reviewed":
                args.integrity_audit_reviewed,
            "rollback_procedure_reviewed":
                args.rollback_procedure_reviewed,
            "admin_confirmation": args.admin_confirmation,
        },
        "database_counts": {
            "before": before,
            "after": after,
            "unchanged": before == after,
        },
        "guardrails": guardrails(),
    }

    output = write_audit(args.output_dir, audit)
    audit["output"] = str(output)

    print(json.dumps(audit, indent=2, sort_keys=True))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

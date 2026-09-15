#!/usr/bin/env python3
"""Fail-closed national validation-metadata execution orchestrator."""

from __future__ import annotations

import argparse
import json
import subprocess
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
from scripts import (  # noqa: E402
    apply_boundary_geometry_validation_metadata_authorized_state_batch
    as state_engine,
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
DISPATCH_CHECKPOINT_SCHEMA = (
    "national_validation_metadata_"
    "state_dispatch_checkpoint.v1"
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


def load_json_object(
    path: Path,
    error_prefix: str,
) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{error_prefix}_NOT_FOUND")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{error_prefix}_INVALID") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{error_prefix}_INVALID")
    return value


def sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def state_artifact_error(
    state: dict[str, Any],
) -> str | None:
    slug = state.get("state_slug") or "unknown"
    required = [
        "state_slug",
        "state_or_ut",
        "import_batch_id",
        "source_sha256",
        "source_feature_count",
        "database_not_validated_count",
        "database_validated_count",
        "batch_id",
        "plan_checksum",
        "selected_row_count",
        "first_source_feature_index",
        "last_source_feature_index",
        "rollback_token",
        "plan_json",
        "checkpoint_json",
    ]
    missing = [
        key for key in required
        if state.get(key) is None
    ]
    if missing:
        return (
            f"{slug}:MANIFEST_STATE_ARTIFACT_IDENTITY_INCOMPLETE:"
            + ",".join(missing)
        )

    try:
        plan_path = Path(state["plan_json"])
        checkpoint_path = Path(state["checkpoint_json"])
        plan = load_json_object(
            plan_path,
            "STATE_PLAN_JSON",
        )
        checkpoint = load_json_object(
            checkpoint_path,
            "STATE_CHECKPOINT_JSON",
        )
    except (KeyError, TypeError, ValueError) as exc:
        return f"{slug}:{exc}"

    scope = plan.get("scope") or {}
    source = plan.get("source") or {}
    batch = plan.get("batch") or {}
    rows = plan.get("rows") or []
    identity = checkpoint.get("identity") or {}

    if (
        plan.get("schema_version") !=
            "boundary_geometry_validation_metadata_"
            "bounded_state_plan.v1"
        or plan.get("healthy") is not True
        or plan.get("database_counts", {}).get("unchanged")
            is not True
    ):
        return f"{slug}:STATE_PLAN_NOT_HEALTHY"

    expected = {
        "state_slug": state["state_slug"],
        "state_or_ut": state["state_or_ut"],
        "import_batch_id": state["import_batch_id"],
        "source_sha256": state["source_sha256"],
        "batch_id": state["batch_id"],
        "plan_checksum": state["plan_checksum"],
        "selected_row_count":
            int(state["selected_row_count"]),
        "first_source_feature_index":
            state["first_source_feature_index"],
        "last_source_feature_index":
            state["last_source_feature_index"],
    }
    actual = {
        "state_slug": scope.get("state_slug"),
        "state_or_ut": scope.get("state_or_ut"),
        "import_batch_id": scope.get("import_batch_id"),
        "source_sha256": source.get("sha256"),
        "batch_id": batch.get("batch_id"),
        "plan_checksum": batch.get("plan_checksum"),
        "selected_row_count":
            int(batch.get("selected_row_count") or 0),
        "first_source_feature_index":
            batch.get("first_source_feature_index"),
        "last_source_feature_index":
            batch.get("last_source_feature_index"),
    }
    if actual != expected:
        return f"{slug}:STATE_PLAN_IDENTITY_MISMATCH"

    if state_engine.recompute_plan_checksum(plan) != expected[
        "plan_checksum"
    ]:
        return f"{slug}:STATE_PLAN_CONTENT_CHECKSUM_MISMATCH"

    if len(rows) != expected["selected_row_count"]:
        return f"{slug}:STATE_PLAN_ROW_COUNT_MISMATCH"
    if len(rows) < 1 or len(rows) > 500:
        return f"{slug}:STATE_PLAN_ROW_LIMIT_INVALID"

    indexes = [
        row.get("source_feature_index")
        for row in rows
    ]
    if (
        indexes != sorted(indexes)
        or len(indexes) != len(set(indexes))
        or indexes[0] != expected[
            "first_source_feature_index"
        ]
        or indexes[-1] != expected[
            "last_source_feature_index"
        ]
    ):
        return f"{slug}:STATE_PLAN_INDEX_BOUNDARY_MISMATCH"

    if not all(
        row.get("classification") == "VALIDATED_NO_REPAIR"
        and row.get("current_geometry_validation_status")
            == "NOT_VALIDATED"
        and row.get("planned_geometry_validation_status")
            == "VALIDATED"
        and row.get("runtime_eligibility_change_planned")
            is False
        and row.get("source_feature_id")
        for row in rows
    ):
        return f"{slug}:STATE_PLAN_CONTAINS_UNSAFE_ROWS"

    if checkpoint.get("schema_version") != (
        "boundary_geometry_validation_metadata_"
        "national_state_checkpoint.v1"
    ):
        return f"{slug}:STATE_CHECKPOINT_SCHEMA_MISMATCH"
    if (
        checkpoint.get("plan_checksum") !=
            expected["plan_checksum"]
        or checkpoint.get("batch_id") !=
            expected["batch_id"]
    ):
        return f"{slug}:STATE_CHECKPOINT_BATCH_MISMATCH"

    checkpoint_expected = {
        "state_slug": expected["state_slug"],
        "state_or_ut": expected["state_or_ut"],
        "import_batch_id": expected["import_batch_id"],
        "source_sha256": expected["source_sha256"],
        "source_feature_count":
            int(state["source_feature_count"]),
        "database_not_validated_count":
            int(state["database_not_validated_count"]),
        "database_validated_count":
            int(state["database_validated_count"]),
        "batch_limit": 500,
    }
    if identity != checkpoint_expected:
        return f"{slug}:STATE_CHECKPOINT_IDENTITY_MISMATCH"

    source_path_value = source.get("path")
    if not source_path_value:
        return f"{slug}:SOURCE_PATH_REQUIRED"
    source_path = Path(source_path_value)
    if not source_path.is_file():
        return f"{slug}:SOURCE_FILE_NOT_FOUND"
    if sha256_file(source_path) != expected["source_sha256"]:
        return f"{slug}:CURRENT_SOURCE_CHECKSUM_MISMATCH"

    return None


def manifest_artifact_errors(
    manifest: dict[str, Any],
) -> list[str]:
    return [
        error
        for state in manifest.get("states") or []
        if (error := state_artifact_error(state)) is not None
    ]


def state_authorization_document(
    manifest: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    approval = manifest.get("authorization") or {}
    policy = manifest.get("execution_policy") or {}

    authorization = {
        "schema_version": state_engine.AUTHORIZATION_SCHEMA,
        "status": "AUTHORIZED",
        "national_plan_checksum":
            manifest["national_plan_checksum"],
        "state": {
            "state_slug": state["state_slug"],
            "state_or_ut": state["state_or_ut"],
            "import_batch_id": state["import_batch_id"],
            "source_sha256": state["source_sha256"],
            "batch_id": state["batch_id"],
            "plan_checksum": state["plan_checksum"],
            "selected_row_count":
                state["selected_row_count"],
            "first_source_feature_index":
                state["first_source_feature_index"],
            "last_source_feature_index":
                state["last_source_feature_index"],
            "rollback_token": state["rollback_token"],
        },
        "approval": {
            "operator": approval["operator"],
            "approver": approval["approver"],
            "approval_reference":
                approval["approval_reference"],
        },
        "permissions": {
            "apply_authorized":
                state["apply_authorized"],
            "rollback_authorized":
                state["rollback_authorized"],
            "maximum_row_count":
                policy["maximum_rows_per_transaction"],
            "validated_without_repair_only":
                policy["validated_without_repair_only"],
            "geometry_repair_allowed":
                policy["geometry_repair_allowed"],
            "runtime_eligibility_change_allowed":
                policy["runtime_eligibility_change_allowed"],
            "candidate_write_allowed": (
                policy["candidate_activation_allowed"]
                or policy["candidate_promotion_allowed"]
            ),
            "runtime_table_write_allowed":
                policy["runtime_table_write_allowed"],
            "runtime_lookup_enablement_allowed":
                policy["runtime_lookup_enablement_allowed"],
            "android_behavior_change_allowed":
                policy["android_behavior_change_allowed"],
        },
    }
    authorization["authorization_checksum"] = (
        state_engine.authorization_checksum(authorization)
    )
    return authorization



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


def ordered_dispatch_states(
    manifest: dict[str, Any],
    *,
    rollback: bool,
) -> list[dict[str, Any]]:
    states = list(manifest.get("states") or [])
    return sorted(
        states,
        key=lambda state: (
            int(state.get("sequence") or 0),
            str(state.get("state_slug") or ""),
        ),
        reverse=rollback,
    )


def state_dispatch_paths(
    output_dir: Path,
    state: dict[str, Any],
) -> dict[str, Path]:
    state_dir = (
        output_dir
        / "states"
        / f"{int(state['sequence']):02d}-{state['state_slug']}"
    )
    return {
        "state_dir": state_dir,
        "authorization_json":
            state_dir / "authorization.json",
        "engine_output_dir":
            state_dir / "engine",
        "checkpoint_json":
            state_dir / "dispatch_checkpoint.json",
    }


def state_engine_command(
    *,
    manifest: dict[str, Any],
    state: dict[str, Any],
    authorization: dict[str, Any],
    authorization_json: Path,
    engine_output_dir: Path,
    rollback: bool,
) -> list[str]:
    approval = manifest["authorization"]
    return [
        sys.executable,
        str(Path(state_engine.__file__).resolve()),
        "--authorization-json",
        str(authorization_json),
        "--authorization-checksum",
        authorization["authorization_checksum"],
        "--national-plan-checksum",
        manifest["national_plan_checksum"],
        "--plan-json",
        str(state["plan_json"]),
        "--plan-checksum",
        state["plan_checksum"],
        "--source-sha256",
        state["source_sha256"],
        "--rollback-token",
        state["rollback_token"],
        "--output-dir",
        str(engine_output_dir),
        "--operator",
        approval["operator"],
        "--approver",
        approval["approver"],
        "--approval-reference",
        approval["approval_reference"],
        "--rollback" if rollback else "--apply",
        "--enable-validation-metadata-write",
        "--dry-run-reviewed",
        "--event-schema-reviewed",
        "--admin-confirmation",
    ]


def dispatch_checkpoint_checksum(
    checkpoint: dict[str, Any],
) -> str:
    return canonical_checksum({
        key: value
        for key, value in checkpoint.items()
        if key != "checkpoint_checksum"
    })


def successful_dispatch_checkpoint(
    *,
    manifest: dict[str, Any],
    state: dict[str, Any],
    authorization: dict[str, Any],
    mode: str,
    audit_json: Path,
) -> dict[str, Any]:
    checkpoint = {
        "schema_version": DISPATCH_CHECKPOINT_SCHEMA,
        "status": "SUCCEEDED",
        "mode": mode,
        "manifest_checksum": manifest["manifest_checksum"],
        "national_plan_checksum":
            manifest["national_plan_checksum"],
        "state_sequence": int(state["sequence"]),
        "state_slug": state["state_slug"],
        "batch_id": state["batch_id"],
        "plan_checksum": state["plan_checksum"],
        "source_sha256": state["source_sha256"],
        "rollback_token": state["rollback_token"],
        "authorization_checksum":
            authorization["authorization_checksum"],
        "audit_json": str(audit_json),
    }
    checkpoint["checkpoint_checksum"] = (
        dispatch_checkpoint_checksum(checkpoint)
    )
    return checkpoint


def reusable_dispatch_checkpoint_error(
    *,
    checkpoint_path: Path,
    manifest: dict[str, Any],
    state: dict[str, Any],
    authorization: dict[str, Any],
    mode: str,
) -> str | None:
    try:
        checkpoint = load_json_object(
            checkpoint_path,
            "DISPATCH_CHECKPOINT_JSON",
        )
    except ValueError as exc:
        return str(exc)

    expected = {
        "schema_version": DISPATCH_CHECKPOINT_SCHEMA,
        "status": "SUCCEEDED",
        "mode": mode,
        "manifest_checksum": manifest["manifest_checksum"],
        "national_plan_checksum":
            manifest["national_plan_checksum"],
        "state_sequence": int(state["sequence"]),
        "state_slug": state["state_slug"],
        "batch_id": state["batch_id"],
        "plan_checksum": state["plan_checksum"],
        "source_sha256": state["source_sha256"],
        "rollback_token": state["rollback_token"],
        "authorization_checksum":
            authorization["authorization_checksum"],
    }
    if any(
        checkpoint.get(key) != value
        for key, value in expected.items()
    ):
        return "DISPATCH_CHECKPOINT_IDENTITY_MISMATCH"

    if checkpoint.get("checkpoint_checksum") != (
        dispatch_checkpoint_checksum(checkpoint)
    ):
        return "DISPATCH_CHECKPOINT_CHECKSUM_MISMATCH"

    audit_value = checkpoint.get("audit_json")
    if not audit_value:
        return "DISPATCH_CHECKPOINT_AUDIT_REQUIRED"

    try:
        audit = load_json_object(
            Path(audit_value),
            "STATE_ENGINE_AUDIT_JSON",
        )
    except ValueError as exc:
        return str(exc)

    audit_error = state_engine_audit_error(
        audit=audit,
        manifest=manifest,
        state=state,
        authorization=authorization,
        mode=mode,
    )
    if audit_error:
        return audit_error

    return None


def state_engine_audit_error(
    *,
    audit: dict[str, Any],
    manifest: dict[str, Any],
    state: dict[str, Any],
    authorization: dict[str, Any],
    mode: str,
) -> str | None:
    expected_mode = (
        "AUTHORIZED_STATE_BATCH_VALIDATION_METADATA_ROLLBACK"
        if mode == "ROLLBACK"
        else "AUTHORIZED_STATE_BATCH_VALIDATION_METADATA_APPLY"
    )
    allowed_actions = (
        {"ROLLED_BACK", "IDEMPOTENT_ROLLBACK_NO_OP"}
        if mode == "ROLLBACK"
        else {"APPLIED", "IDEMPOTENT_NO_OP"}
    )

    if (
        audit.get("healthy") is not True
        or audit.get("mode") != expected_mode
        or audit.get("action") not in allowed_actions
        or audit.get("national_plan_checksum") !=
            manifest["national_plan_checksum"]
        or audit.get("plan_checksum") !=
            state["plan_checksum"]
        or audit.get("authorization_checksum") !=
            authorization["authorization_checksum"]
        or audit.get("rollback_token") !=
            state["rollback_token"]
        or audit.get("approval", {}).get(
            "approved_batch_id"
        ) != state["batch_id"]
        or int(
            audit.get("approval", {}).get(
                "approved_row_count"
            ) or 0
        ) != int(state["selected_row_count"])
    ):
        return "STATE_ENGINE_AUDIT_IDENTITY_MISMATCH"

    guardrail = audit.get("guardrails") or {}
    if any(
        guardrail.get(key) is not False
        for key in [
            "source_files_changed",
            "geometry_repair_persisted",
            "source_runtime_eligibility_changed",
            "boundary_candidates_promoted",
            "boundary_candidates_activated",
            "runtime_tables_written",
            "runtime_lookup_enabled",
            "lgd_geography_overwritten",
            "android_behavior_changed",
        ]
    ):
        return "STATE_ENGINE_AUDIT_GUARDRAIL_VIOLATION"

    return None


def dispatch_authorized_manifest(
    *,
    manifest: dict[str, Any],
    output_dir: Path,
    rollback: bool,
    resume: bool,
    runner=subprocess.run,
) -> dict[str, Any]:
    mode = "ROLLBACK" if rollback else "APPLY"
    results: list[dict[str, Any]] = []
    dispatched_count = 0
    resumed_count = 0

    for state in ordered_dispatch_states(
        manifest,
        rollback=rollback,
    ):
        authorization = state_authorization_document(
            manifest,
            state,
        )
        paths = state_dispatch_paths(output_dir, state)
        checkpoint_path = paths["checkpoint_json"]

        if checkpoint_path.exists():
            if not resume:
                return {
                    "healthy": False,
                    "status": "FAILED",
                    "mode": mode,
                    "error":
                        "STATE_DISPATCH_CHECKPOINT_EXISTS_USE_RESUME",
                    "failed_state": state["state_slug"],
                    "dispatched_state_count": dispatched_count,
                    "resumed_state_count": resumed_count,
                    "results": results,
                }

            checkpoint_error = (
                reusable_dispatch_checkpoint_error(
                    checkpoint_path=checkpoint_path,
                    manifest=manifest,
                    state=state,
                    authorization=authorization,
                    mode=mode,
                )
            )
            if checkpoint_error:
                return {
                    "healthy": False,
                    "status": "FAILED",
                    "mode": mode,
                    "error":
                        "STATE_DISPATCH_CHECKPOINT_REJECTED",
                    "detail": checkpoint_error,
                    "failed_state": state["state_slug"],
                    "dispatched_state_count": dispatched_count,
                    "resumed_state_count": resumed_count,
                    "results": results,
                }

            resumed_count += 1
            results.append({
                "sequence": int(state["sequence"]),
                "state_slug": state["state_slug"],
                "status": "RESUMED",
                "checkpoint_json": str(checkpoint_path),
            })
            continue

        atomic_write_json(
            paths["authorization_json"],
            authorization,
        )
        command = state_engine_command(
            manifest=manifest,
            state=state,
            authorization=authorization,
            authorization_json=paths["authorization_json"],
            engine_output_dir=paths["engine_output_dir"],
            rollback=rollback,
        )
        process = runner(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        dispatched_count += 1

        audit_path = (
            paths["engine_output_dir"]
            / "boundary_validation_metadata_"
              "authorized_state_batch_audit.json"
        )
        if process.returncode != 0:
            return {
                "healthy": False,
                "status": "FAILED",
                "mode": mode,
                "error": "STATE_ENGINE_PROCESS_FAILED",
                "failed_state": state["state_slug"],
                "state_engine_exit_code":
                    process.returncode,
                "state_engine_stdout":
                    process.stdout[-4000:],
                "state_engine_stderr":
                    process.stderr[-4000:],
                "dispatched_state_count": dispatched_count,
                "resumed_state_count": resumed_count,
                "results": results,
            }

        try:
            audit = load_json_object(
                audit_path,
                "STATE_ENGINE_AUDIT_JSON",
            )
        except ValueError as exc:
            return {
                "healthy": False,
                "status": "FAILED",
                "mode": mode,
                "error": str(exc),
                "failed_state": state["state_slug"],
                "dispatched_state_count": dispatched_count,
                "resumed_state_count": resumed_count,
                "results": results,
            }

        audit_error = state_engine_audit_error(
            audit=audit,
            manifest=manifest,
            state=state,
            authorization=authorization,
            mode=mode,
        )
        if audit_error:
            return {
                "healthy": False,
                "status": "FAILED",
                "mode": mode,
                "error": audit_error,
                "failed_state": state["state_slug"],
                "dispatched_state_count": dispatched_count,
                "resumed_state_count": resumed_count,
                "results": results,
            }

        checkpoint = successful_dispatch_checkpoint(
            manifest=manifest,
            state=state,
            authorization=authorization,
            mode=mode,
            audit_json=audit_path,
        )
        atomic_write_json(checkpoint_path, checkpoint)
        results.append({
            "sequence": int(state["sequence"]),
            "state_slug": state["state_slug"],
            "status": "DISPATCHED",
            "authorization_json":
                str(paths["authorization_json"]),
            "audit_json": str(audit_path),
            "checkpoint_json": str(checkpoint_path),
        })

    return {
        "healthy": True,
        "status": "COMPLETED",
        "mode": mode,
        "error": None,
        "failed_state": None,
        "state_count": len(results),
        "dispatched_state_count": dispatched_count,
        "resumed_state_count": resumed_count,
        "results": results,
    }


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

    sequences = [state.get("sequence") for state in states]
    if (
        any(not isinstance(value, int) for value in sequences)
        or sorted(sequences) != list(range(1, 37))
    ):
        return "MANIFEST_STATE_SEQUENCE_INVALID"

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

    if any(
        not isinstance(
            state.get("first_source_feature_index"),
            int,
        )
        or not isinstance(
            state.get("last_source_feature_index"),
            int,
        )
        or state["first_source_feature_index"] >
            state["last_source_feature_index"]
        or not state.get("plan_json")
        or not state.get("checkpoint_json")
        for state in states
    ):
        return "MANIFEST_STATE_DISPATCH_IDENTITY_INCOMPLETE"

    return None


def authorization_error(
    args: argparse.Namespace,
    manifest: dict[str, Any],
) -> str | None:
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

    return None


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
    dispatch: dict[str, Any] | None = None
    artifact_errors: list[str] = []

    try:
        manifest = load_manifest(args.manifest_json)
        error = authorization_error(args, manifest)

        if error is None:
            artifact_errors = manifest_artifact_errors(manifest)
            if artifact_errors:
                error = (
                    "MANIFEST_STATE_ARTIFACT_VALIDATION_FAILED"
                )

        if error is None:
            dispatch = dispatch_authorized_manifest(
                manifest=manifest,
                output_dir=args.output_dir / "dispatch",
                rollback=args.rollback,
                resume=args.resume,
            )
            if dispatch.get("healthy") is not True:
                error = (
                    dispatch.get("error")
                    or "NATIONAL_DISPATCH_FAILED"
                )
    except ValueError as exc:
        manifest = {}
        error = str(exc)

    _, after = database_inventory()
    completed = (
        error is None
        and dispatch is not None
        and dispatch.get("healthy") is True
    )
    dispatched_count = int(
        (dispatch or {}).get("dispatched_state_count") or 0
    )

    audit_guardrails = guardrails()
    audit_guardrails["database_writes_attempted"] = (
        dispatched_count > 0
    )
    audit_guardrails["validation_metadata_written"] = (
        dispatched_count > 0
    )
    audit_guardrails["validation_events_written"] = (
        dispatched_count > 0 and args.apply
    )

    audit = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": completed,
        "mode": (
            "NATIONAL_VALIDATION_METADATA_ROLLBACK"
            if args.rollback
            else "NATIONAL_VALIDATION_METADATA_APPLY"
        ),
        "status": "COMPLETED" if completed else "REJECTED",
        "error": error,
        "artifact_errors": artifact_errors,
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
        "dispatch": dispatch,
        "database_counts": {
            "before": before,
            "after": after,
            "unchanged": before == after,
        },
        "guardrails": audit_guardrails,
    }

    output = write_audit(args.output_dir, audit)
    audit["output"] = str(output)

    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0 if completed else 1


if __name__ == "__main__":
    raise SystemExit(main())

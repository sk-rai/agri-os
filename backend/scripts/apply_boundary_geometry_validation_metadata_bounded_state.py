#!/usr/bin/env python3
"""Approved bounded-state boundary validation metadata apply."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.database import engine  # noqa: E402
from scripts.plan_boundary_geometry_validation_metadata_bounded_state import (  # noqa: E402
    canonical_checksum,
)

SCHEMA_VERSION = (
    "boundary_geometry_validation_metadata_bounded_state_apply.v1"
)
EVENT_TABLE = "geography_boundary_validation_metadata_events"
SOURCE_TABLE = "geography_boundary_source_features"

SOURCE_SHA256 = (
    "46236e51de89a034b99863600b9f46d24a4ed3e01905362fc90ac4b73de20591"
)
PLAN_CHECKSUM = (
    "822ed7575c67de714e1599de243d7ecbd77828471de308c1a087ff38de12ef4d"
)
IMPORT_BATCH_ID = "0a93be10-e508-50b9-97ba-b43659899e9b"
STATE_SLUG = "andaman_and_nicobar_islands"
STATE_NAME = "Andaman and Nicobar Islands"

APPROVED_BATCH_ID = "cf20a985-31c8-550d-8898-51475b568fda"
APPROVED_OPERATOR = "admin-regression"
APPROVED_APPROVER = "admin-regression"
APPROVAL_REFERENCE = "user-authorization-2026-09-09"
APPROVED_ROLLBACK_TOKEN = (
    "andaman-boundary-validation-metadata-batch-1-20260909"
)
APPROVED_ROW_COUNT = 500
FIXTURE_IDS: list[str] = []
FIXTURE_INDEXES: list[int] = []
MARKER = "bounded_validation_metadata_apply"


class ControlledFailure(RuntimeError):
    pass


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-json", type=Path, required=True)
    parser.add_argument("--plan-checksum", required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--rollback-token", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--operator", required=True)
    parser.add_argument("--approver", required=True)
    parser.add_argument("--approval-reference", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument(
        "--enable-validation-metadata-write",
        action="store_true",
    )
    parser.add_argument("--dry-run-reviewed", action="store_true")
    parser.add_argument("--event-schema-reviewed", action="store_true")
    parser.add_argument("--admin-confirmation", action="store_true")
    parser.add_argument("--force-failure-after", type=int, default=0)
    return parser.parse_args()


def recompute_plan_checksum(plan: dict[str, Any]) -> str:
    scope = plan["scope"]
    source = plan["source"]
    payload = {
        "schema_version": plan["schema_version"],
        "state_slug": scope["state_slug"],
        "state_or_ut": scope["state_or_ut"],
        "import_batch_id": scope["import_batch_id"],
        "source_sha256": source["sha256"],
        "geometry_hash_algorithm": source["geometry_hash_algorithm"],
        "cursor_after_index": scope["cursor_after_index"],
        "limit": scope["limit"],
        "rows": plan["rows"],
    }
    return canonical_checksum(payload)


def validate(args: argparse.Namespace, plan: dict[str, Any]) -> None:
    if args.apply == args.rollback:
        raise ValueError("EXACTLY_ONE_OF_APPLY_OR_ROLLBACK_REQUIRED")
    if not args.enable_validation_metadata_write:
        raise ValueError("VALIDATION_METADATA_WRITE_FLAG_REQUIRED")
    if not args.dry_run_reviewed:
        raise ValueError("DRY_RUN_REVIEW_REQUIRED")
    if not args.event_schema_reviewed:
        raise ValueError("EVENT_SCHEMA_REVIEW_REQUIRED")
    if not args.admin_confirmation:
        raise ValueError("ADMIN_CONFIRMATION_REQUIRED")
    if args.operator != APPROVED_OPERATOR:
        raise ValueError("APPROVED_OPERATOR_MISMATCH")
    if args.approver != APPROVED_APPROVER:
        raise ValueError("APPROVED_APPROVER_MISMATCH")
    if args.approval_reference != APPROVAL_REFERENCE:
        raise ValueError("APPROVAL_REFERENCE_MISMATCH")
    if args.rollback_token != APPROVED_ROLLBACK_TOKEN:
        raise ValueError("APPROVED_ROLLBACK_TOKEN_MISMATCH")
    if args.source_sha256 != SOURCE_SHA256:
        raise ValueError("SOURCE_CHECKSUM_MISMATCH")
    if args.plan_checksum != PLAN_CHECKSUM:
        raise ValueError("PLAN_CHECKSUM_MISMATCH")
    if plan.get("healthy") is not True:
        raise ValueError("PLAN_NOT_HEALTHY")
    if (
        plan.get("schema_version")
        != "boundary_geometry_validation_metadata_bounded_state_plan.v1"
    ):
        raise ValueError("PLAN_SCHEMA_MISMATCH")
    if recompute_plan_checksum(plan) != PLAN_CHECKSUM:
        raise ValueError("PLAN_CONTENT_CHECKSUM_MISMATCH")

    scope = plan["scope"]
    source = plan["source"]
    rows = plan["rows"]

    if scope["state_slug"] != STATE_SLUG:
        raise ValueError("STATE_SLUG_MISMATCH")
    if scope["state_or_ut"] != STATE_NAME:
        raise ValueError("STATE_NAME_MISMATCH")
    if scope["import_batch_id"] != IMPORT_BATCH_ID:
        raise ValueError("IMPORT_BATCH_MISMATCH")
    if source["sha256"] != SOURCE_SHA256:
        raise ValueError("PLAN_SOURCE_CHECKSUM_MISMATCH")
    if (
        plan["batch"]["selected_row_count"] != APPROVED_ROW_COUNT
        or len(rows) != APPROVED_ROW_COUNT
    ):
        raise ValueError("EXACT_APPROVED_ROW_COUNT_REQUIRED")
    if plan["batch"].get("batch_id") != APPROVED_BATCH_ID:
        raise ValueError("APPROVED_BATCH_ID_MISMATCH")
    if plan["batch"].get("first_source_feature_index") != 0:
        raise ValueError("APPROVED_FIRST_INDEX_MISMATCH")
    if plan["batch"].get("last_source_feature_index") != 506:
        raise ValueError("APPROVED_LAST_INDEX_MISMATCH")

    if [row["source_feature_id"] for row in rows] != FIXTURE_IDS:
        raise ValueError("FIXTURE_IDS_MISMATCH")
    if [row["source_feature_index"] for row in rows] != FIXTURE_INDEXES:
        raise ValueError("FIXTURE_INDEXES_MISMATCH")
    if not all(
        row["classification"] == "VALIDATED_NO_REPAIR"
        and row["current_geometry_validation_status"] == "NOT_VALIDATED"
        and row["planned_geometry_validation_status"] == "VALIDATED"
        and row["runtime_eligibility_change_planned"] is False
        for row in rows
    ):
        raise ValueError("UNSAFE_FIXTURE_PLAN")


def snapshot_values(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_geometry_hash": row["source_geometry_hash"],
        "source_bbox": row["source_bbox"],
        "transformed_bbox": row["transformed_bbox"],
        "transformed_centroid": row["transformed_centroid"],
        "geometry_validation_status":
            row["geometry_validation_status"],
        "eligible_for_runtime_after_promotion":
            row["eligible_for_runtime_after_promotion"],
        "metadata": row["metadata"],
    }


def load_source(conn, feature_id: str, lock: bool = False) -> dict[str, Any]:
    suffix = " for update" if lock else ""
    row = conn.execute(text(f"""
        select
          id::text as source_feature_id,
          import_batch_id::text as import_batch_id,
          source_feature_index,
          source_vlcode,
          source_geometry_hash,
          source_bbox,
          transformed_bbox,
          transformed_centroid,
          geometry_validation_status,
          eligible_for_runtime_after_promotion,
          metadata
        from {SOURCE_TABLE}
        where id = cast(:feature_id as uuid)
        {suffix}
    """), {"feature_id": feature_id}).mappings().one()
    return dict(row)


def counts(conn) -> dict[str, int]:
    row = conn.execute(text(f"""
        select
          (select count(*) from {SOURCE_TABLE})
            as source_feature_rows,
          (select count(*) from {SOURCE_TABLE}
           where geometry_validation_status = 'NOT_VALIDATED')
            as not_validated_rows,
          (select count(*) from {SOURCE_TABLE}
           where geometry_validation_status = 'VALIDATED')
            as validated_rows,
          (select count(*) from {SOURCE_TABLE}
           where eligible_for_runtime_after_promotion = true)
            as runtime_eligible_source_rows,
          (select count(*) from {EVENT_TABLE})
            as validation_event_rows,
          (select count(*) from {EVENT_TABLE}
           where is_active = true)
            as active_validation_event_rows,
          (select count(*) from geography_boundary_crosswalk_candidates)
            as candidate_rows,
          (select count(*) from geography_boundary_crosswalk_candidates
           where is_active = true)
            as active_candidate_rows,
          (select count(*) from geography_boundary_crosswalk_candidates
           where promotion_status = 'PROMOTED')
            as promoted_candidate_rows,
          (select count(*) from geography_boundary_runtime_sets)
            as runtime_set_rows,
          (select count(*) from geography_boundary_runtime_features)
            as runtime_feature_rows,
          (select count(*) from geography_boundary_runtime_crosswalks)
            as runtime_crosswalk_rows
    """)).mappings().one()
    return {key: int(value or 0) for key, value in row.items()}


def event_id(feature_id: str, rollback_token: str) -> str:
    return str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        (
            f"agri-os:{SCHEMA_VERSION}:{feature_id}:"
            f"{PLAN_CHECKSUM}:{rollback_token}"
        ),
    ))


def insert_event(
    conn,
    current: dict[str, Any],
    planned: dict[str, Any],
    args: argparse.Namespace,
) -> str:
    identifier = event_id(
        current["source_feature_id"],
        args.rollback_token,
    )
    before = snapshot_values(current)
    conn.execute(text(f"""
        insert into {EVENT_TABLE} (
          id, source_feature_id, import_batch_id, source_system,
          state_or_ut, source_feature_index, source_sha256,
          plan_checksum, geometry_hash_algorithm, rollback_token,
          apply_status, before_values, planned_values, after_values,
          apply_report, rollback_report, metadata, applied_by,
          applied_at, is_active, version
        )
        values (
          cast(:id as uuid), cast(:source_feature_id as uuid),
          cast(:import_batch_id as uuid), 'NWDP_GSI_VILLAGE_BOUNDARY',
          :state_or_ut, :source_feature_index, :source_sha256,
          :plan_checksum, 'NWDP_GEOJSON_GEOMETRY_CANONICAL_V1',
          :rollback_token, 'PLANNED', cast(:before_values as jsonb),
          cast(:planned_values as jsonb), '{{}}'::jsonb, '{{}}'::jsonb,
          '{{}}'::jsonb, cast(:metadata as jsonb), :applied_by,
          now(), false, 'v1.0'
        )
    """), {
        "id": identifier,
        "source_feature_id": current["source_feature_id"],
        "import_batch_id": current["import_batch_id"],
        "state_or_ut": STATE_NAME,
        "source_feature_index": current["source_feature_index"],
        "source_sha256": SOURCE_SHA256,
        "plan_checksum": PLAN_CHECKSUM,
        "rollback_token": args.rollback_token,
        "before_values": json.dumps(before),
        "planned_values": json.dumps(planned),
        "metadata": json.dumps({
            "fixture": True,
            "schema_version": SCHEMA_VERSION,
        }),
        "applied_by": args.operator,
    })
    return identifier


def update_source(
    conn,
    current: dict[str, Any],
    planned: dict[str, Any],
    identifier: str,
    args: argparse.Namespace,
) -> None:
    metadata = dict(current.get("metadata") or {})
    metadata[MARKER] = {
        "event_id": identifier,
        "plan_checksum": PLAN_CHECKSUM,
        "rollback_token": args.rollback_token,
    }

    result = conn.execute(text(f"""
        update {SOURCE_TABLE}
        set
          source_geometry_hash = :source_geometry_hash,
          source_bbox = cast(:source_bbox as jsonb),
          transformed_bbox = cast(:transformed_bbox as jsonb),
          transformed_centroid = cast(:transformed_centroid as jsonb),
          geometry_validation_status = 'VALIDATED',
          metadata = cast(:metadata as jsonb)
        where id = cast(:feature_id as uuid)
          and geometry_validation_status = 'NOT_VALIDATED'
          and eligible_for_runtime_after_promotion = false
    """), {
        "feature_id": current["source_feature_id"],
        "source_geometry_hash": planned["source_geometry_hash"],
        "source_bbox": json.dumps(planned["source_bbox"]),
        "transformed_bbox": json.dumps(planned["transformed_bbox"]),
        "transformed_centroid":
            json.dumps(planned["transformed_centroid"]),
        "metadata": json.dumps(metadata),
    })
    if int(result.rowcount or 0) != 1:
        raise RuntimeError("SOURCE_UPDATE_COUNT_MISMATCH")


def activate_event(conn, identifier: str, after: dict[str, Any]) -> None:
    conn.execute(text(f"""
        update {EVENT_TABLE}
        set
          apply_status = 'APPLIED',
          after_values = cast(:after_values as jsonb),
          apply_report = cast(:apply_report as jsonb),
          is_active = true,
          updated_at = now()
        where id = cast(:id as uuid)
    """), {
        "id": identifier,
        "after_values": json.dumps(after),
        "apply_report": json.dumps({
            "schema_version": SCHEMA_VERSION,
            "result": "APPLIED",
        }),
    })


def active_events(conn, token: str) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(text(f"""
        select *
        from {EVENT_TABLE}
        where plan_checksum = :plan_checksum
          and rollback_token = :rollback_token
          and source_feature_id = any(cast(:ids as uuid[]))
        order by source_feature_index
    """), {
        "plan_checksum": PLAN_CHECKSUM,
        "rollback_token": token,
        "ids": FIXTURE_IDS,
    }).mappings()]


def apply_rows(conn, plan: dict[str, Any], args: argparse.Namespace):
    existing = active_events(conn, args.rollback_token)

    if len(existing) == len(FIXTURE_IDS) and all(
        row["apply_status"] == "APPLIED" and row["is_active"]
        for row in existing
    ):
        return "IDEMPOTENT_NO_OP", 0, 0

    if existing:
        raise ValueError("PARTIAL_OR_CONFLICTING_EVENT_SET")

    changed = 0
    event_count = 0

    for planned in plan["rows"]:
        current = load_source(
            conn,
            planned["source_feature_id"],
            lock=True,
        )
        if current["import_batch_id"] != IMPORT_BATCH_ID:
            raise ValueError("CURRENT_IMPORT_BATCH_MISMATCH")
        if current["geometry_validation_status"] != "NOT_VALIDATED":
            raise ValueError("CURRENT_STATUS_MISMATCH")
        if current["eligible_for_runtime_after_promotion"]:
            raise ValueError("CURRENT_RUNTIME_ELIGIBILITY_MISMATCH")

        identifier = insert_event(conn, current, planned, args)
        event_count += 1
        update_source(conn, current, planned, identifier, args)
        changed += 1
        after = load_source(conn, current["source_feature_id"])
        activate_event(conn, identifier, snapshot_values(after))

        if (
            args.force_failure_after
            and changed == args.force_failure_after
        ):
            raise ControlledFailure("FORCED_MID_BATCH_FAILURE")

    return "APPLIED", changed, event_count


def rollback_rows(conn, args: argparse.Namespace):
    events = active_events(conn, args.rollback_token)

    if len(events) == len(FIXTURE_IDS) and all(
        row["apply_status"] == "ROLLED_BACK"
        and not row["is_active"]
        for row in events
    ):
        return "IDEMPOTENT_ROLLBACK_NO_OP", 0, 0

    if len(events) != len(FIXTURE_IDS) or not all(
        row["apply_status"] == "APPLIED" and row["is_active"]
        for row in events
    ):
        raise ValueError("ACTIVE_APPLY_EVENT_SET_REQUIRED")

    changed = 0
    event_count = 0

    for event in events:
        before = event["before_values"]
        result = conn.execute(text(f"""
            update {SOURCE_TABLE}
            set
              source_geometry_hash = :source_geometry_hash,
              source_bbox = cast(:source_bbox as jsonb),
              transformed_bbox = cast(:transformed_bbox as jsonb),
              transformed_centroid =
                cast(:transformed_centroid as jsonb),
              geometry_validation_status = :status,
              eligible_for_runtime_after_promotion =
                :runtime_eligibility,
              metadata = cast(:metadata as jsonb)
            where id = :feature_id
        """), {
            "feature_id": event["source_feature_id"],
            "source_geometry_hash":
                before["source_geometry_hash"],
            "source_bbox": json.dumps(before["source_bbox"]),
            "transformed_bbox":
                json.dumps(before["transformed_bbox"]),
            "transformed_centroid":
                json.dumps(before["transformed_centroid"]),
            "status": before["geometry_validation_status"],
            "runtime_eligibility":
                before["eligible_for_runtime_after_promotion"],
            "metadata": json.dumps(before["metadata"]),
        })
        if int(result.rowcount or 0) != 1:
            raise RuntimeError("ROLLBACK_SOURCE_COUNT_MISMATCH")

        conn.execute(text(f"""
            update {EVENT_TABLE}
            set
              apply_status = 'ROLLED_BACK',
              rollback_report = cast(:report as jsonb),
              rolled_back_by = :operator,
              rolled_back_at = now(),
              is_active = false,
              updated_at = now()
            where id = :event_id
        """), {
            "event_id": event["id"],
            "operator": args.operator,
            "report": json.dumps({
                "schema_version": SCHEMA_VERSION,
                "result": "ROLLED_BACK",
            }),
        })
        changed += 1
        event_count += 1

    return "ROLLED_BACK", changed, event_count


def write_outputs(
    output_dir: Path,
    audit: dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / (
        "boundary_validation_metadata_bounded_state_apply_audit.json"
    )
    csv_path = output_dir / (
        "boundary_validation_metadata_bounded_state_apply_rows.csv"
    )
    audit["output_files"] = {
        "json": str(json_path),
        "csv": str(csv_path),
    }
    json_path.write_text(
        json.dumps(audit, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    fields = [
        "source_feature_id",
        "source_feature_index",
        "geometry_validation_status",
        "eligible_for_runtime_after_promotion",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(audit.get("final_rows") or [])


def main() -> int:
    global FIXTURE_IDS, FIXTURE_INDEXES
    args = arguments()
    plan = json.loads(args.plan_json.read_text(encoding="utf-8"))
    FIXTURE_IDS = [
        str(row.get("source_feature_id") or "")
        for row in plan.get("rows") or []
    ]
    FIXTURE_INDEXES = [
        int(row.get("source_feature_index"))
        for row in plan.get("rows") or []
    ]

    with engine.connect() as connection:
        initial_counts = counts(connection)

    try:
        validate(args, plan)

        with engine.begin() as connection:
            before = counts(connection)
            if args.apply:
                action, changed, event_changed = apply_rows(
                    connection,
                    plan,
                    args,
                )
            else:
                action, changed, event_changed = rollback_rows(
                    connection,
                    args,
                )
            after_transaction = counts(connection)

        error = None
        healthy = True

    except (ValueError, ControlledFailure, RuntimeError) as exc:
        action = "ROLLED_BACK_TRANSACTION"
        changed = 0
        event_changed = 0
        before = initial_counts
        after_transaction = initial_counts
        error = str(exc)
        healthy = False

    with engine.connect() as connection:
        final_counts = counts(connection)
        final_rows = [
            load_source(connection, feature_id)
            for feature_id in FIXTURE_IDS
        ]

    persisted = action in {"APPLIED", "ROLLED_BACK"}
    audit = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": healthy,
        "mode": (
            "BOUNDED_STATE_VALIDATION_METADATA_ROLLBACK"
            if args.rollback
            else "BOUNDED_STATE_VALIDATION_METADATA_APPLY"
        ),
        "action": action,
        "error": error,
        "changed_source_row_count": changed,
        "changed_event_row_count": event_changed,
        "plan_checksum": args.plan_checksum,
        "rollback_token": args.rollback_token,
        "approval": {
            "operator": args.operator,
            "approver": args.approver,
            "approval_reference": args.approval_reference,
            "approved_batch_id": APPROVED_BATCH_ID,
            "approved_row_count": APPROVED_ROW_COUNT,
        },
        "policy": {
            "exact_approved_batch_only": True,
            "maximum_row_count": 500,
            "validated_without_repair_only": True,
            "runtime_eligibility_change_allowed": False,
            "candidate_write_allowed": False,
            "runtime_table_write_allowed": False,
            "runtime_lookup_enablement_allowed": False,
            "android_behavior_change_allowed": False,
        },
        "before_counts": before,
        "after_transaction_counts": after_transaction,
        "final_counts": final_counts,
        "final_rows": final_rows,
        "guardrails": {
            "db_writes_attempted":
                action in {"APPLIED", "ROLLED_BACK"}
                or error == "FORCED_MID_BATCH_FAILURE",
            "transaction_changes_persisted": persisted,
            "source_files_changed": False,
            "geometry_repair_persisted": False,
            "source_runtime_eligibility_changed": False,
            "boundary_candidates_promoted": False,
            "boundary_candidates_activated": False,
            "runtime_tables_written": False,
            "runtime_lookup_enabled": False,
            "lgd_geography_overwritten": False,
            "android_behavior_changed": False,
        },
    }
    write_outputs(args.output_dir, audit)
    print(json.dumps(audit, indent=2, sort_keys=True, default=str))
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())

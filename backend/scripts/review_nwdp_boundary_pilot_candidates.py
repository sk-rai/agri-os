#!/usr/bin/env python3
"""Guarded reviewer-metadata updater for NWDP boundary pilot candidates.

Default mode is dry-run. With --apply, it updates review metadata only for the
selected DIRECT_VLCODE_MATCH pilot candidates that already have materialized
geometry. It does not activate candidates, promote candidates, write runtime
tables, enable runtime lookup, or change Android behavior.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DEFAULT_OUTPUT = Path("/tmp/nwdp-boundary-pilot-reviewer-metadata.json")
RUNTIME_TABLES = [
    "geography_boundary_runtime_sets",
    "geography_boundary_runtime_features",
    "geography_boundary_runtime_crosswalks",
    "geography_boundary_runtime_promotion_events",
]


def db_url_from_settings() -> str:
    from app.core.config import settings

    value = (
        getattr(settings, "database_url", None)
        or getattr(settings, "DATABASE_URL", None)
        or getattr(settings, "sqlalchemy_database_uri", None)
        or getattr(settings, "SQLALCHEMY_DATABASE_URI", None)
        or getattr(settings, "postgres_url", None)
        or getattr(settings, "POSTGRES_URL", None)
    )
    return str(value or "postgresql+psycopg2://agri_os:agri_os_dev@localhost:5432/agri_os")


def json_default(value: Any) -> str:
    return str(value)


def runtime_counts(conn) -> dict[str, int]:
    from sqlalchemy import text

    return {table: int(conn.execute(text(f"select count(*) from {table}")).scalar() or 0) for table in RUNTIME_TABLES}


def select_pilot_rows(conn, state_or_ut: str, source_system: str, limit: int) -> list[dict[str, Any]]:
    from sqlalchemy import text

    return [dict(row) for row in conn.execute(text("""
        select
          c.id::text as candidate_id,
          c.source_feature_id::text,
          c.source_feature_index,
          c.candidate_bucket,
          c.review_status,
          c.reviewer_decision,
          c.promotion_status,
          c.proposed_scope,
          c.proposed_village_lgd_code,
          c.proposed_village_id::text,
          c.is_active,
          c.metadata,
          f.source_district_name,
          f.source_subdistrict_name,
          f.source_block_name,
          f.source_village_name,
          f.source_vlcode,
          f.source_geometry_hash,
          f.transformed_bbox,
          f.transformed_centroid,
          f.geometry_validation_status,
          f.metadata as source_feature_metadata
        from geography_boundary_crosswalk_candidates c
        join geography_boundary_source_features f on f.id = c.source_feature_id
        join geography_boundary_import_batches b on b.id = c.import_batch_id
        where b.state_or_ut = :state_or_ut
          and b.source_system = :source_system
          and c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
          and c.is_active = false
          and c.promotion_status = 'NOT_PROMOTED'
          and c.proposed_scope in ('village', 'village_review')
          and c.proposed_village_id is not null
          and f.metadata ? 'pilot_geometry_materialized_at'
        order by f.source_district_name, f.source_subdistrict_name, c.source_feature_index
        limit :limit
    """), {
        "state_or_ut": state_or_ut,
        "source_system": source_system,
        "limit": limit,
    }).mappings().all()]


def row_ready(row: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons = []
    if row["candidate_bucket"] != "DIRECT_VLCODE_MATCH":
        reasons.append("candidate bucket is not DIRECT_VLCODE_MATCH")
    if row["is_active"]:
        reasons.append("candidate is active")
    if row["promotion_status"] != "NOT_PROMOTED":
        reasons.append("candidate is already promoted/superseded")
    if row["proposed_scope"] not in {"village", "village_review"}:
        reasons.append("candidate scope is not village runtime eligible")
    if not row["proposed_village_id"]:
        reasons.append("candidate is missing proposed village id")
    if row["source_vlcode"] != row["proposed_village_lgd_code"]:
        reasons.append("source vlcode does not match proposed village LGD code")
    if row["geometry_validation_status"] not in {"VALID", "VALIDATED"}:
        reasons.append("geometry is not validated")
    if not row["source_geometry_hash"]:
        reasons.append("source geometry hash is missing")
    if not row["transformed_bbox"] or row["transformed_bbox"] == []:
        reasons.append("transformed bbox is missing")
    if not row["transformed_centroid"] or row["transformed_centroid"] == {}:
        reasons.append("transformed centroid is missing")
    return not reasons, reasons


def build_plan(rows: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(row["review_status"] for row in rows)
    decision_counts = Counter(row["reviewer_decision"] or "NONE" for row in rows)
    ready_items = []
    blocked_items = []

    for row in rows:
        ready, reasons = row_ready(row)
        item = {
            "candidate_id": row["candidate_id"],
            "source_feature_id": row["source_feature_id"],
            "source_feature_index": row["source_feature_index"],
            "source_district_name": row["source_district_name"],
            "source_subdistrict_name": row["source_subdistrict_name"],
            "source_block_name": row["source_block_name"],
            "source_village_name": row["source_village_name"],
            "source_vlcode": row["source_vlcode"],
            "proposed_village_lgd_code": row["proposed_village_lgd_code"],
            "source_vlcode_matches_proposed_lgd": row["source_vlcode"] == row["proposed_village_lgd_code"],
            "review_status": row["review_status"],
            "reviewer_decision": row["reviewer_decision"],
            "planned_review_status": "APPROVED_FOR_PROMOTION",
            "planned_reviewer_decision": "ACCEPT_DIRECT_CODE_MATCH",
            "geometry_validation_status": row["geometry_validation_status"],
            "source_geometry_hash_present": bool(row["source_geometry_hash"]),
            "transformed_bbox_present": bool(row["transformed_bbox"] and row["transformed_bbox"] != []),
            "transformed_centroid_present": bool(row["transformed_centroid"] and row["transformed_centroid"] != {}),
            "runtime_write_planned": False,
            "activation_planned": False,
            "promotion_planned": False,
        }
        if ready:
            ready_items.append(item)
        else:
            item["blocked_reasons"] = reasons
            blocked_items.append(item)

    return {
        "selected_candidate_count": len(rows),
        "ready_for_reviewer_metadata_update_count": len(ready_items),
        "blocked_candidate_count": len(blocked_items),
        "review_status_counts": dict(sorted(status_counts.items())),
        "reviewer_decision_counts": dict(sorted(decision_counts.items())),
        "planned_review_status": "APPROVED_FOR_PROMOTION",
        "planned_reviewer_decision": "ACCEPT_DIRECT_CODE_MATCH",
        "runtime_write_count": 0,
        "activation_count": 0,
        "promotion_count": 0,
        "ready_items": ready_items,
        "blocked_items": blocked_items,
    }


def apply_review_metadata(conn, rows: list[dict[str, Any]], actor_id: str, notes: str) -> int:
    from sqlalchemy import text

    now = datetime.now(timezone.utc)
    updated = 0

    for row in rows:
        metadata = dict(row["metadata"] or {})
        history = list(metadata.get("review_history") or [])
        event = {
            "changed_at": now.isoformat(),
            "changed_by": actor_id,
            "from_review_status": row["review_status"],
            "to_review_status": "APPROVED_FOR_PROMOTION",
            "from_reviewer_decision": row["reviewer_decision"],
            "to_reviewer_decision": "ACCEPT_DIRECT_CODE_MATCH",
            "reviewer_notes": notes,
            "evidence_summary": {
                "pilot_checkpoint": "nwdp_boundary_direct_code_geometry_materialized",
                "source_vlcode_matches_proposed_lgd": row["source_vlcode"] == row["proposed_village_lgd_code"],
                "geometry_validation_status": row["geometry_validation_status"],
                "source_geometry_hash_present": bool(row["source_geometry_hash"]),
                "runtime_write_planned": False,
            },
            "action": "NWDP_BOUNDARY_PILOT_REVIEW_METADATA_ONLY_NO_ACTIVATION",
        }
        history.append(event)
        metadata["review_history"] = history
        metadata["latest_review_event"] = event
        metadata["pilot_review_checkpoint"] = {
            "review_status": "APPROVED_FOR_PROMOTION",
            "reviewer_decision": "ACCEPT_DIRECT_CODE_MATCH",
            "runtime_write_planned": False,
            "activation_planned": False,
            "promotion_planned": False,
            "updated_at": now.isoformat(),
        }
        metadata["review_guardrail"] = {
            "is_active_remains_false": True,
            "promotion_status_remains_not_promoted": True,
            "runtime_spatial_matching_changed": False,
            "android_behavior_changed": False,
        }

        result = conn.execute(text("""
            update geography_boundary_crosswalk_candidates
            set
              review_status = 'APPROVED_FOR_PROMOTION',
              reviewer_decision = 'ACCEPT_DIRECT_CODE_MATCH',
              reviewer_id = :reviewer_id,
              reviewed_at = :reviewed_at,
              reviewer_notes = :reviewer_notes,
              metadata = cast(:metadata as jsonb),
              updated_at = :updated_at
            where id = :candidate_id
              and candidate_bucket = 'DIRECT_VLCODE_MATCH'
              and is_active = false
              and promotion_status = 'NOT_PROMOTED'
        """), {
            "candidate_id": row["candidate_id"],
            "reviewer_id": actor_id,
            "reviewed_at": now,
            "reviewer_notes": notes,
            "metadata": json.dumps(metadata),
            "updated_at": now,
        })
        updated += int(result.rowcount or 0)

    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description="Guarded reviewer-metadata updater for NWDP boundary pilot candidates.")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--state-or-ut", default="Karnataka")
    parser.add_argument("--source-system", default="NWDP_GSI_VILLAGE_BOUNDARY")
    parser.add_argument("--actor-id", default="pilot-review-checkpoint")
    parser.add_argument("--reviewer-notes", default="Pilot direct-code boundary candidate approved after staged geometry materialization checkpoint; no runtime rows written.")
    args = parser.parse_args()

    from sqlalchemy import create_engine

    engine = create_engine(db_url_from_settings())

    with engine.begin() as conn:
        before_runtime = runtime_counts(conn)
        rows = select_pilot_rows(conn, args.state_or_ut, args.source_system, args.limit)
        plan = build_plan(rows)

        if plan["blocked_candidate_count"]:
            updated = 0
            healthy = False
            error = "PILOT_REVIEW_METADATA_BLOCKED_BY_PRECONDITION"
        elif args.apply:
            updated = apply_review_metadata(conn, rows, args.actor_id, args.reviewer_notes)
            healthy = updated == plan["ready_for_reviewer_metadata_update_count"] == args.limit
            error = None if healthy else "PILOT_REVIEW_METADATA_UPDATE_COUNT_MISMATCH"
        else:
            updated = 0
            healthy = plan["ready_for_reviewer_metadata_update_count"] == args.limit
            error = None if healthy else "PILOT_REVIEW_METADATA_DRY_RUN_NOT_READY"

        after_runtime = runtime_counts(conn)

    result = {
        "schema_version": "nwdp_boundary_pilot_reviewer_metadata.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": healthy,
        "error": error,
        "mode": "APPLY_REVIEW_METADATA_ONLY" if args.apply else "DRY_RUN_REVIEW_METADATA_ONLY",
        "apply_mode": bool(args.apply),
        "db_writes_attempted": bool(args.apply and not plan["blocked_candidate_count"]),
        "staging_review_rows_updated": updated,
        "runtime_tables_written": False,
        "runtime_rows_effective": 0,
        "runtime_spatial_matching_changed": False,
        "android_behavior_changed": False,
        "runtime_counts_before": before_runtime,
        "runtime_counts_after": after_runtime,
        "plan": plan,
        "readiness": {
            "pilot_geometry_materialized": plan["ready_for_reviewer_metadata_update_count"] == args.limit,
            "reviewer_metadata_applied": bool(args.apply and updated == args.limit),
            "ready_for_runtime_promotion_dry_run": bool(args.apply and updated == args.limit),
            "ready_for_runtime_spatial_matching": False,
            "android_behavior_changed": False,
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, default=json_default) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True, default=json_default))
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())

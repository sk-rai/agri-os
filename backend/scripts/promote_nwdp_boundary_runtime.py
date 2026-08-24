#!/usr/bin/env python3
"""Dry-run-first NWDP boundary runtime promotion importer.

It calculates promotion eligibility from inactive staging rows only. Apply is
allowed only behind an explicit tiny-pilot policy gate and writes inactive
runtime rows only; it does not activate runtime matching, promote staging
candidates, or change Android behavior.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

RUNTIME_TABLES = [
    "geography_boundary_runtime_sets",
    "geography_boundary_runtime_features",
    "geography_boundary_runtime_crosswalks",
    "geography_boundary_runtime_promotion_events",
]

DEFAULT_OUTPUT = Path("/tmp/nwdp-boundary-runtime-promotion-importer.json")


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


def table_check(conn) -> dict[str, Any]:
    from sqlalchemy import text

    tables = {}
    counts = {}
    for table in RUNTIME_TABLES:
        exists = conn.execute(text("""
            select exists (
              select 1 from information_schema.tables
              where table_schema = 'public' and table_name = :table
            )
        """), {"table": table}).scalar()
        tables[table] = bool(exists)
        counts[table] = int(conn.execute(text(f"select count(*) from {table}")).scalar() or 0) if exists else None

    return {
        "healthy": all(tables.values()),
        "tables": tables,
        "counts": counts,
        "missing_tables": [table for table, exists in tables.items() if not exists],
    }


def eligibility_case() -> str:
    return """
      case
        when c.review_status <> 'APPROVED_FOR_PROMOTION' then 'NOT_REVIEW_APPROVED'
        when c.reviewer_decision not in ('ACCEPT_DIRECT_CODE_MATCH', 'ACCEPT_REVIEWED_NAME_MATCH') then 'REVIEW_DECISION_NOT_PROMOTABLE'
        when c.candidate_bucket in ('SPECIAL_REFERENCE_FEATURE', 'DISTRICT_SCOPED_AMBIGUOUS', 'PARENT_SCOPED_NAME_AMBIGUOUS', 'PARENT_MATCH_VILLAGE_UNRESOLVED') then 'BUCKET_NOT_PROMOTABLE'
        when c.proposed_scope not in ('village', 'village_review') then 'SCOPE_NOT_RUNTIME_ELIGIBLE'
        when c.proposed_village_id is null then 'MISSING_PROPOSED_VILLAGE'
        when f.geometry_validation_status not in ('VALID', 'VALIDATED') then 'GEOMETRY_NOT_VALIDATED'
        else 'PROMOTABLE'
      end
    """



def stable_uuid(label: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, label))


def promotable_rows(conn, state_or_ut: str, source_system: str) -> list[dict[str, Any]]:
    from sqlalchemy import text

    return [dict(row) for row in conn.execute(text(f"""
      select
        c.id::text as candidate_id,
        c.import_batch_id::text,
        c.source_feature_id::text,
        c.source_feature_index,
        c.confidence,
        c.reviewer_decision,
        c.proposed_scope,
        c.proposed_state_id::text,
        c.proposed_district_id::text,
        c.proposed_block_id::text,
        c.proposed_village_id::text,
        c.proposed_state_lgd_code,
        c.proposed_district_lgd_code,
        c.proposed_block_lgd_code,
        c.proposed_village_lgd_code,
        c.source_codes,
        c.source_names,
        c.match_evidence,
        f.feature_category,
        f.source_properties,
        f.source_geometry_hash,
        f.source_bbox,
        f.transformed_bbox,
        f.transformed_centroid,
        f.geometry_validation_status,
        b.source_dataset,
        b.source_format,
        b.source_file_sha256,
        b.source_crs,
        b.source_epsg,
        {eligibility_case()} as eligibility
      from geography_boundary_crosswalk_candidates c
      join geography_boundary_source_features f on f.id = c.source_feature_id
      join geography_boundary_import_batches b on b.id = c.import_batch_id
      where c.is_active = false
        and c.promotion_status = 'NOT_PROMOTED'
        and b.state_or_ut = :state_or_ut
        and b.source_system = :source_system
      order by c.source_feature_index
    """), {"state_or_ut": state_or_ut, "source_system": source_system}).mappings().all() if row["eligibility"] == "PROMOTABLE"]


def apply_tiny_pilot_runtime(conn, rows: list[dict[str, Any]], plan: dict[str, Any], actor_id: str, state_or_ut: str, source_system: str) -> dict[str, Any]:
    from sqlalchemy import text

    now = datetime.now(timezone.utc)
    if len(rows) != 10:
        return {"healthy": False, "error": "TINY_PILOT_REQUIRES_EXACTLY_10_PROMOTABLE_CANDIDATES", "runtime_rows_written": 0}

    import_batch_ids = sorted({row["import_batch_id"] for row in rows})
    source_datasets = sorted({row["source_dataset"] for row in rows if row["source_dataset"]})
    source_formats = sorted({row["source_format"] for row in rows if row["source_format"]})
    source_file_sha256s = sorted({row["source_file_sha256"] for row in rows if row["source_file_sha256"]})
    source_crs_values = sorted({row["source_crs"] for row in rows if row["source_crs"]})
    source_epsg_values = sorted({row["source_epsg"] for row in rows if row["source_epsg"]})

    runtime_set_id = stable_uuid(f"nwdp-boundary-runtime-set|tiny-pilot|{state_or_ut}|{source_system}|{','.join(str(row['candidate_id']) for row in rows)}")
    promotion_event_id = stable_uuid(f"nwdp-boundary-runtime-promotion-event|tiny-pilot|{runtime_set_id}")

    guardrail = {
        "policy_gate": "TINY_PILOT_INACTIVE_RUNTIME_WRITE_ONLY",
        "candidate_count": len(rows),
        "runtime_set_active": False,
        "runtime_spatial_matching_changed": False,
        "android_behavior_changed": False,
        "lookup_api_enabled": False,
        "staging_candidates_activated": False,
        "staging_candidates_promoted": False,
    }

    conn.execute(text("""
        insert into geography_boundary_runtime_sets (
            id, source_system, source_dataset, state_or_ut, source_format,
            source_file_sha256, source_crs, source_epsg, runtime_crs,
            status, activation_status, created_by, review_summary,
            guardrail_metadata, metadata, is_active
        )
        values (
            :id, :source_system, :source_dataset, :state_or_ut, :source_format,
            :source_file_sha256, :source_crs, :source_epsg, 'EPSG:4326',
            'PILOT_IMPORTED_INACTIVE', 'INACTIVE', :created_by,
            cast(:review_summary as jsonb), cast(:guardrail_metadata as jsonb),
            cast(:metadata as jsonb), false
        )
    """), {
        "id": runtime_set_id,
        "source_system": source_system,
        "source_dataset": source_datasets[0] if source_datasets else "Village Boundary",
        "state_or_ut": state_or_ut,
        "source_format": source_formats[0] if source_formats else "SHP",
        "source_file_sha256": source_file_sha256s[0] if source_file_sha256s else None,
        "source_crs": source_crs_values[0] if source_crs_values else None,
        "source_epsg": source_epsg_values[0] if source_epsg_values else None,
        "created_by": actor_id,
        "review_summary": json.dumps(plan),
        "guardrail_metadata": json.dumps(guardrail),
        "metadata": json.dumps({"mode": "TINY_PILOT_RUNTIME_APPLY", "generated_at": now.isoformat()}),
    })

    conn.execute(text("""
        insert into geography_boundary_runtime_promotion_events (
            id, runtime_set_id, source_import_batch_id, promoted_by, promotion_mode,
            promotion_status, candidate_count, runtime_feature_count,
            runtime_crosswalk_count, dry_run_report, promotion_report,
            guardrail_metadata, metadata, is_active
        )
        values (
            :id, :runtime_set_id, :source_import_batch_id, :promoted_by,
            'TINY_PILOT_REVIEWED_BATCH', 'APPLIED', :candidate_count,
            :runtime_feature_count, :runtime_crosswalk_count,
            cast(:dry_run_report as jsonb), cast(:promotion_report as jsonb),
            cast(:guardrail_metadata as jsonb), cast(:metadata as jsonb), false
        )
    """), {
        "id": promotion_event_id,
        "runtime_set_id": runtime_set_id,
        "source_import_batch_id": import_batch_ids[0],
        "promoted_by": actor_id,
        "candidate_count": len(rows),
        "runtime_feature_count": len(rows),
        "runtime_crosswalk_count": len(rows),
        "dry_run_report": json.dumps(plan),
        "promotion_report": json.dumps({"runtime_set_id": runtime_set_id, "promotion_event_id": promotion_event_id}),
        "guardrail_metadata": json.dumps(guardrail),
        "metadata": json.dumps({"mode": "TINY_PILOT_RUNTIME_APPLY", "generated_at": now.isoformat()}),
    })

    for row in rows:
        runtime_feature_id = stable_uuid(f"nwdp-boundary-runtime-feature|{runtime_set_id}|{row['source_feature_id']}")
        runtime_crosswalk_id = stable_uuid(f"nwdp-boundary-runtime-crosswalk|{runtime_set_id}|{row['candidate_id']}")

        conn.execute(text("""
            insert into geography_boundary_runtime_features (
                id, runtime_set_id, source_feature_id, source_feature_index,
                source_codes, source_names, feature_category, geometry_wgs84,
                centroid_wgs84, bbox_wgs84, geometry_hash,
                geometry_validation_status, metadata, is_active
            )
            values (
                :id, :runtime_set_id, :source_feature_id, :source_feature_index,
                cast(:source_codes as jsonb), cast(:source_names as jsonb),
                :feature_category, '{}'::jsonb, cast(:centroid_wgs84 as jsonb),
                cast(:bbox_wgs84 as jsonb), :geometry_hash,
                :geometry_validation_status, cast(:metadata as jsonb), false
            )
        """), {
            "id": runtime_feature_id,
            "runtime_set_id": runtime_set_id,
            "source_feature_id": row["source_feature_id"],
            "source_feature_index": row["source_feature_index"],
            "source_codes": json.dumps(row["source_codes"] or {}),
            "source_names": json.dumps(row["source_names"] or {}),
            "feature_category": row["feature_category"],
            "centroid_wgs84": json.dumps(row["transformed_centroid"] or {}),
            "bbox_wgs84": json.dumps(row["transformed_bbox"] or []),
            "geometry_hash": row["source_geometry_hash"],
            "geometry_validation_status": row["geometry_validation_status"],
            "metadata": json.dumps({"source_bbox": row["source_bbox"], "runtime_geometry_payload_loaded": False}),
        })

        conn.execute(text("""
            insert into geography_boundary_runtime_crosswalks (
                id, runtime_set_id, runtime_feature_id, source_candidate_id,
                runtime_scope, state_id, district_id, block_id, village_id,
                state_lgd_code, district_lgd_code, block_lgd_code, village_lgd_code,
                confidence, reviewer_decision, promotion_event_id, metadata, is_active
            )
            values (
                :id, :runtime_set_id, :runtime_feature_id, :source_candidate_id,
                :runtime_scope, :state_id, :district_id, :block_id, :village_id,
                :state_lgd_code, :district_lgd_code, :block_lgd_code, :village_lgd_code,
                :confidence, :reviewer_decision, :promotion_event_id,
                cast(:metadata as jsonb), false
            )
        """), {
            "id": runtime_crosswalk_id,
            "runtime_set_id": runtime_set_id,
            "runtime_feature_id": runtime_feature_id,
            "source_candidate_id": row["candidate_id"],
            "runtime_scope": row["proposed_scope"],
            "state_id": row["proposed_state_id"],
            "district_id": row["proposed_district_id"],
            "block_id": row["proposed_block_id"],
            "village_id": row["proposed_village_id"],
            "state_lgd_code": row["proposed_state_lgd_code"],
            "district_lgd_code": row["proposed_district_lgd_code"],
            "block_lgd_code": row["proposed_block_lgd_code"],
            "village_lgd_code": row["proposed_village_lgd_code"],
            "confidence": row["confidence"],
            "reviewer_decision": row["reviewer_decision"],
            "promotion_event_id": promotion_event_id,
            "metadata": json.dumps({"match_evidence": row["match_evidence"], "inactive_pilot_crosswalk": True}),
        })

    return {
        "healthy": True,
        "runtime_set_id": runtime_set_id,
        "promotion_event_id": promotion_event_id,
        "runtime_rows_written": 1 + len(rows) + len(rows) + 1,
        "db_writes_attempted": True,
        "runtime_sets_written": 1,
        "runtime_features_written": len(rows),
        "runtime_crosswalks_written": len(rows),
        "promotion_events_written": 1,
    }



def promotion_plan(conn, state_or_ut: str, source_system: str, sample_limit: int) -> dict[str, Any]:
    from sqlalchemy import text

    base = """
      from geography_boundary_crosswalk_candidates c
      join geography_boundary_source_features f on f.id = c.source_feature_id
      join geography_boundary_import_batches b on b.id = c.import_batch_id
      where c.is_active = false
        and c.promotion_status = 'NOT_PROMOTED'
        and b.state_or_ut = :state_or_ut
        and b.source_system = :source_system
    """
    params = {"state_or_ut": state_or_ut, "source_system": source_system, "sample_limit": sample_limit}
    case_sql = eligibility_case()

    total = int(conn.execute(text(f"select count(*) {base}"), params).scalar() or 0)
    rows = conn.execute(text(f"""
      select {case_sql} as eligibility, count(*) as count
      {base}
      group by eligibility
      order by eligibility
    """), params).mappings().all()

    counts = {row["eligibility"]: int(row["count"]) for row in rows}
    promotable = counts.get("PROMOTABLE", 0)

    samples = conn.execute(text(f"""
      select
        c.id::text as candidate_id,
        c.source_feature_index,
        c.candidate_bucket,
        c.review_status,
        c.reviewer_decision,
        c.proposed_scope,
        c.proposed_village_lgd_code,
        f.source_district_name,
        f.source_subdistrict_name,
        f.source_village_name,
        f.source_vlcode,
        f.geometry_validation_status,
        {case_sql} as eligibility
      {base}
      order by c.source_feature_index
      limit :sample_limit
    """), params).mappings().all()

    return {
        "candidate_count": total,
        "promotable_candidate_count": promotable,
        "excluded_candidate_count": total - promotable,
        "eligibility_counts": [{"eligibility": key, "count": value} for key, value in sorted(counts.items())],
        "planned_runtime_set_insert_count": 1 if promotable else 0,
        "planned_runtime_feature_insert_count": promotable,
        "planned_runtime_crosswalk_insert_count": promotable,
        "sample_rows": [dict(row) for row in samples],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--state-or-ut", default="Karnataka")
    parser.add_argument("--source-system", default="NWDP_GSI_VILLAGE_BOUNDARY")
    parser.add_argument("--sample-limit", type=int, default=10)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow-tiny-pilot-runtime-write", action="store_true")
    parser.add_argument("--actor-id", default="runtime-promotion-pilot")
    args = parser.parse_args()

    from sqlalchemy import create_engine

    apply_result = {}
    apply_failed = False

    engine = create_engine(db_url_from_settings())
    with engine.begin() as conn:
        tables = table_check(conn)
        plan = promotion_plan(conn, args.state_or_ut, args.source_system, args.sample_limit) if tables["healthy"] else {}
        if args.apply and args.allow_tiny_pilot_runtime_write and tables["healthy"]:
            if any((tables.get("counts") or {}).values()):
                apply_result = {
                    "healthy": False,
                    "error": "RUNTIME_TABLES_NOT_EMPTY_TINY_PILOT_APPLY_REQUIRES_EMPTY_RUNTIME_TABLES",
                }
                apply_failed = True
            else:
                rows = promotable_rows(conn, args.state_or_ut, args.source_system)
                apply_result = apply_tiny_pilot_runtime(conn, rows, plan, args.actor_id, args.state_or_ut, args.source_system)
                apply_failed = not bool(apply_result.get("healthy"))
            tables = table_check(conn)

    apply_blocked = bool(args.apply and not args.allow_tiny_pilot_runtime_write)
    report = {
        "schema_version": "nwdp_boundary_runtime_promotion_importer.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": tables["healthy"] and not apply_blocked and not apply_failed,
        "apply_mode": bool(args.apply),
        "apply_blocked": apply_blocked,
        "db_writes_attempted": bool(apply_result.get("db_writes_attempted")),
        "runtime_tables_written": bool(apply_result.get("healthy")),
        "runtime_rows_effective": int(apply_result.get("runtime_rows_written") or 0),
        "claim_boundary": "Dry-run-first importer. Tiny-pilot apply writes inactive runtime rows only; lookup/Android remain disabled.",
        "target_table_check": tables,
        "apply_result": apply_result,
        "plan": plan,
        "readiness": {
            "runtime_tables_available": tables["healthy"],
            "ready_for_runtime_table_write": False,
            "ready_for_runtime_spatial_matching": False,
            "android_behavior_changed": False,
            "safe_read_only": not args.apply,
        },
    }
    if apply_blocked:
        report["error"] = "APPLY_BLOCKED_PENDING_REVIEWED_RUNTIME_PROMOTION_POLICY"
    if apply_failed:
        report["error"] = apply_result.get("error", "TINY_PILOT_RUNTIME_APPLY_FAILED")

    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

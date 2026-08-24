#!/usr/bin/env python3
"""Dry-run-first NWDP boundary runtime promotion importer.

It calculates promotion eligibility from inactive staging rows only.
Current --apply mode is blocked by design.
"""

from __future__ import annotations

import argparse
import json
import sys
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
    args = parser.parse_args()

    from sqlalchemy import create_engine

    engine = create_engine(db_url_from_settings())
    with engine.begin() as conn:
        tables = table_check(conn)
        plan = promotion_plan(conn, args.state_or_ut, args.source_system, args.sample_limit) if tables["healthy"] else {}

    apply_blocked = bool(args.apply)
    report = {
        "schema_version": "nwdp_boundary_runtime_promotion_importer.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": tables["healthy"] and not apply_blocked,
        "apply_mode": bool(args.apply),
        "apply_blocked": apply_blocked,
        "db_writes_attempted": False,
        "runtime_tables_written": False,
        "runtime_rows_effective": 0,
        "claim_boundary": "Dry-run-first importer. Current apply path is blocked; no runtime rows are written and lookup/Android remain disabled.",
        "target_table_check": tables,
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

    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Dry-run-first importer skeleton for NWDP boundary review staging.

Current behavior:
- reads candidate CSV;
- validates candidate buckets and inactive staging policy;
- checks whether migration 054 staging tables exist;
- refuses --apply until write path is intentionally implemented.

No database writes are performed.
"""

from __future__ import annotations

import argparse
import csv
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

DEFAULT_INPUT = Path("/tmp/nwdp-karnataka-boundary-crosswalk-candidates.csv")
DEFAULT_OUTPUT = Path("/tmp/nwdp-boundary-guarded-importer-dry-run.json")

TARGET_TABLES = [
    "geography_boundary_import_batches",
    "geography_boundary_source_features",
    "geography_boundary_crosswalk_candidates",
]

BUCKET_POLICY = {
    "DIRECT_VLCODE_MATCH": "STAGE_INACTIVE_AUTO_CANDIDATE",
    "DIRECT_VLCODE_PARENT_MISMATCH": "STAGE_INACTIVE_MANUAL_REVIEW",
    "PARENT_SCOPED_NAME_MATCH": "STAGE_INACTIVE_MANUAL_REVIEW",
    "PARENT_SCOPED_NAME_AMBIGUOUS": "STAGE_INACTIVE_MANUAL_REVIEW",
    "PARENT_MATCH_VILLAGE_UNRESOLVED": "STAGE_INACTIVE_PARENT_SCOPE_ONLY",
    "DISTRICT_SCOPED_AMBIGUOUS": "STAGE_INACTIVE_DISTRICT_REVIEW",
    "SPECIAL_REFERENCE_FEATURE": "STAGE_BLOCKED_REFERENCE_ONLY",
    "BLOCKED_SOURCE_CAVEAT": "STAGE_BLOCKED_SOURCE_CAVEAT",
}


def clean(value: Any) -> str:
    return str(value or "").strip()


def read_candidate_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = [{key: clean(value) for key, value in row.items()} for row in reader]
        return rows, list(reader.fieldnames or [])


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


def check_target_tables() -> dict[str, Any]:
    try:
        from sqlalchemy import create_engine, text
    except Exception as exc:
        return {
            "attempted": True,
            "healthy": False,
            "error": "SQLALCHEMY_NOT_AVAILABLE",
            "message": str(exc),
            "tables": {},
        }

    try:
        engine = create_engine(db_url_from_settings())
        with engine.connect() as conn:
            tables = {}
            for table in TARGET_TABLES:
                exists = conn.execute(
                    text("""
                        select exists (
                          select 1
                          from information_schema.tables
                          where table_schema = 'public'
                            and table_name = :table_name
                        )
                    """),
                    {"table_name": table},
                ).scalar()
                tables[table] = bool(exists)

        return {
            "attempted": True,
            "healthy": all(tables.values()),
            "tables": tables,
            "missing_tables": [table for table, exists in tables.items() if not exists],
        }
    except Exception as exc:
        return {
            "attempted": True,
            "healthy": False,
            "error": type(exc).__name__,
            "message": str(exc),
            "tables": {},
        }

def plan_import(rows: list[dict[str, str]], sample_limit: int) -> dict[str, Any]:
    bucket_counts = Counter()
    planned_action_counts = Counter()
    review_status_counts = Counter()
    unsafe_counts = Counter()
    seen_indexes = Counter()
    samples: dict[str, list[dict[str, Any]]] = {}

    for row in rows:
        index = clean(row.get("index"))
        bucket = clean(row.get("bucket"))
        review_status = clean(row.get("review_status"))
        action = BUCKET_POLICY.get(bucket)

        bucket_counts[bucket or "BLANK"] += 1
        review_status_counts[review_status or "BLANK"] += 1
        seen_indexes[index] += 1

        if not action:
            unsafe_counts["unknown_bucket"] += 1
            samples.setdefault("unknown_bucket", []).append(row)
            continue

        planned_action_counts[action] += 1

        if bucket == "DIRECT_VLCODE_MATCH" and not clean(row.get("backend_village_id")):
            unsafe_counts["direct_vlcode_match_missing_backend_village_id"] += 1

        if bucket == "DIRECT_VLCODE_MATCH" and review_status != "AUTO_CANDIDATE":
            unsafe_counts["direct_vlcode_match_not_auto_candidate"] += 1

        if bucket != "DIRECT_VLCODE_MATCH" and review_status == "AUTO_CANDIDATE":
            unsafe_counts["non_direct_candidate_marked_auto"] += 1

        if len(samples.setdefault(bucket, [])) < sample_limit:
            samples[bucket].append({
                "index": index,
                "bucket": bucket,
                "review_status": review_status,
                "planned_action": action,
                "district": clean(row.get("district")),
                "subdistrict": clean(row.get("subdistrict")),
                "block": clean(row.get("block")),
                "village": clean(row.get("village")),
                "vlcode": clean(row.get("vlcode")),
                "backend_village_id": clean(row.get("backend_village_id")),
            })

    duplicate_indexes = {key: count for key, count in seen_indexes.items() if key and count > 1}
    if duplicate_indexes:
        unsafe_counts["duplicate_source_feature_index"] += len(duplicate_indexes)

    return {
        "healthy": not unsafe_counts and not duplicate_indexes,
        "input_candidate_count": len(rows),
        "planned_batch_insert_count": 1 if rows else 0,
        "planned_source_feature_insert_count": len(rows),
        "planned_candidate_insert_count": len(rows),
        "planned_action_counts": dict(sorted(planned_action_counts.items())),
        "bucket_counts": dict(sorted(bucket_counts.items())),
        "review_status_counts": dict(sorted(review_status_counts.items())),
        "unsafe_counts": dict(sorted(unsafe_counts.items())),
        "duplicate_source_feature_index_count": len(duplicate_indexes),
        "duplicate_source_feature_index_samples": dict(list(duplicate_indexes.items())[:sample_limit]),
        "rows_planned_inactive": len(rows),
        "rows_effective_in_runtime": 0,
        "samples": samples,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run-first NWDP boundary staging importer skeleton.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--sample-limit", type=int, default=8)
    parser.add_argument("--apply", action="store_true", help="Currently refused; write path is not implemented.")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if args.apply:
        result = {
            "schema_version": "nwdp_boundary_guarded_importer_report.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "healthy": False,
            "error": "APPLY_NOT_IMPLEMENTED",
            "message": "Importer is currently dry-run only. No DB writes attempted.",
            "db_writes_attempted": False,
            "apply_mode": True,
            "readiness": {
                "safe_read_only": True,
                "ready_for_db_write_import": False,
                "ready_for_runtime_spatial_matching": False,
            },
        }
    elif not input_path.exists():
        result = {
            "schema_version": "nwdp_boundary_guarded_importer_report.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "healthy": False,
            "error": "INPUT_CSV_NOT_FOUND",
            "path": str(input_path),
            "db_writes_attempted": False,
        }
    else:
        rows, columns = read_candidate_rows(input_path)
        table_check = check_target_tables()
        import_plan = plan_import(rows, args.sample_limit)
        result = {
            "schema_version": "nwdp_boundary_guarded_importer_report.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": {
                "portal": "National Water Data Portal",
                "dataset": "Village Boundary",
                "producer_agency": "Geological Survey of India",
                "pilot_state_or_ut": "Karnataka",
                "candidate_input": str(input_path),
            },
            "claim_boundary": "Dry-run importer skeleton validates staged candidate import readiness only. It does not write database rows, import geometry, promote candidates, or enable runtime spatial matching.",
            "healthy": import_plan["healthy"],
            "apply_mode": False,
            "db_writes_attempted": False,
            "input_columns": columns,
            "target_table_check": table_check,
            "import_plan": import_plan,
            "readiness": {
                "safe_read_only": True,
                "candidate_plan_healthy": import_plan["healthy"],
                "staging_tables_available": table_check.get("healthy") is True,
                "ready_for_db_write_import": False,
                "ready_for_runtime_spatial_matching": False,
            },
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

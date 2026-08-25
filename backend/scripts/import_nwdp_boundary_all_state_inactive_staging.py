#!/usr/bin/env python3
"""Guarded all-state NWDP boundary inactive staging importer.

Default mode is dry-run. This checkpoint intentionally does not implement DB
writes yet. With --apply it remains blocked unless a later checkpoint implements
the state-by-state inactive staging write path.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DEFAULT_INPUT = Path("/tmp/nwdp-boundary-all-state-match-plan.csv")
DEFAULT_OUTPUT = Path("/tmp/nwdp-boundary-all-state-inactive-staging-import-report.json")
SOURCE_SYSTEM = "NWDP_GSI_VILLAGE_BOUNDARY"
SOURCE_DATASET = "Village Boundary"
SOURCE_PRODUCER_AGENCY = "Geological Survey of India"
SOURCE_FORMAT = "GeoJSON"
SOURCE_CRS = "WGS 84 / India NSF LCC"
SOURCE_EPSG = "7755"
TARGET_CRS = "EPSG:4326"
EXPECTED_STATE_COUNT = 36
EXPECTED_ROW_COUNT = 654_285

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
    "DISTRICT_ONLY_UNRESOLVED": "STAGE_INACTIVE_DISTRICT_REVIEW",
    "DISTRICT_SCOPED_AMBIGUOUS": "STAGE_INACTIVE_DISTRICT_REVIEW",
    "SPECIAL_REFERENCE_FEATURE": "STAGE_BLOCKED_REFERENCE_ONLY",
    "BLOCKED_SOURCE_CAVEAT": "STAGE_BLOCKED_SOURCE_CAVEAT",
}


def clean(value: Any) -> str:
    return str(value or "").strip()


def json_default(value: Any) -> str:
    return str(value)


def stable_uuid(label: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, label))


def batch_id_for(state_or_ut: str, source_file_sha256: str, input_path: Path) -> str:
    checksum_or_path = source_file_sha256 or f"NO_SOURCE_SHA::{input_path}"
    key = f"{SOURCE_SYSTEM}|{state_or_ut}|{SOURCE_FORMAT}|{checksum_or_path}"
    return stable_uuid(f"boundary-batch|{key}")


def feature_id_for(batch_id: str, index: str) -> str:
    return stable_uuid(f"boundary-source-feature|{batch_id}|{index}")


def candidate_id_for(batch_id: str, index: str) -> str:
    return stable_uuid(f"boundary-crosswalk-candidate|{batch_id}|{index}")


def planned_review_status(bucket: str, input_review_status: str) -> str:
    if bucket in {"SPECIAL_REFERENCE_FEATURE", "BLOCKED_SOURCE_CAVEAT"}:
        return "BLOCKED"
    return input_review_status or "MANUAL_REVIEW"


def feature_category(bucket: str) -> str:
    if bucket == "SPECIAL_REFERENCE_FEATURE":
        return "SPECIAL_FEATURE"
    if bucket == "BLOCKED_SOURCE_CAVEAT":
        return "REFERENCE_FEATURE"
    return "VILLAGE_BOUNDARY"


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
        return {"attempted": True, "healthy": False, "error": "SQLALCHEMY_NOT_AVAILABLE", "message": str(exc), "tables": {}}

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
        return {"attempted": True, "healthy": False, "error": type(exc).__name__, "message": str(exc), "tables": {}}


def read_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = [{key: clean(value) for key, value in row.items()} for row in reader]
        return rows, list(reader.fieldnames or [])


def filter_rows(rows: list[dict[str, str]], state_or_ut: str | None) -> list[dict[str, str]]:
    if not state_or_ut:
        return rows
    return [row for row in rows if clean(row.get("state_or_ut")) == state_or_ut]


def plan_import(rows: list[dict[str, str]], input_path: Path, source_file_sha256: str, sample_limit: int, expected_state_count: int | None = None, expected_row_count: int | None = None) -> dict[str, Any]:
    state_counts = Counter()
    bucket_counts = Counter()
    planned_action_counts = Counter()
    review_status_counts = Counter()
    planned_review_status_counts = Counter()
    feature_category_counts = Counter()
    proposed_scope_counts = Counter()
    unsafe_counts = Counter()
    duplicate_indexes_by_state: dict[str, Counter[str]] = defaultdict(Counter)
    samples: dict[str, list[dict[str, Any]]] = {}

    for row in rows:
        state_or_ut = clean(row.get("state_or_ut"))
        index = clean(row.get("source_feature_index") or row.get("index"))
        bucket = clean(row.get("candidate_bucket") or row.get("bucket"))
        review_status = clean(row.get("review_status"))
        action = BUCKET_POLICY.get(bucket)

        state_counts[state_or_ut or "BLANK"] += 1
        bucket_counts[bucket or "BLANK"] += 1
        review_status_counts[review_status or "BLANK"] += 1
        planned_review_status_counts[planned_review_status(bucket, review_status)] += 1
        feature_category_counts[feature_category(bucket)] += 1
        proposed_scope_counts[clean(row.get("proposed_scope"))] += 1
        duplicate_indexes_by_state[state_or_ut][index] += 1

        if not state_or_ut:
            unsafe_counts["missing_state_or_ut"] += 1
        if not index.isdigit():
            unsafe_counts["invalid_source_feature_index"] += 1
        if not action:
            unsafe_counts["unknown_bucket"] += 1
        else:
            planned_action_counts[action] += 1

        if bucket == "DIRECT_VLCODE_MATCH" and not clean(row.get("backend_village_id")):
            unsafe_counts["direct_vlcode_match_missing_backend_village_id"] += 1
        if bucket == "DIRECT_VLCODE_MATCH" and review_status != "AUTO_CANDIDATE":
            unsafe_counts["direct_vlcode_match_not_auto_candidate"] += 1
        if bucket != "DIRECT_VLCODE_MATCH" and review_status == "AUTO_CANDIDATE":
            unsafe_counts["non_direct_candidate_marked_auto"] += 1

        if len(samples.setdefault(bucket or "BLANK", [])) < sample_limit:
            state_batch_id = batch_id_for(state_or_ut, source_file_sha256, input_path)
            samples[bucket or "BLANK"].append({
                "state_or_ut": state_or_ut,
                "source_feature_index": index,
                "planned_batch_id": state_batch_id,
                "planned_source_feature_id": feature_id_for(state_batch_id, index) if index else "",
                "planned_candidate_id": candidate_id_for(state_batch_id, index) if index else "",
                "bucket": bucket,
                "review_status": review_status,
                "planned_review_status": planned_review_status(bucket, review_status),
                "planned_action": action,
                "district": clean(row.get("district")),
                "subdistrict": clean(row.get("subdistrict")),
                "block": clean(row.get("block")),
                "village": clean(row.get("village")),
                "vlcode": clean(row.get("vlcode")),
                "backend_village_id": clean(row.get("backend_village_id")),
            })

    duplicate_samples = {}
    duplicate_count = 0
    for state, counter in duplicate_indexes_by_state.items():
        dupes = {idx: count for idx, count in counter.items() if idx and count > 1}
        if dupes:
            duplicate_count += len(dupes)
            duplicate_samples[state] = dict(list(dupes.items())[:sample_limit])

    if duplicate_count:
        unsafe_counts["duplicate_source_feature_index_within_state"] += duplicate_count

    healthy = (
        not unsafe_counts
        and (expected_state_count is None or len(state_counts) == expected_state_count)
        and (expected_row_count is None or sum(state_counts.values()) == expected_row_count)
    )

    return {
        "healthy": healthy,
        "input_candidate_count": len(rows),
        "planned_batch_insert_count": len(state_counts),
        "planned_source_feature_insert_count": len(rows),
        "planned_candidate_insert_count": len(rows),
        "planned_active_source_feature_count": 0,
        "planned_active_candidate_count": 0,
        "planned_runtime_write_count": 0,
        "state_counts": dict(sorted(state_counts.items())),
        "bucket_counts": dict(sorted(bucket_counts.items())),
        "planned_action_counts": dict(sorted(planned_action_counts.items())),
        "review_status_counts": dict(sorted(review_status_counts.items())),
        "planned_review_status_counts": dict(sorted(planned_review_status_counts.items())),
        "feature_category_counts": dict(sorted(feature_category_counts.items())),
        "proposed_scope_counts": dict(sorted(proposed_scope_counts.items())),
        "unsafe_counts": dict(sorted(unsafe_counts.items())),
        "duplicate_source_feature_index_within_state_count": duplicate_count,
        "duplicate_source_feature_index_samples": duplicate_samples,
        "rows_planned_inactive": len(rows),
        "rows_effective_in_runtime": 0,
        "samples": samples,
    }



def apply_import(
    rows: list[dict[str, str]],
    input_path: Path,
    import_plan: dict[str, Any],
    source_file_sha256: str,
    source_file_size_bytes: int | None,
) -> dict[str, Any]:
    from sqlalchemy import create_engine, text

    if len(import_plan["state_counts"]) != 1:
        return {
            "healthy": False,
            "error": "STATE_SCOPED_APPLY_REQUIRES_EXACTLY_ONE_STATE",
            "state_counts": import_plan["state_counts"],
        }

    state_or_ut = next(iter(import_plan["state_counts"]))
    batch_id = batch_id_for(state_or_ut, source_file_sha256, input_path)
    now = datetime.now(timezone.utc)

    inserted_features = 0
    existing_features = 0
    inserted_candidates = 0
    existing_candidates = 0

    engine = create_engine(db_url_from_settings())
    with engine.begin() as conn:
        existing_conflict = conn.execute(
            text("""
                select id::text, status, review_status, is_active
                from geography_boundary_import_batches
                where source_system = :source_system
                  and source_format = :source_format
                  and state_or_ut = :state_or_ut
                  and id <> :batch_id
                order by created_at desc
                limit 1
            """),
            {
                "source_system": SOURCE_SYSTEM,
                "source_format": SOURCE_FORMAT,
                "state_or_ut": state_or_ut,
                "batch_id": batch_id,
            },
        ).mappings().first()
        if existing_conflict:
            return {
                "healthy": False,
                "error": "CONFLICTING_ALL_STATE_STAGING_BATCH_EXISTS_FOR_STATE",
                "state_or_ut": state_or_ut,
                "conflict": dict(existing_conflict),
            }

        before_batch = conn.execute(
            text("select count(*) from geography_boundary_import_batches where id = :id"),
            {"id": batch_id},
        ).scalar()

        conn.execute(
            text("""
                insert into geography_boundary_import_batches (
                    id, source_system, source_dataset, source_producer_agency,
                    state_or_ut, source_format, source_file_sha256,
                    source_file_size_bytes, source_crs, source_epsg, target_crs,
                    crosswalk_audit, status, review_status, metadata, is_active
                )
                values (
                    :id, :source_system, :source_dataset, :source_producer_agency,
                    :state_or_ut, :source_format, :source_file_sha256,
                    :source_file_size_bytes, :source_crs, :source_epsg, :target_crs,
                    cast(:crosswalk_audit as jsonb), 'IMPORTED_INACTIVE',
                    'MANUAL_REVIEW', cast(:metadata as jsonb), false
                )
                on conflict (id) do update set
                    crosswalk_audit = excluded.crosswalk_audit,
                    updated_at = now(),
                    status = 'IMPORTED_INACTIVE'
                where geography_boundary_import_batches.is_active = false
            """),
            {
                "id": batch_id,
                "source_system": SOURCE_SYSTEM,
                "source_dataset": SOURCE_DATASET,
                "source_producer_agency": SOURCE_PRODUCER_AGENCY,
                "state_or_ut": state_or_ut,
                "source_format": SOURCE_FORMAT,
                "source_file_sha256": source_file_sha256 or None,
                "source_file_size_bytes": source_file_size_bytes,
                "source_crs": SOURCE_CRS,
                "source_epsg": SOURCE_EPSG,
                "target_crs": TARGET_CRS,
                "crosswalk_audit": json.dumps(import_plan, default=json_default),
                "metadata": json.dumps({
                    "importer": "import_nwdp_boundary_all_state_inactive_staging.py",
                    "mode": "GUARDED_STATE_SCOPED_INACTIVE_STAGING",
                    "candidate_input": str(input_path),
                    "generated_at": now.isoformat(),
                }),
            },
        )

        after_batch = conn.execute(
            text("select count(*) from geography_boundary_import_batches where id = :id"),
            {"id": batch_id},
        ).scalar()

        for row in rows:
            index = clean(row.get("source_feature_index") or row.get("index"))
            bucket = clean(row.get("candidate_bucket") or row.get("bucket"))
            review_status = clean(row.get("review_status"))
            source_feature_id = feature_id_for(batch_id, index)
            candidate_id = candidate_id_for(batch_id, index)

            source_codes = {
                "stcode": clean(row.get("stcode")),
                "dtcode": clean(row.get("dtcode")),
                "sdcode": clean(row.get("sdcode")),
                "bkcode": clean(row.get("bkcode")),
                "vlcode": clean(row.get("vlcode")),
            }
            source_names = {
                "state": clean(row.get("state")),
                "state_or_ut": state_or_ut,
                "district": clean(row.get("district")),
                "subdistrict": clean(row.get("subdistrict")),
                "block": clean(row.get("block")),
                "village": clean(row.get("village")),
            }
            match_evidence = {
                "bucket": bucket,
                "confidence": clean(row.get("confidence")),
                "reason": clean(row.get("reason")),
                "planned_action": BUCKET_POLICY.get(bucket),
                "input_review_status": review_status,
                "planned_review_status": planned_review_status(bucket, review_status),
            }

            before_feature = conn.execute(
                text("select count(*) from geography_boundary_source_features where id = :id"),
                {"id": source_feature_id},
            ).scalar()

            conn.execute(
                text("""
                    insert into geography_boundary_source_features (
                        id, import_batch_id, source_feature_index,
                        source_stcode, source_dtcode, source_sdcode, source_bkcode,
                        source_vlcode, source_state_name, source_district_name,
                        source_subdistrict_name, source_block_name, source_village_name,
                        source_agency, feature_category, source_properties,
                        metadata, is_active
                    )
                    values (
                        :id, :import_batch_id, :source_feature_index,
                        :source_stcode, :source_dtcode, :source_sdcode, :source_bkcode,
                        :source_vlcode, :source_state_name, :source_district_name,
                        :source_subdistrict_name, :source_block_name, :source_village_name,
                        :source_agency, :feature_category, cast(:source_properties as jsonb),
                        cast(:metadata as jsonb), false
                    )
                    on conflict (import_batch_id, source_feature_index) do update set
                        updated_at = now(),
                        source_properties = excluded.source_properties,
                        metadata = excluded.metadata
                    where geography_boundary_source_features.is_active = false
                """),
                {
                    "id": source_feature_id,
                    "import_batch_id": batch_id,
                    "source_feature_index": int(index),
                    "source_stcode": source_codes["stcode"],
                    "source_dtcode": source_codes["dtcode"],
                    "source_sdcode": source_codes["sdcode"],
                    "source_bkcode": source_codes["bkcode"],
                    "source_vlcode": source_codes["vlcode"],
                    "source_state_name": state_or_ut,
                    "source_district_name": source_names["district"],
                    "source_subdistrict_name": source_names["subdistrict"],
                    "source_block_name": source_names["block"],
                    "source_village_name": source_names["village"],
                    "source_agency": clean(row.get("src_agency")),
                    "feature_category": feature_category(bucket),
                    "source_properties": json.dumps(source_codes | source_names),
                    "metadata": json.dumps({"candidate_bucket": bucket}),
                },
            )
            if before_feature:
                existing_features += 1
            else:
                inserted_features += 1

            before_candidate = conn.execute(
                text("select count(*) from geography_boundary_crosswalk_candidates where id = :id"),
                {"id": candidate_id},
            ).scalar()

            conn.execute(
                text("""
                    insert into geography_boundary_crosswalk_candidates (
                        id, import_batch_id, source_feature_id, source_feature_index,
                        candidate_bucket, confidence, review_status, proposed_scope,
                        proposed_village_id, proposed_village_lgd_code, source_codes,
                        source_names, match_evidence, promotion_status, metadata, is_active
                    )
                    values (
                        :id, :import_batch_id, :source_feature_id, :source_feature_index,
                        :candidate_bucket, :confidence, :review_status, :proposed_scope,
                        :proposed_village_id, :proposed_village_lgd_code,
                        cast(:source_codes as jsonb), cast(:source_names as jsonb),
                        cast(:match_evidence as jsonb), 'NOT_PROMOTED',
                        cast(:metadata as jsonb), false
                    )
                    on conflict (import_batch_id, source_feature_index) do update set
                        updated_at = now(),
                        confidence = excluded.confidence,
                        match_evidence = excluded.match_evidence,
                        metadata = excluded.metadata
                    where geography_boundary_crosswalk_candidates.review_status in ('AUTO_CANDIDATE', 'MANUAL_REVIEW', 'BLOCKED')
                      and geography_boundary_crosswalk_candidates.promotion_status = 'NOT_PROMOTED'
                      and geography_boundary_crosswalk_candidates.is_active = false
                """),
                {
                    "id": candidate_id,
                    "import_batch_id": batch_id,
                    "source_feature_id": source_feature_id,
                    "source_feature_index": int(index),
                    "candidate_bucket": bucket,
                    "confidence": clean(row.get("confidence")),
                    "review_status": planned_review_status(bucket, review_status),
                    "proposed_scope": clean(row.get("proposed_scope")) or "",
                    "proposed_village_id": clean(row.get("backend_village_id")) or None,
                    "proposed_village_lgd_code": clean(row.get("backend_village_lgd_code")) or None,
                    "source_codes": json.dumps(source_codes),
                    "source_names": json.dumps(source_names),
                    "match_evidence": json.dumps(match_evidence),
                    "metadata": json.dumps({"importer_action": BUCKET_POLICY.get(bucket)}),
                },
            )
            if before_candidate:
                existing_candidates += 1
            else:
                inserted_candidates += 1

        post_counts = {
            "batches": conn.execute(text("select count(*) from geography_boundary_import_batches where id = :id"), {"id": batch_id}).scalar(),
            "source_features": conn.execute(text("select count(*) from geography_boundary_source_features where import_batch_id = :id"), {"id": batch_id}).scalar(),
            "candidates": conn.execute(text("select count(*) from geography_boundary_crosswalk_candidates where import_batch_id = :id"), {"id": batch_id}).scalar(),
            "active_source_features": conn.execute(text("select count(*) from geography_boundary_source_features where import_batch_id = :id and is_active = true"), {"id": batch_id}).scalar(),
            "active_candidates": conn.execute(text("select count(*) from geography_boundary_crosswalk_candidates where import_batch_id = :id and is_active = true"), {"id": batch_id}).scalar(),
            "promoted_candidates": conn.execute(text("select count(*) from geography_boundary_crosswalk_candidates where import_batch_id = :id and promotion_status <> 'NOT_PROMOTED'"), {"id": batch_id}).scalar(),
        }

    expected = len(rows)
    return {
        "healthy": (
            bool(after_batch)
            and post_counts["source_features"] == expected
            and post_counts["candidates"] == expected
            and post_counts["active_source_features"] == 0
            and post_counts["active_candidates"] == 0
            and post_counts["promoted_candidates"] == 0
        ),
        "state_or_ut": state_or_ut,
        "batch_id": batch_id,
        "batch_existed_before": bool(before_batch),
        "batch_exists_after": bool(after_batch),
        "inserted_source_features": inserted_features,
        "existing_source_features": existing_features,
        "inserted_candidates": inserted_candidates,
        "existing_candidates": existing_candidates,
        "post_counts": post_counts,
        "runtime_tables_written": False,
        "runtime_spatial_matching_changed": False,
        "android_behavior_changed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Guarded all-state NWDP inactive staging importer.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--sample-limit", type=int, default=8)
    parser.add_argument("--apply", action="store_true", help="Request inactive staging import.")
    parser.add_argument("--state-or-ut", default="", help="Required for apply; limits import to one state/UT.")
    parser.add_argument("--allow-all-state-inactive-staging-write", action="store_true", help="Future policy gate for all-state inactive staging writes.")
    parser.add_argument("--source-file-sha256", default="", help="Optional source manifest checksum for deterministic batch ids.")
    parser.add_argument("--source-file-size-bytes", type=int, default=None)
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        result = {
            "schema_version": "nwdp_boundary_all_state_inactive_staging_importer.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "healthy": False,
            "error": "INPUT_CSV_NOT_FOUND",
            "path": str(input_path),
            "db_writes_attempted": False,
            "runtime_tables_written": False,
        }
    else:
        all_rows, columns = read_rows(input_path)
        rows = filter_rows(all_rows, clean(args.state_or_ut) or None)
        table_check = check_target_tables()
        expected_state_count = 1 if clean(args.state_or_ut) else EXPECTED_STATE_COUNT
        expected_row_count = len(rows) if clean(args.state_or_ut) else EXPECTED_ROW_COUNT
        import_plan = plan_import(rows, input_path, args.source_file_sha256, args.sample_limit, expected_state_count, expected_row_count)

        apply_result = None
        db_writes_attempted = False
        healthy = import_plan["healthy"]

        if args.apply and not args.allow_all_state_inactive_staging_write:
            healthy = False
            apply_result = {
                "healthy": False,
                "error": "ALL_STATE_INACTIVE_STAGING_APPLY_REQUIRES_POLICY_FLAG",
                "policy_flag_present": False,
            }
        elif args.apply and not clean(args.state_or_ut):
            healthy = False
            apply_result = {
                "healthy": False,
                "error": "ALL_STATE_INACTIVE_STAGING_APPLY_REQUIRES_STATE_SCOPE",
                "policy_flag_present": True,
            }
        elif args.apply:
            if not table_check.get("healthy"):
                healthy = False
                apply_result = {"healthy": False, "error": "TARGET_TABLES_NOT_READY", "table_check": table_check}
            elif not import_plan["healthy"]:
                healthy = False
                apply_result = {"healthy": False, "error": "IMPORT_PLAN_UNSAFE", "unsafe_counts": import_plan.get("unsafe_counts")}
            else:
                db_writes_attempted = True
                apply_result = apply_import(rows, input_path, import_plan, args.source_file_sha256, args.source_file_size_bytes)
                healthy = bool(apply_result.get("healthy"))

        result = {
            "schema_version": "nwdp_boundary_all_state_inactive_staging_importer.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": {
                "portal": "National Water Data Portal",
                "dataset": SOURCE_DATASET,
                "producer_agency": SOURCE_PRODUCER_AGENCY,
                "state_or_ut_scope": "ALL_STATES",
                "candidate_input": str(input_path),
                "source_format": SOURCE_FORMAT,
                "source_crs": SOURCE_CRS,
                "source_epsg": SOURCE_EPSG,
                "target_crs": TARGET_CRS,
            },
            "claim_boundary": "Guarded importer checkpoint plans inactive review rows only. Apply remains blocked; no runtime rows, lookup behavior, Android behavior, candidate activation, or candidate promotion are changed.",
            "healthy": healthy,
            "apply_mode": bool(args.apply),
            "db_writes_attempted": db_writes_attempted,
            "runtime_tables_written": False,
            "runtime_spatial_matching_changed": False,
            "android_behavior_changed": False,
            "lookup_api_enabled": False,
            "input_columns": columns,
            "target_table_check": table_check,
            "import_plan": import_plan,
            "apply_result": apply_result,
            "readiness": {
                "safe_read_only": not args.apply,
                "candidate_plan_healthy": import_plan["healthy"],
                "staging_tables_available": table_check.get("healthy") is True,
                "ready_for_inactive_staging_apply": bool(clean(args.state_or_ut)) and import_plan["healthy"] and table_check.get("healthy") is True,
                "ready_for_runtime_spatial_matching": False,
                "ready_for_runtime_table_write": False,
            },
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True, default=json_default) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True, default=json_default))
    return 0 if result["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

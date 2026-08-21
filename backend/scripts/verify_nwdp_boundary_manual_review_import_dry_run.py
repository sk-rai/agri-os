#!/usr/bin/env python3
"""Dry-run verifier for NWDP boundary manual-review candidate imports."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_INPUT = Path("/tmp/nwdp-karnataka-boundary-crosswalk-candidates.csv")
DEFAULT_OUTPUT = Path("/tmp/nwdp-boundary-manual-review-import-dry-run.json")

REQUIRED_COLUMNS = {
    "index", "stcode", "dtcode", "sdcode", "bkcode", "vlcode",
    "district", "subdistrict", "block", "village", "src_agency",
    "bucket", "confidence", "review_status", "proposed_scope",
    "backend_village_id", "backend_village_lgd_code", "reason",
}

BUCKET_POLICY = {
    "DIRECT_VLCODE_MATCH": {
        "planned_review_status": "AUTO_CANDIDATE",
        "planned_import_action": "STAGE_INACTIVE_AUTO_CANDIDATE",
        "requires_backend_village_id": True,
    },
    "DIRECT_VLCODE_PARENT_MISMATCH": {
        "planned_review_status": "MANUAL_REVIEW",
        "planned_import_action": "STAGE_INACTIVE_MANUAL_REVIEW",
        "requires_backend_village_id": True,
    },
    "PARENT_SCOPED_NAME_MATCH": {
        "planned_review_status": "MANUAL_REVIEW",
        "planned_import_action": "STAGE_INACTIVE_MANUAL_REVIEW",
        "requires_backend_village_id": True,
    },
    "PARENT_SCOPED_NAME_AMBIGUOUS": {
        "planned_review_status": "MANUAL_REVIEW",
        "planned_import_action": "STAGE_INACTIVE_MANUAL_REVIEW",
        "requires_backend_village_id": True,
    },
    "PARENT_MATCH_VILLAGE_UNRESOLVED": {
        "planned_review_status": "MANUAL_REVIEW",
        "planned_import_action": "STAGE_INACTIVE_PARENT_SCOPE_ONLY",
        "requires_backend_village_id": False,
    },
    "DISTRICT_SCOPED_AMBIGUOUS": {
        "planned_review_status": "MANUAL_REVIEW",
        "planned_import_action": "STAGE_INACTIVE_DISTRICT_REVIEW",
        "requires_backend_village_id": True,
    },
    "SPECIAL_REFERENCE_FEATURE": {
        "planned_review_status": "BLOCKED",
        "planned_import_action": "STAGE_BLOCKED_REFERENCE_ONLY",
        "requires_backend_village_id": False,
    },
    "BLOCKED_SOURCE_CAVEAT": {
        "planned_review_status": "BLOCKED",
        "planned_import_action": "STAGE_BLOCKED_SOURCE_CAVEAT",
        "requires_backend_village_id": False,
    },
}


def clean(value: Any) -> str:
    return str(value or "").strip()


def add_sample(samples: dict[str, list[dict[str, Any]]], key: str, row: dict[str, Any], limit: int) -> None:
    bucket = samples.setdefault(key, [])
    if len(bucket) < limit:
        bucket.append(row)

def read_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = [{key: clean(value) for key, value in row.items()} for row in reader]
        return rows, list(reader.fieldnames or [])


def verify_rows(rows: list[dict[str, str]], columns: list[str], sample_limit: int) -> dict[str, Any]:
    missing_columns = sorted(REQUIRED_COLUMNS - set(columns))
    unknown_columns = sorted(set(columns) - REQUIRED_COLUMNS)

    bucket_counts = Counter()
    input_review_counts = Counter()
    planned_review_counts = Counter()
    planned_action_counts = Counter()
    confidence_counts = Counter()
    proposed_scope_counts = Counter()
    district_bucket_counts = Counter()
    unsafe_counts = Counter()
    seen_indexes = Counter()
    seen_source_keys = Counter()
    samples: dict[str, list[dict[str, Any]]] = {}

    for row in rows:
        index = clean(row.get("index"))
        stcode = clean(row.get("stcode"))
        dtcode = clean(row.get("dtcode"))
        sdcode = clean(row.get("sdcode"))
        bkcode = clean(row.get("bkcode"))
        vlcode = clean(row.get("vlcode"))
        district = clean(row.get("district"))
        subdistrict = clean(row.get("subdistrict"))
        block = clean(row.get("block"))
        village = clean(row.get("village"))
        bucket = clean(row.get("bucket"))
        review_status = clean(row.get("review_status"))
        confidence = clean(row.get("confidence"))
        proposed_scope = clean(row.get("proposed_scope"))
        backend_village_id = clean(row.get("backend_village_id"))
        backend_village_lgd_code = clean(row.get("backend_village_lgd_code"))

        policy = BUCKET_POLICY.get(bucket)

        bucket_counts[bucket or "BLANK"] += 1
        input_review_counts[review_status or "BLANK"] += 1
        confidence_counts[confidence or "BLANK"] += 1
        proposed_scope_counts[proposed_scope or "BLANK"] += 1
        district_bucket_counts[f"{district or 'UNKNOWN'}|{bucket or 'BLANK'}"] += 1
        seen_indexes[index] += 1
        seen_source_keys[f"{stcode}|{dtcode}|{sdcode}|{bkcode}|{vlcode}|{index}"] += 1

        if not policy:
            unsafe_counts["unknown_bucket"] += 1
            add_sample(samples, "unknown_bucket", row, sample_limit)
            continue

        planned_review_counts[policy["planned_review_status"]] += 1
        planned_action_counts[policy["planned_import_action"]] += 1

        if policy["requires_backend_village_id"] and not backend_village_id:
            unsafe_counts["missing_required_backend_village_id"] += 1
            add_sample(samples, "missing_required_backend_village_id", row, sample_limit)

        if bucket == "DIRECT_VLCODE_MATCH" and review_status != "AUTO_CANDIDATE":
            unsafe_counts["direct_match_not_auto_candidate"] += 1
            add_sample(samples, "direct_match_not_auto_candidate", row, sample_limit)

        if bucket != "DIRECT_VLCODE_MATCH" and review_status == "AUTO_CANDIDATE":
            unsafe_counts["non_direct_match_marked_auto_candidate"] += 1
            add_sample(samples, "non_direct_match_marked_auto_candidate", row, sample_limit)

        if bucket == "SPECIAL_REFERENCE_FEATURE" and proposed_scope == "village":
            unsafe_counts["special_reference_marked_village_scope"] += 1
            add_sample(samples, "special_reference_marked_village_scope", row, sample_limit)

        if bucket == "DIRECT_VLCODE_MATCH" and backend_village_lgd_code and backend_village_lgd_code != vlcode:
            unsafe_counts["direct_match_backend_code_differs"] += 1
            add_sample(samples, "direct_match_backend_code_differs", row, sample_limit)

        add_sample(samples, bucket, {
            "index": index,
            "bucket": bucket,
            "review_status": review_status,
            "planned_review_status": policy["planned_review_status"],
            "planned_import_action": policy["planned_import_action"],
            "district": district,
            "subdistrict": subdistrict,
            "block": block,
            "village": village,
            "vlcode": vlcode,
            "backend_village_id": backend_village_id,
            "backend_village_lgd_code": backend_village_lgd_code,
        }, sample_limit)

    duplicate_indexes = {key: count for key, count in seen_indexes.items() if key and count > 1}
    duplicate_source_keys = {key: count for key, count in seen_source_keys.items() if key and count > 1}

    if duplicate_indexes:
        unsafe_counts["duplicate_source_feature_index"] += len(duplicate_indexes)
    if duplicate_source_keys:
        unsafe_counts["duplicate_source_key"] += len(duplicate_source_keys)

    district_bucket_summary = []
    for key, count in district_bucket_counts.most_common(80):
        district, bucket = key.split("|", 1)
        district_bucket_summary.append({"district": district, "bucket": bucket, "count": count})

    rows_with_unknown_bucket = sum(count for bucket, count in bucket_counts.items() if bucket not in BUCKET_POLICY)
    rows_eligible_for_staging = len(rows) - rows_with_unknown_bucket
    rows_effective_in_runtime = 0

    healthy = (
        not missing_columns
        and rows_eligible_for_staging == len(rows)
        and rows_effective_in_runtime == 0
        and not duplicate_indexes
        and not duplicate_source_keys
        and not unsafe_counts
    )

    return {
        "healthy": healthy,
        "input_schema": {
            "required_columns_present": not missing_columns,
            "missing_columns": missing_columns,
            "unknown_columns": unknown_columns,
        },
        "row_counts": {
            "input_rows": len(rows),
            "rows_eligible_for_staging": rows_eligible_for_staging,
            "rows_planned_inactive": rows_eligible_for_staging,
            "rows_effective_in_runtime": rows_effective_in_runtime,
            "rows_with_unknown_bucket": rows_with_unknown_bucket,
        },
        "bucket_counts": dict(sorted(bucket_counts.items())),
        "input_review_status_counts": dict(sorted(input_review_counts.items())),
        "planned_review_status_counts": dict(sorted(planned_review_counts.items())),
        "planned_import_action_counts": dict(sorted(planned_action_counts.items())),
        "confidence_counts": dict(sorted(confidence_counts.items())),
        "proposed_scope_counts": dict(sorted(proposed_scope_counts.items())),
        "district_bucket_summary_top80": district_bucket_summary,
        "duplicate_checks": {
            "duplicate_source_feature_index_count": len(duplicate_indexes),
            "duplicate_source_key_count": len(duplicate_source_keys),
            "duplicate_source_feature_index_samples": dict(list(duplicate_indexes.items())[:sample_limit]),
            "duplicate_source_key_samples": dict(list(duplicate_source_keys.items())[:sample_limit]),
        },
        "unsafe_counts": dict(sorted(unsafe_counts.items())),
        "samples": samples,
        "policy": BUCKET_POLICY,
        "readiness": {
            "safe_read_only": True,
            "db_writes_attempted": False,
            "geometry_writes_attempted": False,
            "runtime_lookup_changes_attempted": False,
            "ready_for_guarded_candidate_importer_design": healthy,
            "ready_for_db_write_import": False,
            "ready_for_runtime_spatial_matching": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run verifier for NWDP boundary manual-review candidate imports.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--sample-limit", type=int, default=10)
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        result = {
            "schema_version": "nwdp_boundary_manual_review_import_dry_run.v1",
            "healthy": False,
            "error": "INPUT_CSV_NOT_FOUND",
            "path": str(input_path),
            "readiness": {
                "safe_read_only": True,
                "db_writes_attempted": False,
                "ready_for_db_write_import": False,
            },
        }
    else:
        rows, columns = read_rows(input_path)
        result = {
            "schema_version": "nwdp_boundary_manual_review_import_dry_run.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": {
                "portal": "National Water Data Portal",
                "dataset": "Village Boundary",
                "producer_agency": "Geological Survey of India",
                "pilot_state_or_ut": "Karnataka",
                "candidate_input": str(input_path),
            },
            "claim_boundary": "Dry-run verifier reads candidate artifacts only. It does not write database rows, import geometry, promote crosswalks, or authorize runtime point-in-polygon use.",
            "verification": verify_rows(rows, columns, args.sample_limit),
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Plan national district readiness snapshots from one offline calculation.

This planner is read-only. It performs the expensive national readiness
calculation once, partitions the result into district-scoped snapshot
candidates, and writes review artifacts only.

It never inserts, updates, activates, deactivates, or refreshes database rows.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import sys
import time
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.database import SessionLocal
from app.modules.master_data.api.geography import (
    _build_geography_layer_readiness_matrix,
)


EXPECTED_DISTRICT_COUNT = 779
SNAPSHOT_SCHEMA_VERSION = "geography_layer_readiness_snapshot.v1"
PLAN_SCHEMA_VERSION = (
    "geography_layer_readiness_national_snapshot_plan.v1"
)
DEFAULT_OUTPUT_DIR = (
    ROOT
    / "data/staged/core_stack/"
    "geography_readiness_snapshots"
)


def json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    raise TypeError(
        f"Object of type {type(value).__name__} "
        "is not JSON serializable"
    )


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=json_default,
    )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_text(canonical_json(value))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )
    return parser.parse_args()


def load_canonical_districts(db) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in db.execute(
            text(
                """
                select
                  state.id::text as state_id,
                  district.id::text as district_id,
                  state.lgd_code::text as state_lgd_code,
                  district.lgd_code::text as district_lgd_code,
                  state.canonical_name as state_or_ut,
                  district.canonical_name as district
                from geography_states state
                join geography_districts district
                  on district.state_id = state.id
                 and district.is_active = true
                where state.is_active = true
                order by
                  state.lgd_code::text,
                  district.lgd_code::text
                """
            )
        ).mappings()
    ]


def load_active_snapshots(db) -> dict[tuple[str, str], dict[str, Any]]:
    rows = db.execute(
        text(
            """
            select
              id::text as snapshot_id,
              state_lgd_code,
              district_lgd_code,
              readiness_payload,
              computed_at,
              refresh_run_id
            from geography_layer_readiness_snapshots
            where is_active = true
              and calculation_status = 'READY'
            """
        )
    ).mappings()

    return {
        (
            str(row["state_lgd_code"]),
            str(row["district_lgd_code"]),
        ): dict(row)
        for row in rows
    }


def district_summary(row: dict[str, Any]) -> dict[str, int]:
    summary = {"state_district_row_count": 1}
    for key, value in row.items():
        if key.endswith("_count"):
            summary[key] = int(value or 0)
    return summary


def build_district_payload(
    national_payload: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any]:
    payload = copy.deepcopy(national_payload)
    payload.pop("generated_at", None)

    payload["mode"] = (
        "OFFLINE_PRECOMPUTED_DISTRICT_SNAPSHOT_CANDIDATE"
    )
    payload["filters"] = {
        "state_or_ut": row["state_or_ut"],
        "district": row["district"],
        "limit": 50,
    }
    payload["summary"] = district_summary(row)
    payload["rows"] = [row]

    payload["snapshot_scope"] = {
        "scope_level": "DISTRICT",
        "state_lgd_code": row["state_lgd_code"],
        "district_lgd_code": row["district_lgd_code"],
        "district_row_is_scope_exact": True,
        "shared_national_context_present": True,
        "shared_national_context_fields": [
            "gap_accounting",
            "climate_readiness",
            "project_boundary_readiness",
            "boundary_geometry_validation_readiness",
            "boundary_geometry_repair_classification",
            "boundary_geometry_repair_events",
            "selected_boundary_runtime_promotion_readiness",
            "external_api_readiness",
        ],
        "shared_context_policy": (
            "REFERENCE_ONLY_NOT_DISTRICT_GEOMETRY_COMPUTATION"
        ),
    }
    payload["guardrails"] = {
        **(payload.get("guardrails") or {}),
        "interactive_computation_attempted": False,
        "geometry_computation_attempted": False,
        "database_writes_attempted": False,
        "canonical_geography_changed": False,
        "global_mapping_changed": False,
        "project_override_changed": False,
        "runtime_activation_changed": False,
        "android_behavior_changed": False,
    }
    return payload


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()

    with SessionLocal() as db:
        canonical = load_canonical_districts(db)
        active_snapshots = load_active_snapshots(db)

        national_payload = _build_geography_layer_readiness_matrix(
            db=db,
            state_or_ut=None,
            district=None,
            limit=5000,
        )

    elapsed_ms = round(
        (time.perf_counter() - started) * 1000,
        3,
    )

    rows = national_payload.get("rows") or []

    canonical_by_key = {
        (
            row["state_lgd_code"],
            row["district_lgd_code"],
        ): row
        for row in canonical
    }
    readiness_by_key = {
        (
            str(row["state_lgd_code"]),
            str(row["district_lgd_code"]),
        ): row
        for row in rows
    }

    duplicate_canonical_count = (
        len(canonical) - len(canonical_by_key)
    )
    duplicate_readiness_count = (
        len(rows) - len(readiness_by_key)
    )

    canonical_keys = set(canonical_by_key)
    readiness_keys = set(readiness_by_key)
    missing_keys = sorted(canonical_keys - readiness_keys)
    unexpected_keys = sorted(readiness_keys - canonical_keys)

    source_fingerprint = sha256_json({
        "canonical_districts": canonical,
        "readiness_rows": rows,
        "readiness_schema_version":
            national_payload.get("schema_version"),
    })
    plan_id = (
        "national-district-readiness-"
        + source_fingerprint[:16]
    )

    candidates = []
    for key in sorted(canonical_keys):
        identity = canonical_by_key[key]
        row = readiness_by_key.get(key)
        if row is None:
            continue

        payload = build_district_payload(
            national_payload,
            row,
        )
        payload_sha256 = sha256_json(payload)

        existing = active_snapshots.get(key)
        existing_sha256 = (
            sha256_json(existing["readiness_payload"])
            if existing
            else None
        )

        if existing is None:
            action = "INSERT_NEW_ACTIVE_SNAPSHOT"
        elif existing_sha256 == payload_sha256:
            action = "RETAIN_IDENTICAL_ACTIVE_SNAPSHOT"
        else:
            action = "REPLACE_CHANGED_ACTIVE_SNAPSHOT"

        candidates.append({
            "plan_id": plan_id,
            "snapshot_schema_version":
                SNAPSHOT_SCHEMA_VERSION,
            "state_id": identity["state_id"],
            "district_id": identity["district_id"],
            "state_lgd_code":
                identity["state_lgd_code"],
            "district_lgd_code":
                identity["district_lgd_code"],
            "state_or_ut": identity["state_or_ut"],
            "district": identity["district"],
            "plan_action": action,
            "existing_snapshot_id": (
                existing["snapshot_id"]
                if existing
                else None
            ),
            "existing_payload_sha256": existing_sha256,
            "planned_payload_sha256": payload_sha256,
            "readiness_payload": payload,
            "source_versions": {
                "lgd_identity":
                    "DATABASE_CANONICAL_ACTIVE",
                "readiness_schema_version":
                    national_payload.get("schema_version"),
                "national_source_fingerprint":
                    source_fingerprint,
            },
            "evidence_metadata": {
                "calculation_mode":
                    "OFFLINE_SINGLE_NATIONAL_CALCULATION",
                "partitioned_to_district": True,
                "district_identity_verified": True,
                "interactive_computation_authorized": False,
                "geometry_computation_runtime_authorized":
                    False,
                "database_apply_authorized": False,
                "runtime_activation_authorized": False,
                "android_behavior_change_authorized": False,
            },
        })

    action_counts = dict(
        sorted(
            Counter(
                row["plan_action"]
                for row in candidates
            ).items()
        )
    )

    checks = {
        "canonical_district_count_exact":
            len(canonical) == EXPECTED_DISTRICT_COUNT,
        "readiness_row_count_exact":
            len(rows) == EXPECTED_DISTRICT_COUNT,
        "candidate_count_exact":
            len(candidates) == EXPECTED_DISTRICT_COUNT,
        "canonical_identity_unique":
            duplicate_canonical_count == 0,
        "readiness_identity_unique":
            duplicate_readiness_count == 0,
        "canonical_partition_exact":
            not missing_keys and not unexpected_keys,
        "all_candidates_scope_exact": all(
            candidate["readiness_payload"]["rows"][0][
                "state_lgd_code"
            ]
            == candidate["state_lgd_code"]
            and candidate["readiness_payload"]["rows"][0][
                "district_lgd_code"
            ]
            == candidate["district_lgd_code"]
            for candidate in candidates
        ),
        "all_candidates_single_row": all(
            len(candidate["readiness_payload"]["rows"]) == 1
            for candidate in candidates
        ),
        "national_calculation_executed_once": True,
        "no_database_writes": True,
        "not_authorized_for_apply": True,
        "interactive_computation_disabled": True,
        "runtime_activation_unchanged": True,
        "android_behavior_unchanged": True,
    }
    healthy = all(checks.values())

    rows_path = (
        args.output_dir
        / "geography_layer_readiness_national_snapshot_plan_rows.jsonl"
    )
    csv_path = (
        args.output_dir
        / "geography_layer_readiness_national_snapshot_plan.csv"
    )
    summary_path = (
        args.output_dir
        / "geography_layer_readiness_national_snapshot_plan.json"
    )

    rows_text = "".join(
        canonical_json(row) + "\n"
        for row in candidates
    )
    rows_path.write_text(rows_text, encoding="utf-8")

    csv_fields = [
        "plan_id",
        "state_lgd_code",
        "district_lgd_code",
        "state_or_ut",
        "district",
        "plan_action",
        "existing_snapshot_id",
        "existing_payload_sha256",
        "planned_payload_sha256",
    ]
    with csv_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=csv_fields,
        )
        writer.writeheader()
        for row in candidates:
            writer.writerow({
                field: row.get(field)
                for field in csv_fields
            })

    rows_sha256 = sha256_text(rows_text)
    csv_sha256 = hashlib.sha256(
        csv_path.read_bytes()
    ).hexdigest()

    summary = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "status": (
            "NATIONAL_DISTRICT_SNAPSHOT_PLAN_READY_NOT_AUTHORIZED"
            if healthy
            else "NATIONAL_DISTRICT_SNAPSHOT_PLAN_INVALID"
        ),
        "healthy": healthy,
        "plan_id": plan_id,
        "database_writes_attempted": False,
        "national_calculation_count": 1,
        "diagnostic_elapsed_ms": elapsed_ms,
        "expected_district_count":
            EXPECTED_DISTRICT_COUNT,
        "canonical_district_count": len(canonical),
        "readiness_row_count": len(rows),
        "candidate_count": len(candidates),
        "active_snapshot_count":
            len(active_snapshots),
        "counts_by_plan_action": action_counts,
        "duplicate_canonical_identity_count":
            duplicate_canonical_count,
        "duplicate_readiness_identity_count":
            duplicate_readiness_count,
        "missing_canonical_keys": missing_keys,
        "unexpected_readiness_keys": unexpected_keys,
        "source_fingerprint": source_fingerprint,
        "rows": str(rows_path),
        "rows_sha256": rows_sha256,
        "csv": str(csv_path),
        "csv_sha256": csv_sha256,
        "estimated_payload_bytes":
            len(rows_text.encode("utf-8")),
        "checks": checks,
        "policy": {
            "offline_single_national_calculation": True,
            "district_partition_required": True,
            "database_apply_authorized": False,
            "interactive_computation_authorized": False,
            "runtime_activation_authorized": False,
            "android_behavior_change_authorized": False,
        },
        "shared_context_policy": {
            "shared_national_context_present": True,
            "purpose": (
                "Compatibility reference only; not district "
                "geometry computation"
            ),
            "district_specific_source":
                "readiness_payload.rows[0]",
        },
    }
    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
    )
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())

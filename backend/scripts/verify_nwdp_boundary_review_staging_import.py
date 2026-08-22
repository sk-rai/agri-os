#!/usr/bin/env python3
"""Verify NWDP boundary inactive review staging import.

Read-only. Checks staged batch/source-feature/candidate rows and confirms:
- expected counts;
- no active candidates;
- no promoted candidates;
- no orphan candidates;
- runtime spatial matching remains out of scope.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DEFAULT_OUTPUT = Path("/tmp/nwdp-boundary-review-staging-import-verify.json")
DEFAULT_SOURCE_SYSTEM = "NWDP_GSI_VILLAGE_BOUNDARY"
DEFAULT_STATE = "Karnataka"
DEFAULT_EXPECTED_COUNT = 29789


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


def rows_to_dicts(rows: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def verify(source_system: str, state_or_ut: str, expected_count: int) -> dict[str, Any]:
    engine = create_engine(db_url_from_settings())

    with engine.connect() as conn:
        batch = conn.execute(
            text("""
                select id, source_system, state_or_ut, source_format, status, review_status, is_active
                from geography_boundary_import_batches
                where source_system = :source_system
                  and state_or_ut = :state_or_ut
                order by created_at desc
                limit 1
            """),
            {"source_system": source_system, "state_or_ut": state_or_ut},
        ).mappings().first()

        if not batch:
            return {
                "healthy": False,
                "error": "BATCH_NOT_FOUND",
                "source_system": source_system,
                "state_or_ut": state_or_ut,
            }

        batch_id = batch["id"]

        counts = {
            "source_feature_count": conn.execute(
                text("""
                    select count(*)
                    from geography_boundary_source_features
                    where import_batch_id = :batch_id
                """),
                {"batch_id": batch_id},
            ).scalar(),
            "candidate_count": conn.execute(
                text("""
                    select count(*)
                    from geography_boundary_crosswalk_candidates
                    where import_batch_id = :batch_id
                """),
                {"batch_id": batch_id},
            ).scalar(),
            "active_candidate_count": conn.execute(
                text("""
                    select count(*)
                    from geography_boundary_crosswalk_candidates
                    where import_batch_id = :batch_id
                      and is_active = true
                """),
                {"batch_id": batch_id},
            ).scalar(),
            "promoted_candidate_count": conn.execute(
                text("""
                    select count(*)
                    from geography_boundary_crosswalk_candidates
                    where import_batch_id = :batch_id
                      and promotion_status <> 'NOT_PROMOTED'
                """),
                {"batch_id": batch_id},
            ).scalar(),
            "orphan_candidate_count": conn.execute(
                text("""
                    select count(*)
                    from geography_boundary_crosswalk_candidates c
                    left join geography_boundary_source_features f on f.id = c.source_feature_id
                    where c.import_batch_id = :batch_id
                      and f.id is null
                """),
                {"batch_id": batch_id},
            ).scalar(),
        }

        review_status_counts = rows_to_dicts(
            conn.execute(
                text("""
                    select review_status, count(*) as count
                    from geography_boundary_crosswalk_candidates
                    where import_batch_id = :batch_id
                    group by review_status
                    order by review_status
                """),
                {"batch_id": batch_id},
            ).mappings()
        )

        bucket_counts = rows_to_dicts(
            conn.execute(
                text("""
                    select candidate_bucket, count(*) as count
                    from geography_boundary_crosswalk_candidates
                    where import_batch_id = :batch_id
                    group by candidate_bucket
                    order by candidate_bucket
                """),
                {"batch_id": batch_id},
            ).mappings()
        )

        feature_category_counts = rows_to_dicts(
            conn.execute(
                text("""
                    select feature_category, count(*) as count
                    from geography_boundary_source_features
                    where import_batch_id = :batch_id
                    group by feature_category
                    order by feature_category
                """),
                {"batch_id": batch_id},
            ).mappings()
        )

    healthy = (
        counts["source_feature_count"] == expected_count
        and counts["candidate_count"] == expected_count
        and counts["active_candidate_count"] == 0
        and counts["promoted_candidate_count"] == 0
        and counts["orphan_candidate_count"] == 0
        and batch["is_active"] is False
    )

    return {
        "healthy": healthy,
        "batch": dict(batch),
        "expected_count": expected_count,
        "counts": counts,
        "review_status_counts": review_status_counts,
        "candidate_bucket_counts": bucket_counts,
        "feature_category_counts": feature_category_counts,
        "readiness": {
            "safe_read_only": True,
            "db_writes_attempted": False,
            "inactive_staging_verified": healthy,
            "ready_for_admin_review_endpoint": healthy,
            "ready_for_runtime_spatial_matching": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify NWDP boundary inactive review staging import.")
    parser.add_argument("--source-system", default=DEFAULT_SOURCE_SYSTEM)
    parser.add_argument("--state-or-ut", default=DEFAULT_STATE)
    parser.add_argument("--expected-count", type=int, default=DEFAULT_EXPECTED_COUNT)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    result = {
        "schema_version": "nwdp_boundary_review_staging_import_verify.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "claim_boundary": "Verifier is read-only. It does not promote candidates, activate rows, import runtime geometry, or enable point-in-polygon matching.",
        "verification": verify(args.source_system, args.state_or_ut, args.expected_count),
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

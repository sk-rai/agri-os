#!/usr/bin/env python3
"""Read-only pilot selection report for NWDP boundary promotion review."""

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

DEFAULT_OUTPUT = Path("/tmp/nwdp-boundary-pilot-promotion-review-plan.json")


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--state-or-ut", default="Karnataka")
    parser.add_argument("--source-system", default="NWDP_GSI_VILLAGE_BOUNDARY")
    args = parser.parse_args()

    from sqlalchemy import create_engine, text

    engine = create_engine(db_url_from_settings())
    with engine.connect() as conn:
        rows = conn.execute(text("""
            select
              c.id::text as candidate_id,
              c.source_feature_index,
              c.candidate_bucket,
              c.review_status,
              c.reviewer_decision,
              c.promotion_status,
              c.proposed_scope,
              c.proposed_village_lgd_code,
              c.proposed_village_id::text,
              f.source_district_name,
              f.source_subdistrict_name,
              f.source_block_name,
              f.source_village_name,
              f.source_vlcode,
              f.source_geometry_hash,
              f.transformed_bbox,
              f.transformed_centroid,
              f.geometry_validation_status,
              c.match_evidence
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
            order by f.source_district_name, f.source_subdistrict_name, c.source_feature_index
            limit :limit
        """), {
            "state_or_ut": args.state_or_ut,
            "source_system": args.source_system,
            "limit": args.limit,
        }).mappings().all()

    items = []
    for row in rows:
        row = dict(row)
        source_vlcode = row.get("source_vlcode")
        proposed_lgd = row.get("proposed_village_lgd_code")
        geometry_status = row.get("geometry_validation_status")
        review_status = row.get("review_status")
        required = []
        if review_status != "APPROVED_FOR_PROMOTION":
            required.append("reviewer must set APPROVED_FOR_PROMOTION with promotion-compatible decision")
        if geometry_status not in {"VALID", "VALIDATED"}:
            required.append("geometry validation checkpoint required")
        if source_vlcode != proposed_lgd:
            required.append("reviewer must document source vlcode/proposed LGD mismatch")
        if not row.get("source_geometry_hash"):
            required.append("source geometry hash required")

        items.append({
            **row,
            "source_vlcode_matches_proposed_lgd": source_vlcode == proposed_lgd,
            "pilot_recommended_decision": "ACCEPT_DIRECT_CODE_MATCH",
            "pilot_recommended_review_status": "APPROVED_FOR_PROMOTION",
            "required_next_actions": required or ["ready for promotion dry-run after reviewer confirmation"],
            "runtime_write_allowed_now": False,
        })

    report = {
        "schema_version": "nwdp_boundary_pilot_promotion_review_plan.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": bool(items),
        "mode": "READ_ONLY_PILOT_SELECTION",
        "db_writes_attempted": False,
        "runtime_tables_written": False,
        "runtime_spatial_matching_changed": False,
        "android_behavior_changed": False,
        "filters": {
            "state_or_ut": args.state_or_ut,
            "source_system": args.source_system,
            "candidate_bucket": "DIRECT_VLCODE_MATCH",
            "limit": args.limit,
        },
        "summary": {
            "selected_candidate_count": len(items),
            "runtime_write_allowed_now": False,
            "requires_reviewer_metadata": True,
            "requires_geometry_validation": True,
        },
        "items": items,
    }

    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, default=json_default), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True, default=json_default))
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
Import CoRE/LGD district overlay candidates as inactive MANUAL_REVIEW mappings.

Default mode is dry-run. Use --apply to write DB rows.

Safety policy:
- writes only rows with would_write_db_row=true / excluded=false;
- writes review_status=MANUAL_REVIEW;
- writes is_active=false;
- does not modify or deactivate fallback mappings;
- idempotent by region_code + scope_level + state_lgd_code + district_lgd_code
  + confidence + review_status.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from app.core.database import SessionLocal


ROOT = Path(__file__).resolve().parents[2]
PLAN_CSV = ROOT / "data/staged/core_stack/manual_review_import_plan/core_lgd_manual_review_import_plan.csv"

CONFIDENCE = "POLY_REV"
REVIEW_STATUS = "MANUAL_REVIEW"
VERSION = "clri_v1"


def parse_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


def parse_json(value: Any, fallback: Any) -> Any:
    if value is None or str(value).strip() == "":
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def load_plan_rows() -> list[dict[str, Any]]:
    with PLAN_CSV.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def eligible_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        if parse_bool(row.get("would_write_db_row")) and not parse_bool(row.get("excluded")):
            out.append(row)
    return out


def existing_key(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "region_code": row["target_region_code"],
        "scope_level": row.get("scope_level") or "DISTRICT",
        "state_lgd_code": row.get("state_lgd_code") or None,
        "district_lgd_code": row.get("district_lgd_code") or None,
        "confidence": CONFIDENCE,
        "review_status": REVIEW_STATUS,
    }


def count_existing(db, row: dict[str, Any]) -> int:
    params = existing_key(row)
    return db.execute(text("""
        select count(*) as count
        from geography_climate_region_mappings
        where region_code = :region_code
          and scope_level = :scope_level
          and state_lgd_code is not distinct from :state_lgd_code
          and district_lgd_code is not distinct from :district_lgd_code
          and confidence = :confidence
          and review_status = :review_status
    """), params).scalar_one()


def build_insert_params(row: dict[str, Any]) -> dict[str, Any]:
    source_references = parse_json(row.get("source_references"), [])
    metadata = parse_json(row.get("metadata"), {})

    metadata.update({
        "importer": VERSION,
        "importer_label": "core_lgd_manual_review_import.v1",
        "confidence_label": "POLYGON_DERIVED_DISTRICT_OVERLAY_REVIEW",
        "candidate_policy": {
            "source": "BharatAtlas operational LGD-keyed geometry + CoRE overlay",
            "is_effective_in_land_intelligence": False,
            "writes_replace_fallbacks": False,
            "requires_manual_promotion": True,
        },
        "district_name": row.get("district_name"),
        "state_name": row.get("state_name"),
        "region_system": row.get("region_system"),
        "region_class_code": row.get("region_class_code"),
        "region_class_name": row.get("region_class_name"),
        "overlap_percent_of_district": row.get("overlap_percent_of_district"),
        "crosswalk_category": row.get("crosswalk_category"),
        "low_overlap_bucket": row.get("low_overlap_bucket"),
    })

    now = datetime.now(timezone.utc)
    return {
        "id": str(uuid.uuid4()),
        "region_id": row["target_region_id"],
        "region_code": row["target_region_code"],
        "scope_level": row.get("scope_level") or "DISTRICT",
        "state_lgd_code": row.get("state_lgd_code") or None,
        "district_lgd_code": row.get("district_lgd_code") or None,
        "block_lgd_code": None,
        "village_lgd_code": None,
        "pin_code": None,
        "source_references": json.dumps(source_references),
        "confidence": CONFIDENCE,
        "review_status": REVIEW_STATUS,
        "metadata": json.dumps(metadata),
        "created_at": now,
        "updated_at": now,
        "version": VERSION,
        "is_active": False,
    }


def insert_row(db, row: dict[str, Any]) -> None:
    params = build_insert_params(row)
    db.execute(text("""
        insert into geography_climate_region_mappings (
            id,
            region_id,
            region_code,
            scope_level,
            state_lgd_code,
            district_lgd_code,
            block_lgd_code,
            village_lgd_code,
            pin_code,
            source_references,
            confidence,
            review_status,
            metadata,
            created_at,
            updated_at,
            version,
            is_active
        ) values (
            :id,
            :region_id,
            :region_code,
            :scope_level,
            :state_lgd_code,
            :district_lgd_code,
            :block_lgd_code,
            :village_lgd_code,
            :pin_code,
            cast(:source_references as jsonb),
            :confidence,
            :review_status,
            cast(:metadata as jsonb),
            :created_at,
            :updated_at,
            :version,
            :is_active
        )
    """), params)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write inactive MANUAL_REVIEW rows.")
    parser.add_argument("--limit", type=int, default=None, help="Optional row limit for cautious first apply.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = load_plan_rows()
    candidates = eligible_rows(rows)
    if args.limit is not None:
        candidates = candidates[: args.limit]

    result: dict[str, Any] = {
        "schema_version": "core_lgd_manual_review_mapping_import.v1",
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "db_writes_made": False,
        "external_calls_made": False,
        "plan_csv": str(PLAN_CSV),
        "planned_policy": {
            "confidence": CONFIDENCE,
            "review_status": REVIEW_STATUS,
            "is_active": False,
            "writes_replace_fallbacks": False,
        },
        "input_counts": {
            "plan_rows": len(rows),
            "eligible_rows": len(eligible_rows(rows)),
            "processed_rows": len(candidates),
        },
        "counts": {
            "would_insert": 0,
            "inserted": 0,
            "already_exists": 0,
            "skipped_missing_region_id": 0,
        },
        "samples": {
            "would_insert": [],
            "already_exists": [],
            "skipped_missing_region_id": [],
        },
    }

    db = SessionLocal()
    try:
        for row in candidates:
            if not row.get("target_region_id"):
                result["counts"]["skipped_missing_region_id"] += 1
                if len(result["samples"]["skipped_missing_region_id"]) < 5:
                    result["samples"]["skipped_missing_region_id"].append(row)
                continue

            if count_existing(db, row) > 0:
                result["counts"]["already_exists"] += 1
                if len(result["samples"]["already_exists"]) < 5:
                    result["samples"]["already_exists"].append(existing_key(row))
                continue

            if args.apply:
                insert_row(db, row)
                result["counts"]["inserted"] += 1
                result["db_writes_made"] = True
            else:
                result["counts"]["would_insert"] += 1
                if len(result["samples"]["would_insert"]) < 5:
                    result["samples"]["would_insert"].append(existing_key(row))

        if args.apply:
            db.commit()
        else:
            db.rollback()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    result["readiness"] = {
        "safe_default_dry_run": not args.apply,
        "wrote_only_inactive_manual_review_candidates": True,
        "fallback_mappings_preserved": True,
    }

    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

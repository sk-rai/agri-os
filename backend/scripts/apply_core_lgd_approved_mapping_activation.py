#!/usr/bin/env python3
"""
Activate approved CoRE/LGD polygon-derived mappings for an explicit district.

Default mode is dry-run. Actual behavior change requires --apply plus explicit
--state and --district.

Safety policy:
- only activates inactive POLY_REV rows with review_status=APPROVED_FOR_PROMOTION;
- only processes rows eligible by high-overlap/crosswalk guardrails;
- updates activated rows to confidence=POLY_APPR, version=clap_v1, is_active=true;
- deactivates active LOCAL_DEMO fallback rows for the same state/district only;
- never touches non-approved POLY_REV rows.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from app.core.database import SessionLocal

SOURCE_CONFIDENCE = "POLY_REV"
ACTIVE_CONFIDENCE = "POLY_APPR"
APPROVED_STATUS = "APPROVED_FOR_PROMOTION"
PROMOTED_STATUS = "PROMOTED"
VERSION = "clap_v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, dest="state_lgd_code")
    parser.add_argument("--district", required=True, dest="district_lgd_code")
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def eligible_rows(db, state_lgd_code: str, district_lgd_code: str) -> list[dict]:
    rows = db.execute(text("""
        select
          m.id::text as mapping_id,
          m.metadata,
          m.region_code,
          r.region_system,
          m.state_lgd_code,
          m.district_lgd_code,
          coalesce(nullif(m.metadata ->> 'low_overlap_bucket', ''), 'NOT_LOW_OVERLAP') as low_overlap_bucket,
          nullif(m.metadata ->> 'overlap_percent_of_district', '')::numeric as overlap_percent_of_district,
          coalesce(m.metadata ->> 'crosswalk_category', '') as crosswalk_category
        from geography_climate_region_mappings m
        left join geography_climate_regions r on r.id = m.region_id
        where m.confidence = :source_confidence
          and m.review_status = :approved_status
          and m.is_active is false
          and m.state_lgd_code = :state_lgd_code
          and m.district_lgd_code = :district_lgd_code
        order by r.region_system, m.region_code
    """), {
        "source_confidence": SOURCE_CONFIDENCE,
        "approved_status": APPROVED_STATUS,
        "state_lgd_code": state_lgd_code,
        "district_lgd_code": district_lgd_code,
    }).mappings().all()

    eligible = []
    blocked = []
    for row in rows:
        item = dict(row)
        reason = None
        if item["low_overlap_bucket"] != "NOT_LOW_OVERLAP":
            reason = f"low_overlap_bucket {item['low_overlap_bucket']}"
        elif item["overlap_percent_of_district"] is None or float(item["overlap_percent_of_district"]) < 80:
            reason = f"overlap below 80: {item['overlap_percent_of_district']}"
        elif item["crosswalk_category"] in {"BHARATLAS_ONLY", "STATE_CODE_MISMATCH", "UNSET"}:
            reason = f"crosswalk category {item['crosswalk_category']}"

        if reason:
            item["blocked_reason"] = reason
            blocked.append(item)
        else:
            eligible.append(item)

    return eligible, blocked


def active_fallbacks(db, state_lgd_code: str, district_lgd_code: str) -> list[dict]:
    return [dict(row) for row in db.execute(text("""
        select id::text, region_code, confidence, review_status, is_active, metadata
        from geography_climate_region_mappings
        where is_active is true
          and confidence in ('LOCAL_DEMO_DISTRICT_FALLBACK', 'LOCAL_DEMO_SEED')
          and state_lgd_code = :state_lgd_code
          and district_lgd_code = :district_lgd_code
        order by region_code
    """), {
        "state_lgd_code": state_lgd_code,
        "district_lgd_code": district_lgd_code,
    }).mappings().all()]


def active_scope_snapshot(db, state_lgd_code: str, district_lgd_code: str) -> list[dict]:
    return [dict(row) for row in db.execute(text("""
        select
          m.id::text,
          m.region_code,
          r.region_name,
          r.region_system,
          m.confidence,
          m.review_status,
          m.version,
          m.is_active
        from geography_climate_region_mappings m
        left join geography_climate_regions r on r.id = m.region_id
        where m.is_active is true
          and m.state_lgd_code = :state_lgd_code
          and m.district_lgd_code = :district_lgd_code
        order by r.region_system, m.region_code
    """), {
        "state_lgd_code": state_lgd_code,
        "district_lgd_code": district_lgd_code,
    }).mappings().all()]


def main() -> int:
    args = parse_args()
    now = datetime.now(timezone.utc)

    db = SessionLocal()
    try:
        before = active_scope_snapshot(db, args.state_lgd_code, args.district_lgd_code)
        eligible, blocked = eligible_rows(db, args.state_lgd_code, args.district_lgd_code)
        fallbacks = active_fallbacks(db, args.state_lgd_code, args.district_lgd_code)

        result = {
            "schema_version": "core_lgd_approved_mapping_activation_apply.v1",
            "mode": "APPLY" if args.apply else "DRY_RUN",
            "db_writes_made": False,
            "external_calls_made": False,
            "filters": {
                "state_lgd_code": args.state_lgd_code,
                "district_lgd_code": args.district_lgd_code,
            },
            "counts": {
                "approved_eligible_rows": len(eligible),
                "blocked_rows": len(blocked),
                "active_fallback_rows_to_deactivate": len(fallbacks),
                "activated_rows": 0,
                "deactivated_fallback_rows": 0,
            },
            "before_active_mappings": before,
            "samples": {
                "eligible": eligible[:10],
                "blocked": blocked[:10],
                "fallbacks_to_deactivate": fallbacks[:10],
            },
            "readiness": {
                "explicit_scope_required": True,
                "has_eligible_rows": len(eligible) > 0,
                "no_blocked_rows": len(blocked) == 0,
                "safe_default_dry_run": not args.apply,
                "android_maestro_required_after_apply": True,
            },
        }

        if args.apply:
            if not eligible:
                raise SystemExit("No eligible approved rows to activate")
            if blocked:
                raise SystemExit("Blocked rows present; refusing apply")

            for row in eligible:
                metadata = dict(row["metadata"] or {})
                history = list(metadata.get("activation_history") or [])
                event = {
                    "changed_at": now.isoformat(),
                    "action": "ACTIVATE_APPROVED_POLY_REV_MAPPING",
                    "from_confidence": SOURCE_CONFIDENCE,
                    "to_confidence": ACTIVE_CONFIDENCE,
                    "from_review_status": APPROVED_STATUS,
                    "to_review_status": PROMOTED_STATUS,
                    "version": VERSION,
                    "guardrail": "district-scoped explicit apply",
                }
                history.append(event)
                metadata["activation_history"] = history
                metadata["latest_activation"] = event
                metadata["confidence_label"] = "POLYGON_DERIVED_APPROVED_DISTRICT_MAPPING"
                metadata["effective_in_land_intelligence"] = True

                db.execute(text("""
                    update geography_climate_region_mappings
                    set confidence = :active_confidence,
                        review_status = :promoted_status,
                        version = :version,
                        is_active = true,
                        metadata = cast(:metadata as jsonb),
                        updated_at = :updated_at
                    where id = :mapping_id
                      and confidence = :source_confidence
                      and review_status = :approved_status
                      and is_active is false
                """), {
                    "mapping_id": row["mapping_id"],
                    "active_confidence": ACTIVE_CONFIDENCE,
                    "promoted_status": PROMOTED_STATUS,
                    "version": VERSION,
                    "metadata": json.dumps(metadata),
                    "updated_at": now,
                    "source_confidence": SOURCE_CONFIDENCE,
                    "approved_status": APPROVED_STATUS,
                })
                result["counts"]["activated_rows"] += 1

            for row in fallbacks:
                metadata = dict(row["metadata"] or {})
                metadata["superseded_by_core_lgd_activation"] = {
                    "changed_at": now.isoformat(),
                    "state_lgd_code": args.state_lgd_code,
                    "district_lgd_code": args.district_lgd_code,
                    "new_confidence": ACTIVE_CONFIDENCE,
                    "new_version": VERSION,
                }
                db.execute(text("""
                    update geography_climate_region_mappings
                    set is_active = false,
                        metadata = cast(:metadata as jsonb),
                        updated_at = :updated_at
                    where id = :mapping_id
                      and is_active is true
                      and confidence in ('LOCAL_DEMO_DISTRICT_FALLBACK', 'LOCAL_DEMO_SEED')
                """), {
                    "mapping_id": row["id"],
                    "metadata": json.dumps(metadata),
                    "updated_at": now,
                })
                result["counts"]["deactivated_fallback_rows"] += 1

            db.commit()
            result["db_writes_made"] = True
            result["after_active_mappings"] = active_scope_snapshot(db, args.state_lgd_code, args.district_lgd_code)
        else:
            db.rollback()

        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

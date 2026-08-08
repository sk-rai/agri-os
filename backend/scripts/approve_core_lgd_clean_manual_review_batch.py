#!/usr/bin/env python3
"""Approve a small clean CoRE/LGD manual-review batch for later activation.

Default mode is DRY_RUN:
- no activation
- no land-intelligence behavior change
- only changes review_status to APPROVED_FOR_PROMOTION when --apply is passed
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import SessionLocal  # noqa: E402

CORE_SYSTEMS = {
    "CORE_STACK_AGRO_CLIMATIC_ZONE",
    "CORE_STACK_AGRO_ECOLOGICAL_ZONE",
    "CORE_STACK_BIOGEOGRAPHIC_ZONE",
}
DEFAULT_STATES = ["29", "27", "3"]


def jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    return value


def as_dict(row: Any) -> dict[str, Any]:
    return {key: jsonable(value) for key, value in dict(row).items()}


def is_clean_candidate(rows: list[dict[str, Any]], min_overlap: Decimal) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    systems = {row["region_system"] for row in rows if row["region_system"]}

    if len(rows) != 3:
        reasons.append(f"row_count_{len(rows)}")
    if not CORE_SYSTEMS.issubset(systems):
        reasons.append("missing_core_system")
    if max(row["active_fallback_count"] or 0 for row in rows) < 1:
        reasons.append("no_active_fallback")
    if any(row["review_status"] != "MANUAL_REVIEW" for row in rows):
        reasons.append("not_manual_review")
    if any(row["confidence"] != "POLY_REV" or row["is_active"] for row in rows):
        reasons.append("not_inactive_poly_rev")
    if any(row["low_overlap_bucket"] != "NOT_LOW_OVERLAP" for row in rows):
        reasons.append("low_overlap_bucket")
    if any(row["crosswalk_category"] not in ("MATCHED_EXACT", "MATCHED_NAME_VARIANT") for row in rows):
        reasons.append("crosswalk_not_clean")

    overlaps = []
    for row in rows:
        value = row["overlap_percent_of_district"]
        if value is None:
            reasons.append("missing_overlap")
        else:
            overlaps.append(Decimal(str(value)))

    if overlaps and min(overlaps) < min_overlap:
        reasons.append("overlap_below_threshold")

    return not reasons, reasons


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--states", default=",".join(DEFAULT_STATES), help="Comma-separated state LGD codes")
    parser.add_argument("--limit-districts", type=int, default=5)
    parser.add_argument("--min-overlap", default="80.0")
    parser.add_argument("--changed-by", default="script:clean_manual_review_batch")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    states = [part.strip() for part in args.states.split(",") if part.strip()]
    min_overlap = Decimal(str(args.min_overlap))
    mode = "APPLY" if args.apply else "DRY_RUN"

    db = SessionLocal()
    try:
        rows = [
            as_dict(row)
            for row in db.execute(
                text(
                    """
                    with fallback as (
                      select state_lgd_code, district_lgd_code, count(*)::int as active_fallback_count
                      from geography_climate_region_mappings
                      where is_active is true
                        and confidence in ('LOCAL_DEMO_DISTRICT_FALLBACK', 'LOCAL_DEMO_SEED')
                        and scope_level = 'DISTRICT'
                      group by state_lgd_code, district_lgd_code
                    )
                    select
                      m.id::text as mapping_id,
                      m.region_id::text as region_id,
                      m.state_lgd_code,
                      coalesce(m.metadata ->> 'state_name', m.state_lgd_code) as state_name,
                      m.district_lgd_code,
                      coalesce(m.metadata ->> 'district_name', m.district_lgd_code) as district_name,
                      r.region_system,
                      m.region_code,
                      coalesce(r.region_name, m.region_code) as region_name,
                      m.confidence,
                      m.review_status,
                      m.is_active,
                      m.version,
                      m.metadata,
                      nullif(m.metadata ->> 'overlap_percent_of_district', '')::numeric as overlap_percent_of_district,
                      coalesce(nullif(m.metadata ->> 'crosswalk_category', ''), 'UNKNOWN') as crosswalk_category,
                      coalesce(nullif(m.metadata ->> 'low_overlap_bucket', ''), 'NOT_LOW_OVERLAP') as low_overlap_bucket,
                      coalesce(fallback.active_fallback_count, 0) as active_fallback_count
                    from geography_climate_region_mappings m
                    left join geography_climate_regions r on r.id = m.region_id
                    left join fallback
                      on fallback.state_lgd_code is not distinct from m.state_lgd_code
                     and fallback.district_lgd_code is not distinct from m.district_lgd_code
                    where m.scope_level = 'DISTRICT'
                      and m.confidence = 'POLY_REV'
                      and m.is_active is false
                      and m.review_status = 'MANUAL_REVIEW'
                      and m.state_lgd_code = any(:states)
                    order by m.state_lgd_code, district_name, r.region_system
                    """
                ),
                {"states": states},
            ).mappings()
        ]

        grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[(row["state_lgd_code"], row["district_lgd_code"])].append(row)

        candidates = []
        blocked = []
        for (_state, _district), district_rows in grouped.items():
            clean, reasons = is_clean_candidate(district_rows, min_overlap)
            overlaps = [
                Decimal(str(row["overlap_percent_of_district"]))
                for row in district_rows
                if row["overlap_percent_of_district"] is not None
            ]
            item = {
                "state_lgd_code": district_rows[0]["state_lgd_code"],
                "state_name": district_rows[0]["state_name"],
                "district_lgd_code": district_rows[0]["district_lgd_code"],
                "district_name": district_rows[0]["district_name"],
                "row_count": len(district_rows),
                "min_overlap": str(min(overlaps)) if overlaps else None,
                "active_fallback_count": max(row["active_fallback_count"] or 0 for row in district_rows),
                "systems": sorted(row["region_system"] for row in district_rows),
                "mapping_ids": [row["mapping_id"] for row in district_rows],
                "rows": [
                    {
                        "mapping_id": row["mapping_id"],
                        "region_system": row["region_system"],
                        "region_code": row["region_code"],
                        "region_name": row["region_name"],
                        "overlap": str(row["overlap_percent_of_district"]),
                        "crosswalk_category": row["crosswalk_category"],
                        "low_overlap_bucket": row["low_overlap_bucket"],
                    }
                    for row in district_rows
                ],
                "block_reasons": reasons,
            }
            if clean:
                candidates.append(item)
            else:
                blocked.append(item)

        # Balanced selection: round-robin by state, alphabetic within state.
        by_state: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for candidate in sorted(candidates, key=lambda row: (row["state_lgd_code"], row["district_name"])):
            by_state[candidate["state_lgd_code"]].append(candidate)

        selected = []
        while len(selected) < args.limit_districts:
            added = False
            for state in states:
                if by_state[state] and len(selected) < args.limit_districts:
                    selected.append(by_state[state].pop(0))
                    added = True
            if not added:
                break

        selected_mapping_ids = [
            mapping_id
            for district in selected
            for mapping_id in district["mapping_ids"]
        ]

        approved_rows = 0
        if args.apply and selected_mapping_ids:
            event_time = datetime.now(timezone.utc).isoformat()
            for row in rows:
                if row["mapping_id"] not in selected_mapping_ids:
                    continue

                metadata = dict(row["metadata"] or {})
                history = list(metadata.get("review_decision_history") or [])
                event = {
                    "changed_at": event_time,
                    "changed_by": args.changed_by,
                    "from_status": row["review_status"],
                    "to_status": "APPROVED_FOR_PROMOTION",
                    "review_notes": "Clean high-overlap batch approval for later guarded activation.",
                    "action": "BATCH_REVIEW_DECISION_ONLY_NO_ACTIVATION",
                }
                history.append(event)
                metadata["review_decision_history"] = history
                metadata["latest_review_decision"] = event
                metadata["promotion_guardrail"] = {
                    "is_active_remains_false": True,
                    "land_intelligence_behavior_changed": False,
                    "activation_requires_separate_workflow": True,
                }

                result = db.execute(
                    text(
                        """
                        update geography_climate_region_mappings
                        set review_status = 'APPROVED_FOR_PROMOTION',
                            metadata = cast(:metadata as jsonb),
                            updated_at = :updated_at
                        where id = :mapping_id
                          and confidence = 'POLY_REV'
                          and is_active is false
                          and review_status = 'MANUAL_REVIEW'
                        """
                    ),
                    {
                        "mapping_id": row["mapping_id"],
                        "metadata": json.dumps(metadata),
                        "updated_at": datetime.now(timezone.utc),
                    },
                )
                approved_rows += result.rowcount or 0
            db.commit()

        result = {
            "schema_version": "core_lgd_clean_manual_review_batch_approval.v1",
            "mode": mode,
            "db_writes_made": bool(args.apply),
            "external_calls_made": False,
            "filters": {
                "states": states,
                "limit_districts": args.limit_districts,
                "min_overlap": str(min_overlap),
                "source_confidence": "POLY_REV",
                "source_review_status": "MANUAL_REVIEW",
                "source_is_active": False,
            },
            "counts": {
                "candidate_districts": len(candidates),
                "blocked_districts": len(blocked),
                "selected_districts": len(selected),
                "selected_rows": len(selected_mapping_ids),
                "approved_rows": approved_rows,
                "would_approve_rows": 0 if args.apply else len(selected_mapping_ids),
            },
            "samples": {
                "selected": selected,
                "blocked": blocked[:10],
            },
            "readiness": {
                "safe_default_dry_run": not args.apply,
                "activation_not_performed": True,
                "land_intelligence_behavior_changed": False,
                "activation_requires_separate_apply": True,
            },
        }

        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

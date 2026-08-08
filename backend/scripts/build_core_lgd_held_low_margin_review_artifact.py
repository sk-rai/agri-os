#!/usr/bin/env python3
"""Build a manual/map-review artifact for held low-margin CoRE/LGD rows.

Read-only:
- no DB writes
- no external calls
- produces JSON, CSV, and Markdown review packet
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy import text

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import SessionLocal  # noqa: E402

OUTPUT_DIR = REPO_ROOT / "data/staged/core_stack/held_low_margin_review"
HELD_DISTRICTS = {
    ("29", "531"): {
        "canonical_display": "Chamarajanagar / Chamarajanagara",
        "reason": "Minimum overlap is close to threshold; name variant present.",
    },
    ("29", "535"): {
        "canonical_display": "Davanagere / Davangere",
        "reason": "Minimum overlap is close to threshold; name variant present.",
    },
}


def dict_row(row: Any) -> dict[str, Any]:
    return dict(row)


def find_local_geospatial_files() -> list[str]:
    candidates: list[str] = []
    roots = [
        REPO_ROOT / "data/staged",
        REPO_ROOT / "backend/data/staged",
    ]
    suffixes = {".shp", ".geojson", ".gpkg", ".parquet", ".fgb"}
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in suffixes:
                candidates.append(str(path))
    return sorted(candidates)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    try:
        rows = [
            dict_row(row)
            for row in db.execute(
                text(
                    """
                    with fallback as (
                      select
                        state_lgd_code,
                        district_lgd_code,
                        count(*)::int as active_fallback_count,
                        string_agg(m.id::text, ' | ' order by m.id::text) as active_fallback_ids,
                        string_agg(m.region_code, ' | ' order by m.region_code) as active_fallback_region_codes,
                        string_agg(coalesce(r.region_name, m.region_code), ' | ' order by m.region_code) as active_fallback_region_names
                      from geography_climate_region_mappings m
                      left join geography_climate_regions r on r.id = m.region_id
                      where m.is_active is true
                        and m.confidence in ('LOCAL_DEMO_DISTRICT_FALLBACK', 'LOCAL_DEMO_SEED')
                        and m.scope_level = 'DISTRICT'
                      group by m.state_lgd_code, m.district_lgd_code
                    )
                    select
                      m.id::text as mapping_id,
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
                      m.metadata ->> 'region_class_code' as region_class_code,
                      m.metadata ->> 'region_class_name' as region_class_name,
                      m.metadata ->> 'overlap_percent_of_district' as overlap_percent_of_district,
                      m.metadata ->> 'crosswalk_category' as crosswalk_category,
                      coalesce(nullif(m.metadata ->> 'low_overlap_bucket', ''), 'NOT_LOW_OVERLAP') as low_overlap_bucket,
                      m.metadata -> 'latest_review_decision' as latest_review_decision,
                      f.active_fallback_count,
                      f.active_fallback_ids,
                      f.active_fallback_region_codes,
                      f.active_fallback_region_names
                    from geography_climate_region_mappings m
                    left join geography_climate_regions r on r.id = m.region_id
                    left join fallback f
                      on f.state_lgd_code is not distinct from m.state_lgd_code
                     and f.district_lgd_code is not distinct from m.district_lgd_code
                    where m.scope_level = 'DISTRICT'
                      and m.state_lgd_code = '29'
                      and m.district_lgd_code in ('531', '535')
                      and (
                        (m.confidence = 'POLY_REV' and m.review_status = 'APPROVED_FOR_PROMOTION' and m.is_active is false)
                        or (m.confidence in ('LOCAL_DEMO_DISTRICT_FALLBACK', 'LOCAL_DEMO_SEED'))
                      )
                    order by m.district_lgd_code, m.confidence, r.region_system
                    """
                )
            ).mappings()
        ]

        grouped: dict[str, dict[str, Any]] = {}
        csv_rows: list[dict[str, Any]] = []

        for row in rows:
            key_tuple = (row["state_lgd_code"], row["district_lgd_code"])
            key = f"{row['state_lgd_code']}/{row['district_lgd_code']}"
            held_info = HELD_DISTRICTS.get(key_tuple, {})
            grouped.setdefault(
                key,
                {
                    "state_lgd_code": row["state_lgd_code"],
                    "state_name": row["state_name"],
                    "district_lgd_code": row["district_lgd_code"],
                    "district_name": row["district_name"],
                    "display_name": held_info.get("canonical_display", row["district_name"]),
                    "hold_reason": held_info.get("reason", "Held for manual review."),
                    "active_fallback_count": row["active_fallback_count"],
                    "active_fallback_ids": row["active_fallback_ids"],
                    "active_fallback_region_codes": row["active_fallback_region_codes"],
                    "active_fallback_region_names": row["active_fallback_region_names"],
                    "approved_rows": [],
                    "fallback_rows": [],
                },
            )

            record = {
                "mapping_id": row["mapping_id"],
                "region_system": row["region_system"],
                "region_code": row["region_code"],
                "region_name": row["region_name"],
                "confidence": row["confidence"],
                "review_status": row["review_status"],
                "is_active": row["is_active"],
                "version": row["version"],
                "region_class_code": row["region_class_code"],
                "region_class_name": row["region_class_name"],
                "overlap_percent_of_district": row["overlap_percent_of_district"],
                "crosswalk_category": row["crosswalk_category"],
                "low_overlap_bucket": row["low_overlap_bucket"],
                "latest_review_decision": row["latest_review_decision"],
            }

            if row["confidence"] == "POLY_REV":
                grouped[key]["approved_rows"].append(record)
            else:
                grouped[key]["fallback_rows"].append(record)

            csv_row = {
                "state_lgd_code": row["state_lgd_code"],
                "state_name": row["state_name"],
                "district_lgd_code": row["district_lgd_code"],
                "district_name": row["district_name"],
                **{k: v for k, v in record.items() if k != "latest_review_decision"},
                "active_fallback_count": row["active_fallback_count"],
                "active_fallback_region_codes": row["active_fallback_region_codes"],
            }
            csv_rows.append(csv_row)

        for district in grouped.values():
            overlaps = [
                float(row["overlap_percent_of_district"])
                for row in district["approved_rows"]
                if row["overlap_percent_of_district"] not in (None, "")
            ]
            district["approved_row_count"] = len(district["approved_rows"])
            district["min_overlap"] = min(overlaps) if overlaps else None
            district["map_review_recommendation"] = "REVIEW_BEFORE_ACTIVATION"
            district["activation_policy"] = {
                "activation_allowed_by_script": True,
                "activation_recommended_now": False,
                "reason": "Approved rows are mechanically eligible, but held because minimum overlap is near threshold.",
            }

        geospatial_files = find_local_geospatial_files()
        relevant_geospatial_files = [
            item for item in geospatial_files
            if any(token in item.lower() for token in ["bharat", "district", "boundary", "core", "soi", "state"])
        ]

        result = {
            "schema_version": "core_lgd_held_low_margin_review_artifact.v1",
            "mode": "READ_ONLY_ARTIFACT",
            "db_writes_made": False,
            "external_calls_made": False,
            "districts": list(grouped.values()),
            "geospatial_inventory": {
                "candidate_file_count": len(geospatial_files),
                "relevant_file_count": len(relevant_geospatial_files),
                "relevant_files_sample": relevant_geospatial_files[:30],
            },
            "review_checklist": [
                "Open candidate district geometry and CoRE overlay geometry in QGIS or admin map view.",
                "Confirm whether the low-overlap row reflects a real edge/transition-zone split rather than source misalignment.",
                "Compare district identity/name variant against backend LGD master.",
                "If visual/manual review confirms the assignment, activate via scoped guarded activation script.",
                "If not confirmed, leave approved rows inactive or return them to MANUAL_REVIEW/REJECTED.",
            ],
            "readiness": {
                "safe_read_only": True,
                "activation_not_performed": True,
                "map_review_useful": True,
                "ready_for_manual_review": True,
            },
        }

        json_path = OUTPUT_DIR / "core_lgd_held_low_margin_review_artifact.json"
        csv_path = OUTPUT_DIR / "core_lgd_held_low_margin_review_rows.csv"
        md_path = OUTPUT_DIR / "core_lgd_held_low_margin_review.md"

        json_path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str))

        if csv_rows:
            with csv_path.open("w", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(csv_rows[0].keys()))
                writer.writeheader()
                writer.writerows(csv_rows)

        md_lines = [
            "# CoRE/LGD held low-margin review",
            "",
            "This packet is read-only. No rows were activated.",
            "",
        ]
        for district in result["districts"]:
            md_lines.extend([
                f"## {district['display_name']} (`{district['state_lgd_code']}/{district['district_lgd_code']}`)",
                "",
                f"- Backend district name: {district['district_name']}",
                f"- Minimum overlap: {district['min_overlap']}%",
                f"- Active fallback: {district['active_fallback_region_codes']}",
                f"- Recommendation: {district['map_review_recommendation']}",
                "",
                "| System | Region | Overlap | Crosswalk | Bucket |",
                "|---|---|---:|---|---|",
            ])
            for row in district["approved_rows"]:
                md_lines.append(
                    f"| {row['region_system']} | {row['region_name']} | {row['overlap_percent_of_district']} | {row['crosswalk_category']} | {row['low_overlap_bucket']} |"
                )
            md_lines.append("")
        md_lines.extend([
            "## Review checklist",
            "",
            *[f"- {item}" for item in result["review_checklist"]],
            "",
            "## Relevant local geospatial files sample",
            "",
            *[f"- `{item}`" for item in relevant_geospatial_files[:30]],
            "",
        ])
        md_path.write_text("\n".join(md_lines))

        result["output_files"] = {
            "json": str(json_path),
            "csv": str(csv_path),
            "markdown": str(md_path),
        }

        json_path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str))
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

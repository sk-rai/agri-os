#!/usr/bin/env python3
"""Seed district-level fallback mappings for climate regions.

This does NOT claim polygon-accurate CoRE mapping. It inherits the current
selected-state starter climate region down to each district so Android/admin can
use district-level approximation until CoRE polygon/LGD boundary overlay exists.

Dry-run by default. Use --apply to write.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
from app.modules.master_data.models import (
    GeographyClimateRegion,
    GeographyClimateRegionMapping,
    GeographyDistrict,
    GeographyState,
)

STATE_REGION_MAP = {
    "27": "IND_ACZ_WESTERN_PLATEAU_HILLS_MH",          # Maharashtra
    "29": "IND_ACZ_SOUTHERN_PLATEAU_HILLS_KA",         # Karnataka
    "9": "IND_ACZ_UPPER_MIDDLE_GANGETIC_PLAINS_UP",   # Uttar Pradesh
    "3": "IND_ACZ_TRANS_GANGETIC_PLAINS_PB",           # Punjab
    "19": "IND_ACZ_LOWER_GANGETIC_PLAINS_WB",          # West Bengal
}

SOURCE_REFS = [
    {
        "source": "LOCAL_STATE_TO_DISTRICT_FALLBACK",
        "source_role": "DISTRICT_APPROXIMATION",
        "note": (
            "District mapping inherited from selected-state starter climate region. "
            "Replace/refine after CoRE polygon export and LGD boundary/centroid overlay."
        ),
        "review_required": True,
    }
]


def now():
    return datetime.now(timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write changes. Default is dry-run.")
    args = parser.parse_args()

    result = {
        "schema_version": "climate_region_district_fallback_seed_result.v1",
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "target_state_count": len(STATE_REGION_MAP),
        "districts_seen": 0,
        "district_mappings_created": 0,
        "district_mappings_existing": 0,
        "missing_regions": [],
        "missing_states": [],
        "state_summaries": {},
        "warning": "Approximate district fallback; not polygon-derived.",
    }

    db = SessionLocal()
    try:
        for state_lgd_code, region_code in STATE_REGION_MAP.items():
            state = db.query(GeographyState).filter(GeographyState.lgd_code == state_lgd_code).first()
            region = db.query(GeographyClimateRegion).filter(
                GeographyClimateRegion.region_code == region_code,
                GeographyClimateRegion.is_active == True,
            ).first()

            if not state:
                result["missing_states"].append(state_lgd_code)
                continue
            if not region:
                result["missing_regions"].append(region_code)
                continue

            districts = (
                db.query(GeographyDistrict)
                .filter(GeographyDistrict.state_id == state.id, GeographyDistrict.is_active == True)
                .order_by(GeographyDistrict.canonical_name)
                .all()
            )

            summary = {
                "state_name": state.canonical_name,
                "state_lgd_code": state.lgd_code,
                "region_code": region.region_code,
                "district_count": len(districts),
                "created": 0,
                "existing": 0,
            }

            for district in districts:
                result["districts_seen"] += 1
                existing = db.query(GeographyClimateRegionMapping).filter(
                    GeographyClimateRegionMapping.region_code == region.region_code,
                    GeographyClimateRegionMapping.scope_level == "DISTRICT",
                    GeographyClimateRegionMapping.state_lgd_code == state.lgd_code,
                    GeographyClimateRegionMapping.district_lgd_code == district.lgd_code,
                    GeographyClimateRegionMapping.is_active == True,
                ).first()

                if existing:
                    result["district_mappings_existing"] += 1
                    summary["existing"] += 1
                    continue

                result["district_mappings_created"] += 1
                summary["created"] += 1

                if args.apply:
                    db.add(
                        GeographyClimateRegionMapping(
                            id=uuid.uuid4(),
                            region_id=region.id,
                            region_code=region.region_code,
                            scope_level="DISTRICT",
                            state_lgd_code=state.lgd_code,
                            district_lgd_code=district.lgd_code,
                            source_references=SOURCE_REFS,
                            confidence="LOCAL_DEMO_DISTRICT_FALLBACK",
                            review_status="MANUAL_REVIEW",
                            metadata_={
                                "state_name": state.canonical_name,
                                "district_name": district.canonical_name,
                                "mapping_method": "STATE_REGION_INHERITED_TO_DISTRICT",
                                "precision": "APPROXIMATE",
                                "replace_with": "CORE_STACK_POLYGON_OVERLAY_OR_OFFICIAL_DISTRICT_CROSSWALK",
                            },
                            created_at=now(),
                            updated_at=now(),
                        )
                    )

            result["state_summaries"][state.canonical_name] = summary

        if args.apply:
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not result["missing_regions"] and not result["missing_states"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

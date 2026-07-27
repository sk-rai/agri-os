#!/usr/bin/env python3
"""Audit crop climate suitability metadata readiness."""

from __future__ import annotations

from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func

from app.core.database import SessionLocal
from app.modules.master_data.models import (
    Crop,
    CropClimateSuitabilityRule,
    GeographyClimateRegion,
    GeographyClimateRegionMapping,
    GeographyState,
)

SELECTED_STATES = ["MAHARASHTRA", "KARNATAKA", "UTTAR PRADESH", "PUNJAB", "WEST BENGAL"]
TARGET_RULES = 45
TARGET_REGIONS = 5


def rows_to_dict(rows):
    return {str(k): int(v) for k, v in rows}


def main() -> int:
    db = SessionLocal()
    try:
        regions = db.query(GeographyClimateRegion).filter(GeographyClimateRegion.is_active == True).count()
        mappings = db.query(GeographyClimateRegionMapping).filter(GeographyClimateRegionMapping.is_active == True).count()
        rules = db.query(CropClimateSuitabilityRule).filter(CropClimateSuitabilityRule.is_active == True).count()
        selected_state_rows = (
            db.query(GeographyState)
            .filter(func.upper(GeographyState.canonical_name).in_(SELECTED_STATES))
            .all()
        )
        selected_state_codes = {state.canonical_name.upper(): state.lgd_code for state in selected_state_rows}
        mapped_selected_states = set(
            code
            for (code,) in db.query(GeographyClimateRegionMapping.state_lgd_code)
            .filter(
                GeographyClimateRegionMapping.scope_level == "STATE",
                GeographyClimateRegionMapping.state_lgd_code.in_(selected_state_codes.values()),
                GeographyClimateRegionMapping.is_active == True,
            )
            .all()
        )
        rule_season_counts = rows_to_dict(
            db.query(CropClimateSuitabilityRule.season_code, func.count(CropClimateSuitabilityRule.id))
            .filter(CropClimateSuitabilityRule.is_active == True)
            .group_by(CropClimateSuitabilityRule.season_code)
            .order_by(CropClimateSuitabilityRule.season_code)
            .all()
        )
        rule_status_counts = rows_to_dict(
            db.query(CropClimateSuitabilityRule.suitability_status, func.count(CropClimateSuitabilityRule.id))
            .filter(CropClimateSuitabilityRule.is_active == True)
            .group_by(CropClimateSuitabilityRule.suitability_status)
            .order_by(CropClimateSuitabilityRule.suitability_status)
            .all()
        )
        crop_rule_counts = rows_to_dict(
            db.query(CropClimateSuitabilityRule.crop_code, func.count(CropClimateSuitabilityRule.id))
            .filter(CropClimateSuitabilityRule.is_active == True)
            .group_by(CropClimateSuitabilityRule.crop_code)
            .order_by(CropClimateSuitabilityRule.crop_code)
            .all()
        )
        review_counts = rows_to_dict(
            db.query(CropClimateSuitabilityRule.review_status, func.count(CropClimateSuitabilityRule.id))
            .filter(CropClimateSuitabilityRule.is_active == True)
            .group_by(CropClimateSuitabilityRule.review_status)
            .order_by(CropClimateSuitabilityRule.review_status)
            .all()
        )
        crops_with_rules = len(crop_rule_counts)
        crops_total = db.query(Crop).filter(Crop.is_active == True).count()
        selected_state_ready = len(mapped_selected_states) == len(selected_state_codes) == len(SELECTED_STATES)
        result = {
            "schema_version": "crop_climate_suitability_readiness_audit.v1",
            "target": {
                "selected_states": SELECTED_STATES,
                "starter_region_minimum": TARGET_REGIONS,
                "starter_rule_minimum": TARGET_RULES,
            },
            "counts": {
                "active_crops": crops_total,
                "climate_regions": regions,
                "climate_region_mappings": mappings,
                "crop_suitability_rules": rules,
                "crops_with_suitability_rules": crops_with_rules,
            },
            "selected_state_codes": selected_state_codes,
            "selected_state_mapping_ready": selected_state_ready,
            "rule_season_counts": rule_season_counts,
            "rule_status_counts": rule_status_counts,
            "rule_review_status_counts": review_counts,
            "crop_rule_counts": crop_rule_counts,
            "readiness": {
                "starter_regions_ready": regions >= TARGET_REGIONS,
                "starter_rules_ready": rules >= TARGET_RULES,
                "selected_states_mapped": selected_state_ready,
                "needs_source_verification": review_counts.get("MANUAL_REVIEW", 0) > 0,
                "ready_for_android_demo_warnings": selected_state_ready and rules >= TARGET_RULES,
            },
            "next_actions": [
                "Run seed_crop_climate_suitability.py --apply if starter regions/rules are missing.",
                "Attach official source references before upgrading confidence from LOCAL_DEMO_SEED.",
                "Refine state-level mappings to district/block mappings after source geometry or authoritative district-zone crosswalk is available.",
                "Expose an Android-safe crop suitability endpoint once seed and audit are green.",
            ],
        }
    finally:
        db.close()
    print(json.dumps(result, indent=2, sort_keys=True))
    ready = result["readiness"]["starter_regions_ready"] and result["readiness"]["starter_rules_ready"] and result["readiness"]["selected_states_mapped"]
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
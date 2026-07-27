#!/usr/bin/env python3
"""Seed starter crop climate region and suitability metadata.

Dry-run by default. Use --apply to write.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
from app.modules.master_data.models import (
    Crop,
    CropCategory,
    CropClimateSuitabilityRule,
    GeographyClimateRegion,
    GeographyClimateRegionMapping,
    GeographyState,
)

SOURCE_REFS = [
    {
        "source": "STARTER_RESEARCH_STACK",
        "source_role": "LOCAL_DEMO_SEED_REFERENCE",
        "note": "Starter mapping based on Indian agro-climatic/agro-ecological concepts. Needs source-file review before GOVT_SOURCE confidence.",
        "review_required": True,
    }
]

REGIONS = [
    {
        "region_code": "IND_ACZ_WESTERN_PLATEAU_HILLS_MH",
        "region_name": "Maharashtra - Western Plateau and Hills starter zone",
        "region_system": "AGRO_CLIMATIC_ZONE_STARTER",
        "state_name": "MAHARASHTRA",
        "rainfall_band_mm": {"typical_annual_min": 500, "typical_annual_max": 1200, "note": "Highly variable; Konkan/Ghats need district-level refinement."},
        "temperature_band_c": {"typical_min": 18, "typical_max": 36},
        "length_of_growing_period_days": {"typical_min": 90, "typical_max": 180},
        "dominant_soil_groups": ["BLACK_COTTON", "RED", "ALLUVIAL_COASTAL"],
        "irrigation_context": {"default": "MIXED_RAINFED_IRRIGATED", "warning": "Sugarcane and summer crops require irrigation in many districts."},
    },
    {
        "region_code": "IND_ACZ_SOUTHERN_PLATEAU_HILLS_KA",
        "region_name": "Karnataka - Southern Plateau and Hills starter zone",
        "region_system": "AGRO_CLIMATIC_ZONE_STARTER",
        "state_name": "KARNATAKA",
        "rainfall_band_mm": {"typical_annual_min": 450, "typical_annual_max": 1000, "note": "Coastal/Malenadu districts need separate high-rainfall mapping."},
        "temperature_band_c": {"typical_min": 16, "typical_max": 35},
        "length_of_growing_period_days": {"typical_min": 90, "typical_max": 180},
        "dominant_soil_groups": ["RED", "BLACK_COTTON", "LATERITE"],
        "irrigation_context": {"default": "MIXED_RAINFED_IRRIGATED"},
    },
    {
        "region_code": "IND_ACZ_UPPER_MIDDLE_GANGETIC_PLAINS_UP",
        "region_name": "Uttar Pradesh - Upper/Middle Gangetic Plains starter zone",
        "region_system": "AGRO_CLIMATIC_ZONE_STARTER",
        "state_name": "UTTAR PRADESH",
        "rainfall_band_mm": {"typical_annual_min": 600, "typical_annual_max": 1200, "note": "Western and eastern UP differ materially; district refinement required."},
        "temperature_band_c": {"typical_min": 8, "typical_max": 42},
        "length_of_growing_period_days": {"typical_min": 120, "typical_max": 210},
        "dominant_soil_groups": ["ALLUVIAL"],
        "irrigation_context": {"default": "IRRIGATED_AND_RAINFED"},
    },
    {
        "region_code": "IND_ACZ_TRANS_GANGETIC_PLAINS_PB",
        "region_name": "Punjab - Trans-Gangetic Plains starter zone",
        "region_system": "AGRO_CLIMATIC_ZONE_STARTER",
        "state_name": "PUNJAB",
        "rainfall_band_mm": {"typical_annual_min": 300, "typical_annual_max": 800, "note": "Suitability often depends on irrigation availability."},
        "temperature_band_c": {"typical_min": 5, "typical_max": 42},
        "length_of_growing_period_days": {"typical_min": 120, "typical_max": 210},
        "dominant_soil_groups": ["ALLUVIAL"],
        "irrigation_context": {"default": "IRRIGATION_DOMINANT", "warning": "Paddy should carry groundwater/water-use warning in many contexts."},
    },
    {
        "region_code": "IND_ACZ_LOWER_GANGETIC_PLAINS_WB",
        "region_name": "West Bengal - Lower Gangetic Plains starter zone",
        "region_system": "AGRO_CLIMATIC_ZONE_STARTER",
        "state_name": "WEST BENGAL",
        "rainfall_band_mm": {"typical_annual_min": 1200, "typical_annual_max": 2200, "note": "North Bengal hills and coastal Sundarbans need separate refinement."},
        "temperature_band_c": {"typical_min": 10, "typical_max": 36},
        "length_of_growing_period_days": {"typical_min": 180, "typical_max": 270},
        "dominant_soil_groups": ["ALLUVIAL", "LATERITE", "DELTAIC"],
        "irrigation_context": {"default": "HIGH_RAINFALL_AND_IRRIGATED"},
    },
]

CROP_PROFILES = {
    "RICE": ("CEREALS", "Rice (Paddy)", "Oryza sativa", 120, ["KHARIF"], [{"lang": "hi", "name": "???"}]),
    "WHEAT": ("CEREALS", "Wheat", "Triticum aestivum", 140, ["RABI"], [{"lang": "hi", "name": "?????"}]),
    "MAIZE": ("CEREALS", "Maize", "Zea mays", 100, ["KHARIF", "RABI", "ZAID"], [{"lang": "hi", "name": "?????"}]),
    "SORGHUM": ("CEREALS", "Sorghum (Jowar)", "Sorghum bicolor", 110, ["KHARIF", "RABI"], [{"lang": "hi", "name": "?????"}]),
    "RAGI": ("CEREALS", "Finger Millet (Ragi)", "Eleusine coracana", 110, ["KHARIF"], [{"lang": "hi", "name": "?????"}]),
    "GRAM": ("PULSES", "Gram (Chickpea)", "Cicer arietinum", 110, ["RABI"], [{"lang": "hi", "name": "???"}]),
    "PIGEON_PEA": ("PULSES", "Pigeon Pea (Arhar/Tur)", "Cajanus cajan", 180, ["KHARIF"], [{"lang": "hi", "name": "????"}]),
    "MOONG": ("PULSES", "Green Gram (Moong)", "Vigna radiata", 65, ["ZAID", "KHARIF"], [{"lang": "hi", "name": "????"}]),
    "LENTIL": ("PULSES", "Lentil", "Lens culinaris", 115, ["RABI"], [{"lang": "hi", "name": "????"}]),
    "MUSTARD": ("OILSEEDS", "Mustard", "Brassica juncea", 120, ["RABI"], [{"lang": "hi", "name": "?????"}]),
    "GROUNDNUT": ("OILSEEDS", "Groundnut", "Arachis hypogaea", 120, ["KHARIF", "ZAID"], [{"lang": "hi", "name": "???????"}]),
    "SOYBEAN": ("OILSEEDS", "Soybean", "Glycine max", 100, ["KHARIF"], [{"lang": "hi", "name": "???????"}]),
    "SUNFLOWER": ("OILSEEDS", "Sunflower", "Helianthus annuus", 90, ["ZAID", "KHARIF"], [{"lang": "hi", "name": "????????"}]),
    "SESAME": ("OILSEEDS", "Sesame", "Sesamum indicum", 90, ["ZAID", "KHARIF"], [{"lang": "hi", "name": "???"}]),
    "SUGARCANE": ("CASH_CROPS", "Sugarcane", "Saccharum officinarum", 360, ["KHARIF", "RABI"], [{"lang": "hi", "name": "?????"}]),
    "COTTON": ("CASH_CROPS", "Cotton", "Gossypium spp.", 180, ["KHARIF"], [{"lang": "hi", "name": "????"}]),
    "JUTE": ("FIBRE_CROPS", "Jute", "Corchorus spp.", 120, ["KHARIF"], [{"lang": "hi", "name": "???"}]),
    "POTATO": ("VEGETABLES", "Potato", "Solanum tuberosum", 90, ["RABI"], [{"lang": "hi", "name": "???"}]),
    "ONION": ("VEGETABLES", "Onion", "Allium cepa", 120, ["RABI", "KHARIF"], [{"lang": "hi", "name": "?????"}]),
    "TOMATO": ("VEGETABLES", "Tomato", "Solanum lycopersicum", 100, ["RABI", "KHARIF"], [{"lang": "hi", "name": "?????"}]),
    "CUCUMBER": ("VEGETABLES", "Cucumber", "Cucumis sativus", 60, ["ZAID"], [{"lang": "hi", "name": "????"}]),
    "BOTTLE_GOURD": ("VEGETABLES", "Bottle Gourd", "Lagenaria siceraria", 75, ["ZAID", "KHARIF"], [{"lang": "hi", "name": "????"}]),
    "CHILLI": ("VEGETABLES", "Chilli", "Capsicum annuum", 150, ["KHARIF", "RABI"], [{"lang": "hi", "name": "?????"}]),
    "WATERMELON": ("VEGETABLES", "Watermelon", "Citrullus lanatus", 90, ["ZAID"], [{"lang": "hi", "name": "?????"}]),
    "BANANA": ("HORTICULTURE", "Banana", "Musa spp.", 365, ["PERENNIAL"], [{"lang": "hi", "name": "????"}]),
    "FODDER_MAIZE": ("FODDER", "Fodder Maize", "Zea mays", 75, ["ZAID", "KHARIF"], [{"lang": "hi", "name": "???? ?????"}]),
}

RULES = [
    # Maharashtra
    ("IND_ACZ_WESTERN_PLATEAU_HILLS_MH", "COTTON", "KHARIF", "SUITABLE", True),
    ("IND_ACZ_WESTERN_PLATEAU_HILLS_MH", "SOYBEAN", "KHARIF", "SUITABLE", False),
    ("IND_ACZ_WESTERN_PLATEAU_HILLS_MH", "SORGHUM", "KHARIF", "SUITABLE", False),
    ("IND_ACZ_WESTERN_PLATEAU_HILLS_MH", "GROUNDNUT", "KHARIF", "SUITABLE", False),
    ("IND_ACZ_WESTERN_PLATEAU_HILLS_MH", "SUGARCANE", "KHARIF", "CONDITIONAL", True),
    ("IND_ACZ_WESTERN_PLATEAU_HILLS_MH", "ONION", "RABI", "SUITABLE", True),
    ("IND_ACZ_WESTERN_PLATEAU_HILLS_MH", "GRAM", "RABI", "SUITABLE", False),
    ("IND_ACZ_WESTERN_PLATEAU_HILLS_MH", "SUNFLOWER", "ZAID", "CONDITIONAL", True),
    ("IND_ACZ_WESTERN_PLATEAU_HILLS_MH", "WATERMELON", "ZAID", "CONDITIONAL", True),
    # Karnataka
    ("IND_ACZ_SOUTHERN_PLATEAU_HILLS_KA", "RICE", "KHARIF", "CONDITIONAL", True),
    ("IND_ACZ_SOUTHERN_PLATEAU_HILLS_KA", "RAGI", "KHARIF", "SUITABLE", False),
    ("IND_ACZ_SOUTHERN_PLATEAU_HILLS_KA", "MAIZE", "KHARIF", "SUITABLE", False),
    ("IND_ACZ_SOUTHERN_PLATEAU_HILLS_KA", "GROUNDNUT", "KHARIF", "SUITABLE", False),
    ("IND_ACZ_SOUTHERN_PLATEAU_HILLS_KA", "PIGEON_PEA", "KHARIF", "SUITABLE", False),
    ("IND_ACZ_SOUTHERN_PLATEAU_HILLS_KA", "SUGARCANE", "KHARIF", "CONDITIONAL", True),
    ("IND_ACZ_SOUTHERN_PLATEAU_HILLS_KA", "TOMATO", "RABI", "SUITABLE", True),
    ("IND_ACZ_SOUTHERN_PLATEAU_HILLS_KA", "CHILLI", "RABI", "SUITABLE", True),
    ("IND_ACZ_SOUTHERN_PLATEAU_HILLS_KA", "CUCUMBER", "ZAID", "CONDITIONAL", True),
    # Uttar Pradesh
    ("IND_ACZ_UPPER_MIDDLE_GANGETIC_PLAINS_UP", "RICE", "KHARIF", "SUITABLE", True),
    ("IND_ACZ_UPPER_MIDDLE_GANGETIC_PLAINS_UP", "WHEAT", "RABI", "HIGHLY_SUITABLE", True),
    ("IND_ACZ_UPPER_MIDDLE_GANGETIC_PLAINS_UP", "SUGARCANE", "KHARIF", "SUITABLE", True),
    ("IND_ACZ_UPPER_MIDDLE_GANGETIC_PLAINS_UP", "POTATO", "RABI", "HIGHLY_SUITABLE", True),
    ("IND_ACZ_UPPER_MIDDLE_GANGETIC_PLAINS_UP", "MUSTARD", "RABI", "SUITABLE", False),
    ("IND_ACZ_UPPER_MIDDLE_GANGETIC_PLAINS_UP", "GRAM", "RABI", "SUITABLE", False),
    ("IND_ACZ_UPPER_MIDDLE_GANGETIC_PLAINS_UP", "MAIZE", "ZAID", "CONDITIONAL", True),
    ("IND_ACZ_UPPER_MIDDLE_GANGETIC_PLAINS_UP", "MOONG", "ZAID", "SUITABLE", True),
    ("IND_ACZ_UPPER_MIDDLE_GANGETIC_PLAINS_UP", "BOTTLE_GOURD", "ZAID", "SUITABLE", True),
    # Punjab
    ("IND_ACZ_TRANS_GANGETIC_PLAINS_PB", "RICE", "KHARIF", "CONDITIONAL", True),
    ("IND_ACZ_TRANS_GANGETIC_PLAINS_PB", "WHEAT", "RABI", "HIGHLY_SUITABLE", True),
    ("IND_ACZ_TRANS_GANGETIC_PLAINS_PB", "MAIZE", "KHARIF", "SUITABLE", True),
    ("IND_ACZ_TRANS_GANGETIC_PLAINS_PB", "COTTON", "KHARIF", "SUITABLE", True),
    ("IND_ACZ_TRANS_GANGETIC_PLAINS_PB", "POTATO", "RABI", "SUITABLE", True),
    ("IND_ACZ_TRANS_GANGETIC_PLAINS_PB", "MUSTARD", "RABI", "SUITABLE", False),
    ("IND_ACZ_TRANS_GANGETIC_PLAINS_PB", "SUNFLOWER", "ZAID", "CONDITIONAL", True),
    ("IND_ACZ_TRANS_GANGETIC_PLAINS_PB", "MOONG", "ZAID", "SUITABLE", True),
    ("IND_ACZ_TRANS_GANGETIC_PLAINS_PB", "FODDER_MAIZE", "ZAID", "SUITABLE", True),
    # West Bengal
    ("IND_ACZ_LOWER_GANGETIC_PLAINS_WB", "RICE", "KHARIF", "HIGHLY_SUITABLE", False),
    ("IND_ACZ_LOWER_GANGETIC_PLAINS_WB", "JUTE", "KHARIF", "HIGHLY_SUITABLE", False),
    ("IND_ACZ_LOWER_GANGETIC_PLAINS_WB", "POTATO", "RABI", "HIGHLY_SUITABLE", True),
    ("IND_ACZ_LOWER_GANGETIC_PLAINS_WB", "MUSTARD", "RABI", "SUITABLE", False),
    ("IND_ACZ_LOWER_GANGETIC_PLAINS_WB", "LENTIL", "RABI", "SUITABLE", False),
    ("IND_ACZ_LOWER_GANGETIC_PLAINS_WB", "MAIZE", "RABI", "SUITABLE", True),
    ("IND_ACZ_LOWER_GANGETIC_PLAINS_WB", "SESAME", "ZAID", "CONDITIONAL", False),
    ("IND_ACZ_LOWER_GANGETIC_PLAINS_WB", "CUCUMBER", "ZAID", "SUITABLE", True),
    ("IND_ACZ_LOWER_GANGETIC_PLAINS_WB", "BANANA", "PERENNIAL", "SUITABLE", True),
]


def now():
    return datetime.now(timezone.utc)


def find_state(db, state_name: str):
    normalized = state_name.upper()
    return db.query(GeographyState).filter(GeographyState.canonical_name.ilike(normalized)).first()


def get_or_create_category(db, code: str, dry_run: bool, result: dict):
    existing = db.query(CropCategory).filter(CropCategory.code == code).first()
    if existing:
        return existing
    result["categories_created"] += 1
    if dry_run:
        return None
    category = CropCategory(id=uuid.uuid4(), code=code, canonical_name=code.replace("_", " ").title(), aliases=[], created_at=now(), updated_at=now())
    db.add(category)
    db.flush()
    return category


def upsert_crops(db, dry_run: bool, result: dict):
    for code, (category_code, name, scientific, days, seasons, aliases) in CROP_PROFILES.items():
        crop = db.query(Crop).filter(Crop.code == code).first()
        if not crop:
            category = get_or_create_category(db, category_code, dry_run, result)
            result["crops_created"] += 1
            if dry_run:
                continue
            crop = Crop(
                id=uuid.uuid4(),
                code=code,
                category_id=category.id,
                canonical_name=name,
                scientific_name=scientific,
                typical_duration_days=days,
                suitable_seasons=seasons,
                aliases=aliases,
                created_at=now(),
                updated_at=now(),
            )
            db.add(crop)
            continue
        merged_seasons = sorted(set(crop.suitable_seasons or []) | set(seasons))
        if merged_seasons != (crop.suitable_seasons or []):
            result["crops_updated"] += 1
            if not dry_run:
                crop.suitable_seasons = merged_seasons
                crop.updated_at = now()


def upsert_regions(db, dry_run: bool, result: dict):
    for region_data in REGIONS:
        region = db.query(GeographyClimateRegion).filter(GeographyClimateRegion.region_code == region_data["region_code"]).first()
        payload = {k: v for k, v in region_data.items() if k not in {"state_name"}}
        payload.update({"source_references": SOURCE_REFS, "confidence": "LOCAL_DEMO_SEED", "review_status": "MANUAL_REVIEW"})
        if not region:
            result["regions_created"] += 1
            if dry_run:
                continue
            region = GeographyClimateRegion(id=uuid.uuid4(), created_at=now(), updated_at=now(), **payload)
            db.add(region)
            db.flush()
        else:
            result["regions_updated"] += 1
            if not dry_run:
                for key, value in payload.items():
                    setattr(region, key, value)
                region.updated_at = now()

        state = find_state(db, region_data["state_name"])
        if not state:
            result["missing_state_mappings"].append(region_data["state_name"])
            continue
        mapping = db.query(GeographyClimateRegionMapping).filter(
            GeographyClimateRegionMapping.region_code == region_data["region_code"],
            GeographyClimateRegionMapping.scope_level == "STATE",
            GeographyClimateRegionMapping.state_lgd_code == state.lgd_code,
        ).first()
        if not mapping:
            result["state_mappings_created"] += 1
            if not dry_run:
                db.add(GeographyClimateRegionMapping(
                    id=uuid.uuid4(),
                    region_id=region.id,
                    region_code=region.region_code,
                    scope_level="STATE",
                    state_lgd_code=state.lgd_code,
                    source_references=SOURCE_REFS,
                    confidence="LOCAL_DEMO_SEED",
                    review_status="MANUAL_REVIEW",
                    metadata_={"state_name": state.canonical_name},
                    created_at=now(),
                    updated_at=now(),
                ))


def upsert_rules(db, dry_run: bool, result: dict):
    for region_code, crop_code, season_code, status, irrigation_required in RULES:
        crop = db.query(Crop).filter(Crop.code == crop_code).first()
        region = db.query(GeographyClimateRegion).filter(GeographyClimateRegion.region_code == region_code).first()
        if not crop or not region:
            result["missing_rule_dependencies"].append({"region_code": region_code, "crop_code": crop_code, "season_code": season_code})
            continue
        rule = db.query(CropClimateSuitabilityRule).filter(
            CropClimateSuitabilityRule.crop_code == crop_code,
            CropClimateSuitabilityRule.season_code == season_code,
            CropClimateSuitabilityRule.region_code == region_code,
            CropClimateSuitabilityRule.geography_scope == "REGION",
        ).first()
        warning_rules = []
        if status == "CONDITIONAL" or irrigation_required:
            warning_rules.append({"code": "CHECK_IRRIGATION_AND_LOCAL_PRACTICE", "severity": "INFO", "message": "Suitability depends on irrigation, local rainfall, variety, and district package of practices."})
        payload = {
            "suitability_status": status,
            "confidence": "LOCAL_DEMO_SEED",
            "irrigation_required": irrigation_required,
            "soil_requirements": [],
            "typical_sowing_window": {"season_code": season_code, "source": "LOCAL_DEMO_SEED"},
            "typical_harvest_window": {"source": "LOCAL_DEMO_SEED"},
            "warning_rules": warning_rules,
            "source_references": SOURCE_REFS,
            "review_status": "MANUAL_REVIEW",
            "review_notes": "Starter suitability row for Android/client demo. Upgrade after source-document review.",
            "metadata_": {"starter_state_pack": True},
        }
        if not rule:
            result["rules_created"] += 1
            if not dry_run:
                db.add(CropClimateSuitabilityRule(id=uuid.uuid4(), crop_code=crop_code, season_code=season_code, region_code=region_code, geography_scope="REGION", created_at=now(), updated_at=now(), **payload))
        else:
            result["rules_updated"] += 1
            if not dry_run:
                for key, value in payload.items():
                    setattr(rule, key, value)
                rule.updated_at = now()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write changes. Default is dry-run.")
    args = parser.parse_args()
    result = {
        "schema_version": "crop_climate_suitability_seed_result.v1",
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "regions_targeted": len(REGIONS),
        "rules_targeted": len(RULES),
        "categories_created": 0,
        "crops_created": 0,
        "crops_updated": 0,
        "regions_created": 0,
        "regions_updated": 0,
        "state_mappings_created": 0,
        "rules_created": 0,
        "rules_updated": 0,
        "missing_state_mappings": [],
        "missing_rule_dependencies": [],
        "selected_states": [r["state_name"] for r in REGIONS],
    }
    db = SessionLocal()
    try:
        upsert_crops(db, not args.apply, result)
        if args.apply:
            db.flush()
        upsert_regions(db, not args.apply, result)
        if args.apply:
            db.flush()
        upsert_rules(db, not args.apply, result)
        if args.apply:
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not result["missing_state_mappings"] and not result["missing_rule_dependencies"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
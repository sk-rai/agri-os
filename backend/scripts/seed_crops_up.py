"""Seed crop data for Uttar Pradesh pilot.

Top 10 crops grown in UP with varieties and lifecycle templates.

Usage:
    cd backend
    source ../venv/bin/activate
    python scripts/seed_crops_up.py
"""

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.modules.master_data.models import (
    CropCategory,
    Crop,
    CropVariety,
    CropLifecycleTemplate,
)


def now():
    return datetime.now(timezone.utc)


# UP's top crops with their categories, varieties, and lifecycle stages
UP_CROPS = [
    {
        "category_code": "CEREALS",
        "code": "RICE",
        "canonical_name": "Rice (Paddy)",
        "scientific_name": "Oryza sativa",
        "typical_duration_days": 120,
        "suitable_seasons": ["KHARIF"],
        "suitable_soil_types": ["ALLUVIAL", "BLACK_COTTON"],
        "aliases": [{"lang": "hi", "name": "धान"}],
        "varieties": [
            {"code": "RICE_PB1121", "canonical_name": "Pusa Basmati 1121", "developer": "IARI, New Delhi", "release_year": 2003, "duration_days": 140, "characteristics": {"grain_type": "long", "aroma": "yes"}, "recommended_states": ["UP", "HARYANA", "PUNJAB"]},
            {"code": "RICE_PB1509", "canonical_name": "Pusa Basmati 1509", "developer": "IARI, New Delhi", "release_year": 2013, "duration_days": 120, "characteristics": {"grain_type": "long", "aroma": "yes"}, "recommended_states": ["UP", "HARYANA", "PUNJAB"]},
            {"code": "RICE_SARBATI", "canonical_name": "Sarbati", "developer": "Traditional", "duration_days": 130, "characteristics": {"grain_type": "medium"}, "recommended_states": ["UP"]},
        ],
        "lifecycle": {
            "code": "RICE_KHARIF_DEFAULT",
            "canonical_name": "Rice Kharif Lifecycle (UP)",
            "season_code": "KHARIF",
            "total_duration_days": 130,
            "stages": [
                {"order": 1, "code": "NURSERY", "name": "Nursery Preparation", "duration_days": 25, "description": "Seed bed preparation and seedling growth"},
                {"order": 2, "code": "TRANSPLANTING", "name": "Transplanting", "duration_days": 7, "description": "Transplanting seedlings to main field"},
                {"order": 3, "code": "TILLERING", "name": "Tillering", "duration_days": 30, "description": "Vegetative growth and tiller formation"},
                {"order": 4, "code": "FLOWERING", "name": "Flowering/Heading", "duration_days": 20, "description": "Panicle emergence and flowering"},
                {"order": 5, "code": "GRAIN_FILLING", "name": "Grain Filling", "duration_days": 25, "description": "Grain development and maturation"},
                {"order": 6, "code": "HARVEST", "name": "Harvest", "duration_days": 7, "description": "Cutting and threshing"},
            ],
        },
    },
    {
        "category_code": "CEREALS",
        "code": "WHEAT",
        "canonical_name": "Wheat",
        "scientific_name": "Triticum aestivum",
        "typical_duration_days": 140,
        "suitable_seasons": ["RABI"],
        "suitable_soil_types": ["ALLUVIAL"],
        "aliases": [{"lang": "hi", "name": "गेहूँ"}],
        "varieties": [
            {"code": "WHEAT_HD2967", "canonical_name": "HD 2967", "developer": "IARI, New Delhi", "release_year": 2011, "duration_days": 145, "characteristics": {"type": "bread_wheat", "rust_resistance": "moderate"}, "recommended_states": ["UP", "MP", "RAJASTHAN"]},
            {"code": "WHEAT_PBW343", "canonical_name": "PBW 343", "developer": "PAU, Ludhiana", "release_year": 1995, "duration_days": 135, "characteristics": {"type": "bread_wheat"}, "recommended_states": ["UP", "PUNJAB", "HARYANA"]},
        ],
        "lifecycle": {
            "code": "WHEAT_RABI_DEFAULT",
            "canonical_name": "Wheat Rabi Lifecycle (UP)",
            "season_code": "RABI",
            "total_duration_days": 140,
            "stages": [
                {"order": 1, "code": "SOWING", "name": "Sowing", "duration_days": 7, "description": "Field preparation and seed sowing"},
                {"order": 2, "code": "GERMINATION", "name": "Germination", "duration_days": 14, "description": "Seed germination and emergence"},
                {"order": 3, "code": "CROWN_ROOT", "name": "Crown Root Initiation", "duration_days": 21, "description": "Root establishment and early tillering"},
                {"order": 4, "code": "TILLERING", "name": "Tillering", "duration_days": 28, "description": "Active tiller formation"},
                {"order": 5, "code": "HEADING", "name": "Heading/Flowering", "duration_days": 21, "description": "Ear emergence and pollination"},
                {"order": 6, "code": "GRAIN_FILLING", "name": "Grain Filling", "duration_days": 28, "description": "Grain development"},
                {"order": 7, "code": "HARVEST", "name": "Harvest", "duration_days": 7, "description": "Cutting and threshing"},
            ],
        },
    },
    {
        "category_code": "CASH_CROPS",
        "code": "SUGARCANE",
        "canonical_name": "Sugarcane",
        "scientific_name": "Saccharum officinarum",
        "typical_duration_days": 360,
        "suitable_seasons": ["KHARIF", "RABI"],
        "suitable_soil_types": ["ALLUVIAL", "BLACK_COTTON"],
        "aliases": [{"lang": "hi", "name": "गन्ना"}],
        "varieties": [
            {"code": "SUGARCANE_CO0238", "canonical_name": "CoS 0238 (Karan-4)", "developer": "IISR, Lucknow", "release_year": 2009, "duration_days": 330, "characteristics": {"sugar_content": "high", "maturity": "early"}, "recommended_states": ["UP", "BIHAR", "UTTARAKHAND"]},
        ],
        "lifecycle": {
            "code": "SUGARCANE_DEFAULT",
            "canonical_name": "Sugarcane Lifecycle (UP)",
            "season_code": "KHARIF",
            "total_duration_days": 330,
            "stages": [
                {"order": 1, "code": "PLANTING", "name": "Planting", "duration_days": 14, "description": "Sett planting and initial irrigation"},
                {"order": 2, "code": "GERMINATION", "name": "Germination", "duration_days": 30, "description": "Bud sprouting and establishment"},
                {"order": 3, "code": "TILLERING", "name": "Tillering", "duration_days": 60, "description": "Tiller formation phase"},
                {"order": 4, "code": "GRAND_GROWTH", "name": "Grand Growth", "duration_days": 120, "description": "Rapid cane elongation"},
                {"order": 5, "code": "MATURITY", "name": "Maturity/Ripening", "duration_days": 60, "description": "Sugar accumulation"},
                {"order": 6, "code": "HARVEST", "name": "Harvest", "duration_days": 14, "description": "Cane cutting"},
            ],
        },
    },
    {
        "category_code": "PULSES",
        "code": "GRAM",
        "canonical_name": "Gram (Chickpea)",
        "scientific_name": "Cicer arietinum",
        "typical_duration_days": 110,
        "suitable_seasons": ["RABI"],
        "suitable_soil_types": ["ALLUVIAL", "BLACK_COTTON"],
        "aliases": [{"lang": "hi", "name": "चना"}],
        "varieties": [
            {"code": "GRAM_PUSA256", "canonical_name": "Pusa 256", "developer": "IARI, New Delhi", "duration_days": 115, "characteristics": {"type": "desi"}, "recommended_states": ["UP", "MP", "RAJASTHAN"]},
        ],
        "lifecycle": {
            "code": "GRAM_RABI_DEFAULT",
            "canonical_name": "Gram Rabi Lifecycle (UP)",
            "season_code": "RABI",
            "total_duration_days": 110,
            "stages": [
                {"order": 1, "code": "SOWING", "name": "Sowing", "duration_days": 7, "description": "Seed sowing"},
                {"order": 2, "code": "VEGETATIVE", "name": "Vegetative Growth", "duration_days": 35, "description": "Plant establishment and branching"},
                {"order": 3, "code": "FLOWERING", "name": "Flowering", "duration_days": 25, "description": "Flower formation and pod setting"},
                {"order": 4, "code": "POD_FILLING", "name": "Pod Filling", "duration_days": 25, "description": "Seed development in pods"},
                {"order": 5, "code": "HARVEST", "name": "Harvest", "duration_days": 7, "description": "Plant pulling and threshing"},
            ],
        },
    },
    {
        "category_code": "OILSEEDS",
        "code": "MUSTARD",
        "canonical_name": "Mustard",
        "scientific_name": "Brassica juncea",
        "typical_duration_days": 120,
        "suitable_seasons": ["RABI"],
        "suitable_soil_types": ["ALLUVIAL", "SANDY"],
        "aliases": [{"lang": "hi", "name": "सरसों"}],
        "varieties": [
            {"code": "MUSTARD_PUSA26", "canonical_name": "Pusa Bold (Pusa 26)", "developer": "IARI, New Delhi", "duration_days": 125, "characteristics": {"oil_content": "high"}, "recommended_states": ["UP", "RAJASTHAN", "HARYANA"]},
        ],
        "lifecycle": {
            "code": "MUSTARD_RABI_DEFAULT",
            "canonical_name": "Mustard Rabi Lifecycle (UP)",
            "season_code": "RABI",
            "total_duration_days": 120,
            "stages": [
                {"order": 1, "code": "SOWING", "name": "Sowing", "duration_days": 7, "description": "Seed sowing"},
                {"order": 2, "code": "VEGETATIVE", "name": "Vegetative Growth", "duration_days": 35, "description": "Rosette and stem elongation"},
                {"order": 3, "code": "FLOWERING", "name": "Flowering", "duration_days": 25, "description": "Yellow flower phase"},
                {"order": 4, "code": "SILIQUA", "name": "Siliqua Formation", "duration_days": 30, "description": "Pod development and seed filling"},
                {"order": 5, "code": "HARVEST", "name": "Harvest", "duration_days": 7, "description": "Cutting and threshing"},
            ],
        },
    },
    {
        "category_code": "CEREALS",
        "code": "MAIZE",
        "canonical_name": "Maize (Corn)",
        "scientific_name": "Zea mays",
        "typical_duration_days": 100,
        "suitable_seasons": ["KHARIF", "RABI"],
        "suitable_soil_types": ["ALLUVIAL", "RED"],
        "aliases": [{"lang": "hi", "name": "मक्का"}],
        "varieties": [
            {"code": "MAIZE_DHM117", "canonical_name": "DHM 117", "developer": "DMR, New Delhi", "duration_days": 95, "characteristics": {"type": "hybrid"}, "recommended_states": ["UP", "BIHAR", "KARNATAKA"]},
        ],
        "lifecycle": {
            "code": "MAIZE_KHARIF_DEFAULT",
            "canonical_name": "Maize Kharif Lifecycle (UP)",
            "season_code": "KHARIF",
            "total_duration_days": 100,
            "stages": [
                {"order": 1, "code": "SOWING", "name": "Sowing", "duration_days": 7, "description": "Seed sowing"},
                {"order": 2, "code": "VEGETATIVE", "name": "Vegetative Growth", "duration_days": 35, "description": "Leaf development"},
                {"order": 3, "code": "TASSELING", "name": "Tasseling/Silking", "duration_days": 15, "description": "Pollination phase"},
                {"order": 4, "code": "GRAIN_FILLING", "name": "Grain Filling", "duration_days": 30, "description": "Cob development"},
                {"order": 5, "code": "HARVEST", "name": "Harvest", "duration_days": 7, "description": "Cob harvesting"},
            ],
        },
    },
    {
        "category_code": "VEGETABLES",
        "code": "POTATO",
        "canonical_name": "Potato",
        "scientific_name": "Solanum tuberosum",
        "typical_duration_days": 90,
        "suitable_seasons": ["RABI"],
        "suitable_soil_types": ["ALLUVIAL", "SANDY"],
        "aliases": [{"lang": "hi", "name": "आलू"}],
        "varieties": [
            {"code": "POTATO_KUFRI_BAHAR", "canonical_name": "Kufri Bahar", "developer": "CPRI, Shimla", "duration_days": 90, "characteristics": {"type": "table_purpose"}, "recommended_states": ["UP", "BIHAR", "WEST_BENGAL"]},
        ],
        "lifecycle": {
            "code": "POTATO_RABI_DEFAULT",
            "canonical_name": "Potato Rabi Lifecycle (UP)",
            "season_code": "RABI",
            "total_duration_days": 90,
            "stages": [
                {"order": 1, "code": "PLANTING", "name": "Planting", "duration_days": 7, "description": "Tuber planting"},
                {"order": 2, "code": "EMERGENCE", "name": "Emergence", "duration_days": 14, "description": "Sprout emergence"},
                {"order": 3, "code": "VEGETATIVE", "name": "Vegetative Growth", "duration_days": 25, "description": "Canopy development"},
                {"order": 4, "code": "TUBER_BULKING", "name": "Tuber Bulking", "duration_days": 30, "description": "Tuber enlargement"},
                {"order": 5, "code": "HARVEST", "name": "Harvest", "duration_days": 7, "description": "Digging and collection"},
            ],
        },
    },
    {
        "category_code": "PULSES",
        "code": "LENTIL",
        "canonical_name": "Lentil (Masoor)",
        "scientific_name": "Lens culinaris",
        "typical_duration_days": 110,
        "suitable_seasons": ["RABI"],
        "suitable_soil_types": ["ALLUVIAL"],
        "aliases": [{"lang": "hi", "name": "मसूर"}],
        "varieties": [
            {"code": "LENTIL_PL406", "canonical_name": "PL 406", "developer": "IIPR, Kanpur", "duration_days": 110, "characteristics": {"seed_size": "small"}, "recommended_states": ["UP", "MP"]},
        ],
        "lifecycle": {
            "code": "LENTIL_RABI_DEFAULT",
            "canonical_name": "Lentil Rabi Lifecycle (UP)",
            "season_code": "RABI",
            "total_duration_days": 110,
            "stages": [
                {"order": 1, "code": "SOWING", "name": "Sowing", "duration_days": 7, "description": "Seed sowing"},
                {"order": 2, "code": "VEGETATIVE", "name": "Vegetative Growth", "duration_days": 40, "description": "Plant establishment"},
                {"order": 3, "code": "FLOWERING", "name": "Flowering", "duration_days": 20, "description": "Flower formation"},
                {"order": 4, "code": "POD_FILLING", "name": "Pod Filling", "duration_days": 25, "description": "Seed development"},
                {"order": 5, "code": "HARVEST", "name": "Harvest", "duration_days": 7, "description": "Plant pulling"},
            ],
        },
    },
    {
        "category_code": "OILSEEDS",
        "code": "GROUNDNUT",
        "canonical_name": "Groundnut (Peanut)",
        "scientific_name": "Arachis hypogaea",
        "typical_duration_days": 110,
        "suitable_seasons": ["KHARIF"],
        "suitable_soil_types": ["ALLUVIAL", "SANDY", "RED"],
        "aliases": [{"lang": "hi", "name": "मूँगफली"}],
        "varieties": [
            {"code": "GROUNDNUT_GG20", "canonical_name": "GG 20", "developer": "JAU, Junagadh", "duration_days": 110, "characteristics": {"type": "bunch"}, "recommended_states": ["UP", "GUJARAT", "RAJASTHAN"]},
        ],
        "lifecycle": {
            "code": "GROUNDNUT_KHARIF_DEFAULT",
            "canonical_name": "Groundnut Kharif Lifecycle (UP)",
            "season_code": "KHARIF",
            "total_duration_days": 110,
            "stages": [
                {"order": 1, "code": "SOWING", "name": "Sowing", "duration_days": 7, "description": "Seed sowing"},
                {"order": 2, "code": "VEGETATIVE", "name": "Vegetative Growth", "duration_days": 30, "description": "Plant establishment"},
                {"order": 3, "code": "FLOWERING", "name": "Flowering/Pegging", "duration_days": 25, "description": "Flower and peg formation"},
                {"order": 4, "code": "POD_DEVELOPMENT", "name": "Pod Development", "duration_days": 30, "description": "Underground pod filling"},
                {"order": 5, "code": "HARVEST", "name": "Harvest", "duration_days": 7, "description": "Digging and drying"},
            ],
        },
    },
    {
        "category_code": "CEREALS",
        "code": "BAJRA",
        "canonical_name": "Pearl Millet (Bajra)",
        "scientific_name": "Pennisetum glaucum",
        "typical_duration_days": 80,
        "suitable_seasons": ["KHARIF"],
        "suitable_soil_types": ["SANDY", "ALLUVIAL"],
        "aliases": [{"lang": "hi", "name": "बाजरा"}],
        "varieties": [
            {"code": "BAJRA_HHB67", "canonical_name": "HHB 67 Improved", "developer": "HAU, Hisar", "duration_days": 75, "characteristics": {"type": "hybrid", "drought_tolerance": "high"}, "recommended_states": ["UP", "RAJASTHAN", "HARYANA"]},
        ],
        "lifecycle": {
            "code": "BAJRA_KHARIF_DEFAULT",
            "canonical_name": "Bajra Kharif Lifecycle (UP)",
            "season_code": "KHARIF",
            "total_duration_days": 80,
            "stages": [
                {"order": 1, "code": "SOWING", "name": "Sowing", "duration_days": 7, "description": "Seed sowing"},
                {"order": 2, "code": "VEGETATIVE", "name": "Vegetative Growth", "duration_days": 25, "description": "Tillering and leaf growth"},
                {"order": 3, "code": "HEADING", "name": "Heading/Flowering", "duration_days": 15, "description": "Ear emergence and pollination"},
                {"order": 4, "code": "GRAIN_FILLING", "name": "Grain Filling", "duration_days": 20, "description": "Grain development"},
                {"order": 5, "code": "HARVEST", "name": "Harvest", "duration_days": 7, "description": "Cutting and threshing"},
            ],
        },
    },
]


def seed_crops(db: Session):
    """Seed crops, varieties, and lifecycle templates for UP pilot."""
    for crop_data in UP_CROPS:
        # Get category
        category = db.query(CropCategory).filter_by(
            code=crop_data["category_code"]
        ).first()
        if not category:
            print(f"  WARNING: Category {crop_data['category_code']} not found. Run seed_reference_data.py first.")
            continue

        # Create or get crop
        crop = db.query(Crop).filter_by(code=crop_data["code"]).first()
        if not crop:
            crop = Crop(
                id=uuid.uuid4(),
                code=crop_data["code"],
                category_id=category.id,
                canonical_name=crop_data["canonical_name"],
                scientific_name=crop_data.get("scientific_name"),
                typical_duration_days=crop_data.get("typical_duration_days"),
                suitable_seasons=crop_data.get("suitable_seasons", []),
                suitable_soil_types=crop_data.get("suitable_soil_types", []),
                aliases=crop_data.get("aliases", []),
                created_at=now(),
                updated_at=now(),
            )
            db.add(crop)
            db.flush()

        # Create varieties
        for var_data in crop_data.get("varieties", []):
            existing = db.query(CropVariety).filter_by(code=var_data["code"]).first()
            if not existing:
                db.add(CropVariety(
                    id=uuid.uuid4(),
                    code=var_data["code"],
                    crop_id=crop.id,
                    canonical_name=var_data["canonical_name"],
                    developer=var_data.get("developer"),
                    release_year=var_data.get("release_year"),
                    duration_days=var_data.get("duration_days"),
                    characteristics=var_data.get("characteristics", {}),
                    recommended_states=var_data.get("recommended_states", []),
                    aliases=var_data.get("aliases", []),
                    created_at=now(),
                    updated_at=now(),
                ))

        # Create lifecycle template
        lc_data = crop_data.get("lifecycle")
        if lc_data:
            existing = db.query(CropLifecycleTemplate).filter_by(
                code=lc_data["code"]
            ).first()
            if not existing:
                db.add(CropLifecycleTemplate(
                    id=uuid.uuid4(),
                    code=lc_data["code"],
                    crop_id=crop.id,
                    season_code=lc_data["season_code"],
                    canonical_name=lc_data["canonical_name"],
                    total_duration_days=lc_data.get("total_duration_days"),
                    stages=lc_data["stages"],
                    is_default=True,
                    created_at=now(),
                    updated_at=now(),
                ))

    db.commit()
    print(f"  Crops: {db.query(Crop).count()} records")
    print(f"  Varieties: {db.query(CropVariety).count()} records")
    print(f"  Lifecycle templates: {db.query(CropLifecycleTemplate).count()} records")


if __name__ == "__main__":
    print("Seeding UP pilot crop data...")
    db = SessionLocal()
    try:
        seed_crops(db)
        print("\nDone! UP crop data seeded.")
    finally:
        db.close()

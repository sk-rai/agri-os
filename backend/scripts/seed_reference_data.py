"""Seed reference data: soil types, seasons, crop categories, input categories.

This is static/semi-static data that rarely changes.
Run once to populate the database with foundational reference data.

Usage:
    cd backend
    source ../venv/bin/activate
    python scripts/seed_reference_data.py
"""

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session
from app.core.database import engine, SessionLocal
from app.modules.master_data.models import (
    SoilType,
    Season,
    CropCategory,
    InputCategory,
    Manufacturer,
)


def now():
    return datetime.now(timezone.utc)


def seed_soil_types(db: Session):
    """Indian soil classification (ICAR-NBSS&LUP)."""
    soils = [
        {
            "code": "ALLUVIAL",
            "canonical_name": "Alluvial Soil",
            "description": "Found in Indo-Gangetic plains. Most fertile and widespread in India.",
            "characteristics": {"texture": "loamy", "drainage": "good", "fertility": "high"},
            "suitable_crops": ["rice", "wheat", "sugarcane", "maize", "pulses"],
            "ph_range_min": "6.5",
            "ph_range_max": "8.0",
            "aliases": [{"lang": "hi", "name": "जलोढ़ मिट्टी"}],
        },
        {
            "code": "BLACK_COTTON",
            "canonical_name": "Black Cotton Soil (Regur)",
            "description": "Rich in clay, retains moisture. Found in Deccan plateau.",
            "characteristics": {"texture": "clayey", "drainage": "poor", "fertility": "high"},
            "suitable_crops": ["cotton", "soybean", "wheat", "jowar", "sugarcane"],
            "ph_range_min": "7.0",
            "ph_range_max": "8.5",
            "aliases": [{"lang": "hi", "name": "काली मिट्टी"}, {"lang": "en", "name": "Regur"}],
        },
        {
            "code": "RED",
            "canonical_name": "Red Soil",
            "description": "Iron-rich, found in southern and eastern India.",
            "characteristics": {"texture": "sandy-loam", "drainage": "good", "fertility": "medium"},
            "suitable_crops": ["groundnut", "millets", "pulses", "tobacco"],
            "ph_range_min": "5.5",
            "ph_range_max": "7.0",
            "aliases": [{"lang": "hi", "name": "लाल मिट्टी"}],
        },
        {
            "code": "LATERITE",
            "canonical_name": "Laterite Soil",
            "description": "Leached soil, found in high rainfall areas.",
            "characteristics": {"texture": "gravelly", "drainage": "excessive", "fertility": "low"},
            "suitable_crops": ["tea", "coffee", "cashew", "rubber"],
            "ph_range_min": "5.0",
            "ph_range_max": "6.5",
            "aliases": [{"lang": "hi", "name": "लैटेराइट मिट्टी"}],
        },
        {
            "code": "SANDY",
            "canonical_name": "Sandy Soil (Desert)",
            "description": "Low moisture retention, found in Rajasthan and parts of Gujarat.",
            "characteristics": {"texture": "sandy", "drainage": "excessive", "fertility": "low"},
            "suitable_crops": ["bajra", "guar", "moth_bean"],
            "ph_range_min": "7.0",
            "ph_range_max": "9.0",
            "aliases": [{"lang": "hi", "name": "बालू मिट्टी"}],
        },
    ]

    for soil_data in soils:
        existing = db.query(SoilType).filter_by(code=soil_data["code"]).first()
        if not existing:
            db.add(SoilType(id=uuid.uuid4(), created_at=now(), updated_at=now(), **soil_data))

    db.commit()
    print(f"  Soil types: {db.query(SoilType).count()} records")


def seed_seasons(db: Session):
    """Standard Indian agricultural seasons."""
    seasons = [
        {
            "code": "KHARIF",
            "canonical_name": "Kharif",
            "description": "Monsoon season crop (June-October). Major crops: rice, maize, cotton, soybean.",
            "start_month": 6,
            "end_month": 10,
            "sowing_window_start": 152,   # June 1
            "sowing_window_end": 196,     # July 15
            "harvest_window_start": 274,  # October 1
            "harvest_window_end": 334,    # November 30
            "aliases": [{"lang": "hi", "name": "खरीफ"}],
        },
        {
            "code": "RABI",
            "canonical_name": "Rabi",
            "description": "Winter season crop (October-March). Major crops: wheat, mustard, gram, peas.",
            "start_month": 10,
            "end_month": 3,
            "sowing_window_start": 288,   # October 15
            "sowing_window_end": 334,     # November 30
            "harvest_window_start": 60,   # March 1
            "harvest_window_end": 120,    # April 30
            "aliases": [{"lang": "hi", "name": "रबी"}],
        },
        {
            "code": "ZAID",
            "canonical_name": "Zaid",
            "description": "Summer season crop (March-June). Short duration crops between Rabi and Kharif.",
            "start_month": 3,
            "end_month": 6,
            "sowing_window_start": 60,    # March 1
            "sowing_window_end": 105,     # April 15
            "harvest_window_start": 135,  # May 15
            "harvest_window_end": 166,    # June 15
            "aliases": [{"lang": "hi", "name": "जायद"}],
        },
    ]

    for season_data in seasons:
        existing = db.query(Season).filter_by(code=season_data["code"]).first()
        if not existing:
            db.add(Season(id=uuid.uuid4(), created_at=now(), updated_at=now(), **season_data))

    db.commit()
    print(f"  Seasons: {db.query(Season).count()} records")


def seed_crop_categories(db: Session):
    """Top-level crop classification."""
    categories = [
        {"code": "CEREALS", "canonical_name": "Cereals", "description": "Grain crops (rice, wheat, maize, millets)", "aliases": [{"lang": "hi", "name": "अनाज"}]},
        {"code": "PULSES", "canonical_name": "Pulses", "description": "Leguminous crops (gram, lentil, peas, moong)", "aliases": [{"lang": "hi", "name": "दालें"}]},
        {"code": "OILSEEDS", "canonical_name": "Oilseeds", "description": "Oil-bearing crops (mustard, soybean, groundnut, sunflower)", "aliases": [{"lang": "hi", "name": "तिलहन"}]},
        {"code": "CASH_CROPS", "canonical_name": "Cash Crops", "description": "Commercial crops (sugarcane, cotton, jute, tobacco)", "aliases": [{"lang": "hi", "name": "नकदी फसलें"}]},
        {"code": "VEGETABLES", "canonical_name": "Vegetables", "description": "Horticultural vegetable crops", "aliases": [{"lang": "hi", "name": "सब्जियाँ"}]},
        {"code": "FRUITS", "canonical_name": "Fruits", "description": "Horticultural fruit crops", "aliases": [{"lang": "hi", "name": "फल"}]},
        {"code": "SPICES", "canonical_name": "Spices", "description": "Spice crops (turmeric, chilli, coriander)", "aliases": [{"lang": "hi", "name": "मसाले"}]},
        {"code": "FODDER", "canonical_name": "Fodder Crops", "description": "Animal feed crops (berseem, napier, lucerne)", "aliases": [{"lang": "hi", "name": "चारा"}]},
    ]

    for cat_data in categories:
        existing = db.query(CropCategory).filter_by(code=cat_data["code"]).first()
        if not existing:
            db.add(CropCategory(id=uuid.uuid4(), created_at=now(), updated_at=now(), **cat_data))

    db.commit()
    print(f"  Crop categories: {db.query(CropCategory).count()} records")


def seed_input_categories(db: Session):
    """Agricultural input categories."""
    categories = [
        {"code": "FERTILIZER", "canonical_name": "Fertilizer", "description": "Chemical and organic fertilizers", "aliases": [{"lang": "hi", "name": "उर्वरक"}]},
        {"code": "PESTICIDE", "canonical_name": "Pesticide", "description": "Insecticides, fungicides, herbicides", "aliases": [{"lang": "hi", "name": "कीटनाशक"}]},
        {"code": "SEED", "canonical_name": "Seed", "description": "Certified and hybrid seeds", "aliases": [{"lang": "hi", "name": "बीज"}]},
        {"code": "GROWTH_REGULATOR", "canonical_name": "Growth Regulator", "description": "Plant growth regulators and bio-stimulants", "aliases": [{"lang": "hi", "name": "वृद्धि नियामक"}]},
        {"code": "MICRONUTRIENT", "canonical_name": "Micronutrient", "description": "Zinc, boron, iron supplements", "aliases": [{"lang": "hi", "name": "सूक्ष्म पोषक तत्व"}]},
    ]

    for cat_data in categories:
        existing = db.query(InputCategory).filter_by(code=cat_data["code"]).first()
        if not existing:
            db.add(InputCategory(id=uuid.uuid4(), created_at=now(), updated_at=now(), **cat_data))

    db.commit()
    print(f"  Input categories: {db.query(InputCategory).count()} records")


def seed_manufacturers(db: Session):
    """Major Indian agricultural input manufacturers."""
    manufacturers = [
        {"code": "IFFCO", "canonical_name": "Indian Farmers Fertiliser Cooperative", "short_name": "IFFCO", "aliases": [{"lang": "hi", "name": "इफको"}]},
        {"code": "NFL", "canonical_name": "National Fertilizers Limited", "short_name": "NFL", "aliases": []},
        {"code": "COROMANDEL", "canonical_name": "Coromandel International", "short_name": "Coromandel", "aliases": []},
        {"code": "UPL", "canonical_name": "UPL Limited", "short_name": "UPL", "aliases": [{"lang": "en", "name": "United Phosphorus"}]},
        {"code": "BAYER", "canonical_name": "Bayer CropScience", "short_name": "Bayer", "aliases": []},
        {"code": "SYNGENTA", "canonical_name": "Syngenta India", "short_name": "Syngenta", "aliases": []},
        {"code": "DHANUKA", "canonical_name": "Dhanuka Agritech", "short_name": "Dhanuka", "aliases": []},
        {"code": "TATA_RALLIS", "canonical_name": "Tata Rallis India", "short_name": "Rallis", "aliases": []},
        {"code": "PI_INDUSTRIES", "canonical_name": "PI Industries", "short_name": "PI", "aliases": []},
        {"code": "ZUARI", "canonical_name": "Zuari Agro Chemicals", "short_name": "Zuari", "aliases": []},
    ]

    for mfr_data in manufacturers:
        existing = db.query(Manufacturer).filter_by(code=mfr_data["code"]).first()
        if not existing:
            db.add(Manufacturer(id=uuid.uuid4(), created_at=now(), updated_at=now(), **mfr_data))

    db.commit()
    print(f"  Manufacturers: {db.query(Manufacturer).count()} records")


if __name__ == "__main__":
    print("Seeding reference data...")
    db = SessionLocal()
    try:
        seed_soil_types(db)
        seed_seasons(db)
        seed_crop_categories(db)
        seed_input_categories(db)
        seed_manufacturers(db)
        print("\nDone! All reference data seeded.")
    finally:
        db.close()

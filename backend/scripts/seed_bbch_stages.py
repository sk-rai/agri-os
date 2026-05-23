"""Seed BBCH principal stages reference data.

The BBCH scale is universal — this data rarely changes.
Crop-specific BBCH mappings are stored in lifecycle_templates.stages[].bbch_range.

Usage:
    cd backend
    source ../venv/bin/activate
    python scripts/seed_bbch_stages.py
"""

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.modules.master_data.models.bbch import BBCHPrincipalStage


def now():
    return datetime.now(timezone.utc)


BBCH_STAGES = [
    {
        "code": 0,
        "code_range_start": 0,
        "code_range_end": 9,
        "canonical_name": "Germination / Bud Development",
        "description": "Seeds soaking up water, root emergence, opening of buds.",
        "aliases": [{"lang": "hi", "name": "अंकुरण / कलिका विकास"}],
        "applicable_crop_types": ["CEREALS", "PULSES", "OILSEEDS", "VEGETABLES", "FRUITS", "CASH_CROPS"],
    },
    {
        "code": 1,
        "code_range_start": 10,
        "code_range_end": 19,
        "canonical_name": "Leaf Development",
        "description": "First true leaves, shoots, and main foliage expanding.",
        "aliases": [{"lang": "hi", "name": "पत्ती विकास"}],
        "applicable_crop_types": ["CEREALS", "PULSES", "OILSEEDS", "VEGETABLES", "FRUITS", "CASH_CROPS"],
    },
    {
        "code": 2,
        "code_range_start": 20,
        "code_range_end": 29,
        "canonical_name": "Formation of Side Shoots / Tillering",
        "description": "Branching in dicots, tillering in cereals.",
        "aliases": [{"lang": "hi", "name": "कल्ले निकलना / शाखा बनना"}],
        "applicable_crop_types": ["CEREALS", "PULSES", "OILSEEDS", "VEGETABLES"],
    },
    {
        "code": 3,
        "code_range_start": 30,
        "code_range_end": 39,
        "canonical_name": "Stem Elongation / Rosette Growth",
        "description": "Vertical elongation of main stem or rosette growth.",
        "aliases": [{"lang": "hi", "name": "तना बढ़ाव"}],
        "applicable_crop_types": ["CEREALS", "PULSES", "OILSEEDS", "CASH_CROPS"],
    },
    {
        "code": 4,
        "code_range_start": 40,
        "code_range_end": 49,
        "canonical_name": "Development of Harvestable Vegetative Parts / Booting",
        "description": "Swelling of roots/tubers, or booting in cereals.",
        "aliases": [{"lang": "hi", "name": "कंद/जड़ विकास / बूटिंग"}],
        "applicable_crop_types": ["CEREALS", "VEGETABLES", "CASH_CROPS"],
    },
    {
        "code": 5,
        "code_range_start": 50,
        "code_range_end": 59,
        "canonical_name": "Inflorescence / Ear Emergence",
        "description": "Flower clusters or seed heads become visible.",
        "aliases": [{"lang": "hi", "name": "पुष्पक्रम / बाली निकलना"}],
        "applicable_crop_types": ["CEREALS", "PULSES", "OILSEEDS", "FRUITS"],
    },
    {
        "code": 6,
        "code_range_start": 60,
        "code_range_end": 69,
        "canonical_name": "Flowering",
        "description": "Pollen release, petal drop, fertilization.",
        "aliases": [{"lang": "hi", "name": "फूल आना"}],
        "applicable_crop_types": ["CEREALS", "PULSES", "OILSEEDS", "VEGETABLES", "FRUITS", "CASH_CROPS"],
    },
    {
        "code": 7,
        "code_range_start": 70,
        "code_range_end": 79,
        "canonical_name": "Development of Fruit / Grain Filling",
        "description": "Growth of fruit or grain to final size.",
        "aliases": [{"lang": "hi", "name": "फल/दाना भरना"}],
        "applicable_crop_types": ["CEREALS", "PULSES", "OILSEEDS", "VEGETABLES", "FRUITS"],
    },
    {
        "code": 8,
        "code_range_start": 80,
        "code_range_end": 89,
        "canonical_name": "Ripening / Maturity",
        "description": "Seed or fruit gains full color and nutritional readiness.",
        "aliases": [{"lang": "hi", "name": "पकना / परिपक्वता"}],
        "applicable_crop_types": ["CEREALS", "PULSES", "OILSEEDS", "VEGETABLES", "FRUITS", "CASH_CROPS"],
    },
    {
        "code": 9,
        "code_range_start": 90,
        "code_range_end": 99,
        "canonical_name": "Senescence / Dormancy / Harvest",
        "description": "Plant dies (annuals) or enters dormancy (perennials). Harvest window.",
        "aliases": [{"lang": "hi", "name": "कटाई / सुषुप्ति"}],
        "applicable_crop_types": ["CEREALS", "PULSES", "OILSEEDS", "VEGETABLES", "FRUITS", "CASH_CROPS"],
    },
]


if __name__ == "__main__":
    print("Seeding BBCH principal stages...")
    db = SessionLocal()
    try:
        for stage_data in BBCH_STAGES:
            existing = db.query(BBCHPrincipalStage).filter_by(code=stage_data["code"]).first()
            if not existing:
                db.add(BBCHPrincipalStage(
                    id=uuid.uuid4(),
                    created_at=now(),
                    updated_at=now(),
                    **stage_data,
                ))
        db.commit()
        count = db.query(BBCHPrincipalStage).count()
        print(f"  BBCH stages: {count} records")
        print("\nDone!")
    finally:
        db.close()

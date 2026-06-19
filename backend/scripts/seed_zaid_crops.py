"""Seed Zaid season crops and tag Maize as Zaid-suitable."""
import sys, uuid
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
from app.modules.master_data.models import Crop, CropCategory

def now():
    return datetime.now(timezone.utc)

db = SessionLocal()

# Get categories
vegetables = db.query(CropCategory).filter(CropCategory.code == "VEGETABLES").first()
pulses = db.query(CropCategory).filter(CropCategory.code == "PULSES").first()
oilseeds = db.query(CropCategory).filter(CropCategory.code == "OILSEEDS").first()

# Add Zaid crops
zaid_crops = [
    {"code": "MOONG", "category": pulses, "name": "Green Gram (Moong)", "scientific": "Vigna radiata", "days": 65, "seasons": ["ZAID", "KHARIF"], "aliases": [{"lang": "hi", "name": "मूंग"}]},
    {"code": "WATERMELON", "category": vegetables, "name": "Watermelon", "scientific": "Citrullus lanatus", "days": 90, "seasons": ["ZAID"], "aliases": [{"lang": "hi", "name": "तरबूज"}]},
    {"code": "CUCUMBER", "category": vegetables, "name": "Cucumber", "scientific": "Cucumis sativus", "days": 60, "seasons": ["ZAID"], "aliases": [{"lang": "hi", "name": "खीरा"}]},
    {"code": "BOTTLE_GOURD", "category": vegetables, "name": "Bottle Gourd (Lauki)", "scientific": "Lagenaria siceraria", "days": 75, "seasons": ["ZAID", "KHARIF"], "aliases": [{"lang": "hi", "name": "लौकी"}]},
    {"code": "SUNFLOWER", "category": oilseeds, "name": "Sunflower", "scientific": "Helianthus annuus", "days": 90, "seasons": ["ZAID", "KHARIF"], "aliases": [{"lang": "hi", "name": "सूरजमुखी"}]},
    {"code": "URAD", "category": pulses, "name": "Black Gram (Urad)", "scientific": "Vigna mungo", "days": 70, "seasons": ["ZAID", "KHARIF"], "aliases": [{"lang": "hi", "name": "उड़द"}]},
]

created = 0
for c in zaid_crops:
    existing = db.query(Crop).filter(Crop.code == c["code"]).first()
    if not existing and c["category"]:
        db.add(Crop(
            id=uuid.uuid4(), code=c["code"], category_id=c["category"].id,
            canonical_name=c["name"], scientific_name=c["scientific"],
            typical_duration_days=c["days"], suitable_seasons=c["seasons"],
            aliases=c["aliases"], created_at=now(), updated_at=now(),
        ))
        created += 1
        print(f"  Created: {c['name']}")

# Also tag Maize as ZAID-suitable (it already has KHARIF, RABI)
maize = db.query(Crop).filter(Crop.code == "MAIZE").first()
if maize and "ZAID" not in (maize.suitable_seasons or []):
    maize.suitable_seasons = (maize.suitable_seasons or []) + ["ZAID"]
    print(f"  Updated Maize: added ZAID season")

db.commit()
db.close()
print(f"\nDone! {created} Zaid crops added.")

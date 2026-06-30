"""Re-seed crop lifecycle templates with enhanced stage schema.

Adds: stage_type, phase, bbch_range, description (i18n), farmer_actions,
typical_inputs, icon, color, propagation metadata.

Usage:
    cd backend
    source ../venv/bin/activate
    python scripts/seed_enhanced_templates.py
"""

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.modules.master_data.models import Crop, CropLifecycleTemplate
from scripts.seed_recommended_activities import RICE_ACTIVITIES


def now():
    return datetime.now(timezone.utc)


ENHANCED_TEMPLATES = [
    {
        "crop_code": "RICE",
        "season_code": "KHARIF",
        "code": "RICE_KHARIF_DEFAULT",
        "canonical_name": "Rice Kharif Lifecycle (UP)",
        "total_duration_days": 130,
        "metadata": {
            "crop_group": "CEREAL",
            "propagation_method": "NURSERY_TRANSPLANT",
            "has_nursery": True,
            "date_label": {"en": "Nursery Start Date", "hi": "नर्सरी शुरू करने की तारीख"},
            "staging_system": "ZADOKS_BBCH",
        },
        "stages": [
            {
                "order": 1, "code": "NURSERY",
                "name": {"en": "Nursery Preparation", "hi": "नर्सरी तैयारी"},
                "duration_days": 25,
                "stage_type": "PRE_FIELD",
                "phase": "ESTABLISHMENT",
                "bbch_range": [0, 9],
                "propagation_step": True,
                "description": {"en": "Prepare seed bed, soak seeds, grow seedlings for 20-25 days", "hi": "बीज की क्यारी तैयार करें, बीज भिगोएं, 20-25 दिन पौध उगाएं"},
                "farmer_actions": ["SEED_SOAKING", "BED_PREPARATION", "WATERING", "SEED_TREATMENT"],
                "typical_inputs": ["SEED", "WATER", "FUNGICIDE"],
                "key_observations": ["GERMINATION_RATE", "SEEDLING_HEIGHT", "DISEASE_CHECK"],
                "icon": "seedling",
                "color": "#81C784",
            },
            {
                "order": 2, "code": "TRANSPLANTING",
                "name": {"en": "Transplanting", "hi": "रोपाई"},
                "duration_days": 7,
                "stage_type": "FIELD_ESTABLISHMENT",
                "phase": "ESTABLISHMENT",
                "bbch_range": [10, 13],
                "propagation_step": True,
                "description": {"en": "Transplant seedlings from nursery to puddled main field", "hi": "नर्सरी से पौध को मुख्य खेत में रोपें"},
                "farmer_actions": ["PUDDLING", "TRANSPLANTING", "INITIAL_FLOODING"],
                "typical_inputs": ["LABOR", "WATER"],
                "key_observations": ["PLANT_SPACING", "WATER_LEVEL", "SURVIVAL_RATE"],
                "icon": "plant_transfer",
                "color": "#66BB6A",
            },
            {
                "order": 3, "code": "TILLERING",
                "name": {"en": "Tillering", "hi": "कल्ले निकलना"},
                "duration_days": 30,
                "stage_type": "VEGETATIVE",
                "phase": "VEGETATIVE_GROWTH",
                "bbch_range": [20, 29],
                "propagation_step": False,
                "description": {"en": "Active tiller formation. Critical for yield density. Apply nitrogen.", "hi": "कल्ले बनने का समय। उपज के लिए महत्वपूर्ण। नाइट्रोजन दें।"},
                "farmer_actions": ["NITROGEN_APPLICATION", "WEED_CONTROL", "WATER_MANAGEMENT"],
                "typical_inputs": ["UREA", "HERBICIDE", "WATER"],
                "key_observations": ["TILLER_COUNT", "WEED_DENSITY", "NUTRIENT_DEFICIENCY"],
                "icon": "grass",
                "color": "#4CAF50",
            },
            {
                "order": 4, "code": "FLOWERING",
                "name": {"en": "Flowering / Heading", "hi": "फूल आना / बाली निकलना"},
                "duration_days": 20,
                "stage_type": "REPRODUCTIVE",
                "phase": "REPRODUCTIVE",
                "bbch_range": [50, 69],
                "propagation_step": False,
                "description": {"en": "Panicle emergence and flowering. Protect from pests.", "hi": "बाली निकलना और फूल आना। कीटों से बचाव करें।"},
                "farmer_actions": ["PEST_MONITORING", "POTASSIUM_APPLICATION", "WATER_MANAGEMENT"],
                "typical_inputs": ["POTASH", "PESTICIDE", "WATER"],
                "key_observations": ["PANICLE_COUNT", "PEST_ATTACK", "DISEASE_SYMPTOMS"],
                "icon": "flower",
                "color": "#FFC107",
            },
            {
                "order": 5, "code": "GRAIN_FILLING",
                "name": {"en": "Grain Filling", "hi": "दाना भरना"},
                "duration_days": 25,
                "stage_type": "REPRODUCTIVE",
                "phase": "MATURATION",
                "bbch_range": [70, 79],
                "propagation_step": False,
                "description": {"en": "Grain development and maturation. Reduce water gradually.", "hi": "दाना बनना और पकना। धीरे-धीरे पानी कम करें।"},
                "farmer_actions": ["WATER_REDUCTION", "BIRD_SCARING", "HARVEST_PLANNING"],
                "typical_inputs": [],
                "key_observations": ["GRAIN_HARDNESS", "MOISTURE_CONTENT", "BIRD_DAMAGE"],
                "icon": "grain",
                "color": "#FF9800",
            },
            {
                "order": 6, "code": "HARVEST",
                "name": {"en": "Harvest", "hi": "कटाई"},
                "duration_days": 7,
                "stage_type": "HARVEST",
                "phase": "HARVEST",
                "bbch_range": [90, 99],
                "propagation_step": False,
                "description": {"en": "Cut and thresh when grain moisture is 20-22%", "hi": "जब दाने में 20-22% नमी हो तब काटें"},
                "farmer_actions": ["CUTTING", "THRESHING", "DRYING", "STORAGE"],
                "typical_inputs": ["MACHINERY", "LABOR"],
                "key_observations": ["YIELD_ESTIMATE", "GRAIN_QUALITY", "MOISTURE_AT_HARVEST"],
                "icon": "harvest",
                "color": "#795548",
            },
        ],
    },
    {
        "crop_code": "WHEAT",
        "season_code": "RABI",
        "code": "WHEAT_RABI_DEFAULT",
        "canonical_name": "Wheat Rabi Lifecycle (UP)",
        "total_duration_days": 140,
        "metadata": {
            "crop_group": "CEREAL",
            "propagation_method": "DIRECT_SOWING",
            "has_nursery": False,
            "date_label": {"en": "Sowing Date", "hi": "बुवाई की तारीख"},
            "staging_system": "ZADOKS_BBCH",
        },
        "stages": [
            {
                "order": 1, "code": "SOWING",
                "name": {"en": "Sowing", "hi": "बुवाई"},
                "duration_days": 7,
                "stage_type": "FIELD_ESTABLISHMENT",
                "phase": "ESTABLISHMENT",
                "bbch_range": [0, 5],
                "propagation_step": False,
                "description": {"en": "Field preparation and seed sowing. Ensure proper moisture.", "hi": "खेत तैयारी और बीज बुवाई। उचित नमी सुनिश्चित करें।"},
                "farmer_actions": ["FIELD_PREPARATION", "SEED_SOWING", "FIRST_IRRIGATION"],
                "typical_inputs": ["SEED", "DAP", "WATER"],
                "key_observations": ["SOIL_MOISTURE", "SEED_DEPTH", "ROW_SPACING"],
                "icon": "seed_sowing",
                "color": "#8D6E63",
            },
            {
                "order": 2, "code": "GERMINATION",
                "name": {"en": "Germination", "hi": "अंकुरण"},
                "duration_days": 14,
                "stage_type": "VEGETATIVE",
                "phase": "ESTABLISHMENT",
                "bbch_range": [5, 9],
                "propagation_step": False,
                "description": {"en": "Seed germination and emergence. Monitor for gaps.", "hi": "बीज अंकुरण। कहीं खाली जगह तो नहीं, देखें।"},
                "farmer_actions": ["GAP_FILLING", "LIGHT_IRRIGATION"],
                "typical_inputs": ["WATER"],
                "key_observations": ["GERMINATION_PERCENTAGE", "SEEDLING_VIGOR"],
                "icon": "sprout",
                "color": "#A5D6A7",
            },
            {
                "order": 3, "code": "CROWN_ROOT",
                "name": {"en": "Crown Root Initiation", "hi": "जड़ विकास"},
                "duration_days": 21,
                "stage_type": "VEGETATIVE",
                "phase": "VEGETATIVE_GROWTH",
                "bbch_range": [10, 19],
                "propagation_step": False,
                "description": {"en": "Root establishment and early tillering begins", "hi": "जड़ मजबूत होना और शुरुआती कल्ले"},
                "farmer_actions": ["FIRST_NITROGEN_DOSE", "IRRIGATION"],
                "typical_inputs": ["UREA", "WATER"],
                "key_observations": ["ROOT_DEVELOPMENT", "EARLY_TILLERS"],
                "icon": "roots",
                "color": "#66BB6A",
            },
            {
                "order": 4, "code": "TILLERING",
                "name": {"en": "Tillering", "hi": "कल्ले निकलना"},
                "duration_days": 28,
                "stage_type": "VEGETATIVE",
                "phase": "VEGETATIVE_GROWTH",
                "bbch_range": [20, 29],
                "propagation_step": False,
                "description": {"en": "Active tiller formation. Apply second dose of nitrogen.", "hi": "कल्ले बनने का समय। नाइट्रोजन की दूसरी खुराक दें।"},
                "farmer_actions": ["SECOND_NITROGEN_DOSE", "WEED_CONTROL", "IRRIGATION"],
                "typical_inputs": ["UREA", "HERBICIDE", "WATER"],
                "key_observations": ["TILLER_COUNT", "WEED_PRESSURE", "YELLOW_RUST_CHECK"],
                "icon": "grass",
                "color": "#4CAF50",
            },
            {
                "order": 5, "code": "HEADING",
                "name": {"en": "Heading / Flowering", "hi": "बाली निकलना / फूल"},
                "duration_days": 21,
                "stage_type": "REPRODUCTIVE",
                "phase": "REPRODUCTIVE",
                "bbch_range": [50, 69],
                "propagation_step": False,
                "description": {"en": "Ear emergence and pollination. Critical irrigation needed.", "hi": "बाली निकलना और परागण। सिंचाई जरूरी।"},
                "farmer_actions": ["CRITICAL_IRRIGATION", "PEST_SPRAY", "NO_NITROGEN"],
                "typical_inputs": ["WATER", "FUNGICIDE"],
                "key_observations": ["EAR_COUNT", "RUST_SYMPTOMS", "APHID_CHECK"],
                "icon": "wheat_ear",
                "color": "#FFC107",
            },
            {
                "order": 6, "code": "GRAIN_FILLING",
                "name": {"en": "Grain Filling", "hi": "दाना भरना"},
                "duration_days": 28,
                "stage_type": "REPRODUCTIVE",
                "phase": "MATURATION",
                "bbch_range": [70, 89],
                "propagation_step": False,
                "description": {"en": "Grain development from milk to hard dough stage", "hi": "दाना दूधिया से सख्त होने तक"},
                "farmer_actions": ["LAST_IRRIGATION", "HARVEST_PLANNING"],
                "typical_inputs": ["WATER"],
                "key_observations": ["GRAIN_COLOR", "MOISTURE_CONTENT"],
                "icon": "grain",
                "color": "#FF9800",
            },
            {
                "order": 7, "code": "HARVEST",
                "name": {"en": "Harvest", "hi": "कटाई"},
                "duration_days": 7,
                "stage_type": "HARVEST",
                "phase": "HARVEST",
                "bbch_range": [90, 99],
                "propagation_step": False,
                "description": {"en": "Cut when grain is golden and moisture ~12-14%", "hi": "जब दाना सुनहरा हो और नमी 12-14% हो तब काटें"},
                "farmer_actions": ["CUTTING", "THRESHING", "WINNOWING", "STORAGE"],
                "typical_inputs": ["MACHINERY", "LABOR"],
                "key_observations": ["YIELD_PER_BIGHA", "GRAIN_QUALITY", "STRAW_YIELD"],
                "icon": "harvest",
                "color": "#795548",
            },
        ],
    },
]


def stages_with_recommendations(tmpl_data: dict) -> list[dict]:
    """Return enhanced stages without losing seeded recommendation rows."""
    stages = []
    for stage in tmpl_data["stages"]:
        stage_copy = dict(stage)
        if tmpl_data["code"] == "RICE_KHARIF_DEFAULT":
            stage_copy["recommended_activities"] = RICE_ACTIVITIES.get(stage_copy["code"], [])
        stages.append(stage_copy)
    return stages


def seed_enhanced_templates(db: Session):
    """Update existing templates with enhanced stage schema."""
    for tmpl_data in ENHANCED_TEMPLATES:
        stages = stages_with_recommendations(tmpl_data)

        # Find existing template
        existing = db.query(CropLifecycleTemplate).filter(
            CropLifecycleTemplate.code == tmpl_data["code"]
        ).first()

        if existing:
            # Update with enhanced stages, recommendation rows, and metadata
            existing.stages = stages
            existing.total_duration_days = tmpl_data["total_duration_days"]
            existing.updated_at = now()
            # Store metadata in aliases field (reuse JSONB field for now)
            existing.aliases = tmpl_data["metadata"]
            print(f"  Updated: {tmpl_data['code']} ({len(stages)} stages)")
        else:
            # Find crop
            crop = db.query(Crop).filter(Crop.code == tmpl_data["crop_code"]).first()
            if not crop:
                print(f"  SKIP: Crop {tmpl_data['crop_code']} not found")
                continue
            # Create new template
            t = CropLifecycleTemplate(
                id=uuid.uuid4(),
                code=tmpl_data["code"],
                crop_id=crop.id,
                season_code=tmpl_data["season_code"],
                canonical_name=tmpl_data["canonical_name"],
                total_duration_days=tmpl_data["total_duration_days"],
                stages=stages,
                is_default=True,
                aliases=tmpl_data["metadata"],
                created_at=now(),
                updated_at=now(),
            )
            db.add(t)
            print(f"  Created: {tmpl_data['code']}")

    db.commit()


if __name__ == "__main__":
    print("Seeding enhanced lifecycle templates...")
    db = SessionLocal()
    try:
        seed_enhanced_templates(db)
        print("\nDone! Templates updated with enhanced stage schema.")
    finally:
        db.close()

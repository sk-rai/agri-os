"""Seed canonical agricultural input catalog and map workflow recommendations.

This keeps Android-compatible recommendation text while adding stable input_code
references for admin/search/analytics.
"""

from __future__ import annotations

import re
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.modules.master_data.models import AgriculturalInput, InputCategory, Manufacturer
from app.modules.workflow.models import WorkflowTemplateRecommendation


def now():
    return datetime.now(timezone.utc)


CATEGORY_DEFS = [
    ("SEED", "Seed", "Seeds and planting material"),
    ("FERTILIZER", "Fertilizer", "Chemical fertilizers and nutrient sources"),
    ("ORGANIC_MANURE", "Organic Manure", "FYM, compost and organic nutrient sources"),
    ("MICRONUTRIENT", "Micronutrient", "Zinc, boron, iron and other micronutrients"),
    ("PESTICIDE", "Pesticide", "General crop protection products"),
    ("INSECTICIDE", "Insecticide", "Products for insect pest control"),
    ("FUNGICIDE", "Fungicide", "Products for fungal disease control"),
    ("HERBICIDE", "Herbicide/Weedicide", "Products for weed control"),
    ("BIOSTIMULANT", "Biostimulant", "Growth promoters and biostimulants"),
    ("LABOR", "Labor", "Manual field operations"),
    ("MACHINERY", "Machinery", "Machine operations and services"),
    ("IRRIGATION", "Irrigation", "Water and irrigation operations"),
    ("OBSERVATION", "Observation", "Monitoring, scouting and checks"),
    ("OTHER", "Other", "Other agronomic operations"),
]

# code, category, name, unit, composition, crops, aliases
INPUT_DEFS = [
    ("CARBENDAZIM_THIRAM", "FUNGICIDE", "Carbendazim/Thiram Seed Treatment", "g", "Carbendazim/Thiram fungicide seed treatment", ["RICE"], ["Seed Treatment (Carbendazim/Thiram)", "Seed Treatment"]),
    ("SEED_SOAKING", "SEED", "Seed Soaking", "hour", None, ["RICE"], ["Seed Soaking"]),
    ("FYM_COMPOST", "ORGANIC_MANURE", "FYM/Compost", "kg", "Farmyard manure / compost", ["RICE", "SUGARCANE"], ["FYM/Compost (Bed Preparation)", "FYM/Compost"]),
    ("DAP_18_46_0", "FERTILIZER", "DAP", "kg", "N:P:K = 18:46:0", ["RICE", "SUGARCANE"], ["DAP (Basal Dose)", "DAP + Zinc Sulphate (Basal)"]),
    ("ZINC_SULPHATE", "MICRONUTRIENT", "Zinc Sulphate", "kg", "ZnSO4", ["RICE"], ["Zinc Sulphate", "ZnSO4"]),
    ("CHLORPYRIFOS", "INSECTICIDE", "Chlorpyrifos", "ml", "Organophosphate insecticide", ["RICE"], ["Chlorpyrifos (Pest Spray)"]),
    ("UREA_46_N", "FERTILIZER", "Urea", "kg", "46% Nitrogen", ["RICE", "SUGARCANE"], ["Urea (1st Top Dressing)", "Urea (2nd Top Dressing)", "Urea First Top Dressing", "Urea Second Top Dressing"]),
    ("BUTACHLOR_PRETILACHLOR", "HERBICIDE", "Butachlor/Pretilachlor", "litre", "Pre-emergence rice herbicide", ["RICE"], ["Herbicide (Butachlor/Pretilachlor)"]),
    ("MOP_POTASH", "FERTILIZER", "MOP/Potash", "kg", "Muriate of potash", ["RICE", "SUGARCANE"], ["MOP/Potash"]),
    ("TRICYCLAZOLE", "FUNGICIDE", "Tricyclazole", "g", "Rice blast fungicide", ["RICE"], ["Blast/Sheath Blight Spray"]),
    ("HEALTHY_CANE_SETTS", "SEED", "Healthy Cane Setts", "sett", "Sugarcane planting material", ["SUGARCANE"], ["Healthy Cane Setts"]),
    ("SETT_TREATMENT", "FUNGICIDE", "Sett Treatment", "operation", "Fungicide/insecticide sett dip", ["SUGARCANE"], ["Sett Treatment"]),
    ("BASAL_NPK", "FERTILIZER", "Basal NPK Dose", "kg", "Basal NPK as per soil test", ["SUGARCANE"], ["Basal NPK Dose"]),
    ("BORER_CONTROL", "INSECTICIDE", "Borer Control", "operation", "Need-based borer control", ["SUGARCANE"], ["Shoot Borer Control If Needed"]),
    ("PEST_DISEASE_MONITORING", "OBSERVATION", "Pest/Disease Monitoring", "operation", None, ["RICE", "SUGARCANE"], ["BPH/Stem Borer Check", "Early Shoot Borer Monitoring", "Top Borer / Pyrilla Monitoring"]),
    ("IRRIGATION_LIGHT", "IRRIGATION", "Light Irrigation", "hour", None, ["RICE", "SUGARCANE"], ["First Light Irrigation", "First Irrigation After Planting"]),
    ("IRRIGATION_MAINTAIN_WATER", "IRRIGATION", "Maintain Water Level", "hour", None, ["RICE"], ["Maintain Water Level", "Critical Irrigation"]),
    ("IRRIGATION_MOISTURE", "IRRIGATION", "Moisture Maintenance Irrigation", "hour", None, ["SUGARCANE"], ["Moisture Maintenance", "Tillering Irrigation", "Critical Growth Irrigation", "Reduce Irrigation Frequency", "Reduce Water Gradually"]),
    ("FIELD_PREPARATION_LABOR", "LABOR", "Field Preparation Labor", "operation", None, ["RICE", "SUGARCANE"], ["Puddling (Field Preparation)", "Deep Ploughing & Field Preparation"]),
    ("TRANSPLANTING_LABOR", "LABOR", "Transplanting Labor", "operation", None, ["RICE"], ["Transplanting"]),
    ("WEEDING_HOEING_LABOR", "LABOR", "Weeding/Hoeing Labor", "operation", None, ["SUGARCANE"], ["First Hoeing / Light Weeding", "Interculture & Weeding"]),
    ("EARTHING_UP_LABOR", "LABOR", "Earthing Up Labor", "operation", None, ["SUGARCANE"], ["Earthing Up"]),
    ("HARVEST_LABOR", "LABOR", "Harvest Labor", "operation", None, ["RICE", "SUGARCANE"], ["Cane Cutting", "Detrashing & Bundling", "Threshing & Winnowing"]),
    ("HARVEST_MACHINERY", "MACHINERY", "Harvesting Machinery", "operation", None, ["RICE"], ["Harvesting (Manual/Combine)"]),
    ("TRANSPORT_MACHINERY", "MACHINERY", "Transport Machinery", "operation", None, ["SUGARCANE"], ["Transport to Mill/Crusher"]),
    ("GAP_FILLING", "OTHER", "Gap Filling", "operation", None, ["SUGARCANE"], ["Gap Filling"]),
    ("TRASH_MANAGEMENT", "OTHER", "Trash Management", "operation", None, ["SUGARCANE"], ["Trash Management"]),
    ("MATURITY_CHECK", "OBSERVATION", "Maturity/Harvest Readiness Check", "operation", None, ["RICE", "SUGARCANE"], ["Seedling Readiness Check", "Harvest Readiness Check", "Maturity Check", "Harvest Planning", "Ratoon Decision"]),
    ("BIRD_SCARING", "OTHER", "Bird Scaring", "operation", None, ["RICE"], ["Bird Scaring"]),
    ("SUN_DRYING", "OTHER", "Sun Drying", "operation", None, ["RICE"], ["Sun Drying"]),
]


def normalize(value: str | None) -> str:
    value = (value or "").lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def seed_categories(db: Session) -> dict[str, InputCategory]:
    result = {}
    for code, name, description in CATEGORY_DEFS:
        category = db.query(InputCategory).filter(InputCategory.code == code).first()
        if not category:
            category = InputCategory(id=uuid.uuid4(), code=code, created_at=now(), updated_at=now())
            db.add(category)
        category.canonical_name = name
        category.description = description
        category.aliases = category.aliases or []
        category.updated_at = now()
        result[code] = category
    db.flush()
    return result


def ensure_generic_manufacturer(db: Session) -> Manufacturer:
    manufacturer = db.query(Manufacturer).filter(Manufacturer.code == "GENERIC").first()
    if not manufacturer:
        manufacturer = Manufacturer(
            id=uuid.uuid4(),
            code="GENERIC",
            canonical_name="Generic / Farmer Supplied",
            short_name="Generic",
            country="India",
            aliases=[],
            created_at=now(),
            updated_at=now(),
        )
        db.add(manufacturer)
    return manufacturer


def seed_inputs(db: Session, categories: dict[str, InputCategory], manufacturer: Manufacturer) -> dict[str, str]:
    alias_to_code = {}
    for code, category_code, name, unit, composition, crops, aliases in INPUT_DEFS:
        item = db.query(AgriculturalInput).filter(AgriculturalInput.code == code).first()
        if not item:
            item = AgriculturalInput(id=uuid.uuid4(), code=code, created_at=now(), updated_at=now())
            db.add(item)
        item.category_id = categories[category_code].id
        item.manufacturer_id = manufacturer.id
        item.canonical_name = name
        item.brand_name = None
        item.composition = composition
        item.unit = unit
        item.standard_weight = None
        item.applicable_crops = crops
        item.application_method = None
        item.safety_instructions = None
        item.aliases = [{"lang": "en", "name": alias} for alias in aliases]
        item.updated_at = now()
        for label in [name, *aliases]:
            alias_to_code[normalize(label)] = code
    db.flush()
    return alias_to_code


def map_recommendations(db: Session, alias_to_code: dict[str, str]) -> int:
    updated = 0
    recommendations = db.query(WorkflowTemplateRecommendation).all()
    for rec in recommendations:
        key = normalize(rec.input_name)
        input_code = alias_to_code.get(key)
        if not input_code:
            # Conservative contains matching for labels with extra parenthetical text.
            input_code = next((code for alias, code in alias_to_code.items() if alias and (alias in key or key in alias)), None)
        if input_code and rec.input_code != input_code:
            rec.input_code = input_code
            rec.updated_at = now()
            updated += 1
    db.flush()
    return updated


def seed_input_catalog():
    db = SessionLocal()
    try:
        categories = seed_categories(db)
        manufacturer = ensure_generic_manufacturer(db)
        alias_to_code = seed_inputs(db, categories, manufacturer)
        mapped = map_recommendations(db, alias_to_code)
        db.commit()
        print(
            f"Seeded input categories={len(categories)}, inputs={len(INPUT_DEFS)}, "
            f"mapped_recommendations={mapped}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    seed_input_catalog()

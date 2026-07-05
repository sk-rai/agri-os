"""Seed canonical crop taxonomy and propagation catalog.

This is the first step toward modular backend-driven crop workflows. It does
not replace existing crop_lifecycle_templates; it enriches the crop master data
with multi-axis taxonomy and allowed propagation methods.

Usage:
    cd backend
    source ../venv/bin/activate
    PYTHONPATH=. python3 scripts/seed_crop_taxonomy.py
"""

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
from app.modules.master_data.models import (
    Crop,
    CropPropagationOption,
    CropPropagationType,
    CropTaxonomyAssignment,
    CropTaxonomyEdge,
    CropTaxonomyNode,
)


def now():
    return datetime.now(timezone.utc)


TAXONOMY_NODES = [
    ("AGRICULTURE", "Agriculture", "ROOT", 0, 0),
    ("FIELD_CROP", "Field Crop", "AGRONOMIC", 1, 10),
    ("HORTICULTURE", "Horticulture", "AGRONOMIC", 1, 20),
    ("PLANTATION_CROP", "Plantation Crop", "AGRONOMIC", 1, 30),
    ("FODDER_FORAGE", "Fodder & Forage", "AGRONOMIC", 1, 40),
    ("CEREAL", "Cereal", "AGRONOMIC", 2, 10),
    ("GRAIN_CROP", "Grain Crop", "ECONOMIC", 2, 11),
    ("PULSE", "Pulse", "AGRONOMIC", 2, 20),
    ("OILSEED", "Oilseed", "AGRONOMIC", 2, 30),
    ("SUGAR_CROP", "Sugar Crop", "AGRONOMIC", 2, 40),
    ("FIBRE_CROP", "Fibre Crop", "AGRONOMIC", 2, 50),
    ("VEGETABLE", "Vegetable", "HORTICULTURE", 2, 60),
    ("FRUIT", "Fruit", "HORTICULTURE", 2, 70),
    ("SPICE", "Spice", "HORTICULTURE", 2, 80),
    ("FOOD_CROP", "Food Crop", "ECONOMIC", 2, 90),
    ("CASH_CROP", "Cash Crop", "ECONOMIC", 2, 100),
    ("INDUSTRIAL_CROP", "Industrial Crop", "ECONOMIC", 2, 110),
    ("ANNUAL", "Annual Crop", "GROWTH_HABIT", 2, 120),
    ("PERENNIAL", "Perennial Crop", "GROWTH_HABIT", 2, 130),
    ("VEGETATIVE_PROPAGATED", "Vegetatively Propagated Crop", "PROPAGATION", 2, 140),
]

TAXONOMY_EDGES = [
    ("AGRICULTURE", "FIELD_CROP"),
    ("AGRICULTURE", "HORTICULTURE"),
    ("AGRICULTURE", "PLANTATION_CROP"),
    ("AGRICULTURE", "FODDER_FORAGE"),
    ("FIELD_CROP", "CEREAL"),
    ("FIELD_CROP", "PULSE"),
    ("FIELD_CROP", "OILSEED"),
    ("FIELD_CROP", "SUGAR_CROP"),
    ("FIELD_CROP", "FIBRE_CROP"),
    ("HORTICULTURE", "VEGETABLE"),
    ("HORTICULTURE", "FRUIT"),
    ("HORTICULTURE", "SPICE"),
]

PROPAGATION_TYPES = [
    ("DIRECT_SEEDED", "Direct Seeded", "Seed sown directly into the field", "SEED"),
    ("NURSERY_TRANSPLANT", "Nursery + Transplant", "Seedlings raised in nursery and transplanted", "TRANSPLANT"),
    ("VEGETATIVE_SETT", "Vegetative Sett", "Stem/setts used as planting material", "VEGETATIVE"),
    ("TUBER", "Tuber", "Tubers used as planting material", "VEGETATIVE"),
    ("CUTTING", "Cutting", "Stem or branch cuttings used for establishment", "VEGETATIVE"),
    ("SAPLING", "Sapling", "Saplings planted in field/orchard", "PERENNIAL_PLANTING"),
    ("GRAFTED_PLANT", "Grafted Plant", "Grafted plants used for establishment", "PERENNIAL_PLANTING"),
    ("BULB", "Bulb", "Bulbs used as planting material", "VEGETATIVE"),
    ("RHIZOME", "Rhizome", "Rhizomes used as planting material", "VEGETATIVE"),
]

CROP_TAXONOMY = {
    "RICE": ["FIELD_CROP", "CEREAL", "GRAIN_CROP", "FOOD_CROP", "ANNUAL"],
    "WHEAT": ["FIELD_CROP", "CEREAL", "GRAIN_CROP", "FOOD_CROP", "ANNUAL"],
    "MAIZE": ["FIELD_CROP", "CEREAL", "GRAIN_CROP", "FOOD_CROP", "ANNUAL"],
    "BAJRA": ["FIELD_CROP", "CEREAL", "GRAIN_CROP", "FOOD_CROP", "ANNUAL"],
    "GRAM": ["FIELD_CROP", "PULSE", "FOOD_CROP", "ANNUAL"],
    "LENTIL": ["FIELD_CROP", "PULSE", "FOOD_CROP", "ANNUAL"],
    "MOONG": ["FIELD_CROP", "PULSE", "FOOD_CROP", "ANNUAL"],
    "URAD": ["FIELD_CROP", "PULSE", "FOOD_CROP", "ANNUAL"],
    "GROUNDNUT": ["FIELD_CROP", "OILSEED", "FOOD_CROP", "CASH_CROP", "ANNUAL"],
    "MUSTARD": ["FIELD_CROP", "OILSEED", "FOOD_CROP", "CASH_CROP", "ANNUAL"],
    "SUNFLOWER": ["FIELD_CROP", "OILSEED", "CASH_CROP", "ANNUAL"],
    "SUGARCANE": ["FIELD_CROP", "SUGAR_CROP", "INDUSTRIAL_CROP", "CASH_CROP", "VEGETATIVE_PROPAGATED", "PERENNIAL"],
    "POTATO": ["HORTICULTURE", "VEGETABLE", "FOOD_CROP", "VEGETATIVE_PROPAGATED", "ANNUAL"],
    "CUCUMBER": ["HORTICULTURE", "VEGETABLE", "FOOD_CROP", "ANNUAL"],
    "BOTTLE_GOURD": ["HORTICULTURE", "VEGETABLE", "FOOD_CROP", "ANNUAL"],
    "WATERMELON": ["HORTICULTURE", "FRUIT", "VEGETABLE", "FOOD_CROP", "ANNUAL"],
}

CROP_PROPAGATION = {
    "RICE": [("NURSERY_TRANSPLANT", "KHARIF", True), ("DIRECT_SEEDED", "KHARIF", False)],
    "WHEAT": [("DIRECT_SEEDED", "RABI", True)],
    "MAIZE": [("DIRECT_SEEDED", None, True)],
    "BAJRA": [("DIRECT_SEEDED", "KHARIF", True)],
    "GRAM": [("DIRECT_SEEDED", "RABI", True)],
    "LENTIL": [("DIRECT_SEEDED", "RABI", True)],
    "MOONG": [("DIRECT_SEEDED", None, True)],
    "URAD": [("DIRECT_SEEDED", None, True)],
    "GROUNDNUT": [("DIRECT_SEEDED", "KHARIF", True)],
    "MUSTARD": [("DIRECT_SEEDED", "RABI", True)],
    "SUNFLOWER": [("DIRECT_SEEDED", None, True)],
    "SUGARCANE": [("VEGETATIVE_SETT", None, True)],
    "POTATO": [("TUBER", "RABI", True)],
    "CUCUMBER": [("DIRECT_SEEDED", "ZAID", True)],
    "BOTTLE_GOURD": [("DIRECT_SEEDED", None, True)],
    "WATERMELON": [("DIRECT_SEEDED", "ZAID", True)],
}


def upsert_node(db, code, name, node_type, level, display_order):
    node = db.query(CropTaxonomyNode).filter(CropTaxonomyNode.code == code).first()
    if not node:
        node = CropTaxonomyNode(id=uuid.uuid4(), code=code, created_at=now(), updated_at=now())
        db.add(node)
    node.canonical_name = name
    node.node_type = node_type
    node.level = level
    node.display_order = display_order
    node.updated_at = now()
    return node


def main():
    db = SessionLocal()
    try:
        nodes = {
            code: upsert_node(db, code, name, node_type, level, display_order)
            for code, name, node_type, level, display_order in TAXONOMY_NODES
        }
        db.flush()

        for order, (parent_code, child_code) in enumerate(TAXONOMY_EDGES):
            edge = (
                db.query(CropTaxonomyEdge)
                .filter(
                    CropTaxonomyEdge.parent_node_id == nodes[parent_code].id,
                    CropTaxonomyEdge.child_node_id == nodes[child_code].id,
                )
                .first()
            )
            if not edge:
                edge = CropTaxonomyEdge(
                    id=uuid.uuid4(),
                    parent_node_id=nodes[parent_code].id,
                    child_node_id=nodes[child_code].id,
                    created_at=now(),
                    updated_at=now(),
                )
                db.add(edge)
            edge.display_order = order
            edge.updated_at = now()

        propagation_by_code = {}
        for code, name, description, establishment_type in PROPAGATION_TYPES:
            propagation_type = db.query(CropPropagationType).filter(CropPropagationType.code == code).first()
            if not propagation_type:
                propagation_type = CropPropagationType(id=uuid.uuid4(), code=code, created_at=now(), updated_at=now())
                db.add(propagation_type)
            propagation_type.canonical_name = name
            propagation_type.description = description
            propagation_type.establishment_type = establishment_type
            propagation_type.updated_at = now()
            propagation_by_code[code] = propagation_type
        db.flush()

        assigned_count = 0
        option_count = 0
        for crop_code, taxonomy_codes in CROP_TAXONOMY.items():
            crop = db.query(Crop).filter(Crop.code == crop_code).first()
            if not crop:
                continue
            for index, taxonomy_code in enumerate(taxonomy_codes):
                node = nodes[taxonomy_code]
                assignment = (
                    db.query(CropTaxonomyAssignment)
                    .filter(
                        CropTaxonomyAssignment.crop_id == crop.id,
                        CropTaxonomyAssignment.taxonomy_node_id == node.id,
                    )
                    .first()
                )
                if not assignment:
                    assignment = CropTaxonomyAssignment(
                        id=uuid.uuid4(),
                        crop_id=crop.id,
                        taxonomy_node_id=node.id,
                        created_at=now(),
                        updated_at=now(),
                    )
                    db.add(assignment)
                assignment.assignment_type = "PRIMARY" if index == 0 else "SECONDARY"
                assignment.is_primary = index == 0
                assignment.source = "SYSTEM"
                assignment.updated_at = now()
                assigned_count += 1

        for crop_code, options in CROP_PROPAGATION.items():
            crop = db.query(Crop).filter(Crop.code == crop_code).first()
            if not crop:
                continue
            for propagation_code, season_code, is_default in options:
                propagation_type = propagation_by_code[propagation_code]
                query = db.query(CropPropagationOption).filter(
                    CropPropagationOption.crop_id == crop.id,
                    CropPropagationOption.propagation_type_id == propagation_type.id,
                )
                query = query.filter(CropPropagationOption.season_code == season_code) if season_code else query.filter(CropPropagationOption.season_code.is_(None))
                option = query.first()
                if not option:
                    option = CropPropagationOption(
                        id=uuid.uuid4(),
                        crop_id=crop.id,
                        propagation_type_id=propagation_type.id,
                        season_code=season_code,
                        created_at=now(),
                        updated_at=now(),
                    )
                    db.add(option)
                option.is_default = is_default
                option.updated_at = now()
                option_count += 1

        db.commit()
        print(f"Seeded taxonomy nodes={len(nodes)}, propagation_types={len(propagation_by_code)}, assignments={assigned_count}, propagation_options={option_count}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

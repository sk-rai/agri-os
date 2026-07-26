#!/usr/bin/env python3
"""Seed company/manufacturer and representative product catalog metadata.

This is a curated starter pack for local Android/admin testing. It uses public
company-directory references as source evidence for company/manufacturer names,
then seeds representative demo/reference products mapped to canonical inputs.

Important: rows marked DEMO_REFERENCE_PRODUCT are not regulatory claims. Exact
product labels, registrations, prices, and certifications must be verified from
manufacturer/regulator sources before production use.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
from app.modules.farmer.models import CompanyDiscoveryCandidate, CompanyProfile, Tenant
from app.modules.master_data.models import (
    AgriculturalInput,
    AgriculturalProduct,
    AgriculturalProductPackage,
    InputCategory,
    Manufacturer,
    ProductCatalogAuditEvent,
)


SEED_PACK = "COMPANY_PRODUCT_STARTER_PACK_2026_07"

SCREENER_SOURCE = {
    "source": "SCREENER_FERTILIZERS_AGROCHEMICALS",
    "url": "https://www.screener.in/market/IN01/IN0101/IN010102/",
    "retrieved_at": "2026-07-26",
    "notes": "Public market screener sector page for fertilizers and agrochemicals companies. Used only as company-directory evidence.",
}

TNAU_SEED_SOURCE = {
    "source": "TNAU_SEED_INDUSTRIES_INDIA_PDF",
    "url": "https://agritech.tnau.ac.in/agricultural_marketing/pdf/Seed_Industries_India.pdf",
    "retrieved_at": "2026-07-26",
    "notes": "TNAU AgriTech seed-industry directory PDF. Used only as seed-company directory evidence.",
}


MANUFACTURER_SEEDS = [
    # Screener fertilizers/agrochemicals starter set.
    {"code": "COROMANDEL", "name": "Coromandel International", "short": "Coromandel", "company_type": "INPUT_COMPANY", "segments": ["FERTILIZER", "CROP_PROTECTION"], "source": SCREENER_SOURCE},
    {"code": "FACT", "name": "Fertilisers and Chemicals Travancore", "short": "FACT", "company_type": "FERTILIZER_COMPANY", "segments": ["FERTILIZER"], "source": SCREENER_SOURCE},
    {"code": "UPL", "name": "UPL Limited", "short": "UPL", "company_type": "PESTICIDE_COMPANY", "segments": ["CROP_PROTECTION"], "source": SCREENER_SOURCE},
    {"code": "PI_INDUSTRIES", "name": "PI Industries", "short": "PI", "company_type": "PESTICIDE_COMPANY", "segments": ["CROP_PROTECTION"], "source": SCREENER_SOURCE},
    {"code": "SUMITOMO_CHEMICAL_INDIA", "name": "Sumitomo Chemical India", "short": "Sumitomo", "company_type": "PESTICIDE_COMPANY", "segments": ["CROP_PROTECTION"], "source": SCREENER_SOURCE},
    {"code": "BAYER", "name": "Bayer CropScience", "short": "Bayer", "company_type": "PESTICIDE_COMPANY", "segments": ["CROP_PROTECTION"], "source": SCREENER_SOURCE},
    {"code": "CHAMBAL_FERTILIZERS", "name": "Chambal Fertilisers and Chemicals", "short": "Chambal", "company_type": "FERTILIZER_COMPANY", "segments": ["FERTILIZER"], "source": SCREENER_SOURCE},
    {"code": "PARADEEP_PHOSPHATES", "name": "Paradeep Phosphates", "short": "PPL", "company_type": "FERTILIZER_COMPANY", "segments": ["FERTILIZER"], "source": SCREENER_SOURCE},
    {"code": "RCF", "name": "Rashtriya Chemicals and Fertilizers", "short": "RCF", "company_type": "FERTILIZER_COMPANY", "segments": ["FERTILIZER"], "source": SCREENER_SOURCE},
    {"code": "MB_AGRO_PRODUCTS", "name": "M B Agro Products", "short": "MB Agro", "company_type": "FERTILIZER_COMPANY", "segments": ["FERTILIZER"], "source": SCREENER_SOURCE},
    {"code": "GSFC", "name": "Gujarat State Fertilizers and Chemicals", "short": "GSFC", "company_type": "FERTILIZER_COMPANY", "segments": ["FERTILIZER"], "source": SCREENER_SOURCE},
    {"code": "KRISHANA_PHOSCHEM", "name": "Krishana Phoschem", "short": "Krishana", "company_type": "FERTILIZER_COMPANY", "segments": ["FERTILIZER"], "source": SCREENER_SOURCE},
    {"code": "NACL_INDUSTRIES", "name": "NACL Industries", "short": "NACL", "company_type": "PESTICIDE_COMPANY", "segments": ["CROP_PROTECTION"], "source": SCREENER_SOURCE},
    {"code": "DHANUKA", "name": "Dhanuka Agritech", "short": "Dhanuka", "company_type": "PESTICIDE_COMPANY", "segments": ["CROP_PROTECTION"], "source": SCREENER_SOURCE},
    {"code": "RALLIS", "name": "Rallis India", "short": "Rallis", "company_type": "INPUT_COMPANY", "segments": ["CROP_PROTECTION", "SEED"], "source": SCREENER_SOURCE},
    {"code": "NFL", "name": "National Fertilizers Limited", "short": "NFL", "company_type": "FERTILIZER_COMPANY", "segments": ["FERTILIZER"], "source": SCREENER_SOURCE},
    {"code": "GSP_CROP_SCIENCE", "name": "GSP Crop Science", "short": "GSP", "company_type": "PESTICIDE_COMPANY", "segments": ["CROP_PROTECTION"], "source": SCREENER_SOURCE},
    {"code": "BHARAT_RASAYAN", "name": "Bharat Rasayan", "short": "Bharat Rasayan", "company_type": "PESTICIDE_COMPANY", "segments": ["CROP_PROTECTION"], "source": SCREENER_SOURCE},
    {"code": "INSECTICIDES_INDIA", "name": "Insecticides India", "short": "IIL", "company_type": "PESTICIDE_COMPANY", "segments": ["CROP_PROTECTION"], "source": SCREENER_SOURCE},
    {"code": "INDIA_PESTICIDES", "name": "India Pesticides", "short": "India Pesticides", "company_type": "PESTICIDE_COMPANY", "segments": ["CROP_PROTECTION"], "source": SCREENER_SOURCE},
    {"code": "MEGHMANI_ORGANICS", "name": "Meghmani Organics", "short": "Meghmani", "company_type": "PESTICIDE_COMPANY", "segments": ["CROP_PROTECTION"], "source": SCREENER_SOURCE},
    {"code": "PUNJAB_CHEMICALS", "name": "Punjab Chemicals and Crop Protection", "short": "Punjab Chemicals", "company_type": "PESTICIDE_COMPANY", "segments": ["CROP_PROTECTION"], "source": SCREENER_SOURCE},

    # Existing/common co-op/generic manufacturers.
    {"code": "IFFCO", "name": "Indian Farmers Fertiliser Cooperative", "short": "IFFCO", "company_type": "FERTILIZER_COMPANY", "segments": ["FERTILIZER"], "source": {"source": "LOCAL_EXISTING_CATALOG"}},
    {"code": "GENERIC", "name": "Generic / Farmer Supplied", "short": "Generic", "company_type": "OTHER", "segments": ["ORGANIC", "NATURAL", "SEED", "LABOR"], "source": {"source": "LOCAL_EXISTING_CATALOG"}},

    # TNAU seed-industry starter set.
    {"code": "ADVANTA_INDIA", "name": "Advanta India Limited", "short": "Advanta", "company_type": "SEED_COMPANY", "segments": ["SEED"], "source": TNAU_SEED_SOURCE},
    {"code": "AG_SUNSEEDS", "name": "A.G. Sunseeds (India) Pvt. Ltd.", "short": "A.G. Sunseeds", "company_type": "SEED_COMPANY", "segments": ["SEED"], "source": TNAU_SEED_SOURCE},
    {"code": "AGRI_GENETIC_RESEARCH", "name": "Agri Genetic Research Organisation Pvt. Ltd.", "short": "AGRO", "company_type": "SEED_COMPANY", "segments": ["SEED"], "source": TNAU_SEED_SOURCE},
    {"code": "AGRO_BIOTECH", "name": "Agro Biotech", "short": "Agro Biotech", "company_type": "SEED_COMPANY", "segments": ["SEED", "BIO_INPUT"], "source": TNAU_SEED_SOURCE},
    {"code": "AJEET_SEEDS", "name": "Ajeet Seed Pvt. Ltd.", "short": "Ajeet", "company_type": "SEED_COMPANY", "segments": ["SEED"], "source": TNAU_SEED_SOURCE},
    {"code": "ANKUR_SEEDS", "name": "Ankur Seeds Pvt. Ltd.", "short": "Ankur", "company_type": "SEED_COMPANY", "segments": ["SEED"], "source": TNAU_SEED_SOURCE},
    {"code": "AP_STATE_SEEDS", "name": "Andhra Pradesh State Seeds Development Corporation Ltd.", "short": "AP Seeds", "company_type": "SEED_COMPANY", "segments": ["SEED"], "source": TNAU_SEED_SOURCE},
    {"code": "BASANT_AGRO_TECH", "name": "Basant Agro Tech (India) Ltd.", "short": "Basant Agro", "company_type": "SEED_COMPANY", "segments": ["SEED", "FERTILIZER"], "source": TNAU_SEED_SOURCE},
    {"code": "BEJO_SHEETAL", "name": "Bejo Sheetal Seed Pvt. Ltd.", "short": "Bejo Sheetal", "company_type": "SEED_COMPANY", "segments": ["SEED"], "source": TNAU_SEED_SOURCE},
    {"code": "CAMSON_AGRITECH", "name": "Camson Agritech Ltd.", "short": "Camson", "company_type": "BIO_INPUT_COMPANY", "segments": ["SEED", "BIO_INPUT", "ORGANIC"], "source": TNAU_SEED_SOURCE},
    {"code": "CONTINENTAL_SEED_CHEMICALS", "name": "Continental Seed & Chemicals Ltd.", "short": "Continental", "company_type": "INPUT_COMPANY", "segments": ["SEED", "CROP_PROTECTION"], "source": TNAU_SEED_SOURCE},
    {"code": "EID_PARRY_SEEDS", "name": "E I D Parry (India) Ltd. (Seeds Division)", "short": "EID Parry Seeds", "company_type": "SEED_COMPANY", "segments": ["SEED"], "source": TNAU_SEED_SOURCE},
]


INPUT_SEEDS = [
    {"code": "RICE_SEED_CERTIFIED", "category": "SEED", "name": "Certified Rice Seed", "composition": "Certified paddy/rice seed", "unit": "kg", "origin": "SEED"},
    {"code": "WHEAT_SEED_CERTIFIED", "category": "SEED", "name": "Certified Wheat Seed", "composition": "Certified wheat seed", "unit": "kg", "origin": "SEED"},
    {"code": "MAIZE_HYBRID_SEED", "category": "SEED", "name": "Hybrid Maize Seed", "composition": "Hybrid maize seed", "unit": "kg", "origin": "SEED"},
    {"code": "VEGETABLE_HYBRID_SEED", "category": "SEED", "name": "Hybrid Vegetable Seed", "composition": "Vegetable hybrid seed", "unit": "packet", "origin": "SEED"},
    {"code": "VERMICOMPOST", "category": "ORGANIC_MANURE", "name": "Vermicompost", "composition": "Decomposed organic matter processed by earthworms", "unit": "kg", "origin": "ORGANIC_CERTIFIABLE"},
    {"code": "NEEM_CAKE", "category": "ORGANIC_MANURE", "name": "Neem Cake", "composition": "Neem seed cake organic manure", "unit": "kg", "origin": "ORGANIC_CERTIFIABLE"},
    {"code": "JEEVAMRIT", "category": "BIOSTIMULANT", "name": "Jeevamrit", "composition": "Natural farming microbial preparation", "unit": "litre", "origin": "NATURAL_FARMING"},
    {"code": "BEEJAMRIT", "category": "BIOSTIMULANT", "name": "Beejamrit", "composition": "Natural farming seed treatment preparation", "unit": "litre", "origin": "NATURAL_FARMING"},
    {"code": "AZOSPIRILLUM_BIOFERTILIZER", "category": "BIOSTIMULANT", "name": "Azospirillum Biofertilizer", "composition": "Nitrogen-fixing microbial inoculant", "unit": "kg", "origin": "BIOLOGICAL"},
    {"code": "PSB_BIOFERTILIZER", "category": "BIOSTIMULANT", "name": "Phosphate Solubilizing Bacteria", "composition": "Phosphate solubilizing microbial inoculant", "unit": "kg", "origin": "BIOLOGICAL"},
]


PRODUCT_SEEDS = [
    # Fertilizer/crop-protection examples using current local canonical inputs.
    {"code": "COROMANDEL_NPK_DEMO_50KG", "manufacturer": "COROMANDEL", "input": "BASAL_NPK", "brand": "Coromandel NPK Demo", "composition": "NPK complex fertilizer demo/reference", "qty": "50", "unit": "kg", "pack": "50 kg bag", "origin": "MINERAL_SYNTHETIC", "class": "CONVENTIONAL", "confidence": "DEMO_REFERENCE_PRODUCT"},
    {"code": "FACT_COMPLEX_FERTILIZER_DEMO_50KG", "manufacturer": "FACT", "input": "BASAL_NPK", "brand": "FACT Complex Fertilizer Demo", "composition": "Complex fertilizer demo/reference", "qty": "50", "unit": "kg", "pack": "50 kg bag", "origin": "MINERAL_SYNTHETIC", "class": "CONVENTIONAL", "confidence": "DEMO_REFERENCE_PRODUCT"},
    {"code": "CHAMBAL_UREA_DEMO_45KG", "manufacturer": "CHAMBAL_FERTILIZERS", "input": "UREA_46_N", "brand": "Chambal Urea Demo", "composition": "46% Nitrogen", "qty": "45", "unit": "kg", "pack": "45 kg bag", "origin": "MINERAL_SYNTHETIC", "class": "CONVENTIONAL", "confidence": "DEMO_REFERENCE_PRODUCT"},
    {"code": "PARADEEP_DAP_DEMO_50KG", "manufacturer": "PARADEEP_PHOSPHATES", "input": "DAP_18_46_0", "brand": "Paradeep DAP Demo", "composition": "N:P:K = 18:46:0", "qty": "50", "unit": "kg", "pack": "50 kg bag", "origin": "MINERAL_SYNTHETIC", "class": "CONVENTIONAL", "confidence": "DEMO_REFERENCE_PRODUCT"},
    {"code": "RCF_UREA_DEMO_45KG", "manufacturer": "RCF", "input": "UREA_46_N", "brand": "RCF Urea Demo", "composition": "46% Nitrogen", "qty": "45", "unit": "kg", "pack": "45 kg bag", "origin": "MINERAL_SYNTHETIC", "class": "CONVENTIONAL", "confidence": "DEMO_REFERENCE_PRODUCT"},
    {"code": "GSFC_DAP_DEMO_50KG", "manufacturer": "GSFC", "input": "DAP_18_46_0", "brand": "GSFC DAP Demo", "composition": "N:P:K = 18:46:0", "qty": "50", "unit": "kg", "pack": "50 kg bag", "origin": "MINERAL_SYNTHETIC", "class": "CONVENTIONAL", "confidence": "DEMO_REFERENCE_PRODUCT"},
    {"code": "UPL_CHLORPYRIFOS_DEMO_1L", "manufacturer": "UPL", "input": "CHLORPYRIFOS", "brand": "UPL Chlorpyrifos Demo", "composition": "Chlorpyrifos crop-protection demo/reference", "qty": "1", "unit": "litre", "pack": "1 litre bottle", "origin": "SYNTHETIC_CROP_PROTECTION", "class": "CONVENTIONAL", "confidence": "DEMO_REFERENCE_PRODUCT"},
    {"code": "PI_HERBICIDE_DEMO_1L", "manufacturer": "PI_INDUSTRIES", "input": "BUTACHLOR_PRETILACHLOR", "brand": "PI Rice Herbicide Demo", "composition": "Rice herbicide demo/reference", "qty": "1", "unit": "litre", "pack": "1 litre bottle", "origin": "SYNTHETIC_CROP_PROTECTION", "class": "CONVENTIONAL", "confidence": "DEMO_REFERENCE_PRODUCT"},
    {"code": "DHANUKA_SEED_TREATMENT_DEMO_100G", "manufacturer": "DHANUKA", "input": "CARBENDAZIM_THIRAM", "brand": "Dhanuka Seed Treatment Demo", "composition": "Carbendazim/Thiram seed treatment demo/reference", "qty": "100", "unit": "g", "pack": "100 g pouch", "origin": "SYNTHETIC_CROP_PROTECTION", "class": "CONVENTIONAL", "confidence": "DEMO_REFERENCE_PRODUCT"},
    {"code": "BAYER_TRICYCLAZOLE_DEMO_250G", "manufacturer": "BAYER", "input": "TRICYCLAZOLE", "brand": "Bayer Tricyclazole Demo", "composition": "Rice blast fungicide demo/reference", "qty": "250", "unit": "g", "pack": "250 g pouch", "origin": "SYNTHETIC_CROP_PROTECTION", "class": "CONVENTIONAL", "confidence": "DEMO_REFERENCE_PRODUCT"},
    {"code": "RALLIS_CROP_PROTECTION_DEMO_500ML", "manufacturer": "RALLIS", "input": "CHLORPYRIFOS", "brand": "Rallis Crop Protection Demo", "composition": "Crop-protection demo/reference", "qty": "500", "unit": "ml", "pack": "500 ml bottle", "origin": "SYNTHETIC_CROP_PROTECTION", "class": "CONVENTIONAL", "confidence": "DEMO_REFERENCE_PRODUCT"},

    # Seed examples from TNAU seed-company directory.
    {"code": "ADVANTA_RICE_SEED_DEMO_10KG", "manufacturer": "ADVANTA_INDIA", "input": "RICE_SEED_CERTIFIED", "brand": "Advanta Rice Seed Demo", "composition": "Certified rice seed demo/reference", "qty": "10", "unit": "kg", "pack": "10 kg bag", "origin": "SEED", "class": "SEED", "confidence": "DEMO_REFERENCE_PRODUCT"},
    {"code": "AJEET_MAIZE_SEED_DEMO_5KG", "manufacturer": "AJEET_SEEDS", "input": "MAIZE_HYBRID_SEED", "brand": "Ajeet Maize Seed Demo", "composition": "Hybrid maize seed demo/reference", "qty": "5", "unit": "kg", "pack": "5 kg bag", "origin": "SEED", "class": "SEED", "confidence": "DEMO_REFERENCE_PRODUCT"},
    {"code": "ANKUR_COTTON_SEED_DEMO_PACKET", "manufacturer": "ANKUR_SEEDS", "input": "VEGETABLE_HYBRID_SEED", "brand": "Ankur Hybrid Seed Demo", "composition": "Hybrid seed demo/reference", "qty": "1", "unit": "packet", "pack": "1 packet", "origin": "SEED", "class": "SEED", "confidence": "DEMO_REFERENCE_PRODUCT"},
    {"code": "AP_SEEDS_PADDY_SEED_DEMO_10KG", "manufacturer": "AP_STATE_SEEDS", "input": "RICE_SEED_CERTIFIED", "brand": "AP Seeds Paddy Seed Demo", "composition": "Certified paddy seed demo/reference", "qty": "10", "unit": "kg", "pack": "10 kg bag", "origin": "SEED", "class": "SEED", "confidence": "DEMO_REFERENCE_PRODUCT"},
    {"code": "BEJO_SHEETAL_VEGETABLE_SEED_DEMO", "manufacturer": "BEJO_SHEETAL", "input": "VEGETABLE_HYBRID_SEED", "brand": "Bejo Sheetal Vegetable Seed Demo", "composition": "Vegetable seed demo/reference", "qty": "1", "unit": "packet", "pack": "1 packet", "origin": "SEED", "class": "SEED", "confidence": "DEMO_REFERENCE_PRODUCT"},

    # Organic/natural/bio-input examples.
    {"code": "GENERIC_VERMICOMPOST_25KG", "manufacturer": "GENERIC", "input": "VERMICOMPOST", "brand": "Generic Vermicompost", "composition": "Organic manure", "qty": "25", "unit": "kg", "pack": "25 kg bag", "origin": "ORGANIC_CERTIFIABLE", "class": "ORGANIC", "confidence": "GENERIC_INPUT"},
    {"code": "GENERIC_NEEM_CAKE_25KG", "manufacturer": "GENERIC", "input": "NEEM_CAKE", "brand": "Generic Neem Cake", "composition": "Neem cake organic manure", "qty": "25", "unit": "kg", "pack": "25 kg bag", "origin": "ORGANIC_CERTIFIABLE", "class": "ORGANIC", "confidence": "GENERIC_INPUT"},
    {"code": "GENERIC_JEEVAMRIT_10L", "manufacturer": "GENERIC", "input": "JEEVAMRIT", "brand": "On-farm Jeevamrit", "composition": "Natural farming preparation", "qty": "10", "unit": "litre", "pack": "10 litre batch", "origin": "NATURAL_FARMING", "class": "NATURAL", "confidence": "GENERIC_INPUT"},
    {"code": "GENERIC_BEEJAMRIT_5L", "manufacturer": "GENERIC", "input": "BEEJAMRIT", "brand": "On-farm Beejamrit", "composition": "Natural farming seed treatment", "qty": "5", "unit": "litre", "pack": "5 litre batch", "origin": "NATURAL_FARMING", "class": "NATURAL", "confidence": "GENERIC_INPUT"},
    {"code": "CAMSON_AZOSPIRILLUM_DEMO_1KG", "manufacturer": "CAMSON_AGRITECH", "input": "AZOSPIRILLUM_BIOFERTILIZER", "brand": "Camson Biofertilizer Demo", "composition": "Microbial inoculant demo/reference", "qty": "1", "unit": "kg", "pack": "1 kg pack", "origin": "BIOLOGICAL", "class": "BIO_INPUT", "confidence": "DEMO_REFERENCE_PRODUCT"},
    {"code": "AGRO_BIOTECH_PSB_DEMO_1KG", "manufacturer": "AGRO_BIOTECH", "input": "PSB_BIOFERTILIZER", "brand": "Agro Biotech PSB Demo", "composition": "Phosphate solubilizing bacteria demo/reference", "qty": "1", "unit": "kg", "pack": "1 kg pack", "origin": "BIOLOGICAL", "class": "BIO_INPUT", "confidence": "DEMO_REFERENCE_PRODUCT"},
]


def code(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", value.upper()).strip("_")


def clean_dict(value: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in value.items() if v is not None}


def row_metadata(source: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = {
        "seed_pack": SEED_PACK,
        "source_references": [source],
        "source_confidence": "DIRECTORY_REFERENCE",
        "production_use_note": "Verify exact product/company details from manufacturer/regulator source before production use.",
    }
    if extra:
        metadata.update(extra)
    return metadata


def ensure_category(db, *, code_value: str, name: str, apply: bool, now_ts: datetime) -> tuple[InputCategory, str]:
    row = db.query(InputCategory).filter(InputCategory.code == code_value).first()
    if row:
        return row, "existing"
    row = InputCategory(
        id=uuid.uuid4(),
        code=code_value,
        canonical_name=name,
        description=f"Seeded category for {name}",
        aliases=[],
        created_at=now_ts,
        updated_at=now_ts,
    )
    if apply:
        db.add(row)
        db.flush()
    return row, "created"


def ensure_manufacturer(db, item: dict[str, Any], *, apply: bool, now_ts: datetime) -> tuple[Manufacturer, str]:
    row = db.query(Manufacturer).filter(Manufacturer.code == item["code"]).first()
    aliases = [{"name": item["name"], "source": item["source"].get("source")}]
    metadata_alias = {
        "segments": item["segments"],
        "company_type": item["company_type"],
        "source_reference": item["source"],
        "seed_pack": SEED_PACK,
    }
    if row:
        if apply:
            row.canonical_name = item["name"]
            row.short_name = item["short"]
            row.country = "India"
            current_aliases = row.aliases or []
            if not any(alias.get("source") == item["source"].get("source") and alias.get("name") == item["name"] for alias in current_aliases):
                current_aliases.append(aliases[0])
            # Manufacturer has no metadata column, so source is stored in aliases.
            if not any(alias.get("seed_pack") == SEED_PACK for alias in current_aliases):
                current_aliases.append(metadata_alias)
            row.aliases = current_aliases
            row.updated_at = now_ts
        return row, "updated"

    row = Manufacturer(
        id=uuid.uuid4(),
        code=item["code"],
        canonical_name=item["name"],
        short_name=item["short"],
        country="India",
        aliases=[aliases[0], metadata_alias],
        created_at=now_ts,
        updated_at=now_ts,
    )
    if apply:
        db.add(row)
        db.flush()
    return row, "created"


def ensure_input(db, item: dict[str, Any], categories: dict[str, InputCategory], *, apply: bool, now_ts: datetime) -> tuple[AgriculturalInput, str]:
    row = db.query(AgriculturalInput).filter(AgriculturalInput.code == item["code"]).first()
    category = categories[item["category"]]
    aliases = [{"name": item["name"], "seed_pack": SEED_PACK, "input_origin": item["origin"]}]
    if row:
        if apply:
            row.category_id = category.id
            row.canonical_name = item["name"]
            row.composition = item["composition"]
            row.unit = item["unit"]
            current_aliases = row.aliases or []
            if not any(alias.get("seed_pack") == SEED_PACK and alias.get("input_origin") == item["origin"] for alias in current_aliases):
                current_aliases.append(aliases[0])
            row.aliases = current_aliases
            row.catalog_status = "APPROVED"
            row.updated_at = now_ts
        return row, "updated"

    row = AgriculturalInput(
        id=uuid.uuid4(),
        code=item["code"],
        category_id=category.id,
        canonical_name=item["name"],
        composition=item["composition"],
        unit=item["unit"],
        aliases=aliases,
        catalog_status="APPROVED",
        created_at=now_ts,
        updated_at=now_ts,
    )
    if apply:
        db.add(row)
        db.flush()
    return row, "created"


def ensure_product(
    db,
    item: dict[str, Any],
    manufacturers: dict[str, Manufacturer],
    inputs: dict[str, AgriculturalInput],
    *,
    apply: bool,
    now_ts: datetime,
) -> tuple[AgriculturalProduct, str, str]:
    row = db.query(AgriculturalProduct).filter(AgriculturalProduct.code == item["code"]).first()
    manufacturer = manufacturers[item["manufacturer"]]
    canonical_input = inputs[item["input"]]
    product_metadata = row_metadata(
        {"source": "CURATED_STARTER_PRODUCT_MAPPING", "base_sources": [SCREENER_SOURCE["url"], TNAU_SEED_SOURCE["url"]]},
        {
            "catalog_seed_type": item["confidence"],
            "agriculture_type": item["class"],
            "input_origin": item["origin"],
            "farming_system_tags": {
                "conventional": item["class"] == "CONVENTIONAL",
                "seed": item["class"] == "SEED",
                "organic_compatible": item["class"] in {"ORGANIC", "BIO_INPUT"},
                "natural_farming": item["class"] == "NATURAL",
                "bio_input": item["class"] == "BIO_INPUT",
            },
            "organic_natural_distinction": {
                "organic": "External inputs may be used only if certification rules allow them; certification evidence must be verified.",
                "natural": "Natural-farming examples represent on-farm or minimal-purchased preparations and are tracked separately from organic-certified products.",
            },
            "source_confidence": item["confidence"],
        },
    )
    if row:
        if apply:
            row.canonical_input_id = canonical_input.id
            row.manufacturer_id = manufacturer.id
            row.brand_name = item["brand"]
            row.composition = item["composition"]
            row.country = "India"
            row.status = "ACTIVE"
            row.metadata_ = product_metadata
            row.updated_at = now_ts
        product_action = "updated"
    else:
        row = AgriculturalProduct(
            id=uuid.uuid4(),
            code=item["code"],
            canonical_input_id=canonical_input.id,
            manufacturer_id=manufacturer.id,
            brand_name=item["brand"],
            composition=item["composition"],
            registration_number=None,
            registration_authority=None,
            country="India",
            status="ACTIVE",
            metadata_=product_metadata,
            created_at=now_ts,
            updated_at=now_ts,
        )
        if apply:
            db.add(row)
            db.flush()
        product_action = "created"

    sku = f"{item['code']}_{code(item['pack'])}"
    package = db.query(AgriculturalProductPackage).filter(AgriculturalProductPackage.sku == sku).first()
    if package:
        if apply:
            package.product_id = row.id
            package.quantity = Decimal(item["qty"])
            package.unit = item["unit"]
            package.pack_label = item["pack"]
            package.status = "ACTIVE"
            package.updated_at = now_ts
        package_action = "updated"
    else:
        if apply:
            db.add(AgriculturalProductPackage(
                id=uuid.uuid4(),
                product_id=row.id,
                sku=sku,
                quantity=Decimal(item["qty"]),
                unit=item["unit"],
                pack_label=item["pack"],
                status="ACTIVE",
                created_at=now_ts,
                updated_at=now_ts,
            ))
        package_action = "created"

    return row, product_action, package_action


def upsert_discovery_candidate(db, item: dict[str, Any], *, tenant_id: str, apply: bool, now_ts: datetime) -> str:
    normalized = code(item["name"])
    row = (
        db.query(CompanyDiscoveryCandidate)
        .filter(
            CompanyDiscoveryCandidate.tenant_id == tenant_id,
            CompanyDiscoveryCandidate.normalized_name == normalized,
            CompanyDiscoveryCandidate.source == item["source"].get("source", "CURATED"),
        )
        .first()
    )
    payload = {
        "legal_name": item["name"],
        "display_name": item["short"],
        "company_type": item["company_type"],
        "segments": item["segments"],
        "catalog_seed_pack": SEED_PACK,
    }
    if row:
        if apply:
            row.candidate_name = item["name"]
            row.company_type = item["company_type"]
            row.source_references = [item["source"]]
            row.discovered_profile = payload
            row.operating_geography = {"country": "India"}
            row.crop_focus = []
            row.confidence_score = Decimal("0.7000")
            row.duplicate_keys = {"manufacturer_code": item["code"]}
            row.metadata_ = row_metadata(item["source"], {"manufacturer_code": item["code"]})
            row.updated_at = now_ts
        return "updated"

    if apply:
        db.add(CompanyDiscoveryCandidate(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            candidate_name=item["name"],
            normalized_name=normalized,
            company_type=item["company_type"],
            source=item["source"].get("source", "CURATED"),
            source_references=[item["source"]],
            discovered_profile=payload,
            operating_geography={"country": "India"},
            crop_focus=[],
            confidence_score=Decimal("0.7000"),
            duplicate_keys={"manufacturer_code": item["code"]},
            review_status="PENDING_REVIEW",
            metadata_=row_metadata(item["source"], {"manufacturer_code": item["code"]}),
            created_at=now_ts,
            updated_at=now_ts,
        ))
    return "created"


def update_default_company_profile(db, *, tenant_id: str, apply: bool, now_ts: datetime) -> str:
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise SystemExit(f"Tenant {tenant_id} not found")
    row = db.query(CompanyProfile).filter(CompanyProfile.tenant_id == tenant_id).first()
    payload = {
        "catalog_readiness": {
            "manufacturer_directory_seed_pack": SEED_PACK,
            "company_profile_role": "LOCAL_TENANT_PROFILE_NOT_EXTERNAL_MANUFACTURER",
            "external_companies_modeled_as": ["manufacturers", "company_discovery_candidates"],
        },
        "input_classification": {
            "conventional": "Synthetic/mineral fertilizer and crop-protection products.",
            "organic": "Certification-aware external organic-compatible inputs such as compost/neem cake; certification evidence still required.",
            "natural": "Natural-farming/on-farm preparations such as Jeevamrit/Beejamrit, tracked separately from organic certification.",
            "bio_input": "Microbial or biological input products such as biofertilizers.",
            "seed": "Seed/planting material companies and products.",
        },
        "source_references": [SCREENER_SOURCE, TNAU_SEED_SOURCE],
    }
    if row:
        if apply:
            config = dict(row.config or {})
            config.update(payload)
            row.config = config
            row.metadata_ = {**(row.metadata_ or {}), "last_company_product_seed_pack": SEED_PACK}
            row.updated_at = now_ts
        return "updated"

    if apply:
        db.add(CompanyProfile(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            legal_name=tenant.name,
            display_name=tenant.name,
            company_type="ENTERPRISE",
            profile_source="SEED_SCRIPT",
            verification_status="UNVERIFIED",
            source_references=[{"source": "LOCAL_TENANT"}],
            operating_geography={"country": "India"},
            crop_focus=[],
            service_model={"role": "Agri-OS local/default tenant"},
            config=payload,
            metadata_={"last_company_product_seed_pack": SEED_PACK},
            created_at=now_ts,
            updated_at=now_ts,
        ))
    return "created"


def record_product_audit(db, *, tenant_id: str, entity_type: str, entity_id: uuid.UUID, entity_code: str, action: str, after: dict[str, Any], actor_id: uuid.UUID | None, now_ts: datetime, apply: bool) -> None:
    if not apply:
        return
    db.add(ProductCatalogAuditEvent(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_code=entity_code,
        actor_id=actor_id,
        action=action,
        before_payload=None,
        after_payload=after,
        reason="Seed company/product starter catalog for Android/admin testing.",
        metadata_={"seed_pack": SEED_PACK},
        created_at=now_ts,
        updated_at=now_ts,
    ))


def seed_catalog(db, *, tenant_id: str, actor_id: uuid.UUID | None, apply: bool) -> dict[str, Any]:
    now_ts = datetime.now(timezone.utc)
    actions: dict[str, int] = {}
    warnings: list[str] = []

    category_defs = {
        "SEED": "Seed",
        "ORGANIC_MANURE": "Organic Manure",
        "BIOSTIMULANT": "Biostimulant",
    }
    categories: dict[str, InputCategory] = {}
    for code_value, name in category_defs.items():
        row, action = ensure_category(db, code_value=code_value, name=name, apply=apply, now_ts=now_ts)
        categories[code_value] = row
        actions[f"categories_{action}"] = actions.get(f"categories_{action}", 0) + 1

    manufacturers: dict[str, Manufacturer] = {}
    discovery_actions: dict[str, int] = {}
    for item in MANUFACTURER_SEEDS:
        row, action = ensure_manufacturer(db, item, apply=apply, now_ts=now_ts)
        manufacturers[item["code"]] = row
        actions[f"manufacturers_{action}"] = actions.get(f"manufacturers_{action}", 0) + 1
        discovery_action = upsert_discovery_candidate(db, item, tenant_id=tenant_id, apply=apply, now_ts=now_ts)
        discovery_actions[discovery_action] = discovery_actions.get(discovery_action, 0) + 1
        record_product_audit(
            db,
            tenant_id=tenant_id,
            entity_type="MANUFACTURER",
            entity_id=row.id,
            entity_code=item["code"],
            action=f"SEED_{action.upper()}_MANUFACTURER",
            after={"code": item["code"], "name": item["name"], "segments": item["segments"]},
            actor_id=actor_id,
            now_ts=now_ts,
            apply=apply,
        )

    inputs: dict[str, AgriculturalInput] = {row.code: row for row in db.query(AgriculturalInput).all()}
    for item in INPUT_SEEDS:
        row, action = ensure_input(db, item, categories, apply=apply, now_ts=now_ts)
        inputs[item["code"]] = row
        actions[f"inputs_{action}"] = actions.get(f"inputs_{action}", 0) + 1

    product_results = []
    for item in PRODUCT_SEEDS:
        if item["manufacturer"] not in manufacturers:
            warnings.append(f"Missing manufacturer {item['manufacturer']} for product {item['code']}")
            continue
        if item["input"] not in inputs:
            warnings.append(f"Missing input {item['input']} for product {item['code']}")
            continue
        row, product_action, package_action = ensure_product(db, item, manufacturers, inputs, apply=apply, now_ts=now_ts)
        actions[f"products_{product_action}"] = actions.get(f"products_{product_action}", 0) + 1
        actions[f"packages_{package_action}"] = actions.get(f"packages_{package_action}", 0) + 1
        product_results.append({
            "code": item["code"],
            "brand_name": item["brand"],
            "manufacturer_code": item["manufacturer"],
            "canonical_input_code": item["input"],
            "agriculture_type": item["class"],
            "input_origin": item["origin"],
            "product_action": product_action,
            "package_action": package_action,
        })
        record_product_audit(
            db,
            tenant_id=tenant_id,
            entity_type="PRODUCT",
            entity_id=row.id,
            entity_code=item["code"],
            action=f"SEED_{product_action.upper()}_PRODUCT",
            after=product_results[-1],
            actor_id=actor_id,
            now_ts=now_ts,
            apply=apply,
        )

    profile_action = update_default_company_profile(db, tenant_id=tenant_id, apply=apply, now_ts=now_ts)

    products_by_type: dict[str, int] = {}
    for row in product_results:
        products_by_type[row["agriculture_type"]] = products_by_type.get(row["agriculture_type"], 0) + 1

    return {
        "schema_version": "company_product_catalog_seed_result.v1",
        "mode": "APPLY" if apply else "DRY_RUN",
        "tenant_id": tenant_id,
        "seed_pack": SEED_PACK,
        "source_references": [SCREENER_SOURCE, TNAU_SEED_SOURCE],
        "actions": actions,
        "company_discovery_candidates": discovery_actions,
        "company_profile_action": profile_action,
        "manufacturer_count": len(MANUFACTURER_SEEDS),
        "input_seed_count": len(INPUT_SEEDS),
        "product_seed_count": len(product_results),
        "products_by_agriculture_type": products_by_type,
        "warnings": warnings,
        "organic_vs_natural_contract": {
            "organic": "Organic-compatible products may be external purchased inputs, but certification/evidence must be verified separately.",
            "natural": "Natural-farming inputs are tracked separately because they are commonly on-farm preparations or low-external-input practices.",
            "metadata_fields": ["agriculture_type", "input_origin", "farming_system_tags"],
        },
        "products": product_results,
        "next_actions": [
            "Review seeded companies in company discovery/admin before marking any as verified.",
            "Replace demo/reference products with manufacturer/regulator-verified product rows before production.",
            "Populate price/effective-date/package metadata once source-specific product lists are approved.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed company/manufacturer and representative product catalog metadata.")
    parser.add_argument("--tenant-id", default="default")
    parser.add_argument("--actor-id", type=uuid.UUID)
    parser.add_argument("--apply", action="store_true", help="Persist seed data. Default is dry-run.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = seed_catalog(db, tenant_id=args.tenant_id, actor_id=args.actor_id, apply=args.apply)
        if args.apply:
            db.commit()
        else:
            db.rollback()
        print(json.dumps(result, indent=2, sort_keys=True, default=str, ensure_ascii=False))
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

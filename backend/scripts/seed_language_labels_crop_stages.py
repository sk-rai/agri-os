#!/usr/bin/env python3
"""Seed Hindi aliases/labels for crop and lifecycle stage metadata.

Dry-run by default. Use --apply to write.

This improves Android/demo label coverage while keeping backend as the source
of truth for localized labels.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
from app.modules.master_data.models import Crop, CropLifecycleTemplate

CROP_HI = {
    "BAJRA": "बाजरा",
    "BANANA": "केला",
    "BOTTLE_GOURD": "लौकी",
    "CHILLI": "मिर्च",
    "COTTON": "कपास",
    "CUCUMBER": "खीरा",
    "FODDER_MAIZE": "चारा मक्का",
    "GRAM": "चना",
    "GROUNDNUT": "मूंगफली",
    "JUTE": "जूट",
    "LENTIL": "मसूर",
    "MAIZE": "मक्का",
    "MOONG": "मूंग",
    "MUSTARD": "सरसों",
    "ONION": "प्याज",
    "PIGEON_PEA": "अरहर",
    "POTATO": "आलू",
    "RAGI": "रागी",
    "RICE": "धान",
    "SESAME": "तिल",
    "SORGHUM": "ज्वार",
    "SOYBEAN": "सोयाबीन",
    "SUGARCANE": "गन्ना",
    "SUNFLOWER": "सूरजमुखी",
    "TOMATO": "टमाटर",
    "URAD": "उड़द",
    "WATERMELON": "तरबूज",
    "WHEAT": "गेहूं",
    "WORKLIST_RICE": "धान",
    "PROFILE_TEST_RICE": "धान",
}

STAGE_HI_BY_CODE = {
    "LAND_PREPARATION": "भूमि तैयारी",
    "NURSERY": "नर्सरी",
    "SOWING": "बुवाई",
    "TRANSPLANTING": "रोपाई",
    "GERMINATION": "अंकुरण",
    "VEGETATIVE": "वानस्पतिक वृद्धि",
    "TILLERING": "कल्ले निकलना",
    "GRAND_GROWTH": "तेज वृद्धि",
    "FLOWERING": "फूल आना",
    "POD_FORMATION": "फली बनना",
    "FRUITING": "फल बनना",
    "BOLL_FORMATION": "टिंडा बनना",
    "GRAIN_FILLING": "दाना भरना",
    "RIPENING": "पकना",
    "MATURITY": "परिपक्वता",
    "HARVEST": "कटाई",
    "HARVESTING": "कटाई",
    "RATOON": "रैटून प्रबंधन",
}

STAGE_HI_BY_NAME = {
    "land preparation": "भूमि तैयारी",
    "nursery": "नर्सरी",
    "sowing": "बुवाई",
    "transplanting": "रोपाई",
    "germination": "अंकुरण",
    "vegetative": "वानस्पतिक वृद्धि",
    "vegetative growth": "वानस्पतिक वृद्धि",
    "tillering": "कल्ले निकलना",
    "grand growth": "तेज वृद्धि",
    "flowering": "फूल आना",
    "pod formation": "फली बनना",
    "fruiting": "फल बनना",
    "boll formation": "टिंडा बनना",
    "grain filling": "दाना भरना",
    "ripening": "पकना",
    "maturity": "परिपक्वता",
    "harvest": "कटाई",
    "harvesting": "कटाई",
    "ratoon": "रैटून प्रबंधन",
}


def now():
    return datetime.now(timezone.utc)


def aliases_list(value):
    if isinstance(value, list):
        return list(value)
    return []


def has_lang_alias(aliases, lang: str) -> bool:
    return any(isinstance(item, dict) and item.get("lang") == lang for item in aliases)


def add_alias(aliases, lang: str, name: str, source: str) -> tuple[list, bool]:
    aliases = aliases_list(aliases)
    for item in aliases:
        if isinstance(item, dict) and item.get("lang") == lang:
            existing_name = item.get("name")
            if existing_name == name and item.get("source") == source:
                return aliases, False
            item["name"] = name
            item["source"] = source
            return aliases, True

    aliases.append({"lang": lang, "name": name, "source": source})
    return aliases, True


def stage_label(stage: dict) -> str | None:
    code = str(stage.get("stage_code") or stage.get("code") or "").upper()
    if code in STAGE_HI_BY_CODE:
        return STAGE_HI_BY_CODE[code]

    name = str(stage.get("stage_name") or stage.get("name") or "").strip().lower()
    if name in STAGE_HI_BY_NAME:
        return STAGE_HI_BY_NAME[name]

    return None


def seed_crops(db, dry_run: bool, result: dict):
    crops = db.query(Crop).filter(Crop.is_active == True).all()
    for crop in crops:
        result["crops_seen"] += 1
        hi = CROP_HI.get(crop.code)
        if not hi:
            result["crops_missing_seed_label"].append(crop.code)
            continue

        aliases = aliases_list(crop.aliases)
        if has_lang_alias(aliases, "hi"):
            result["crops_already_hindi"] += 1

        new_aliases, changed = add_alias(aliases, "hi", hi, "LOCAL_LANGUAGE_SEED")
        if changed:
            result["crops_updated"] += 1
            if not dry_run:
                crop.aliases = new_aliases
                crop.updated_at = now()


def seed_lifecycle_templates(db, dry_run: bool, result: dict):
    templates = db.query(CropLifecycleTemplate).filter(CropLifecycleTemplate.is_active == True).all()
    for template in templates:
        result["templates_seen"] += 1

        aliases = aliases_list(template.aliases)
        template_label = None
        crop = db.query(Crop).filter(Crop.id == template.crop_id).first()
        if crop and crop.code in CROP_HI:
            template_label = f"{CROP_HI[crop.code]} {template.season_code or ''}".strip()

        template_alias_changed = False
        if template_label:
            new_aliases, template_alias_changed = add_alias(
                aliases,
                "hi",
                template_label,
                "LOCAL_LANGUAGE_SEED",
            )

        stages = list(template.stages or [])
        stage_updates = 0
        for stage in stages:
            if not isinstance(stage, dict):
                continue
            hi = stage_label(stage)
            if not hi:
                result["stage_labels_missing_seed"].append(
                    {
                        "template_code": template.code,
                        "stage_code": stage.get("stage_code") or stage.get("code"),
                        "stage_name": stage.get("stage_name") or stage.get("name"),
                    }
                )
                continue

            labels = dict(stage.get("labels") or {})
            existing_hi = labels.get("hi")
            if existing_hi == hi:
                continue

            labels["hi"] = hi
            labels.setdefault("source", "LOCAL_LANGUAGE_SEED")
            stage["labels"] = labels
            stage_updates += 1

        if template_alias_changed or stage_updates:
            result["templates_updated"] += 1
            result["stage_labels_updated"] += stage_updates
            if not dry_run:
                if template_alias_changed:
                    template.aliases = new_aliases
                template.stages = stages
                template.updated_at = now()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    dry_run = not args.apply
    result = {
        "schema_version": "language_label_seed_result.v1",
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "crops_seen": 0,
        "crops_updated": 0,
        "crops_already_hindi": 0,
        "crops_missing_seed_label": [],
        "templates_seen": 0,
        "templates_updated": 0,
        "stage_labels_updated": 0,
        "stage_labels_missing_seed": [],
        "policy": {
            "source": "LOCAL_LANGUAGE_SEED",
            "android_hardcodes_labels": False,
            "advisory_translation_included": False,
            "advisory_translation_policy": "Advisories require reviewed content variants; this script seeds only metadata labels.",
        },
    }

    db = SessionLocal()
    try:
        seed_crops(db, dry_run, result)
        seed_lifecycle_templates(db, dry_run, result)

        if dry_run:
            db.rollback()
        else:
            db.commit()
    finally:
        db.close()

    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if result["crops_seen"] > 0 and result["templates_seen"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

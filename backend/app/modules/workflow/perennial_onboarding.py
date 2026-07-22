"""Perennial, plantation, spice, and agroforestry onboarding policy helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CropSystemDefinition:
    code: str
    label_en: str
    examples: list[str]
    allowed_start_stages: list[str]
    warning_rules: list[str]
    requires_establishment_year: bool = False
    supports_multi_year_cycle: bool = False


CROP_SYSTEM_REGISTRY: tuple[CropSystemDefinition, ...] = (
    CropSystemDefinition(
        code='ANNUAL_FIELD_CROP',
        label_en='Annual field crop',
        examples=['RICE', 'WHEAT', 'MAIZE', 'GRAM', 'MUSTARD'],
        allowed_start_stages=['PRE_FIELD', 'FIELD_ESTABLISHMENT', 'VEGETATIVE', 'REPRODUCTIVE', 'HARVEST'],
        warning_rules=['season_mismatch', 'geography_mismatch', 'stage_calendar_mismatch'],
    ),
    CropSystemDefinition(
        code='PERENNIAL_ORCHARD',
        label_en='Perennial orchard crop',
        examples=['MANGO', 'APPLE', 'CITRUS', 'GUAVA', 'POMEGRANATE'],
        allowed_start_stages=['ORCHARD_ESTABLISHMENT', 'VEGETATIVE_FLUSH', 'FLOWERING', 'FRUITING', 'HARVEST', 'DORMANCY'],
        warning_rules=['orchard_age_missing', 'stage_calendar_mismatch', 'geography_mismatch'],
        requires_establishment_year=True,
        supports_multi_year_cycle=True,
    ),
    CropSystemDefinition(
        code='PLANTATION_CROP',
        label_en='Plantation crop',
        examples=['TEA', 'COFFEE', 'COCONUT', 'ARECANUT', 'RUBBER'],
        allowed_start_stages=['NURSERY', 'PLANTING', 'ESTABLISHMENT', 'MAINTENANCE', 'FLUSH_OR_PICKING', 'HARVEST'],
        warning_rules=['plantation_age_missing', 'stage_calendar_mismatch', 'geography_mismatch'],
        requires_establishment_year=True,
        supports_multi_year_cycle=True,
    ),
    CropSystemDefinition(
        code='PERENNIAL_SPICE',
        label_en='Perennial spice crop',
        examples=['BLACK_PEPPER', 'CARDAMOM', 'CINNAMON', 'CLOVE'],
        allowed_start_stages=['NURSERY', 'PLANTING', 'ESTABLISHMENT', 'VEGETATIVE', 'FLOWERING', 'HARVEST'],
        warning_rules=['crop_system_mismatch', 'stage_calendar_mismatch', 'geography_mismatch'],
        requires_establishment_year=True,
        supports_multi_year_cycle=True,
    ),
    CropSystemDefinition(
        code='FLORICULTURE',
        label_en='Floriculture crop',
        examples=['MARIGOLD', 'ROSE', 'JASMINE', 'GLADIOLUS', 'CHRYSANTHEMUM'],
        allowed_start_stages=['NURSERY', 'TRANSPLANTING', 'VEGETATIVE', 'BUD_INITIATION', 'FLOWERING', 'PICKING_OR_HARVEST'],
        warning_rules=['crop_system_mismatch', 'stage_calendar_mismatch', 'geography_mismatch', 'market_window_mismatch'],
        requires_establishment_year=False,
        supports_multi_year_cycle=False,
    ),
    CropSystemDefinition(
        code='AGROFORESTRY_TIMBER',
        label_en='Agroforestry / timber crop',
        examples=['EUCALYPTUS', 'TEAK', 'POPLAR', 'MELIA_DUBIA'],
        allowed_start_stages=['NURSERY', 'PLANTING', 'ESTABLISHMENT', 'MAINTENANCE', 'THINNING', 'HARVEST'],
        warning_rules=['rotation_age_missing', 'stage_calendar_mismatch', 'geography_mismatch'],
        requires_establishment_year=True,
        supports_multi_year_cycle=True,
    ),
)


def list_crop_systems() -> list[dict]:
    return [definition.__dict__.copy() for definition in CROP_SYSTEM_REGISTRY]


def find_crop_system(code: str) -> Optional[CropSystemDefinition]:
    normalized = code.upper()
    for definition in CROP_SYSTEM_REGISTRY:
        if definition.code == normalized:
            return definition
    return None


def current_stage_onboarding_policy(*, crop_system: str, requested_stage: Optional[str] = None, establishment_year: Optional[int] = None) -> dict:
    definition = find_crop_system(crop_system)
    if not definition:
        return {
            'valid': False,
            'error_code': 'UNKNOWN_CROP_SYSTEM',
            'message': 'Unknown crop system. Android should refresh backend metadata before proceeding.',
        }
    warnings = []
    if definition.requires_establishment_year and not establishment_year:
        warnings.append({
            'code': 'ESTABLISHMENT_YEAR_RECOMMENDED',
            'message': 'Existing perennial/plantation/agroforestry crops should capture establishment year or approximate crop age.',
            'allow_override': True,
        })
    if requested_stage and requested_stage.upper() not in definition.allowed_start_stages:
        warnings.append({
            'code': 'STAGE_NOT_TYPICAL_FOR_CROP_SYSTEM',
            'message': 'Selected stage is not typical for this crop system. Confirm before continuing.',
            'allow_override': True,
        })
    return {
        'valid': True,
        'crop_system': definition.__dict__.copy(),
        'requested_stage': requested_stage.upper() if requested_stage else None,
        'warnings': warnings,
        'requires_confirmation': any(item.get('allow_override') for item in warnings),
    }


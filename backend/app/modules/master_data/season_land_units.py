"""Config-backed season and land-unit registry for Android/backend calculations."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class SeasonDefinition:
    code: str
    label_en: str
    label_hi: str
    typical_months: list[int]
    sort_order: int
    is_active: bool = True


@dataclass(frozen=True)
class LandUnitDefinition:
    code: str
    label_en: str
    label_hi: str
    category: str
    acres_per_unit: Optional[Decimal]
    hectares_per_unit: Optional[Decimal]
    geography_scope: str = 'ALL_INDIA'
    source: str = 'backend_config'
    is_active: bool = True


SEASON_REGISTRY: tuple[SeasonDefinition, ...] = (
    SeasonDefinition(code='KHARIF', label_en='Kharif', label_hi='खरीफ', typical_months=[6, 7, 8, 9, 10], sort_order=10),
    SeasonDefinition(code='RABI', label_en='Rabi', label_hi='रबी', typical_months=[11, 12, 1, 2, 3, 4], sort_order=20),
    SeasonDefinition(code='ZAID', label_en='Zaid', label_hi='ज़ैद', typical_months=[3, 4, 5, 6], sort_order=30),
    SeasonDefinition(code='PERENNIAL', label_en='Perennial / Orchard', label_hi='बारहमासी / बाग', typical_months=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12], sort_order=40),
)


LAND_UNIT_REGISTRY: tuple[LandUnitDefinition, ...] = (
    LandUnitDefinition(code='ACRE', label_en='Acre', label_hi='एकड़', category='canonical', acres_per_unit=Decimal('1'), hectares_per_unit=Decimal('0.40468564224')),
    LandUnitDefinition(code='HECTARE', label_en='Hectare', label_hi='हेक्टेयर', category='metric', acres_per_unit=Decimal('2.4710538147'), hectares_per_unit=Decimal('1')),
    LandUnitDefinition(code='BIGHA_UP_EAST', label_en='Bigha (UP East)', label_hi='बीघा (पूर्वी उत्तर प्रदेश)', category='local_variable', acres_per_unit=Decimal('0.625'), hectares_per_unit=Decimal('0.2529285264'), geography_scope='IN-UP-EAST'),
    LandUnitDefinition(code='BISWA_UP_EAST', label_en='Biswa (UP East)', label_hi='बिस्वा (पूर्वी उत्तर प्रदेश)', category='local_variable', acres_per_unit=Decimal('0.03125'), hectares_per_unit=Decimal('0.01264642632'), geography_scope='IN-UP-EAST'),
    LandUnitDefinition(code='BIGHA_UNSPECIFIED', label_en='Bigha (requires local conversion)', label_hi='बीघा (स्थानीय रूपांतरण आवश्यक)', category='local_variable_requires_scope', acres_per_unit=None, hectares_per_unit=None),
    LandUnitDefinition(code='BISWA_UNSPECIFIED', label_en='Biswa (requires local conversion)', label_hi='बिस्वा (स्थानीय रूपांतरण आवश्यक)', category='local_variable_requires_scope', acres_per_unit=None, hectares_per_unit=None),
)


def list_seasons() -> list[dict]:
    return [season.__dict__.copy() for season in sorted(SEASON_REGISTRY, key=lambda item: item.sort_order) if season.is_active]


def list_land_units(*, include_variable_placeholders: bool = True) -> list[dict]:
    rows = []
    for unit in LAND_UNIT_REGISTRY:
        if not unit.is_active:
            continue
        if not include_variable_placeholders and unit.acres_per_unit is None:
            continue
        rows.append({
            'code': unit.code,
            'label_en': unit.label_en,
            'label_hi': unit.label_hi,
            'category': unit.category,
            'acres_per_unit': str(unit.acres_per_unit) if unit.acres_per_unit is not None else None,
            'hectares_per_unit': str(unit.hectares_per_unit) if unit.hectares_per_unit is not None else None,
            'geography_scope': unit.geography_scope,
            'source': unit.source,
        })
    return rows


def normalize_area_to_acres(value: Decimal, unit_code: str) -> Optional[Decimal]:
    code = unit_code.upper()
    for unit in LAND_UNIT_REGISTRY:
        if unit.code == code and unit.acres_per_unit is not None:
            return value * unit.acres_per_unit
    return None


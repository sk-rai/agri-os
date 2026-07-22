#!/usr/bin/env python3
"""Regression for config-backed season and land-unit registry."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.master_data.season_land_units import list_land_units, list_seasons, normalize_area, normalize_area_to_acres


def check(condition, label, payload=None):
    if not condition:
        print(f'  FAIL {label}')
        if payload is not None:
            print(f'       {payload}')
        raise AssertionError(label)
    print(f'  PASS {label}')
    if payload is not None:
        print(f'       {payload}')


def main() -> int:
    seasons = list_seasons()
    season_codes = [row['code'] for row in seasons]
    check(season_codes[:3] == ['KHARIF', 'RABI', 'ZAID'], 'Core seasons are stable', season_codes)
    check('PERENNIAL' in season_codes, 'Perennial/orchard season is configurable', season_codes)

    units = list_land_units()
    unit_codes = [row['code'] for row in units]
    check('ACRE' in unit_codes, 'Acre unit is available')
    check('HECTARE' in unit_codes, 'Hectare unit is available')
    check('BIGHA_UNSPECIFIED' in unit_codes, 'Variable local bigha placeholder is available')
    check(normalize_area_to_acres(Decimal('2'), 'ACRE') == Decimal('2'), 'Acre normalization is identity')
    check(normalize_area_to_acres(Decimal('1'), 'HECTARE') == Decimal('2.4710538147'), 'Hectare converts to acres')
    check(normalize_area_to_acres(Decimal('1'), 'BIGHA_UNSPECIFIED') is None, 'Unscoped local unit refuses unsafe conversion')
    acre_result = normalize_area(Decimal('2'), 'ACRE')
    check(acre_result.conversion_status == 'CONVERTED', 'Area normalization returns converted status')
    check(acre_result.normalized_acres == Decimal('2'), 'Area normalization preserves acre value')
    bigha_result = normalize_area(Decimal('2'), 'BIGHA')
    check(bigha_result.conversion_status in {'REQUIRES_GEOGRAPHY_SCOPED_CONVERSION', 'UNSUPPORTED_UNIT'}, 'Area normalization blocks unsafe bigha conversion', bigha_result.to_dict())
    print('=' * 72)
    print('Season and land-unit registry validated')
    print('=' * 72)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

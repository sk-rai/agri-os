#!/usr/bin/env python3
"""Regression for perennial/current-stage onboarding policy."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.workflow.perennial_onboarding import current_stage_onboarding_policy, list_crop_systems


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
    systems = list_crop_systems()
    codes = [row['code'] for row in systems]
    check('PERENNIAL_ORCHARD' in codes, 'Orchard crop system is available', codes)
    check('PLANTATION_CROP' in codes, 'Plantation crop system is available', codes)
    check('PERENNIAL_SPICE' in codes, 'Perennial spice crop system is available', codes)
    check('AGROFORESTRY_TIMBER' in codes, 'Agroforestry timber crop system is available', codes)

    mango = current_stage_onboarding_policy(crop_system='PERENNIAL_ORCHARD', requested_stage='FRUITING')
    check(mango['valid'] is True, 'Mango/orchard can start at fruiting stage', mango)
    check(mango['requires_confirmation'] is True, 'Orchard missing establishment year asks confirmation', mango)

    tea = current_stage_onboarding_policy(crop_system='PLANTATION_CROP', requested_stage='FLUSH_OR_PICKING', establishment_year=2018)
    check(tea['valid'] is True, 'Tea/coffee style plantation can start at picking stage', tea)
    check(tea['requires_confirmation'] is False, 'Plantation with establishment year avoids unnecessary warning', tea)

    teak = current_stage_onboarding_policy(crop_system='AGROFORESTRY_TIMBER', requested_stage='FLOWERING', establishment_year=2020)
    check(teak['requires_confirmation'] is True, 'Agroforestry unusual stage asks confirmation', teak)
    check(any(w['code'] == 'STAGE_NOT_TYPICAL_FOR_CROP_SYSTEM' for w in teak['warnings']), 'Unusual agroforestry stage warning is explicit', teak)

    unknown = current_stage_onboarding_policy(crop_system='UNKNOWN_SYSTEM')
    check(unknown['valid'] is False and unknown['error_code'] == 'UNKNOWN_CROP_SYSTEM', 'Unknown crop system is rejected')

    print('=' * 72)
    print('Perennial onboarding policy validated')
    print('=' * 72)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

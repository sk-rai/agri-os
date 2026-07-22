#!/usr/bin/env python3
"""Read-only audit for global geography readiness and India compatibility coverage."""

from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.master_data.models.geography import GeographyState, GeographyDistrict, GeographyBlock, GeographyVillage


def active_count(db, model):
    return db.query(model).filter(model.is_active == True).count()


def main() -> int:
    db = SessionLocal()
    try:
        client = TestClient(app)
        profile_response = client.get('/api/v1/master-data/geography/hierarchy-profile')
        profile_ok = profile_response.status_code == 200
        profile = profile_response.json() if profile_ok else {'error': profile_response.text[:500]}
        states = active_count(db, GeographyState)
        districts = active_count(db, GeographyDistrict)
        blocks = active_count(db, GeographyBlock)
        villages = active_count(db, GeographyVillage)
        villages_with_pin_codes = db.query(GeographyVillage).filter(GeographyVillage.is_active == True, GeographyVillage.pin_codes.isnot(None)).count()
        payload = {
            'schema_version': 'global_geography_readiness_audit.v1',
            'hierarchy_profile_endpoint': {
                'status_code': profile_response.status_code,
                'healthy': profile_ok and profile.get('schema_version') == 'geography_hierarchy_profile.v1',
                'mode': profile.get('mode'),
                'level_codes': [row.get('level_code') for row in profile.get('levels', [])] if isinstance(profile.get('levels'), list) else [],
                'android_render_levels_from_backend': (profile.get('android_guidance') or {}).get('render_levels_from_backend_profile'),
                'canonical_fields_editable': (profile.get('governance') or {}).get('canonical_government_fields_editable'),
            },
            'current_india_compatibility_counts': {
                'states': states,
                'districts': districts,
                'blocks': blocks,
                'villages': villages,
                'villages_with_pin_codes': villages_with_pin_codes,
            },
            'global_model_readiness': {
                'generic_geo_entity_tables_present': False,
                'country_specific_level_profiles_present': False,
                'india_compatibility_api_stable': profile_ok,
                'needs_all_india_lgd_expansion': states < 36,
                'needs_generic_model_migration_before_global_rollout': True,
            },
            'next_actions': [
                'Keep India compatibility endpoints stable for Android MVP.',
                'Import/validate all-India LGD/Census coverage before claiming all-India readiness.',
                'Add generic geo_entity model only when multi-country rollout or non-India imports are scheduled.',
                'Expose country-specific hierarchy profiles before Android renders non-India geography.',
            ],
        }
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    finally:
        db.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

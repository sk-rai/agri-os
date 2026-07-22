#!/usr/bin/env python3
"""Read-only audit for season and land-unit metadata readiness."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
from app.modules.farmer.models import Parcel, Project
from app.modules.master_data.models.crop import Crop
from app.modules.workflow.models import CropCycle, WorkflowTemplate, WorkflowTemplateVersion


LOCAL_UNIT_HINTS = {
    'ACRE': {'canonical_acres': 1.0, 'metric_hectares': 0.40468564224, 'category': 'canonical'},
    'HECTARE': {'canonical_acres': 2.4710538147, 'metric_hectares': 1.0, 'category': 'metric'},
    'BIGHA': {'canonical_acres': None, 'metric_hectares': None, 'category': 'local_variable'},
    'BISWA': {'canonical_acres': None, 'metric_hectares': None, 'category': 'local_variable'},
    'KATTHA': {'canonical_acres': None, 'metric_hectares': None, 'category': 'local_variable'},
    'KANAL': {'canonical_acres': None, 'metric_hectares': None, 'category': 'local_variable'},
    'MARLA': {'canonical_acres': None, 'metric_hectares': None, 'category': 'local_variable'},
    'GUNTA': {'canonical_acres': None, 'metric_hectares': None, 'category': 'local_variable'},
}


def count_model(db, model):
    try:
        return db.query(model).count()
    except Exception as exc:
        return {'error': exc.__class__.__name__, 'message': str(exc)}


def main() -> int:
    db = SessionLocal()
    try:
        crops = db.query(Crop).all()
        projects = db.query(Project).all()
        parcels = db.query(Parcel).all()
        crop_cycles = db.query(CropCycle).all()
        templates = db.query(WorkflowTemplate).all()
        versions = db.query(WorkflowTemplateVersion).all()

        crop_seasons = Counter()
        crop_seasonless = []
        for crop in crops:
            seasons = getattr(crop, 'suitable_seasons', None) or []
            if not seasons:
                crop_seasonless.append(getattr(crop, 'code', None))
            for season in seasons:
                crop_seasons[str(season).upper()] += 1

        project_seasons = Counter()
        for project in projects:
            config = getattr(project, 'config', None) or {}
            for season in config.get('seasons', []) if isinstance(config, dict) else []:
                project_seasons[str(season).upper()] += 1

        parcel_units = Counter(str(getattr(parcel, 'reported_area_unit', None) or 'UNKNOWN').upper() for parcel in parcels)
        crop_cycle_seasons = Counter(str(getattr(cycle, 'season', None) or 'UNKNOWN').upper() for cycle in crop_cycles)

        payload = {
            'schema_version': 'season_land_unit_readiness_audit.v1',
            'counts': {
                'crops': len(crops),
                'projects': len(projects),
                'parcels': len(parcels),
                'crop_cycles': len(crop_cycles),
                'workflow_templates': len(templates),
                'workflow_versions': len(versions),
            },
            'season_readiness': {
                'crop_suitable_season_counts': dict(sorted(crop_seasons.items())),
                'crop_codes_without_suitable_seasons': sorted([x for x in crop_seasonless if x]),
                'project_config_season_counts': dict(sorted(project_seasons.items())),
                'crop_cycle_season_counts': dict(sorted(crop_cycle_seasons.items())),
                'expected_core_seasons': ['KHARIF', 'RABI', 'ZAID'],
                'needs_backend_configurable_season_registry': True,
            },
            'land_unit_readiness': {
                'parcel_reported_area_unit_counts': dict(sorted(parcel_units.items())),
                'known_unit_hints': LOCAL_UNIT_HINTS,
                'local_variable_units_need_geography_scope': ['BIGHA', 'BISWA', 'KATTHA', 'KANAL', 'MARLA', 'GUNTA'],
                'needs_backend_conversion_registry': True,
                'recommended_storage_contract': {
                    'persist_original_value_and_unit': True,
                    'persist_normalized_acres': True,
                    'persist_normalized_hectares': True,
                    'display_preferred_local_unit_from_backend': True,
                },
            },
            'next_actions': [
                'Add config-backed season registry before adding a table migration unless admin editing requires persistence.',
                'Add config-backed land-unit conversion registry with geography-scoped overrides for variable local units.',
                'Normalize parcel/crop-cycle/P&L calculations to acres/hectares while preserving original farmer-entered units.',
                'Expose preferred_display_unit in Android bootstrap/profile form options.',
            ],
        }
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    finally:
        db.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

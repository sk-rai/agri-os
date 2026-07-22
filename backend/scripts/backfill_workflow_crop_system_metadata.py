#!/usr/bin/env python3
"""Backfill crop-system/BBCH metadata on existing workflow templates and versions."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
from app.modules.workflow.models import WorkflowTemplate, WorkflowTemplateVersion


TEMPLATE_METADATA = {
    'RICE': {
        'crop_system': 'ANNUAL_FIELD_CROP',
        'bbch_baseline': {'enabled': True, 'scale': 'BBCH_CEREAL_RICE_ADAPTED'},
        'allowed_start_stages': ['NURSERY', 'TRANSPLANTING', 'VEGETATIVE', 'REPRODUCTIVE', 'MATURITY', 'HARVEST'],
        'supports_existing_crop_current_stage': True,
        'requires_establishment_year': False,
        'stage_warning_rules': ['season_mismatch', 'geography_mismatch', 'stage_calendar_mismatch'],
        'decision_nodes': [
            {
                'code': 'NURSERY_OR_DIRECT_SEEDED',
                'label': {'en': 'Nursery transplant or direct seeded?', 'hi': 'नर्सरी रोपाई या सीधी बुवाई?'},
                'stage_code': 'PRE_FIELD',
                'choices': ['NURSERY_TRANSPLANT', 'DIRECT_SEEDED'],
                'default_choice': 'NURSERY_TRANSPLANT',
                'allow_override': True,
            }
        ],
    },
    'SUGARCANE': {
        'crop_system': 'ANNUAL_FIELD_CROP',
        'bbch_baseline': {'enabled': True, 'scale': 'BBCH_SUGARCANE_ADAPTED'},
        'allowed_start_stages': ['FIELD_PREPARATION', 'PLANTING', 'TILLERING', 'GRAND_GROWTH', 'MATURITY', 'HARVEST'],
        'supports_existing_crop_current_stage': True,
        'requires_establishment_year': False,
        'stage_warning_rules': ['season_mismatch', 'geography_mismatch', 'stage_calendar_mismatch'],
        'decision_nodes': [
            {
                'code': 'RATOON_OR_NEW_CROP',
                'label': {'en': 'Keep ratoon crop or plant new crop?', 'hi': 'रैटून रखें या नई फसल लगाएं?'},
                'stage_code': 'HARVEST',
                'choices': ['KEEP_RATOON', 'NEW_CROP'],
                'default_choice': 'NEW_CROP',
                'allow_override': True,
            }
        ],
    },
}


def merge_metadata(existing: dict | None, patch: dict) -> tuple[dict, bool]:
    metadata = dict(existing or {})
    changed = False
    for key, value in patch.items():
        if metadata.get(key) != value:
            metadata[key] = value
            changed = True
    return metadata, changed


def main() -> int:
    db = SessionLocal()
    changed_templates = 0
    changed_versions = 0
    try:
        now = datetime.now(timezone.utc)
        for template in db.query(WorkflowTemplate).all():
            patch = TEMPLATE_METADATA.get(str(template.crop_code or '').upper())
            if not patch:
                continue
            metadata, changed = merge_metadata(template.metadata_, patch)
            if changed:
                metadata['metadata_backfill'] = 'workflow_crop_system_bbch.v1'
                metadata['metadata_backfilled_at'] = now.isoformat()
                template.metadata_ = metadata
                template.updated_at = now
                changed_templates += 1

            for version in db.query(WorkflowTemplateVersion).filter(WorkflowTemplateVersion.template_id == template.id).all():
                version_metadata, version_changed = merge_metadata(version.metadata_, patch)
                if version_changed:
                    version_metadata['metadata_backfill'] = 'workflow_crop_system_bbch.v1'
                    version_metadata['metadata_backfilled_at'] = now.isoformat()
                    version.metadata_ = version_metadata
                    version.updated_at = now
                    changed_versions += 1

        db.commit()
        print(f'changed_templates={changed_templates}')
        print(f'changed_versions={changed_versions}')
    finally:
        db.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

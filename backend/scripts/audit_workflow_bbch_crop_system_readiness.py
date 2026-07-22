#!/usr/bin/env python3
"""Read-only audit for workflow BBCH and crop-system metadata readiness."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
from app.modules.workflow.models import WorkflowTemplate, WorkflowTemplateVersion, WorkflowTemplateStage, WorkflowTemplateRecommendation


RECOMMENDED_TEMPLATE_METADATA_KEYS = [
    'crop_system',
    'bbch_baseline',
    'allowed_start_stages',
    'supports_existing_crop_current_stage',
    'requires_establishment_year',
    'stage_warning_rules',
    'decision_nodes',
]


def has_nonempty(value) -> bool:
    return value not in (None, '', [], {})


def main() -> int:
    db = SessionLocal()
    try:
        templates = db.query(WorkflowTemplate).all()
        versions = db.query(WorkflowTemplateVersion).all()
        stages = db.query(WorkflowTemplateStage).all()
        recs = db.query(WorkflowTemplateRecommendation).all()

        stage_type_counts = Counter(str(stage.stage_type or 'UNKNOWN').upper() for stage in stages)
        stages_with_bbch = [stage for stage in stages if has_nonempty(stage.bbch_range)]
        propagation_steps = [stage for stage in stages if bool(stage.propagation_step)]

        template_metadata_key_counts = Counter()
        version_metadata_key_counts = Counter()
        missing_template_keys = []

        for template in templates:
            metadata = getattr(template, 'metadata_', None) or {}
            for key in metadata.keys():
                template_metadata_key_counts[str(key)] += 1
            missing = [key for key in RECOMMENDED_TEMPLATE_METADATA_KEYS if key not in metadata]
            if missing:
                missing_template_keys.append({
                    'template_id': str(template.id),
                    'crop_code': getattr(template, 'crop_code', None),
                    'season_code': getattr(template, 'season_code', None),
                    'propagation_type_code': getattr(template, 'propagation_type_code', None),
                    'missing_keys': missing,
                })

        for version in versions:
            metadata = getattr(version, 'metadata_', None) or {}
            for key in metadata.keys():
                version_metadata_key_counts[str(key)] += 1

        recommendation_cost_count = sum(1 for rec in recs if getattr(rec, 'typical_cost_per_acre', None) is not None)
        decision_like_recs = [
            rec for rec in recs
            if 'decision' in str(getattr(rec, 'activity_type', '')).lower()
            or 'decision' in str(getattr(rec, 'input_name', '')).lower()
            or 'ratoon' in str(getattr(rec, 'input_name', '')).lower()
        ]

        payload = {
            'schema_version': 'workflow_bbch_crop_system_readiness_audit.v1',
            'counts': {
                'templates': len(templates),
                'versions': len(versions),
                'stages': len(stages),
                'recommendations': len(recs),
                'stages_with_bbch_range': len(stages_with_bbch),
                'propagation_step_stages': len(propagation_steps),
                'recommendations_with_cost_per_acre': recommendation_cost_count,
                'decision_like_recommendations': len(decision_like_recs),
            },
            'stage_type_counts': dict(sorted(stage_type_counts.items())),
            'template_metadata_key_counts': dict(sorted(template_metadata_key_counts.items())),
            'version_metadata_key_counts': dict(sorted(version_metadata_key_counts.items())),
            'missing_recommended_template_metadata': missing_template_keys[:50],
            'decision_like_recommendations': [
                {
                    'id': str(rec.id),
                    'stage_id': str(rec.template_stage_id),
                    'activity_type': rec.activity_type,
                    'input_name': rec.input_name,
                    'typical_cost_per_acre': str(rec.typical_cost_per_acre) if rec.typical_cost_per_acre is not None else None,
                }
                for rec in decision_like_recs[:25]
            ],
            'readiness': {
                'bbch_baseline_present': len(stages_with_bbch) > 0,
                'cost_metadata_present': recommendation_cost_count == len(recs) if recs else False,
                'formal_decision_node_metadata_present': any('decision_nodes' in (getattr(template, 'metadata_', None) or {}) for template in templates),
                'crop_system_metadata_present': any('crop_system' in (getattr(template, 'metadata_', None) or {}) for template in templates),
            },
            'next_actions': [
                'Backfill crop_system and bbch_baseline metadata on workflow templates/versions.',
                'Add formal decision_nodes metadata for ratoon/new-crop, nursery/direct-seeded, and keep/replant orchard choices.',
                'Expose crop-system metadata in workflow CSV template/export/import validation.',
                'Keep admin edits audit logged and versioned through draft/publish flow.',
            ],
        }
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    finally:
        db.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

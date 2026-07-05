"""Seed versioned workflow templates from existing crop lifecycle templates.

This is the bridge from the legacy crop_lifecycle_templates.stages JSONB model to
normalized workflow_templates / versions / stages / recommendations.

Usage:
    cd backend && source ../venv/bin/activate
    PYTHONPATH=. python3 scripts/seed_workflow_templates.py
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.modules.master_data.models import CropLifecycleTemplate
from app.modules.workflow.models import (
    WorkflowTemplate,
    WorkflowTemplateVersion,
    WorkflowTemplateStage,
    WorkflowTemplateRecommendation,
)


def now():
    return datetime.now(timezone.utc)


def normalize_name(value):
    if isinstance(value, dict):
        return value
    return {"en": str(value or ""), "hi": str(value or "")}


def infer_propagation_type(crop_code: str, metadata: dict) -> str | None:
    existing = metadata.get("propagation_method") if isinstance(metadata, dict) else None
    if existing:
        return str(existing).upper()
    if crop_code == "RICE":
        return "NURSERY_TRANSPLANT" if metadata.get("has_nursery") else "DIRECT_SEEDED"
    if crop_code == "SUGARCANE":
        return "VEGETATIVE_SETT"
    return None


def parse_cost(value):
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def upsert_versioned_template(db: Session, legacy: CropLifecycleTemplate) -> tuple[int, int]:
    crop = legacy.crop
    if not crop:
        return 0, 0

    metadata = legacy.aliases if isinstance(legacy.aliases, dict) else {}
    workflow_code = f"WF_{legacy.code}"
    template = (
        db.query(WorkflowTemplate)
        .filter(WorkflowTemplate.tenant_id == "default", WorkflowTemplate.code == workflow_code)
        .first()
    )
    if not template:
        template = WorkflowTemplate(
            id=uuid.uuid4(),
            tenant_id="default",
            code=workflow_code,
            created_at=now(),
            updated_at=now(),
        )
        db.add(template)

    template.crop_id = crop.id
    template.crop_code = crop.code
    template.season_code = legacy.season_code
    template.propagation_type_code = infer_propagation_type(crop.code, metadata)
    template.canonical_name = legacy.canonical_name
    template.description = legacy.description
    template.is_default = bool(legacy.is_default)
    template.lifecycle_template_id = legacy.id
    template.metadata_ = metadata
    template.is_active = True
    template.updated_at = now()

    version = (
        db.query(WorkflowTemplateVersion)
        .filter(
            WorkflowTemplateVersion.template_id == template.id,
            WorkflowTemplateVersion.version_number == "1.0.0",
        )
        .first()
    )
    if not version:
        version = WorkflowTemplateVersion(
            id=uuid.uuid4(),
            template_id=template.id,
            version_number="1.0.0",
            created_at=now(),
            updated_at=now(),
        )
        db.add(version)
        db.flush()

    existing_stages = (
        db.query(WorkflowTemplateStage)
        .filter(WorkflowTemplateStage.template_version_id == version.id)
        .all()
    )
    if existing_stages:
        stage_ids = [stage.id for stage in existing_stages]
        db.query(WorkflowTemplateRecommendation).filter(
            WorkflowTemplateRecommendation.template_stage_id.in_(stage_ids)
        ).delete(synchronize_session=False)
        db.query(WorkflowTemplateStage).filter(
            WorkflowTemplateStage.template_version_id == version.id
        ).delete(synchronize_session=False)
        db.flush()

    stages = legacy.stages or []
    total_duration = 0
    recommendation_count = 0
    for index, stage_def in enumerate(stages, start=1):
        duration = int(stage_def.get("duration_days") or 0)
        total_duration += duration
        stage = WorkflowTemplateStage(
            id=uuid.uuid4(),
            template_version_id=version.id,
            stage_code=stage_def.get("code"),
            stage_name=normalize_name(stage_def.get("name")),
            stage_order=int(stage_def.get("order") or index),
            duration_days=duration,
            stage_type=stage_def.get("stage_type"),
            phase=stage_def.get("phase"),
            bbch_range=stage_def.get("bbch_range"),
            propagation_step=bool(stage_def.get("propagation_step", False)),
            description=stage_def.get("description"),
            farmer_actions=stage_def.get("farmer_actions", []),
            typical_inputs=stage_def.get("typical_inputs", []),
            key_observations=stage_def.get("key_observations", []),
            icon=stage_def.get("icon"),
            color=stage_def.get("color"),
            metadata_=stage_def.get("metadata", {}),
            created_at=now(),
            updated_at=now(),
        )
        db.add(stage)
        db.flush()

        for rec_order, rec in enumerate(stage_def.get("recommended_activities", []) or [], start=1):
            db.add(WorkflowTemplateRecommendation(
                id=uuid.uuid4(),
                template_stage_id=stage.id,
                sort_order=rec_order,
                day_offset=int(rec.get("day_offset") or 0),
                activity_type=(rec.get("activity_type") or "OTHER").upper(),
                input_code=rec.get("input_code"),
                input_name=rec.get("input_name") or "Activity",
                typical_quantity=rec.get("typical_quantity"),
                typical_cost_per_acre=parse_cost(rec.get("typical_cost_per_acre")),
                is_critical=bool(rec.get("is_critical", False)),
                description=rec.get("description"),
                metadata_=rec.get("metadata", {}),
                created_at=now(),
                updated_at=now(),
            ))
            recommendation_count += 1

    version.status = "PUBLISHED"
    version.total_duration_days = total_duration
    version.schema_version = "1.0.0"
    version.metadata_ = metadata
    version.published_at = version.published_at or now()
    version.is_active = True
    version.updated_at = now()

    return len(stages), recommendation_count


def seed_workflow_templates():
    db = SessionLocal()
    try:
        templates = (
            db.query(CropLifecycleTemplate)
            .filter(CropLifecycleTemplate.code.in_(["RICE_KHARIF_DEFAULT", "SUGARCANE_DEFAULT"]))
            .all()
        )
        if not templates:
            print("No Rice/Sugarcane lifecycle templates found")
            return

        total_stages = 0
        total_recommendations = 0
        for legacy in templates:
            stages, recommendations = upsert_versioned_template(db, legacy)
            total_stages += stages
            total_recommendations += recommendations
            print(f"Seeded {legacy.code}: stages={stages}, recommendations={recommendations}")
        db.commit()
        print(f"Seeded workflow templates={len(templates)}, stages={total_stages}, recommendations={total_recommendations}")
    finally:
        db.close()


if __name__ == "__main__":
    seed_workflow_templates()

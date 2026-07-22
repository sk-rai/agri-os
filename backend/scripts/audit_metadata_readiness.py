#!/usr/bin/env python3
"""Read-only metadata readiness audit for pre-Android scenario coverage."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
from app.modules.master_data.models.crop import Crop, CropCategory, CropTaxonomyNode, CropPropagationType
from app.modules.master_data.models.geography import GeographyState, GeographyDistrict, GeographyBlock, GeographyVillage
from app.modules.master_data.models.input import AgriculturalInput, AgriculturalProduct, InputCategory, Manufacturer
from app.modules.workflow.models import WorkflowTemplate, WorkflowTemplateVersion, WorkflowTemplateStage, WorkflowTemplateRecommendation


def count(db, model):
    try:
        return db.query(model).count()
    except Exception as exc:
        return {"error": exc.__class__.__name__, "message": str(exc)}


def active_count(db, model):
    try:
        if hasattr(model, "is_active"):
            return db.query(model).filter(model.is_active == True).count()
        return db.query(model).count()
    except Exception as exc:
        return {"error": exc.__class__.__name__, "message": str(exc)}


def geography_audit(db):
    return {
        "states": active_count(db, GeographyState),
        "districts": active_count(db, GeographyDistrict),
        "blocks": active_count(db, GeographyBlock),
        "villages": active_count(db, GeographyVillage),
        "villages_with_pin_codes": db.query(GeographyVillage).filter(GeographyVillage.pin_codes.isnot(None)).count(),
        "states_with_lgd_code": db.query(GeographyState).filter(GeographyState.lgd_code.isnot(None)).count(),
        "districts_with_lgd_code": db.query(GeographyDistrict).filter(GeographyDistrict.lgd_code.isnot(None)).count(),
    }


def crop_audit(db):
    crops = db.query(Crop).all()
    season_counts = Counter()
    crop_codes = []
    for crop in crops:
        crop_codes.append(crop.code)
        for season in crop.suitable_seasons or []:
            season_counts[str(season).upper()] += 1
    return {
        "categories": active_count(db, CropCategory),
        "taxonomy_nodes": active_count(db, CropTaxonomyNode),
        "propagation_types": active_count(db, CropPropagationType),
        "crops": len(crops),
        "crop_codes": sorted(crop_codes),
        "season_counts": dict(sorted(season_counts.items())),
        "scenario_target_minimum_crops": 15,
        "scenario_target_met": len(crops) >= 15,
    }


def input_provider_audit(db):
    return {
        "input_categories": active_count(db, InputCategory),
        "agricultural_inputs": active_count(db, AgriculturalInput),
        "manufacturers": active_count(db, Manufacturer),
        "agricultural_products": active_count(db, AgriculturalProduct),
    }


def workflow_audit(db):
    stage_type_counts = Counter()
    stages = db.query(WorkflowTemplateStage).all()
    for stage in stages:
        stage_type_counts[str(stage.stage_type or "UNKNOWN").upper()] += 1
    recommendation_cost_count = db.query(WorkflowTemplateRecommendation).filter(WorkflowTemplateRecommendation.typical_cost_per_acre.isnot(None)).count()
    return {
        "templates": active_count(db, WorkflowTemplate),
        "versions": active_count(db, WorkflowTemplateVersion),
        "stages": len(stages),
        "stage_type_counts": dict(sorted(stage_type_counts.items())),
        "recommendations": active_count(db, WorkflowTemplateRecommendation),
        "recommendations_with_cost_per_acre": recommendation_cost_count,
        "needs_decision_node_audit": True,
        "needs_profit_loss_summary_contract": True,
    }


def main() -> int:
    db = SessionLocal()
    try:
        payload = {
            "schema_version": "metadata_readiness_audit.v1",
            "geography": geography_audit(db),
            "crops": crop_audit(db),
            "inputs_and_providers": input_provider_audit(db),
            "workflows": workflow_audit(db),
            "next_actions": [
                "Import/audit all-India LGD geography coverage.",
                "Build crop scenario seed pack covering at least 15 crops.",
                "Audit local land unit conversion registry.",
                "Add workflow decision-node and perennial/orchard current-stage onboarding contracts.",
                "Add stage cost and harvest P&L summary contract.",
                "Build advisory/broadcast seed content pack.",
            ],
        }
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

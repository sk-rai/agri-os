"""Regression for versioned crop workflow templates.

Verifies that published workflow_template rows back the existing Android-facing
crop template API without changing the response shape Android consumes.
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.modules.workflow.models import (
    WorkflowTemplate,
    WorkflowTemplateVersion,
    WorkflowTemplateStage,
    WorkflowTemplateRecommendation,
)

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"


def check(condition, label, detail=None):
    icon = f"{GREEN}✅{RESET}" if condition else f"{RED}❌{RESET}"
    print(f"  {icon} {label}")
    if detail is not None:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(label)


def db_counts(code: str):
    db = SessionLocal()
    try:
        template = db.query(WorkflowTemplate).filter(
            WorkflowTemplate.code == code,
            WorkflowTemplate.tenant_id == "default",
            WorkflowTemplate.is_active == True,
        ).first()
        check(template is not None, f"{code} workflow template exists")
        version = db.query(WorkflowTemplateVersion).filter(
            WorkflowTemplateVersion.template_id == template.id,
            WorkflowTemplateVersion.status == "PUBLISHED",
            WorkflowTemplateVersion.is_active == True,
        ).first()
        check(version is not None, f"{code} has a published version")
        stages = db.query(WorkflowTemplateStage).filter(
            WorkflowTemplateStage.template_version_id == version.id,
            WorkflowTemplateStage.is_active == True,
        ).all()
        recs = db.query(WorkflowTemplateRecommendation).filter(
            WorkflowTemplateRecommendation.template_stage_id.in_([s.id for s in stages]),
            WorkflowTemplateRecommendation.is_active == True,
        ).all()
        return template, version, stages, recs
    finally:
        db.close()


def assert_template_api(client: TestClient, crop: str, expected_stage: str, min_recs: int):
    response = client.get(f"/api/v1/crop-cycles/templates/{crop}?season=KHARIF")
    check(response.status_code == 200, f"{crop} template API returns 200", f"Status: {response.status_code}")
    payload = response.json()
    check(payload.get("template_source") == "workflow_template", f"{crop} template is served from workflow tables")
    check(payload.get("workflow_template_id") is not None, f"{crop} includes workflow_template_id")
    check("stages" in payload and payload["stages"], f"{crop} keeps legacy stages array")
    stage_codes = [stage["code"] for stage in payload["stages"]]
    check(expected_stage in stage_codes, f"{crop} includes {expected_stage} stage")
    rec_count = sum(len(stage.get("recommended_activities") or []) for stage in payload["stages"])
    check(rec_count >= min_recs, f"{crop} recommendations preserved", f"Recommendations: {rec_count}")
    first_stage = payload["stages"][0]
    for key in ["code", "name", "order", "day_offset", "duration_days", "recommended_activities"]:
        check(key in first_stage, f"{crop} stage keeps Android field '{key}'")


def main():
    print("=" * 72)
    print("VERSIONED WORKFLOW TEMPLATE REGRESSION")
    print("=" * 72)

    print("\n[1] Database seed state")
    _, _, rice_stages, rice_recs = db_counts("WF_RICE_KHARIF_DEFAULT")
    check(len(rice_stages) >= 6, "Rice has seeded workflow stages", f"Stages: {len(rice_stages)}")
    check(len(rice_recs) >= 24, "Rice has seeded workflow recommendations", f"Recommendations: {len(rice_recs)}")
    _, _, cane_stages, cane_recs = db_counts("WF_SUGARCANE_DEFAULT")
    check(len(cane_stages) >= 6, "Sugarcane has seeded workflow stages", f"Stages: {len(cane_stages)}")
    check(len(cane_recs) >= 26, "Sugarcane has seeded workflow recommendations", f"Recommendations: {len(cane_recs)}")

    print("\n[2] Existing Android template API contract")
    client = TestClient(app)
    assert_template_api(client, "RICE", "TRANSPLANTING", 24)
    assert_template_api(client, "SUGARCANE", "GRAND_GROWTH", 26)

    print("\n" + "=" * 72)
    print("🟢 Versioned workflow templates validated")
    print("=" * 72)


if __name__ == "__main__":
    main()

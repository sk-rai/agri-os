"""Regression for agricultural input catalog and workflow recommendation mapping."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.modules.workflow.models import WorkflowTemplateRecommendation

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


def main():
    print("=" * 72)
    print("INPUT CATALOG / WORKFLOW MAPPING REGRESSION")
    print("=" * 72)

    client = TestClient(app)

    print("\n[1] Input categories API")
    categories_response = client.get("/api/v1/input-catalog/categories")
    check(categories_response.status_code == 200, "Categories endpoint returns 200", f"Status: {categories_response.status_code}")
    category_codes = {c["code"] for c in categories_response.json()["categories"]}
    for code in ["SEED", "FERTILIZER", "ORGANIC_MANURE", "FUNGICIDE", "HERBICIDE", "LABOR", "MACHINERY", "IRRIGATION"]:
        check(code in category_codes, f"Category includes {code}")

    print("\n[2] Input search/filter API")
    fertilizer_response = client.get("/api/v1/input-catalog/inputs?category=FERTILIZER&crop_code=RICE")
    check(fertilizer_response.status_code == 200, "Fertilizer filter returns 200", f"Status: {fertilizer_response.status_code}")
    fertilizer_codes = {i["code"] for i in fertilizer_response.json()["inputs"]}
    check("UREA_46_N" in fertilizer_codes, "Rice fertilizer filter includes Urea")
    check("DAP_18_46_0" in fertilizer_codes, "Rice fertilizer filter includes DAP")

    urea_response = client.get("/api/v1/input-catalog/inputs/UREA_46_N")
    check(urea_response.status_code == 200, "Input detail returns 200", f"Status: {urea_response.status_code}")
    urea = urea_response.json()
    check(urea["canonical_name"] == "Urea", "Input detail returns canonical name")
    check("RICE" in urea["applicable_crops"], "Input detail includes applicable crop")

    print("\n[3] Workflow recommendation mapping")
    db = SessionLocal()
    try:
        total = db.query(WorkflowTemplateRecommendation).count()
        mapped = db.query(WorkflowTemplateRecommendation).filter(WorkflowTemplateRecommendation.input_code.isnot(None)).count()
        check(total >= 50, "Workflow recommendations exist", f"Total: {total}")
        check(mapped >= 50, "Workflow recommendations have input_code mappings", f"Mapped: {mapped}")
    finally:
        db.close()

    rice_template = client.get("/api/v1/crop-cycles/templates/RICE?season=KHARIF")
    check(rice_template.status_code == 200, "Rice template returns 200", f"Status: {rice_template.status_code}")
    recommendations = [
        rec
        for stage in rice_template.json()["stages"]
        for rec in stage.get("recommended_activities", [])
    ]
    check(any(rec.get("input_code") == "UREA_46_N" for rec in recommendations), "Rice template recommendations include UREA_46_N")
    check(any(rec.get("input_code") == "FYM_COMPOST" for rec in recommendations), "Rice template recommendations include FYM_COMPOST")

    sugar_template = client.get("/api/v1/crop-cycles/templates/SUGARCANE?season=KHARIF")
    check(sugar_template.status_code == 200, "Sugarcane template returns 200", f"Status: {sugar_template.status_code}")
    sugar_recs = [
        rec
        for stage in sugar_template.json()["stages"]
        for rec in stage.get("recommended_activities", [])
    ]
    check(any(rec.get("input_code") == "HEALTHY_CANE_SETTS" for rec in sugar_recs), "Sugarcane recommendations include cane sett input code")
    check(any(rec.get("input_code") == "IRRIGATION_MOISTURE" for rec in sugar_recs), "Sugarcane recommendations include irrigation input code")

    print("\n" + "=" * 72)
    print("🟢 Input catalog and recommendation mappings validated")
    print("=" * 72)


if __name__ == "__main__":
    main()

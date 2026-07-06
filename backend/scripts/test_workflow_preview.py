"""Regression for read-only workflow preview endpoint."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app

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
    print("WORKFLOW PREVIEW REGRESSION")
    print("=" * 72)

    client = TestClient(app)
    headers = {"X-Tenant-ID": "default"}

    catalog = client.get("/api/v1/workflow-catalog/enabled-crop-workflows", headers=headers)
    check(catalog.status_code == 200, "Enabled workflow catalog returns 200", f"Status: {catalog.status_code}")
    workflows = catalog.json()["workflows"]
    rice = next((workflow for workflow in workflows if workflow["crop_code"] == "RICE"), None)
    check(rice is not None, "Catalog includes Rice workflow")

    preview = client.get(
        f"/api/v1/workflow-catalog/workflow-preview/{rice['workflow_template_version_id']}",
        headers=headers,
    )
    check(preview.status_code == 200, "Preview endpoint returns 200", f"Status: {preview.status_code}")
    payload = preview.json()
    check(payload["workflow_template_version_id"] == rice["workflow_template_version_id"], "Preview is for requested version")
    check("android_preview" in payload, "Preview includes android_preview")
    check(len(payload["android_preview"]["stages"]) >= 6, "Android preview includes stages")
    recs = [
        rec
        for stage in payload["android_preview"]["stages"]
        for rec in stage.get("recommended_activities", [])
    ]
    check(any(rec.get("input_code") == "UREA_46_N" for rec in recs), "Preview includes mapped input codes")
    check(isinstance(payload.get("warnings"), list), "Preview includes warnings list")
    check(isinstance(payload.get("applied_overrides"), list), "Preview includes applied overrides list")

    print("\n" + "=" * 72)
    print("🟢 Workflow preview validated")
    print("=" * 72)


if __name__ == "__main__":
    main()

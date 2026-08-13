"""Verify FPO project search/filter/drill-down contracts for Android/admin smoke."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Parcel
from app.modules.workflow.models import CropCycle, CropStageInstance
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin
from scripts.prepare_android_fpo_multi_village_workflow import FARMERS, PROJECT_ID, TENANT_ID, farmer_id


def check(condition: bool, label: str, detail=None) -> None:
    print(f"{'PASS' if condition else 'FAIL'} {label}")
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str) if not isinstance(detail, str) else detail)
    if not condition:
        raise AssertionError(label)


def get_json(client: TestClient, path: str, headers: dict) -> dict:
    response = client.get(path, headers=headers)
    check(response.status_code == 200, f"GET {path} returns 200", response.text[:900])
    return response.json()


def enrollment_report(client: TestClient, headers: dict, query: str) -> dict:
    return get_json(
        client,
        f"/api/v1/reports/project-enrollments?project_id={PROJECT_ID}&status=ACTIVE&q={query}&limit=100",
        headers,
    )


def verify_admin_search(client: TestClient, headers: dict) -> dict:
    rampur = enrollment_report(client, headers, "Rampur")
    check(rampur["summary"]["count"] == 3, "Enrollment search by village returns Rampur farmers", rampur["enrollments"])
    check({row["village"] for row in rampur["enrollments"]} == {"FPO Rampur"}, "Rampur search rows are village scoped")

    rice = enrollment_report(client, headers, "Rice")
    check(rice["summary"]["count"] == 4, "Enrollment search by farmer/crop label returns Rice farmers", rice["enrollments"])
    check(all("Rice" in row["farmer_name"] for row in rice["enrollments"]), "Rice search rows match farmer labels")

    source = enrollment_report(client, headers, "FPO_AFFILIATED_FARMER_LIST")
    check(source["summary"]["count"] == len(FARMERS), "Enrollment source search returns all FPO-affiliated farmers")

    exact_mobile = enrollment_report(client, headers, "+919900002106")
    check(exact_mobile["summary"]["count"] == 1, "Enrollment search by mobile returns one farmer", exact_mobile["enrollments"])
    check(exact_mobile["enrollments"][0]["farmer_name"] == "FPO Farmer 06 Maize", "Mobile search opens Maize farmer")
    return {
        "rampur_count": rampur["summary"]["count"],
        "rice_count": rice["summary"]["count"],
        "source_count": source["summary"]["count"],
        "mobile_farmer": exact_mobile["enrollments"][0],
    }


def verify_project_trace_drilldown(client: TestClient, headers: dict) -> dict:
    rice_trace = get_json(client, f"/api/v1/reports/projects/{PROJECT_ID}/trace?crop_code=RICE&limit=100", headers)
    check(rice_trace["summary"]["crop_cycle_count"] == 4, "Project trace crop filter returns 4 Rice crop cycles", rice_trace["summary"])
    check({row["crop_code"] for row in rice_trace["crop_cycles"]} == {"RICE"}, "Rice trace crop cycles are filtered")

    wheat_trace = get_json(client, f"/api/v1/reports/projects/{PROJECT_ID}/trace?crop_code=WHEAT&cycle_status=COMPLETED&limit=100", headers)
    check(wheat_trace["summary"]["crop_cycle_count"] == 1, "Project trace crop+status drill-down returns completed Wheat cycle", wheat_trace["summary"])
    check(wheat_trace["crop_cycles"][0]["status"] == "COMPLETED", "Completed Wheat cycle status is preserved")

    maize_farmer = farmer_id(6)
    farmer_trace = get_json(client, f"/api/v1/reports/projects/{PROJECT_ID}/trace?farmer_id={maize_farmer}&limit=100", headers)
    check(farmer_trace["summary"]["farmer_count"] == 12, "Project trace keeps project farmer summary while filtering cycles")
    check(farmer_trace["summary"]["crop_cycle_count"] == 1, "Farmer drill-down returns one crop cycle")
    selected_farmers = [row for row in farmer_trace.get("farmers", []) if row.get("id") == str(maize_farmer)]
    check(len(selected_farmers) == 1, "Farmer drill-down context includes selected farmer")
    check(selected_farmers[0].get("crop_cycle_count") == 1, "Selected farmer carries one filtered crop cycle in trace context", selected_farmers[0])
    return {
        "rice_cycle_count": rice_trace["summary"]["crop_cycle_count"],
        "completed_wheat_cycle_count": wheat_trace["summary"]["crop_cycle_count"],
        "maize_farmer_cycle_id": farmer_trace["crop_cycles"][0]["id"],
        "maize_farmer_id": str(maize_farmer),
    }


def verify_android_visible_drilldown(client: TestClient) -> dict:
    headers = {"X-Tenant-ID": TENANT_ID}
    n, mobile, crop, *_ = FARMERS[5]
    selected_farmer_id = farmer_id(n)
    hydration = get_json(client, f"/api/v1/farmers/by-mobile/{mobile}?include_form_contract=true&project_id={PROJECT_ID}", headers)
    check(hydration["farmer"]["id"] == str(selected_farmer_id), "Android hydration opens selected FPO farmer")
    check(hydration["farmer_context"]["mode"] == "PROJECT", "Selected FPO farmer remains in project context")
    cycles = get_json(client, f"/api/v1/crop-cycles?farmer_id={selected_farmer_id}", headers)
    check(len(cycles) == 1 and cycles[0]["crop_code"] == crop, "Android crop-cycle drill-down opens selected farmer crop")
    check(any(stage["status"] == "ACTIVE" for stage in cycles[0]["stages"]), "Android crop-cycle drill-down includes active workflow stage")
    return {
        "selected_mobile": mobile,
        "selected_farmer_id": str(selected_farmer_id),
        "selected_crop_code": crop,
        "selected_cycle_id": cycles[0]["id"],
        "stage_statuses": sorted({stage["status"] for stage in cycles[0]["stages"]}),
    }


def verify_db_stage_search_backing() -> dict:
    db = SessionLocal()
    try:
        rows = (
            db.query(CropCycle.crop_code, CropStageInstance.stage_code, CropStageInstance.status)
            .join(CropStageInstance, CropStageInstance.crop_cycle_id == CropCycle.id)
            .filter(CropCycle.tenant_id == TENANT_ID, CropCycle.project_id == PROJECT_ID)
            .all()
        )
        status_counts = Counter(status for _, _, status in rows)
        active_by_crop = Counter(crop for crop, _, status in rows if status == "ACTIVE")
        check({"ACTIVE", "PENDING", "COMPLETED", "PARTIALLY_COMPLETED"}.issubset(status_counts), "Stage search backing has mixed statuses", dict(status_counts))
        check(set(active_by_crop).issuperset({"RICE", "WHEAT", "MAIZE", "SUGARCANE"}), "Active stage backing spans all crops", dict(active_by_crop))
        return {"stage_status_distribution": dict(sorted(status_counts.items())), "active_stage_crop_distribution": dict(sorted(active_by_crop.items()))}
    finally:
        db.close()


def main() -> int:
    print("=" * 72)
    print("ANDROID FPO SEARCH / DRILL-DOWN VERIFIER")
    print("=" * 72)
    db = SessionLocal()
    admin_user, admin_headers = create_test_admin(db, role="ENTERPRISE_ADMIN", tenant_id=TENANT_ID)
    db.close()
    try:
        client = TestClient(app)
        result = {
            "schema_version": "android_fpo_search_drilldown_verification.v1",
            "tenant_id": TENANT_ID,
            "project_id": str(PROJECT_ID),
            "admin_search": verify_admin_search(client, admin_headers),
            "project_trace_drilldown": verify_project_trace_drilldown(client, admin_headers),
            "android_visible_drilldown": verify_android_visible_drilldown(client),
            "stage_search_backing": verify_db_stage_search_backing(),
            "readiness": {
                "ready_for_android_fpo_search_maestro": True,
                "admin_enrollment_search_covered": True,
                "project_trace_crop_drilldown_covered": True,
                "android_farmer_crop_cycle_drilldown_covered": True,
            },
        }
    finally:
        cleanup_db = SessionLocal()
        try:
            delete_test_admin(cleanup_db, admin_user.id)
            cleanup_db.commit()
        finally:
            cleanup_db.close()

    print("=" * 72)
    print("ANDROID FPO SEARCH / DRILL-DOWN VERIFIED")
    print("=" * 72)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Verify Android FPO multi-village crop workflow fixture."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import CompanyProfile, Farmer, FarmerProjectEnrollment, Parcel, Project, Tenant
from app.modules.workflow.models import CropCycle, CropStageInstance
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin
from scripts.prepare_android_fpo_multi_village_workflow import FARMERS, PROJECT_ID, TENANT_ID, build_contract, farmer_id


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


def verify_db_shape() -> dict:
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.id == TENANT_ID).first()
        project = db.query(Project).filter(Project.id == PROJECT_ID, Project.tenant_id == TENANT_ID).first()
        profile = db.query(CompanyProfile).filter(CompanyProfile.tenant_id == TENANT_ID).first()
        farmers = db.query(Farmer).filter(Farmer.tenant_id == TENANT_ID, Farmer.status == "ACTIVE").all()
        parcels = db.query(Parcel).filter(Parcel.tenant_id == TENANT_ID, Parcel.status == "ACTIVE").all()
        enrollments = db.query(FarmerProjectEnrollment).filter(FarmerProjectEnrollment.tenant_id == TENANT_ID, FarmerProjectEnrollment.project_id == PROJECT_ID, FarmerProjectEnrollment.status == "ACTIVE").all()
        cycles = db.query(CropCycle).filter(CropCycle.tenant_id == TENANT_ID, CropCycle.project_id == PROJECT_ID).all()
        stages = db.query(CropStageInstance).filter(CropStageInstance.tenant_id == TENANT_ID, CropStageInstance.crop_cycle_id.in_([c.id for c in cycles])).all() if cycles else []
        check(tenant is not None and tenant.type == "FPO", "FPO tenant exists")
        check(profile is not None and profile.company_type == "FPO", "FPO company profile exists")
        check(project is not None and project.status == "ACTIVE", "FPO project exists and is active")
        check(len(farmers) == len(FARMERS), "Expected affiliated farmer count materialized", len(farmers))
        check(len(parcels) == len(FARMERS), "Expected parcel count materialized", len(parcels))
        check(len(enrollments) == len(FARMERS), "Expected active project enrollment count materialized", len(enrollments))
        check(len(cycles) == len(FARMERS), "Expected crop cycle count materialized", len(cycles))
        crop_counts = Counter(c.crop_code for c in cycles)
        village_counts = Counter(p.village_name_manual for p in parcels)
        stage_statuses = Counter(s.status for s in stages)
        check(set(crop_counts) == {"RICE", "WHEAT", "MAIZE", "SUGARCANE"}, "Different crops represented", dict(crop_counts))
        check(len(village_counts) == 4, "Multiple villages represented", dict(village_counts))
        check({"ACTIVE", "PENDING", "COMPLETED", "PARTIALLY_COMPLETED"}.issubset(set(stage_statuses)), "Different workflow stage statuses represented", dict(stage_statuses))
        orphan_enrollments = [str(e.id) for e in enrollments if not db.query(Farmer).filter(Farmer.id == e.farmer_id).first() or not db.query(Project).filter(Project.id == e.project_id).first()]
        orphan_cycles = [str(c.id) for c in cycles if not db.query(Farmer).filter(Farmer.id == c.farmer_id).first() or not db.query(Parcel).filter(Parcel.id == c.parcel_id).first()]
        check(orphan_enrollments == [], "No orphan project enrollments", orphan_enrollments)
        check(orphan_cycles == [], "No orphan crop cycles", orphan_cycles)
        return {
            "farmer_count": len(farmers),
            "parcel_count": len(parcels),
            "active_project_enrollments": len(enrollments),
            "crop_cycle_count": len(cycles),
            "crop_distribution": dict(sorted(crop_counts.items())),
            "village_distribution": dict(sorted(village_counts.items())),
            "stage_status_distribution": dict(sorted(stage_statuses.items())),
        }
    finally:
        db.close()


def verify_android_visible_apis(client: TestClient) -> dict:
    db = SessionLocal()
    admin_user, admin_headers = create_test_admin(db, role="ENTERPRISE_ADMIN", tenant_id=TENANT_ID)
    db.close()
    headers = {"X-Tenant-ID": TENANT_ID}
    enrollments = get_json(client, f"/api/v1/projects/{PROJECT_ID}/farmer-enrollments?status=ACTIVE", admin_headers)
    check(len(enrollments) == len(FARMERS), "Project enrollment API returns all FPO affiliated farmers")

    n, mobile, crop, *_ = FARMERS[0]
    sample_farmer_id = farmer_id(n)
    hydration = get_json(client, f"/api/v1/farmers/by-mobile/{mobile}?include_form_contract=true&project_id={PROJECT_ID}", headers)
    check(hydration["farmer"]["id"] == str(sample_farmer_id), "Hydration returns deterministic FPO farmer")
    check(hydration["farmer_context"]["mode"] == "PROJECT", "FPO farmer hydrates in project context")
    check(hydration["summary"]["active_project_enrollment_count"] == 1, "FPO farmer has one active project membership")

    cycles = get_json(client, f"/api/v1/crop-cycles?farmer_id={sample_farmer_id}", headers)
    check(len(cycles) == 1, "Android crop cycle list returns one cycle for FPO farmer", cycles)
    check(cycles[0]["crop_code"] == crop, "Crop cycle uses expected crop code", cycles[0])
    check(bool(cycles[0]["stages"]), "Crop cycle includes workflow stages", cycles[0]["stages"][:4])

    trace = get_json(client, f"/api/v1/reports/projects/{PROJECT_ID}/trace", admin_headers)
    summary = trace["summary"]
    check(summary["farmer_count"] == len(FARMERS), "Project trace reports FPO farmer count", summary)
    check(summary["parcel_count"] == len(FARMERS), "Project trace reports FPO parcel count", summary)
    check(summary["crop_cycle_count"] == len(FARMERS), "Project trace reports crop cycle count", summary)
    trace_crops = {row["crop_code"] for row in trace.get("crop_distribution", [])}
    check({"RICE", "WHEAT", "MAIZE", "SUGARCANE"}.issubset(trace_crops), "Project trace crop distribution includes all demo crops", trace.get("crop_distribution"))

    filters = get_json(client, f"/api/v1/reports/projects/{PROJECT_ID}/trace/filter-options", admin_headers)
    check(len(filters["farmers"]) == len(FARMERS), "Project trace filters include all FPO farmers")
    check({"RICE", "WHEAT", "MAIZE", "SUGARCANE"}.issubset(set(filters["crops"])), "Project trace filters include all crops", filters["crops"])

    village_db = SessionLocal()
    try:
        project_villages = {
            row[0]
            for row in village_db.query(Parcel.village_name_manual)
            .filter(Parcel.tenant_id == TENANT_ID, Parcel.project_id == PROJECT_ID, Parcel.status == "ACTIVE")
            .all()
            if row[0]
        }
    finally:
        village_db.close()
    check(len(project_villages) >= 4, "Project parcels cover multiple villages in DB", sorted(project_villages))

    result = {"enrollment_count": len(enrollments), "sample_farmer_mobile": mobile, "sample_farmer_id": str(sample_farmer_id), "sample_crop_cycle_id": cycles[0]["id"], "trace_summary": summary, "trace_crops": sorted(trace_crops), "filter_crop_codes": sorted(filters["crops"]), "project_villages": sorted(project_villages)}
    cleanup_db = SessionLocal()
    try:
        delete_test_admin(cleanup_db, admin_user.id)
        cleanup_db.commit()
    finally:
        cleanup_db.close()
    return result


def main() -> int:
    print("=" * 72)
    print("ANDROID FPO MULTI-VILLAGE WORKFLOW VERIFIER")
    print("=" * 72)
    client = TestClient(app)
    result = {
        "schema_version": "android_fpo_multi_village_workflow_verification.v1",
        "tenant_id": TENANT_ID,
        "project_id": str(PROJECT_ID),
        "db_integrity": verify_db_shape(),
        "android_visible_apis": verify_android_visible_apis(client),
        "android_contract": build_contract(),
        "readiness": {
            "ready_for_android_fpo_maestro": True,
            "multi_village_affiliation_covered": True,
            "different_crops_covered": True,
            "different_workflow_stages_covered": True,
            "admin_project_trace_covered": True,
        },
    }
    print("=" * 72)
    print("ANDROID FPO MULTI-VILLAGE WORKFLOW VERIFIED")
    print("=" * 72)
    print(json.dumps({k: result[k] for k in ["schema_version", "tenant_id", "project_id", "db_integrity", "android_visible_apis", "readiness"]}, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

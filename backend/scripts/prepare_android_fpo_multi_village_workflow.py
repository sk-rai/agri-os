"""Prepare deterministic FPO multi-village crop workflow fixtures.

This fixture is intentionally Android/demo scoped. It creates one FPO tenant,
one active FPO project, and 12 affiliated farmers across 4 villages with
different crops and different crop-stage statuses.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect, text

from app.core.database import SessionLocal
from app.modules.auth.models import User
from app.modules.farmer.models import CompanyProfile, Farmer, FarmerProjectEnrollment, Parcel, Project, Tenant
from app.modules.master_data.models import Crop, CropLifecycleTemplate, GeographyVillage  # noqa: F401
from app.modules.workflow.models import CropCycle, CropStageInstance, WorkflowTemplate, WorkflowTemplateStage, WorkflowTemplateVersion


TENANT_ID = "android-fpo-multi-village-test"
PROJECT_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000002001")
ADMIN_USER_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000002099")

FARMERS = [
    (1, "+919900002101", "RICE", "KHARIF", "FPO Rampur", "560001", 1, "ACTIVE", "1.20"),
    (2, "+919900002102", "RICE", "KHARIF", "FPO Rampur", "560001", 3, "ACTIVE", "0.95"),
    (3, "+919900002103", "RICE", "KHARIF", "FPO Chikkapura", "560002", 5, "ACTIVE", "1.50"),
    (4, "+919900002104", "WHEAT", "RABI", "FPO Chikkapura", "560002", 1, "ACTIVE", "1.10"),
    (5, "+919900002105", "WHEAT", "RABI", "FPO Harohalli", "560003", 2, "ACTIVE", "2.00"),
    (6, "+919900002106", "MAIZE", "KHARIF", "FPO Harohalli", "560003", 1, "ACTIVE", "1.35"),
    (7, "+919900002107", "MAIZE", "KHARIF", "FPO Nelamangala", "560004", 2, "ACTIVE", "1.80"),
    (8, "+919900002108", "SUGARCANE", "KHARIF", "FPO Nelamangala", "560004", 1, "ACTIVE", "2.25"),
    (9, "+919900002109", "SUGARCANE", "KHARIF", "FPO Rampur", "560001", 4, "ACTIVE", "2.75"),
    (10, "+919900002110", "RICE", "KHARIF", "FPO Chikkapura", "560002", 0, "PENDING", "0.85"),
    (11, "+919900002111", "WHEAT", "RABI", "FPO Harohalli", "560003", 99, "COMPLETED", "1.45"),
    (12, "+919900002112", "SUGARCANE", "KHARIF", "FPO Nelamangala", "560004", 2, "PARTIALLY_COMPLETED", "3.10"),
]


def stable_uuid(suffix: int) -> uuid.UUID:
    return uuid.UUID(f"0f7e0a6b-8472-5d6d-8a14-a9d000002{suffix:03d}")


def now() -> datetime:
    return datetime.now(timezone.utc)


def table_exists(db, table_name: str) -> bool:
    return inspect(db.bind).has_table(table_name)


def delete_if_table(db, table_name: str, sql: str, params: dict, result: dict, dry_run: bool) -> None:
    if not table_exists(db, table_name):
        result["reset"]["skipped_missing_tables"].append(table_name)
        return
    if dry_run:
        count_sql = sql.replace(f"delete from {table_name}", f"select count(*) from {table_name}", 1)
        result["reset"]["dry_run_delete_counts"][table_name] = int(db.execute(text(count_sql), params).scalar() or 0)
        return
    result["reset"]["deleted_counts"][table_name] = int(db.execute(text(sql), params).rowcount or 0)


def farmer_id(n: int) -> uuid.UUID:
    return stable_uuid(100 + n)


def parcel_id(n: int) -> uuid.UUID:
    return stable_uuid(200 + n)


def cycle_id(n: int) -> uuid.UUID:
    return stable_uuid(300 + n)


def enrollment_id(n: int) -> uuid.UUID:
    return stable_uuid(400 + n)


def user_id(n: int) -> uuid.UUID:
    return stable_uuid(500 + n)


def label_text(value, fallback: str) -> str:
    if isinstance(value, dict):
        return value.get("en") or next((str(v) for v in value.values() if v), fallback)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def resolve_workflow(db, crop_code: str, season_code: str):
    workflow = (
        db.query(WorkflowTemplate)
        .filter(WorkflowTemplate.crop_code == crop_code, WorkflowTemplate.season_code == season_code, WorkflowTemplate.is_active == True)
        .order_by(WorkflowTemplate.is_default.desc(), WorkflowTemplate.updated_at.desc())
        .first()
    )
    if workflow:
        version = (
            db.query(WorkflowTemplateVersion)
            .filter(WorkflowTemplateVersion.template_id == workflow.id, WorkflowTemplateVersion.status == "PUBLISHED", WorkflowTemplateVersion.is_active == True)
            .order_by(WorkflowTemplateVersion.published_at.desc().nullslast(), WorkflowTemplateVersion.updated_at.desc())
            .first()
        )
        if version and workflow.lifecycle_template_id:
            stages = (
                db.query(WorkflowTemplateStage)
                .filter(WorkflowTemplateStage.template_version_id == version.id, WorkflowTemplateStage.is_active == True)
                .order_by(WorkflowTemplateStage.stage_order.asc())
                .all()
            )
            if stages:
                return workflow.lifecycle_template_id, version.id, [
                    {
                        "code": stage.stage_code,
                        "name": label_text(stage.stage_name, stage.stage_code.title()),
                        "order": stage.stage_order,
                        "duration": stage.duration_days or 10,
                    }
                    for stage in stages
                ]

    crop = db.query(Crop).filter(Crop.code == crop_code).first()
    template = None
    if crop:
        template = (
            db.query(CropLifecycleTemplate)
            .filter(CropLifecycleTemplate.crop_id == crop.id, CropLifecycleTemplate.season_code == season_code, CropLifecycleTemplate.is_active == True)
            .order_by(CropLifecycleTemplate.is_default.desc(), CropLifecycleTemplate.updated_at.desc())
            .first()
        )
    if template and template.stages:
        stages = []
        for idx, row in enumerate(template.stages):
            stages.append({
                "code": row.get("code") or row.get("stage_code") or f"STAGE_{idx + 1}",
                "name": label_text(row.get("name") or row.get("stage_name"), row.get("code") or f"Stage {idx + 1}"),
                "order": row.get("order") or row.get("stage_order") or idx + 1,
                "duration": row.get("duration_days") or row.get("duration") or 10,
            })
        return template.id, None, stages

    raise RuntimeError(
        f"Missing crop workflow seed for {crop_code}/{season_code}. Run seed_reference_data.py, "
        "seed_crops_up.py, seed_enhanced_templates.py, and seed_workflow_templates.py."
    )


def reset_fixture(db, result: dict, dry_run: bool) -> None:
    params = {
        "tenant_id": TENANT_ID,
        "project_id": str(PROJECT_ID),
        "farmer_ids": [str(farmer_id(row[0])) for row in FARMERS],
        "parcel_ids": [str(parcel_id(row[0])) for row in FARMERS],
        "cycle_ids": [str(cycle_id(row[0])) for row in FARMERS],
        "enrollment_ids": [str(enrollment_id(row[0])) for row in FARMERS],
        "user_ids": [str(user_id(row[0])) for row in FARMERS] + [str(ADMIN_USER_ID)],
    }
    deletes = [
        ("crop_activities", "delete from crop_activities where tenant_id = :tenant_id and crop_cycle_id = any(cast(:cycle_ids as uuid[]))"),
        ("crop_stage_instances", "delete from crop_stage_instances where tenant_id = :tenant_id and crop_cycle_id = any(cast(:cycle_ids as uuid[]))"),
        ("crop_cycles", "delete from crop_cycles where tenant_id = :tenant_id and id = any(cast(:cycle_ids as uuid[]))"),
        ("soil_profiles", "delete from soil_profiles where tenant_id = :tenant_id and parcel_id = any(cast(:parcel_ids as uuid[]))"),
        ("farmer_project_enrollments", "delete from farmer_project_enrollments where tenant_id = :tenant_id and (id = any(cast(:enrollment_ids as uuid[])) or project_id = cast(:project_id as uuid))"),
        ("parcels", "delete from parcels where tenant_id = :tenant_id and id = any(cast(:parcel_ids as uuid[]))"),
        ("farmers", "delete from farmers where tenant_id = :tenant_id and id = any(cast(:farmer_ids as uuid[]))"),
        ("users", "delete from users where id = any(cast(:user_ids as uuid[]))"),
        ("company_profiles", "delete from company_profiles where tenant_id = :tenant_id"),
        ("projects", "delete from projects where tenant_id = :tenant_id and id = cast(:project_id as uuid)"),
        ("tenants", "delete from tenants where id = :tenant_id"),
    ]
    for table, sql in deletes:
        delete_if_table(db, table, sql, params, result, dry_run)


def upsert_fixture(db, result: dict, dry_run: bool) -> None:
    if dry_run:
        result["tenant"] = {"status": "WOULD_CREATE", "tenant_id": TENANT_ID}
        result["project"] = {"status": "WOULD_CREATE", "project_id": str(PROJECT_ID)}
        return

    villages = sorted({row[4] for row in FARMERS})
    pin_codes = sorted({row[5] for row in FARMERS})
    crop_codes = sorted({row[2] for row in FARMERS})
    db.add(Tenant(id=TENANT_ID, name="Android FPO Multi Village Test", type="FPO", config={"fixture": "android_fpo_multi_village_workflow.v1"}, created_at=now(), updated_at=now()))
    db.add(CompanyProfile(id=stable_uuid(90), tenant_id=TENANT_ID, legal_name="Android FPO Multi Village Producer Company", display_name="Android FPO Demo", company_type="FPO", verification_status="VERIFIED", operating_geography={"state": "Karnataka", "villages": villages}, crop_focus=crop_codes, service_model={"affiliated_farmer_model": True, "multi_village_cluster": True}, metadata_={"fixture": "android_fpo_multi_village_workflow.v1"}, created_at=now(), updated_at=now()))
    db.add(User(id=ADMIN_USER_ID, tenant_id=TENANT_ID, mobile_number="+919900002000", role="ENTERPRISE_ADMIN", display_name="Android FPO Admin", language_preference="en", created_at=now(), updated_at=now()))
    db.add(Project(id=PROJECT_ID, tenant_id=TENANT_ID, name="Android FPO Multi Village Crop Program", description="FPO demo project with affiliated farmers across villages, crops, and workflow stages.", start_date=date.today() - timedelta(days=60), end_date=date.today() + timedelta(days=260), status="ACTIVE", geography_scope={"pin_codes": pin_codes, "village_names": villages}, crop_scope=crop_codes, config={"fpo_affiliated_farmer_demo": True, "backend_driven_crop_workflows": True}, created_at=now(), updated_at=now()))
    db.flush()

    for n, mobile, crop, season, village, pin, stage_index, target_status, area in FARMERS:
        lifecycle_template_id, workflow_version_id, stages = resolve_workflow(db, crop, season)
        active_index = min(max(stage_index, 0), len(stages) - 1)
        sowing = date.today() - timedelta(days=sum((s["duration"] or 10) for s in stages[:active_index]) + 4)
        cycle_status = "COMPLETED" if target_status == "COMPLETED" else ("PLANNED" if target_status == "PENDING" and stage_index == 0 else "ACTIVE")

        db.add(User(id=user_id(n), tenant_id=TENANT_ID, mobile_number=mobile, role="FARMER", display_name=f"FPO Farmer {n:02d}", language_preference="en", created_at=now(), updated_at=now()))
        db.add(Farmer(id=farmer_id(n), tenant_id=TENANT_ID, project_id=PROJECT_ID, user_id=user_id(n), mobile_number=mobile, display_name=f"FPO Farmer {n:02d} {crop.title()}", village_name_manual=village, pin_code=pin, primary_crop_code=crop, crops_by_season={season: [crop]}, total_land_area=area, total_land_unit="ACRE", language_preference="en", enrollment_method="BULK", status="ACTIVE", created_at=now(), updated_at=now()))
        db.add(Parcel(id=parcel_id(n), tenant_id=TENANT_ID, farmer_id=farmer_id(n), project_id=PROJECT_ID, village_name_manual=village, pin_code=pin, location_scope={"mode": "FPO_MULTI_VILLAGE", "village_name": village, "pin_codes": [pin], "source": "android_fpo_fixture"}, reported_area=area, reported_area_unit="ACRE", soil_type_code="BLACK_COTTON" if crop in {"RICE", "SUGARCANE"} else "ALLUVIAL", current_crop_code=crop, geometry_source="PIN_DROP", centroid_lat="12.97160000", centroid_lng="77.59460000", local_name=f"{village} Parcel {n:02d}", survey_number=f"FPO-{n:03d}", ownership_type="OWNED", irrigation_source="CANAL" if crop in {"RICE", "SUGARCANE"} else "TUBEWELL_ELECTRIC", crops_by_season={season: [crop]}, status="ACTIVE", created_at=now(), updated_at=now()))
        db.add(FarmerProjectEnrollment(id=enrollment_id(n), tenant_id=TENANT_ID, farmer_id=farmer_id(n), project_id=PROJECT_ID, enrollment_method="BULK_IMPORT", enrollment_source="FPO_AFFILIATED_FARMER_LIST", enrollment_batch_id="android-fpo-demo-batch-001", enrolled_by=ADMIN_USER_ID, status="ACTIVE", parcel_ids=[str(parcel_id(n))], assigned_user_ids=[], metadata_={"fpo_affiliated": True, "village_name": village, "crop_code": crop, "stage_target": target_status}, notes="Android FPO multi-village crop workflow fixture", created_at=now(), updated_at=now()))
        db.add(CropCycle(id=cycle_id(n), tenant_id=TENANT_ID, farmer_id=farmer_id(n), parcel_id=parcel_id(n), project_id=PROJECT_ID, crop_code=crop, season_code=season, lifecycle_template_id=lifecycle_template_id, workflow_template_version_id=workflow_version_id, planned_sowing_date=sowing, actual_sowing_date=sowing if cycle_status != "PLANNED" else None, expected_harvest_date=sowing + timedelta(days=sum((s["duration"] or 10) for s in stages)), actual_harvest_date=date.today() - timedelta(days=1) if cycle_status == "COMPLETED" else None, status=cycle_status, notes="Android FPO multi-village crop workflow fixture", created_at=now(), updated_at=now()))
        for idx, stage in enumerate(stages):
            if cycle_status == "COMPLETED":
                status = "COMPLETED"
            elif target_status == "PENDING" and stage_index == 0:
                status = "PENDING"
            elif idx < active_index:
                status = "COMPLETED"
            elif idx == active_index:
                status = target_status
            else:
                status = "PENDING"
            db.add(CropStageInstance(id=stable_uuid(600 + n * 20 + idx), crop_cycle_id=cycle_id(n), tenant_id=TENANT_ID, stage_code=stage["code"], stage_name=stage["name"], stage_order=stage["order"], expected_duration_days=stage["duration"], planned_start_date=sowing + timedelta(days=sum((s["duration"] or 10) for s in stages[:idx])), actual_start_date=sowing + timedelta(days=sum((s["duration"] or 10) for s in stages[:idx])) if status in {"ACTIVE", "COMPLETED", "PARTIALLY_COMPLETED"} else None, actual_end_date=date.today() - timedelta(days=1) if status == "COMPLETED" else None, status=status, started_by=ADMIN_USER_ID if status in {"ACTIVE", "COMPLETED", "PARTIALLY_COMPLETED"} else None, completed_by=ADMIN_USER_ID if status == "COMPLETED" else None, created_at=now(), updated_at=now()))
        result["farmers"][f"farmer_{n:02d}"] = {"farmer_id": str(farmer_id(n)), "mobile": mobile, "village": village, "pin_code": pin, "crop_code": crop, "season_code": season, "cycle_id": str(cycle_id(n)), "target_stage_status": target_status}


def build_contract() -> dict:
    return {
        "headers": {"X-Tenant-ID": TENANT_ID},
        "tenant_id": TENANT_ID,
        "project_id": str(PROJECT_ID),
        "endpoints": {
            "project_enrollments": f"/api/v1/projects/{PROJECT_ID}/farmer-enrollments?status=ACTIVE",
            "project_trace": f"/api/v1/reports/projects/{PROJECT_ID}/trace",
            "project_trace_filters": f"/api/v1/reports/projects/{PROJECT_ID}/trace/filter-options",
            "app_bootstrap": f"/api/v1/app-config/bootstrap?project_id={PROJECT_ID}",
            "crop_cycles_by_farmer": "/api/v1/crop-cycles?farmer_id={farmer_id}",
            "farmer_hydration_by_mobile": "/api/v1/farmers/by-mobile/{mobile}?include_form_contract=true",
        },
        "expected": {"farmer_count": len(FARMERS), "village_count": len({row[4] for row in FARMERS}), "crop_codes": sorted({row[2] for row in FARMERS}), "stage_statuses": sorted({row[7] for row in FARMERS})},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    dry_run = not args.apply
    result = {"schema_version": "android_fpo_multi_village_workflow_prepare.v1", "mode": "DRY_RUN" if dry_run else "APPLY", "reset_requested": args.reset, "tenant": {}, "project": {}, "farmers": {}, "reset": {"deleted_counts": {}, "dry_run_delete_counts": {}, "skipped_missing_tables": []}, "android_contract": build_contract()}
    db = SessionLocal()
    try:
        if args.reset:
            reset_fixture(db, result, dry_run)
            if not dry_run:
                db.flush()
        upsert_fixture(db, result, dry_run)
        if not dry_run:
            db.commit()
            result["tenant"] = {"status": "CREATED", "tenant_id": TENANT_ID}
            result["project"] = {"status": "CREATED", "project_id": str(PROJECT_ID)}
        else:
            db.rollback()
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

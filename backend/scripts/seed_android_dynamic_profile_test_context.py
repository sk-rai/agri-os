#!/usr/bin/env python3
"""Seed/reset deterministic Android dynamic profile test context.

Creates a test tenant/project where backend-driven profile forms are enabled.
Reset mode deletes test farmer/profile rows for the dedicated test mobile.

Dry-run by default. Use --apply to write. Use --reset --apply to clean test data.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect, text
from app.core.database import SessionLocal
from app.modules.farmer.models import Project, Tenant

TENANT_ID = "android-dynamic-test"
PROJECT_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000000001")
TEST_MOBILE = "+919900000002"

CONFIG_PATCH = {
    "feature_flags": {
        "backend_driven_farmer_forms": True,
        "backend_driven_parcel_forms": True,
        "backend_driven_soil_forms": True,
        "white_label_runtime_branding": True,
        "broadcast_advisories": True,
        "soil_enrichment_snapshots": True,
        "weather_snapshots": True,
    },
    "localization": {
        "default_language": "en",
        "supported_languages": ["en", "hi"],
        "country_code": "IN",
        "timezone": "Asia/Kolkata",
    },
    "units": {
        "default_area_unit": "ACRE",
        "area_units": ["ACRE", "HECTARE", "BIGHA", "GUNTHA"],
        "currency": "INR",
        "measurement_system": "METRIC",
    },
    "self_service": {
        "allow_direct_farmer_registration": True,
        "requires_project_invite": False,
    },
}


def now():
    return datetime.now(timezone.utc)


def table_exists(db, table_name: str) -> bool:
    return inspect(db.bind).has_table(table_name)


def delete_if_table(db, table_name: str, sql: str, params: dict, result: dict, dry_run: bool):
    if not table_exists(db, table_name):
        result["reset"]["skipped_missing_tables"].append(table_name)
        return

    if dry_run:
        count_sql = sql.replace(f"delete from {table_name}", f"select count(*) from {table_name}", 1)
        try:
            count = int(db.execute(text(count_sql), params).scalar() or 0)
        except Exception:
            count = None
        result["reset"]["dry_run_delete_counts"][table_name] = count
        return

    deleted = db.execute(text(sql), params).rowcount
    result["reset"]["deleted_counts"][table_name] = int(deleted or 0)


def reset_test_mobile(db, dry_run: bool, result: dict):
    params = {"tenant_id": TENANT_ID, "mobile": TEST_MOBILE}

    farmer_ids = [
        str(row[0])
        for row in db.execute(
            text("select id from farmers where tenant_id = :tenant_id and mobile_number = :mobile"),
            params,
        ).all()
    ]
    result["reset"]["farmer_ids"] = farmer_ids

    if not farmer_ids:
        return

    params["farmer_ids"] = farmer_ids

    delete_if_table(
        db,
        "crop_activities",
        "delete from crop_activities where crop_cycle_id in (select id from crop_cycles where tenant_id = :tenant_id and farmer_id = any(:farmer_ids))",
        params,
        result,
        dry_run,
    )
    delete_if_table(
        db,
        "crop_stage_instances",
        "delete from crop_stage_instances where crop_cycle_id in (select id from crop_cycles where tenant_id = :tenant_id and farmer_id = any(:farmer_ids))",
        params,
        result,
        dry_run,
    )
    delete_if_table(
        db,
        "crop_cycles",
        "delete from crop_cycles where tenant_id = :tenant_id and farmer_id = any(:farmer_ids)",
        params,
        result,
        dry_run,
    )
    delete_if_table(
        db,
        "soil_profiles",
        "delete from soil_profiles where tenant_id = :tenant_id and farmer_id = any(:farmer_ids)",
        params,
        result,
        dry_run,
    )
    delete_if_table(
        db,
        "soil_enrichment_snapshots",
        "delete from soil_enrichment_snapshots where tenant_id = :tenant_id and farmer_id = any(:farmer_ids)",
        params,
        result,
        dry_run,
    )
    delete_if_table(
        db,
        "farmer_project_enrollments",
        "delete from farmer_project_enrollments where tenant_id = :tenant_id and farmer_id = any(:farmer_ids)",
        params,
        result,
        dry_run,
    )
    delete_if_table(
        db,
        "parcels",
        "delete from parcels where tenant_id = :tenant_id and farmer_id = any(:farmer_ids)",
        params,
        result,
        dry_run,
    )
    delete_if_table(
        db,
        "broadcast_deliveries",
        "delete from broadcast_deliveries where tenant_id = :tenant_id and farmer_id = any(:farmer_ids)",
        params,
        result,
        dry_run,
    )
    delete_if_table(
        db,
        "farmers",
        "delete from farmers where tenant_id = :tenant_id and id = any(:farmer_ids)",
        params,
        result,
        dry_run,
    )


def seed_context(db, dry_run: bool, result: dict):
    tenant = db.query(Tenant).filter(Tenant.id == TENANT_ID).first()
    if tenant:
        result["tenant"]["status"] = "EXISTS"
        if tenant.config != CONFIG_PATCH:
            result["tenant"]["config_update_needed"] = True
            if not dry_run:
                tenant.config = CONFIG_PATCH
                tenant.updated_at = now()
    else:
        result["tenant"]["status"] = "WOULD_CREATE" if dry_run else "CREATED"
        if not dry_run:
            tenant = Tenant(
                id=TENANT_ID,
                name="Android Dynamic Profile Test Tenant",
                type="ENTERPRISE",
                config=CONFIG_PATCH,
                created_at=now(),
                updated_at=now(),
            )
            db.add(tenant)
            db.flush()

    project = db.query(Project).filter(Project.id == PROJECT_ID).first()
    if project:
        result["project"]["status"] = "EXISTS"
        if project.config != CONFIG_PATCH:
            result["project"]["config_update_needed"] = True
            if not dry_run:
                project.config = CONFIG_PATCH
                project.updated_at = now()
    else:
        result["project"]["status"] = "WOULD_CREATE" if dry_run else "CREATED"
        if not dry_run:
            project = Project(
                id=PROJECT_ID,
                tenant_id=TENANT_ID,
                name="Android Dynamic Profile Test Project",
                start_date=date.today(),
                end_date=date.today() + timedelta(days=180),
                status="ACTIVE",
                geography_scope={
                    "state_lgd_codes": ["29"],
                    "district_lgd_codes": ["536"],
                    "pin_codes": ["560001"],
                    "note": "Dharwad/Karnataka style dynamic profile test context.",
                },
                crop_scope=["RICE", "SUGARCANE"],
                config=CONFIG_PATCH,
                created_at=now(),
                updated_at=now(),
            )
            db.add(project)

    result["android_config"] = {
        "tenant_header": {"X-Tenant-ID": TENANT_ID},
        "project_id": str(PROJECT_ID),
        "test_mobile": TEST_MOBILE,
        "bootstrap_url": f"/api/v1/app-config/bootstrap?project_id={PROJECT_ID}",
        "forms": [
            "/api/v1/forms/farmer_registration",
            "/api/v1/forms/parcel_registration",
            "/api/v1/forms/soil_profile",
        ],
        "land_intelligence_pin_only": "/api/v1/profile/land-intelligence-context?pin_code=560001",
        "land_intelligence_crop_season": "/api/v1/profile/land-intelligence-context?pin_code=560001&crop_code=RICE&season_code=KHARIF",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    dry_run = not args.apply
    result = {
        "schema_version": "android_dynamic_profile_test_context_seed.v1",
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "tenant": {"tenant_id": TENANT_ID},
        "project": {"project_id": str(PROJECT_ID)},
        "reset": {
            "requested": args.reset,
            "farmer_ids": [],
            "deleted_counts": {},
            "dry_run_delete_counts": {},
            "skipped_missing_tables": [],
        },
        "android_config": {},
        "expected_flags": {
            "backend_driven_farmer_forms": True,
            "backend_driven_parcel_forms": True,
            "backend_driven_soil_forms": True,
        },
    }

    db = SessionLocal()
    try:
        seed_context(db, dry_run, result)
        if args.reset:
            reset_test_mobile(db, dry_run, result)

        if dry_run:
            db.rollback()
        else:
            db.commit()
    finally:
        db.close()

    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Seed/reset deterministic Android crop-cycle creation test fixture.

Creates a farmer + parcel in the android-dynamic-test context where eligible
parcel checks should return at least one ELIGIBLE parcel for KHARIF/RICE.

Dry-run by default. Use --apply to write. Use --reset --apply before Maestro reruns.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect, text
from app.core.database import SessionLocal
from app.modules.farmer.models import Farmer, Parcel, Project, Tenant
from app.modules.master_data.models import Crop, CropLifecycleTemplate

TENANT_ID = "android-dynamic-test"
PROJECT_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000000001")
TEST_MOBILE = "+919900000003"
FARMER_ID = uuid.UUID("4df387e8-114f-5c44-a129-a9d000000003")
PARCEL_ID = uuid.UUID("4df387e8-114f-5c44-a129-a9d000000004")

SEASON_CODE = "KHARIF"
SEASON_YEAR = 2026
CROP_CODE = "RICE"
ALT_CROP_CODE = "SUGARCANE"


def now():
    return datetime.now(timezone.utc)


def table_exists(db, table_name: str) -> bool:
    return inspect(db.bind).has_table(table_name)


def ensure_dynamic_context(db, dry_run: bool, result: dict):
    tenant = db.query(Tenant).filter(Tenant.id == TENANT_ID).first()
    project = db.query(Project).filter(Project.id == PROJECT_ID).first()

    result["context"] = {
        "tenant_exists": tenant is not None,
        "project_exists": project is not None,
        "tenant_id": TENANT_ID,
        "project_id": str(PROJECT_ID),
    }

    if tenant and project:
        return

    # Reuse dedicated context seeder if available, so we do not duplicate config logic.
    from scripts.seed_android_dynamic_profile_test_context import seed_context

    seed_context(db, dry_run, {"tenant": {}, "project": {}, "android_config": {}})


def delete_for_fixture(db, dry_run: bool, result: dict):
    params = {
        "tenant_id": TENANT_ID,
        "farmer_id": str(FARMER_ID),
        "parcel_id": str(PARCEL_ID),
    }

    deletes = [
        (
            "crop_activities",
            "delete from crop_activities where crop_cycle_id in (select id from crop_cycles where tenant_id = :tenant_id and farmer_id = :farmer_id)",
        ),
        (
            "crop_stage_instances",
            "delete from crop_stage_instances where crop_cycle_id in (select id from crop_cycles where tenant_id = :tenant_id and farmer_id = :farmer_id)",
        ),
        (
            "crop_cycles",
            "delete from crop_cycles where tenant_id = :tenant_id and farmer_id = :farmer_id",
        ),
        (
            "soil_profiles",
            "delete from soil_profiles where tenant_id = :tenant_id and farmer_id = :farmer_id",
        ),
        (
            "farmer_project_enrollments",
            "delete from farmer_project_enrollments where tenant_id = :tenant_id and farmer_id = :farmer_id",
        ),
        (
            "parcels",
            "delete from parcels where tenant_id = :tenant_id and farmer_id = :farmer_id",
        ),
        (
            "farmers",
            "delete from farmers where tenant_id = :tenant_id and id = :farmer_id",
        ),
    ]

    for table, sql in deletes:
        if not table_exists(db, table):
            result["reset"]["skipped_missing_tables"].append(table)
            continue
        if dry_run:
            count_sql = sql.replace(f"delete from {table}", f"select count(*) from {table}", 1)
            try:
                result["reset"]["dry_run_delete_counts"][table] = int(db.execute(text(count_sql), params).scalar() or 0)
            except Exception:
                result["reset"]["dry_run_delete_counts"][table] = None
        else:
            result["reset"]["deleted_counts"][table] = int(db.execute(text(sql), params).rowcount or 0)


def seed_farmer_parcel(db, dry_run: bool, result: dict):
    rice = db.query(Crop).filter(Crop.code == CROP_CODE).first()
    template = (
        db.query(CropLifecycleTemplate)
        .join(Crop, Crop.id == CropLifecycleTemplate.crop_id)
        .filter(Crop.code == CROP_CODE, CropLifecycleTemplate.season_code == SEASON_CODE)
        .first()
    )

    result["fixture"]["rice_exists"] = rice is not None
    result["fixture"]["rice_kharif_template_exists"] = template is not None

    if not rice or not template:
        result["fixture"]["ready"] = False
        return

    farmer = db.query(Farmer).filter(Farmer.id == FARMER_ID).first()
    if farmer:
        result["fixture"]["farmer_status"] = "EXISTS"
    else:
        result["fixture"]["farmer_status"] = "WOULD_CREATE" if dry_run else "CREATED"
        if not dry_run:
            farmer = Farmer(
                id=FARMER_ID,
                tenant_id=TENANT_ID,
                mobile_number=TEST_MOBILE,
                display_name="Android Crop Cycle Test Farmer",
                status="ACTIVE",
                pin_code="560001",
                village_name_manual="Android Crop Cycle Test Village",
                primary_crop_code=CROP_CODE,
                created_at=now(),
                updated_at=now(),
            )
            db.add(farmer)
            db.flush()

    parcel = db.query(Parcel).filter(Parcel.id == PARCEL_ID).first()
    if parcel:
        result["fixture"]["parcel_status"] = "EXISTS"
    else:
        result["fixture"]["parcel_status"] = "WOULD_CREATE" if dry_run else "CREATED"
        if not dry_run:
            parcel = Parcel(
                id=PARCEL_ID,
                tenant_id=TENANT_ID,
                farmer_id=FARMER_ID,
                project_id=PROJECT_ID,
                reported_area=Decimal("1.25"),
                reported_area_unit="ACRE",
                geometry_source="PIN_DROP",
                centroid_lat=Decimal("15.4589"),
                centroid_lng=Decimal("75.0078"),
                pin_code="560001",
                village_name_manual="Android Crop Cycle Test Village",
                status="ACTIVE",
                created_at=now(),
                updated_at=now(),
            )
            db.add(parcel)

    result["fixture"]["ready"] = True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    dry_run = not args.apply
    result = {
        "schema_version": "android_crop_cycle_test_fixture_seed.v1",
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "context": {},
        "fixture": {
            "tenant_id": TENANT_ID,
            "project_id": str(PROJECT_ID),
            "farmer_id": str(FARMER_ID),
            "parcel_id": str(PARCEL_ID),
            "mobile": TEST_MOBILE,
            "crop_code": CROP_CODE,
            "alt_crop_code": ALT_CROP_CODE,
            "season_code": SEASON_CODE,
            "season_year": SEASON_YEAR,
            "ready": False,
        },
        "reset": {
            "requested": args.reset,
            "deleted_counts": {},
            "dry_run_delete_counts": {},
            "skipped_missing_tables": [],
        },
        "android_checks": {
            "headers": {"X-Tenant-ID": TENANT_ID},
            "eligible_parcels": f"/api/v1/crop-cycles/eligible-parcels?farmer_id={FARMER_ID}&season={SEASON_CODE}",
            "crop_template": f"/api/v1/crop-cycles/templates/{CROP_CODE}?season={SEASON_CODE}",
        },
    }

    db = SessionLocal()
    try:
        ensure_dynamic_context(db, dry_run, result)
        if args.reset:
            delete_for_fixture(db, dry_run, result)
        seed_farmer_parcel(db, dry_run, result)

        if dry_run:
            db.rollback()
        else:
            db.commit()
    finally:
        db.close()

    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result["fixture"]["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

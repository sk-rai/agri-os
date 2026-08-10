"""Shared Android dynamic sync fixture baseline helpers.

This module owns the deterministic android-dynamic-test baseline used by
Android sync/conflict fixture scripts. Keep this helper side-effect free unless
called with dry_run=False from a fixture script.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import text

from app.modules.farmer.models import Farmer, FarmerProjectEnrollment, Parcel, Project, Tenant
from app.modules.workflow.models import CropCycle, CropStageInstance


TENANT_ID = "android-dynamic-test"
PROJECT_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000000001")
FARMER_ID = uuid.UUID("e1ee0941-2bad-4a18-a239-2a4119608a06")
PARCEL_ID = uuid.UUID("98c1a0fa-4f5f-4b8c-97ae-d84992db1c44")
CYCLE_ID = uuid.UUID("aa346148-468b-47de-9c86-47ad41aa1f11")
ACTOR_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")


TEST_MOBILE = "+919900000002"


def now():
    return datetime.now(timezone.utc)


def get_lifecycle_template_id(db) -> uuid.UUID:
    row = db.execute(
        text("""
            select lct.id
            from crop_lifecycle_templates lct
            left join crops c on c.id = lct.crop_id
            where upper(coalesce(c.code, '')) = 'RICE'
            order by lct.is_active desc, lct.created_at desc
            limit 1
        """)
    ).first()
    if row:
        return row[0]

    fallback = db.execute(
        text("""
            select id
            from crop_lifecycle_templates
            order by is_active desc, created_at desc
            limit 1
        """)
    ).first()
    if fallback:
        return fallback[0]

    raise RuntimeError(
        "No crop_lifecycle_templates row found; seed workflow master data before Flow 16."
    )


def ensure_android_baseline(db, dry_run: bool) -> dict:
    """Ensure deterministic Android dynamic baseline for WORKFLOW_INVALID fixture."""

    result = {
        "tenant": "EXISTS",
        "project": "EXISTS",
        "farmer": "EXISTS",
        "parcel": "EXISTS",
        "farmer_project_enrollment": "EXISTS",
        "crop_cycle": "EXISTS",
        "nursery_stage": "EXISTS",
    }

    tenant = db.query(Tenant).filter(Tenant.id == TENANT_ID).first()
    if not tenant:
        result["tenant"] = "WOULD_CREATE" if dry_run else "CREATED"
        if not dry_run:
            tenant = Tenant(
                id=TENANT_ID,
                name="Android Dynamic Profile Test Tenant",
                type="ENTERPRISE",
                config={
                    "feature_flags": {
                        "backend_driven_farmer_forms": True,
                        "backend_driven_parcel_forms": True,
                        "backend_driven_soil_forms": True,
                    },
                    "localization": {
                        "default_language": "en",
                        "supported_languages": ["en", "hi"],
                    },
                },
                created_at=now(),
                updated_at=now(),
            )
            db.add(tenant)
            db.flush()

    project = (
        db.query(Project)
        .filter(Project.id == PROJECT_ID, Project.tenant_id == TENANT_ID)
        .first()
    )
    if not project:
        result["project"] = "WOULD_CREATE" if dry_run else "CREATED"
        if not dry_run:
            project = Project(
                id=PROJECT_ID,
                tenant_id=TENANT_ID,
                name="Android Dynamic Profile Test Project",
                description="Primary Android dynamic test project used by sync fixture scripts.",
                start_date=date.today(),
                end_date=date.today() + timedelta(days=180),
                status="ACTIVE",
                geography_scope={
                    "state_lgd_codes": ["29"],
                    "district_lgd_codes": ["536"],
                    "pin_codes": ["560001"],
                    "note": "Android workflow-invalid sync conflict fixture baseline.",
                },
                crop_scope=["RICE", "SUGARCANE"],
                config={},
                created_at=now(),
                updated_at=now(),
                is_active=True,
            )
            db.add(project)
            db.flush()

    farmer = (
        db.query(Farmer)
        .filter(Farmer.id == FARMER_ID, Farmer.tenant_id == TENANT_ID)
        .first()
    )
    if not farmer:
        result["farmer"] = "WOULD_CREATE" if dry_run else "CREATED"
        if not dry_run:
            farmer = Farmer(
                id=FARMER_ID,
                tenant_id=TENANT_ID,
                project_id=PROJECT_ID,
                mobile_number=TEST_MOBILE,
                village_name_manual="Android Dynamic Test Village",
                pin_code="560001",
                primary_crop_code="RICE",
                crops_by_season={"KHARIF": ["RICE"]},
                display_name="Android Workflow Invalid Farmer",
                total_land_area=Decimal("2.00"),
                total_land_unit="ACRE",
                language_preference="en",
                enrollment_method="SYNC_MATERIALIZED",
                status="ACTIVE",
                created_at=now(),
                updated_at=now(),
                is_active=True,
            )
            db.add(farmer)
            db.flush()

    parcel = (
        db.query(Parcel)
        .filter(Parcel.id == PARCEL_ID, Parcel.tenant_id == TENANT_ID)
        .first()
    )
    if not parcel:
        result["parcel"] = "WOULD_CREATE" if dry_run else "CREATED"
        if not dry_run:
            parcel = Parcel(
                id=PARCEL_ID,
                tenant_id=TENANT_ID,
                farmer_id=FARMER_ID,
                project_id=PROJECT_ID,
                village_name_manual="Android Dynamic Test Village",
                pin_code="560001",
                location_scope={
                    "state_lgd_code": "29",
                    "district_lgd_code": "536",
                    "source": "ANDROID_WORKFLOW_INVALID_TEST",
                },
                reported_area=Decimal("2.00"),
                reported_area_unit="ACRE",
                current_crop_code="RICE",
                geometry_source="NONE",
                local_name="Android workflow-invalid test parcel",
                ownership_type="OWNED",
                irrigation_source="CANAL",
                crops_by_season={"KHARIF": ["RICE"]},
                status="ACTIVE",
                created_at=now(),
                updated_at=now(),
                is_active=True,
            )
            db.add(parcel)
            db.flush()
    elif not dry_run and parcel.project_id != PROJECT_ID:
        # Flow 14 deliberately moves this parcel to an alternate project.
        # Flow 16 needs the canonical Android project restored.
        parcel.project_id = PROJECT_ID
        parcel.updated_at = now()
        result["parcel"] = "RESTORED_PROJECT"

    enrollment = (
        db.query(FarmerProjectEnrollment)
        .filter(
            FarmerProjectEnrollment.tenant_id == TENANT_ID,
            FarmerProjectEnrollment.farmer_id == FARMER_ID,
            FarmerProjectEnrollment.project_id == PROJECT_ID,
        )
        .first()
    )
    if not enrollment:
        result["farmer_project_enrollment"] = "WOULD_CREATE" if dry_run else "CREATED"
        if not dry_run:
            enrollment = FarmerProjectEnrollment(
                tenant_id=TENANT_ID,
                farmer_id=FARMER_ID,
                project_id=PROJECT_ID,
                enrollment_method="SYNC_MATERIALIZED",
                enrollment_source="ANDROID_WORKFLOW_INVALID_TEST",
                status="ACTIVE",
                parcel_ids=[str(PARCEL_ID)],
                metadata_={
                    "source": "prepare_android_workflow_invalid_conflict.py",
                    "fixture_owned": True,
                },
                created_at=now(),
                updated_at=now(),
                is_active=True,
            )
            db.add(enrollment)
            db.flush()

    lifecycle_template_id = get_lifecycle_template_id(db)
    cycle = (
        db.query(CropCycle)
        .filter(CropCycle.id == CYCLE_ID, CropCycle.tenant_id == TENANT_ID)
        .first()
    )
    if not cycle:
        result["crop_cycle"] = "WOULD_CREATE" if dry_run else "CREATED"
        if not dry_run:
            cycle = CropCycle(
                id=CYCLE_ID,
                tenant_id=TENANT_ID,
                farmer_id=FARMER_ID,
                parcel_id=PARCEL_ID,
                project_id=PROJECT_ID,
                crop_code="RICE",
                season_code="KHARIF",
                lifecycle_template_id=lifecycle_template_id,
                planned_sowing_date=date(2026, 8, 2),
                actual_sowing_date=date(2026, 8, 2),
                expected_harvest_date=date(2026, 11, 30),
                status="ACTIVE",
                notes="Android WORKFLOW_INVALID conflict fixture baseline.",
                created_at=now(),
                updated_at=now(),
                is_active=True,
            )
            db.add(cycle)
            db.flush()
    elif not dry_run:
        cycle.farmer_id = FARMER_ID
        cycle.parcel_id = PARCEL_ID
        cycle.project_id = PROJECT_ID
        cycle.crop_code = "RICE"
        cycle.season_code = "KHARIF"
        cycle.lifecycle_template_id = cycle.lifecycle_template_id or lifecycle_template_id
        cycle.status = "ACTIVE"
        cycle.actual_sowing_date = cycle.actual_sowing_date or date(2026, 8, 2)
        cycle.updated_at = now()

    stage = (
        db.query(CropStageInstance)
        .filter(
            CropStageInstance.crop_cycle_id == CYCLE_ID,
            CropStageInstance.tenant_id == TENANT_ID,
            CropStageInstance.stage_code == "NURSERY",
        )
        .first()
    )
    if not stage:
        result["nursery_stage"] = "WOULD_CREATE" if dry_run else "CREATED"
        if not dry_run:
            stage = CropStageInstance(
                crop_cycle_id=CYCLE_ID,
                tenant_id=TENANT_ID,
                stage_code="NURSERY",
                stage_name="Nursery",
                stage_order=1,
                expected_duration_days=21,
                planned_start_date=date(2026, 8, 2),
                actual_start_date=date(2026, 8, 2),
                actual_end_date=None,
                status="ACTIVE",
                started_by=ACTOR_ID,
                created_at=now(),
                updated_at=now(),
                is_active=True,
            )
            db.add(stage)
            db.flush()

    return result


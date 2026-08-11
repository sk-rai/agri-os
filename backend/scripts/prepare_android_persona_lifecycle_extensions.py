"""Prepare extended Android persona lifecycle fixtures.

Builds on ``prepare_android_persona_lifecycle.py`` and adds:

- one farmer with two ACTIVE project enrollments for project-picker testing;
- a second field agent for assignment/reassignment lifecycle testing;
- a rich primary farmer plus empty duplicate farmer for duplicate cleanup testing.
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
from app.modules.auth.models import AgentProfile, User
from app.modules.farmer.models import Farmer, FarmerProjectEnrollment, Parcel, Project, ProjectRole, Tenant
from app.modules.farmer.soil_profile import SoilProfile
from app.modules.master_data.models import GeographyVillage  # noqa: F401 - load FK target metadata
from scripts.prepare_android_persona_lifecycle import CONFIG_PATCH, PERSONAS, PROJECT_ID, TENANT_ID, main as prepare_base_main


SECOND_PROJECT_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000000202")

EXT = {
    "project_picker": {
        "mobile": "+919900001601",
        "user_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001601"),
        "farmer_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001602"),
        "parcel_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001603"),
        "soil_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001604"),
        "enrollment_1_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001605"),
        "enrollment_2_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001606"),
    },
    "second_agent": {
        "mobile": "+919900001701",
        "user_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001701"),
        "project_role_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001702"),
        "agent_profile_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001703"),
    },
    "duplicate_primary": {
        "mobile": "+919900001801",
        "user_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001801"),
        "farmer_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001802"),
        "parcel_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001803"),
        "soil_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001804"),
    },
    "duplicate_empty": {
        "farmer_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001805"),
    },
    "multi_assigned": {
        "mobile": "+919900001901",
        "user_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001901"),
        "farmer_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001902"),
        "parcel_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001903"),
        "soil_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001904"),
        "enrollment_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001905"),
    },
}


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


def reset_extension_rows(db, result: dict, dry_run: bool) -> None:
    params = {
        "tenant_id": TENANT_ID,
        "project_ids": [str(PROJECT_ID), str(SECOND_PROJECT_ID)],
        "second_project_id": str(SECOND_PROJECT_ID),
        "farmer_ids": [
            str(EXT["project_picker"]["farmer_id"]),
            str(EXT["duplicate_primary"]["farmer_id"]),
            str(EXT["duplicate_empty"]["farmer_id"]),
            str(EXT["multi_assigned"]["farmer_id"]),
        ],
        "parcel_ids": [
            str(EXT["project_picker"]["parcel_id"]),
            str(EXT["duplicate_primary"]["parcel_id"]),
            str(EXT["multi_assigned"]["parcel_id"]),
        ],
        "soil_ids": [
            str(EXT["project_picker"]["soil_id"]),
            str(EXT["duplicate_primary"]["soil_id"]),
            str(EXT["multi_assigned"]["soil_id"]),
        ],
        "user_ids": [
            str(EXT["project_picker"]["user_id"]),
            str(EXT["second_agent"]["user_id"]),
            str(EXT["duplicate_primary"]["user_id"]),
            str(EXT["multi_assigned"]["user_id"]),
        ],
    }
    deletes = [
        ("soil_profiles", "delete from soil_profiles where tenant_id = :tenant_id and id = any(cast(:soil_ids as uuid[]))"),
        ("parcels", "delete from parcels where tenant_id = :tenant_id and id = any(cast(:parcel_ids as uuid[]))"),
        ("farmer_project_enrollments", "delete from farmer_project_enrollments where tenant_id = :tenant_id and farmer_id = any(cast(:farmer_ids as uuid[]))"),
        ("agent_profiles", "delete from agent_profiles where tenant_id = :tenant_id and user_id = any(cast(:user_ids as uuid[]))"),
        ("project_roles", "delete from project_roles where user_id = any(cast(:user_ids as uuid[])) and project_id = any(cast(:project_ids as uuid[]))"),
        ("user_devices", "delete from user_devices where user_id = any(cast(:user_ids as uuid[]))"),
        ("farmers", "delete from farmers where tenant_id = :tenant_id and id = any(cast(:farmer_ids as uuid[]))"),
        ("projects", "delete from projects where tenant_id = :tenant_id and id = cast(:second_project_id as uuid)"),
        ("users", "delete from users where id = any(cast(:user_ids as uuid[]))"),
    ]
    for table, sql in deletes:
        delete_if_table(db, table, sql, params, result, dry_run)


def upsert_project_two(db, result: dict, dry_run: bool) -> None:
    project = db.query(Project).filter(Project.id == SECOND_PROJECT_ID).first()
    if project:
        result["second_project"]["status"] = "EXISTS"
        if not dry_run:
            project.tenant_id = TENANT_ID
            project.name = "Android Persona Lifecycle Second Project"
            project.status = "ACTIVE"
            project.crop_scope = ["RICE", "SUGARCANE"]
            project.geography_scope = {"pin_codes": ["560001"], "village_names": ["Persona Second Project Village"]}
            project.config = CONFIG_PATCH
            project.updated_at = now()
    elif dry_run:
        result["second_project"]["status"] = "WOULD_CREATE"
    else:
        db.add(Project(
            id=SECOND_PROJECT_ID,
            tenant_id=TENANT_ID,
            name="Android Persona Lifecycle Second Project",
            description="Second active project for Android project-picker lifecycle tests.",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=180),
            status="ACTIVE",
            geography_scope={"pin_codes": ["560001"], "village_names": ["Persona Second Project Village"]},
            crop_scope=["RICE", "SUGARCANE"],
            config=CONFIG_PATCH,
            created_at=now(),
            updated_at=now(),
        ))
        result["second_project"]["status"] = "CREATED"


def upsert_user(db, key: str, *, role: str, result: dict, dry_run: bool) -> None:
    data = EXT[key]
    user = db.query(User).filter(User.id == data["user_id"]).first()
    if user:
        result["users"][key] = "EXISTS"
        if not dry_run:
            user.mobile_number = data["mobile"]
            user.role = role
            user.display_name = f"Android {key.replace('_', ' ').title()}"
            user.language_preference = "hi"
            user.tenant_id = TENANT_ID
            user.updated_at = now()
    elif dry_run:
        result["users"][key] = "WOULD_CREATE"
    else:
        db.add(User(
            id=data["user_id"],
            mobile_number=data["mobile"],
            role=role,
            display_name=f"Android {key.replace('_', ' ').title()}",
            language_preference="hi",
            tenant_id=TENANT_ID,
            created_at=now(),
            updated_at=now(),
        ))
        result["users"][key] = "CREATED"


def upsert_farmer(db, key: str, *, project_id: uuid.UUID | None, result: dict, dry_run: bool) -> None:
    data = EXT[key]
    farmer = db.query(Farmer).filter(Farmer.id == data["farmer_id"], Farmer.tenant_id == TENANT_ID).first()
    values = {
        "tenant_id": TENANT_ID,
        "project_id": project_id,
        "user_id": data.get("user_id"),
        "mobile_number": data["mobile"],
        "display_name": f"Android {key.replace('_', ' ').title()} Farmer",
        "village_name_manual": f"{key.replace('_', ' ').title()} Village",
        "pin_code": "560001",
        "primary_crop_code": "RICE",
        "crops_by_season": {"KHARIF": ["RICE"], "RABI": ["WHEAT"]},
        "total_land_area": 1.25,
        "total_land_unit": "ACRE",
        "language_preference": "hi",
        "enrollment_method": "PROJECT_INVITE" if project_id else "SELF",
        "status": "ACTIVE",
    }
    if farmer:
        result["farmers"][key] = "EXISTS"
        if not dry_run:
            for field, value in values.items():
                setattr(farmer, field, value)
            farmer.updated_at = now()
    elif dry_run:
        result["farmers"][key] = "WOULD_CREATE"
    else:
        db.add(Farmer(id=data["farmer_id"], created_at=now(), updated_at=now(), **values))
        result["farmers"][key] = "CREATED"


def upsert_parcel_soil(db, key: str, *, project_id: uuid.UUID | None, result: dict, dry_run: bool) -> None:
    data = EXT[key]
    parcel = db.query(Parcel).filter(Parcel.id == data["parcel_id"], Parcel.tenant_id == TENANT_ID).first()
    if parcel:
        result["parcels"][key] = "EXISTS"
        if not dry_run:
            parcel.farmer_id = data["farmer_id"]
            parcel.project_id = project_id
            parcel.village_name_manual = f"{key.replace('_', ' ').title()} Village"
            parcel.pin_code = "560001"
            parcel.location_scope = {"mode": "SINGLE_VILLAGE", "source": "android_persona_lifecycle_extension"}
            parcel.reported_area = 1.25
            parcel.reported_area_unit = "ACRE"
            parcel.current_crop_code = "RICE"
            parcel.soil_type_code = "BLACK_COTTON"
            parcel.local_name = f"{key.replace('_', ' ').title()} Parcel"
            parcel.ownership_type = "OWNED"
            parcel.status = "ACTIVE"
            parcel.updated_at = now()
    elif not dry_run:
        db.add(Parcel(
            id=data["parcel_id"],
            tenant_id=TENANT_ID,
            farmer_id=data["farmer_id"],
            project_id=project_id,
            village_name_manual=f"{key.replace('_', ' ').title()} Village",
            pin_code="560001",
            location_scope={"mode": "SINGLE_VILLAGE", "source": "android_persona_lifecycle_extension"},
            reported_area=1.25,
            reported_area_unit="ACRE",
            current_crop_code="RICE",
            soil_type_code="BLACK_COTTON",
            local_name=f"{key.replace('_', ' ').title()} Parcel",
            ownership_type="OWNED",
            geometry_source="PIN_DROP",
            centroid_lat=12.9716,
            centroid_lng=77.5946,
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        ))
        result["parcels"][key] = "CREATED"
    else:
        result["parcels"][key] = "WOULD_CREATE"

    soil = db.query(SoilProfile).filter(SoilProfile.id == data["soil_id"], SoilProfile.tenant_id == TENANT_ID).first()
    if soil:
        result["soil_profiles"][key] = "EXISTS"
        if not dry_run:
            soil.farmer_id = data["farmer_id"]
            soil.parcel_id = data["parcel_id"]
            soil.ph = 6.8
            soil.boron_bo = 0.45
            soil.organic_carbon_oc = 0.72
            soil.updated_at = now()
    elif not dry_run:
        db.add(SoilProfile(
            id=data["soil_id"],
            tenant_id=TENANT_ID,
            farmer_id=data["farmer_id"],
            parcel_id=data["parcel_id"],
            test_date=date(2026, 8, 6),
            ph=6.8,
            boron_bo=0.45,
            organic_carbon_oc=0.72,
            soil_type_code="BLACK_COTTON",
            data_source="ANDROID_PERSONA_EXT_SEED",
            notes="Deterministic Android persona lifecycle extension soil profile.",
            created_at=now(),
            updated_at=now(),
        ))
        result["soil_profiles"][key] = "CREATED"
    else:
        result["soil_profiles"][key] = "WOULD_CREATE"


def upsert_enrollment(db, key: str, enrollment_id: uuid.UUID, project_id: uuid.UUID, assigned_user_ids: list[str], result: dict, dry_run: bool) -> None:
    data = EXT[key]
    enrollment = db.query(FarmerProjectEnrollment).filter(FarmerProjectEnrollment.id == enrollment_id, FarmerProjectEnrollment.tenant_id == TENANT_ID).first()
    if enrollment:
        result["enrollments"][str(enrollment_id)] = "EXISTS"
        if not dry_run:
            enrollment.farmer_id = data["farmer_id"]
            enrollment.project_id = project_id
            enrollment.enrollment_method = "PROJECT_INVITE"
            enrollment.enrollment_source = "ANDROID_PERSONA_EXT_SEED"
            enrollment.status = "ACTIVE"
            enrollment.parcel_ids = [str(data["parcel_id"])]
            enrollment.assigned_user_ids = assigned_user_ids
            enrollment.metadata_ = {"persona": key, "android_test": True}
            enrollment.updated_at = now()
    elif dry_run:
        result["enrollments"][str(enrollment_id)] = "WOULD_CREATE"
    else:
        db.add(FarmerProjectEnrollment(
            id=enrollment_id,
            tenant_id=TENANT_ID,
            farmer_id=data["farmer_id"],
            project_id=project_id,
            enrollment_method="PROJECT_INVITE",
            enrollment_source="ANDROID_PERSONA_EXT_SEED",
            status="ACTIVE",
            parcel_ids=[str(data["parcel_id"])],
            assigned_user_ids=assigned_user_ids,
            metadata_={"persona": key, "android_test": True},
            notes="Deterministic Android persona lifecycle extension enrollment.",
            created_at=now(),
            updated_at=now(),
        ))
        result["enrollments"][str(enrollment_id)] = "CREATED"


def upsert_second_agent(db, result: dict, dry_run: bool) -> None:
    data = EXT["second_agent"]
    role = db.query(ProjectRole).filter(ProjectRole.id == data["project_role_id"]).first()
    if role:
        result["project_roles"]["second_agent"] = "EXISTS"
        if not dry_run:
            role.project_id = PROJECT_ID
            role.user_id = data["user_id"]
            role.role = "FIELD_AGENT"
            role.territory_scope = {"village_names": ["Assisted Village"]}
            role.updated_at = now()
    elif not dry_run:
        db.add(ProjectRole(
            id=data["project_role_id"],
            project_id=PROJECT_ID,
            user_id=data["user_id"],
            role="FIELD_AGENT",
            territory_scope={"village_names": ["Assisted Village"]},
            created_at=now(),
            updated_at=now(),
        ))
        result["project_roles"]["second_agent"] = "CREATED"
    else:
        result["project_roles"]["second_agent"] = "WOULD_CREATE"

    profile = db.query(AgentProfile).filter(AgentProfile.id == data["agent_profile_id"], AgentProfile.tenant_id == TENANT_ID).first()
    if profile:
        result["agent_profiles"]["second_agent"] = "EXISTS"
        if not dry_run:
            profile.user_id = data["user_id"]
            profile.farmer_id = None
            profile.agent_code = "ANDROID-PERSONA-AGENT-002"
            profile.role_type = "FIELD_AGENT"
            profile.display_name = "Android Reassignment Agent Two"
            profile.mobile_number = data["mobile"]
            profile.status = "ACTIVE"
            profile.skills = ["PROFILE_CAPTURE"]
            profile.languages = ["hi", "en"]
            profile.territory_scope = {"village_names": ["Assisted Village"]}
            profile.metadata_ = {"android_test": True, "reassignment_target": True}
            profile.updated_at = now()
    elif not dry_run:
        db.add(AgentProfile(
            id=data["agent_profile_id"],
            tenant_id=TENANT_ID,
            user_id=data["user_id"],
            farmer_id=None,
            agent_code="ANDROID-PERSONA-AGENT-002",
            role_type="FIELD_AGENT",
            display_name="Android Reassignment Agent Two",
            mobile_number=data["mobile"],
            status="ACTIVE",
            skills=["PROFILE_CAPTURE"],
            languages=["hi", "en"],
            territory_scope={"village_names": ["Assisted Village"]},
            availability={"mode": "FIELD_VISITS"},
            certification={},
            metadata_={"android_test": True, "reassignment_target": True},
            created_at=now(),
            updated_at=now(),
        ))
        result["agent_profiles"]["second_agent"] = "CREATED"
    else:
        result["agent_profiles"]["second_agent"] = "WOULD_CREATE"


def upsert_duplicate_empty(db, result: dict, dry_run: bool) -> None:
    primary = EXT["duplicate_primary"]
    empty = EXT["duplicate_empty"]
    farmer = db.query(Farmer).filter(Farmer.id == empty["farmer_id"], Farmer.tenant_id == TENANT_ID).first()
    if farmer:
        result["farmers"]["duplicate_empty"] = "EXISTS"
        if not dry_run:
            farmer.mobile_number = primary["mobile"]
            farmer.display_name = "Android Empty Duplicate Farmer"
            farmer.project_id = None
            farmer.user_id = None
            farmer.village_name_manual = None
            farmer.status = "ACTIVE"
            farmer.updated_at = now()
    elif dry_run:
        result["farmers"]["duplicate_empty"] = "WOULD_CREATE"
    else:
        db.add(Farmer(
            id=empty["farmer_id"],
            tenant_id=TENANT_ID,
            project_id=None,
            user_id=None,
            mobile_number=primary["mobile"],
            display_name="Android Empty Duplicate Farmer",
            language_preference="hi",
            enrollment_method="SELF",
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        ))
        result["farmers"]["duplicate_empty"] = "CREATED"


def result_template(dry_run: bool, reset: bool) -> dict:
    return {
        "schema_version": "android_persona_lifecycle_extensions_prepare.v1",
        "mode": "DRY_RUN" if dry_run else "APPLY",
        "reset_requested": reset,
        "tenant_id": TENANT_ID,
        "project_ids": [str(PROJECT_ID), str(SECOND_PROJECT_ID)],
        "second_project": {"project_id": str(SECOND_PROJECT_ID)},
        "users": {},
        "farmers": {},
        "parcels": {},
        "soil_profiles": {},
        "enrollments": {},
        "project_roles": {},
        "agent_profiles": {},
        "reset": {"deleted_counts": {}, "dry_run_delete_counts": {}, "skipped_missing_tables": []},
        "android_contract": {
            "headers": {"X-Tenant-ID": TENANT_ID},
            "project_picker": {
                "mobile": EXT["project_picker"]["mobile"],
                "user_id": str(EXT["project_picker"]["user_id"]),
                "farmer_id": str(EXT["project_picker"]["farmer_id"]),
                "project_ids": [str(PROJECT_ID), str(SECOND_PROJECT_ID)],
            },
            "agent_reassignment": {
                "assisted_farmer_id": str(PERSONAS["assisted"]["farmer_id"]),
                "primary_agent_user_id": str(PERSONAS["dual_agent"]["user_id"]),
                "second_agent_user_id": str(EXT["second_agent"]["user_id"]),
            },
            "multi_assigned_worklist": {
                "primary_agent_user_id": str(PERSONAS["dual_agent"]["user_id"]),
                "farmer_ids": [
                    str(PERSONAS["assisted"]["farmer_id"]),
                    str(EXT["multi_assigned"]["farmer_id"]),
                ],
                "mobile": EXT["multi_assigned"]["mobile"],
                "parcel_id": str(EXT["multi_assigned"]["parcel_id"]),
            },
            "duplicate_cleanup": {
                "mobile": EXT["duplicate_primary"]["mobile"],
                "primary_farmer_id": str(EXT["duplicate_primary"]["farmer_id"]),
                "duplicate_farmer_id": str(EXT["duplicate_empty"]["farmer_id"]),
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--skip-base", action="store_true", help="Do not run the base persona lifecycle prepare script first.")
    args = parser.parse_args()

    dry_run = not args.apply
    if not args.skip_base and args.apply:
        saved_argv = sys.argv
        try:
            sys.argv = ["prepare_android_persona_lifecycle.py", "--state", "base", "--apply"]
            prepare_base_main()
        finally:
            sys.argv = saved_argv

    result = result_template(dry_run, args.reset)
    db = SessionLocal()
    try:
        if args.reset:
            reset_extension_rows(db, result, dry_run)
            if dry_run:
                db.rollback()

        upsert_project_two(db, result, dry_run)
        if not dry_run:
            db.flush()
        upsert_user(db, "project_picker", role="FARMER", result=result, dry_run=dry_run)
        upsert_user(db, "second_agent", role="FIELD_AGENT", result=result, dry_run=dry_run)
        upsert_user(db, "duplicate_primary", role="FARMER", result=result, dry_run=dry_run)
        upsert_user(db, "multi_assigned", role="FARMER", result=result, dry_run=dry_run)
        if not dry_run:
            db.flush()

        upsert_farmer(db, "project_picker", project_id=None, result=result, dry_run=dry_run)
        upsert_farmer(db, "duplicate_primary", project_id=None, result=result, dry_run=dry_run)
        upsert_farmer(db, "multi_assigned", project_id=PROJECT_ID, result=result, dry_run=dry_run)
        upsert_duplicate_empty(db, result, dry_run)
        if not dry_run:
            db.flush()

        upsert_parcel_soil(db, "project_picker", project_id=None, result=result, dry_run=dry_run)
        upsert_parcel_soil(db, "duplicate_primary", project_id=None, result=result, dry_run=dry_run)
        upsert_parcel_soil(db, "multi_assigned", project_id=PROJECT_ID, result=result, dry_run=dry_run)
        upsert_enrollment(db, "project_picker", EXT["project_picker"]["enrollment_1_id"], PROJECT_ID, [], result, dry_run)
        upsert_enrollment(db, "project_picker", EXT["project_picker"]["enrollment_2_id"], SECOND_PROJECT_ID, [], result, dry_run)
        upsert_enrollment(db, "multi_assigned", EXT["multi_assigned"]["enrollment_id"], PROJECT_ID, [str(PERSONAS["dual_agent"]["user_id"])], result, dry_run)
        upsert_second_agent(db, result, dry_run)

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

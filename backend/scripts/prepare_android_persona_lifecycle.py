"""Prepare deterministic Android persona/profile lifecycle fixtures.

This script is intentionally Android-test scoped. It creates a dedicated tenant
and stable farmer/user/project rows for profile membership lifecycle Maestro
coverage without changing the default tenant posture.
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


TENANT_ID = "android-persona-lifecycle-test"
PROJECT_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000000201")

CONFIG_PATCH = {
    "feature_flags": {
        "backend_driven_farmer_forms": True,
        "backend_driven_parcel_forms": True,
        "backend_driven_soil_forms": True,
        "white_label_runtime_branding": True,
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

PERSONAS = {
    "independent": {
        "mobile": "+919900001101",
        "user_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001101"),
        "farmer_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001102"),
        "parcel_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001103"),
        "soil_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001104"),
    },
    "associated": {
        "mobile": "+919900001201",
        "user_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001201"),
        "farmer_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001202"),
        "parcel_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001203"),
        "soil_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001204"),
        "enrollment_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001205"),
    },
    "dual_agent": {
        "mobile": "+919900001301",
        "user_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001301"),
        "farmer_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001302"),
        "parcel_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001303"),
        "soil_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001304"),
        "enrollment_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001305"),
        "project_role_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001306"),
        "agent_profile_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001307"),
    },
    "assisted": {
        "mobile": "+919900001401",
        "user_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001401"),
        "farmer_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001402"),
        "parcel_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001403"),
        "soil_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001404"),
        "enrollment_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001405"),
    },
    "transition": {
        "mobile": "+919900001501",
        "user_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001501"),
        "farmer_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001502"),
        "parcel_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001503"),
        "soil_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001504"),
        "enrollment_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000001505"),
    },
}


def now() -> datetime:
    return datetime.now(timezone.utc)


def table_exists(db, table_name: str) -> bool:
    return inspect(db.bind).has_table(table_name)


def execute_delete(db, table_name: str, sql: str, params: dict, result: dict, dry_run: bool) -> None:
    if not table_exists(db, table_name):
        result["reset"]["skipped_missing_tables"].append(table_name)
        return
    if dry_run:
        count_sql = sql.replace(f"delete from {table_name}", f"select count(*) from {table_name}", 1)
        result["reset"]["dry_run_delete_counts"][table_name] = int(db.execute(text(count_sql), params).scalar() or 0)
        return
    result["reset"]["deleted_counts"][table_name] = int(db.execute(text(sql), params).rowcount or 0)


def reset_fixture(db, result: dict, dry_run: bool) -> None:
    params = {
        "tenant_id": TENANT_ID,
        "project_id": str(PROJECT_ID),
        "farmer_ids": [str(persona["farmer_id"]) for persona in PERSONAS.values()],
        "parcel_ids": [str(persona["parcel_id"]) for persona in PERSONAS.values()],
        "user_ids": [str(persona["user_id"]) for persona in PERSONAS.values()],
        "soil_ids": [str(persona["soil_id"]) for persona in PERSONAS.values()],
    }
    deletes = [
        ("soil_profiles", "delete from soil_profiles where tenant_id = :tenant_id and id = any(cast(:soil_ids as uuid[]))"),
        ("parcels", "delete from parcels where tenant_id = :tenant_id and id = any(cast(:parcel_ids as uuid[]))"),
        ("farmer_project_enrollments", "delete from farmer_project_enrollments where tenant_id = :tenant_id and (farmer_id = any(cast(:farmer_ids as uuid[])) or project_id = cast(:project_id as uuid))"),
        ("agent_profiles", "delete from agent_profiles where tenant_id = :tenant_id"),
        ("project_roles", "delete from project_roles where project_id in (select id from projects where tenant_id = :tenant_id) or user_id = any(cast(:user_ids as uuid[]))"),
        ("user_devices", "delete from user_devices where user_id = any(cast(:user_ids as uuid[]))"),
        ("farmers", "delete from farmers where tenant_id = :tenant_id and id = any(cast(:farmer_ids as uuid[]))"),
        ("projects", "delete from projects where tenant_id = :tenant_id and id = cast(:project_id as uuid)"),
        ("users", "delete from users where id = any(cast(:user_ids as uuid[]))"),
    ]
    for table_name, sql in deletes:
        execute_delete(db, table_name, sql, params, result, dry_run)


def upsert_tenant_project(db, result: dict, dry_run: bool) -> None:
    tenant = db.query(Tenant).filter(Tenant.id == TENANT_ID).first()
    if tenant:
        result["tenant"]["status"] = "EXISTS"
        if tenant.config != CONFIG_PATCH:
            result["tenant"]["config_update_needed"] = True
            if not dry_run:
                tenant.config = CONFIG_PATCH
                tenant.updated_at = now()
    elif not dry_run:
        db.add(Tenant(id=TENANT_ID, name="Android Persona Lifecycle Test Tenant", type="ENTERPRISE", config=CONFIG_PATCH, created_at=now(), updated_at=now()))
        result["tenant"]["status"] = "CREATED"
    else:
        result["tenant"]["status"] = "WOULD_CREATE"

    project = db.query(Project).filter(Project.id == PROJECT_ID).first()
    if project:
        result["project"]["status"] = "EXISTS"
        if project.config != CONFIG_PATCH:
            result["project"]["config_update_needed"] = True
            if not dry_run:
                project.config = CONFIG_PATCH
                project.updated_at = now()
    elif not dry_run:
        db.add(Project(
            id=PROJECT_ID,
            tenant_id=TENANT_ID,
            name="Android Persona Lifecycle Test Project",
            description="Dedicated Android persona/profile membership lifecycle fixture.",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=180),
            status="ACTIVE",
            geography_scope={"pin_codes": ["560001"], "village_names": ["Persona Test Village"]},
            crop_scope=["RICE", "SUGARCANE"],
            config=CONFIG_PATCH,
            created_at=now(),
            updated_at=now(),
        ))
        result["project"]["status"] = "CREATED"
    else:
        result["project"]["status"] = "WOULD_CREATE"


def upsert_user(db, key: str, role: str, result: dict, dry_run: bool) -> None:
    persona = PERSONAS[key]
    user = db.query(User).filter(User.id == persona["user_id"]).first()
    if user:
        result["users"][key] = "EXISTS"
        if not dry_run:
            user.mobile_number = persona["mobile"]
            user.role = role
            user.display_name = f"Android {key.replace('_', ' ').title()}"
            user.language_preference = "hi"
            user.tenant_id = TENANT_ID
            user.updated_at = now()
    elif not dry_run:
        db.add(User(
            id=persona["user_id"],
            mobile_number=persona["mobile"],
            role=role,
            display_name=f"Android {key.replace('_', ' ').title()}",
            language_preference="hi",
            tenant_id=TENANT_ID,
            created_at=now(),
            updated_at=now(),
        ))
        result["users"][key] = "CREATED"
    else:
        result["users"][key] = "WOULD_CREATE"


def upsert_farmer_parcel_soil(db, key: str, *, associated: bool, assigned_agent: bool, result: dict, dry_run: bool) -> None:
    persona = PERSONAS[key]
    project_id = PROJECT_ID if associated else None
    farmer = db.query(Farmer).filter(Farmer.id == persona["farmer_id"], Farmer.tenant_id == TENANT_ID).first()
    if farmer:
        result["farmers"][key] = "EXISTS"
        if not dry_run:
            farmer.project_id = project_id
            farmer.user_id = persona["user_id"]
            farmer.mobile_number = persona["mobile"]
            farmer.display_name = f"Android {key.replace('_', ' ').title()} Farmer"
            farmer.village_name_manual = f"{key.replace('_', ' ').title()} Village"
            farmer.pin_code = "560001"
            farmer.primary_crop_code = "RICE"
            farmer.crops_by_season = {"KHARIF": ["RICE"], "RABI": ["WHEAT"]}
            farmer.total_land_area = 1.25
            farmer.total_land_unit = "ACRE"
            farmer.language_preference = "hi"
            farmer.enrollment_method = "PROJECT_INVITE" if associated else "SELF"
            farmer.status = "ACTIVE"
            farmer.updated_at = now()
    elif not dry_run:
        db.add(Farmer(
            id=persona["farmer_id"],
            tenant_id=TENANT_ID,
            project_id=project_id,
            user_id=persona["user_id"],
            mobile_number=persona["mobile"],
            display_name=f"Android {key.replace('_', ' ').title()} Farmer",
            village_name_manual=f"{key.replace('_', ' ').title()} Village",
            pin_code="560001",
            primary_crop_code="RICE",
            crops_by_season={"KHARIF": ["RICE"], "RABI": ["WHEAT"]},
            total_land_area=1.25,
            total_land_unit="ACRE",
            language_preference="hi",
            enrollment_method="PROJECT_INVITE" if associated else "SELF",
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        ))
        result["farmers"][key] = "CREATED"
    else:
        result["farmers"][key] = "WOULD_CREATE"

    parcel = db.query(Parcel).filter(Parcel.id == persona["parcel_id"], Parcel.tenant_id == TENANT_ID).first()
    if parcel:
        result["parcels"][key] = "EXISTS"
        if not dry_run:
            parcel.farmer_id = persona["farmer_id"]
            parcel.project_id = project_id
            parcel.village_name_manual = f"{key.replace('_', ' ').title()} Village"
            parcel.pin_code = "560001"
            parcel.location_scope = {"mode": "SINGLE_VILLAGE", "source": "android_persona_lifecycle"}
            parcel.reported_area = 1.25
            parcel.reported_area_unit = "ACRE"
            parcel.current_crop_code = "RICE"
            parcel.soil_type_code = "BLACK_COTTON"
            parcel.local_name = f"{key.replace('_', ' ').title()} Parcel"
            parcel.ownership_type = "OWNED"
            parcel.irrigation_source = "RAIN_FED"
            parcel.crops_by_season = {"KHARIF": ["RICE"]}
            parcel.geometry_source = "PIN_DROP"
            parcel.centroid_lat = 12.9716
            parcel.centroid_lng = 77.5946
            parcel.status = "ACTIVE"
            parcel.updated_at = now()
    elif not dry_run:
        db.add(Parcel(
            id=persona["parcel_id"],
            tenant_id=TENANT_ID,
            farmer_id=persona["farmer_id"],
            project_id=project_id,
            village_name_manual=f"{key.replace('_', ' ').title()} Village",
            pin_code="560001",
            location_scope={"mode": "SINGLE_VILLAGE", "source": "android_persona_lifecycle"},
            reported_area=1.25,
            reported_area_unit="ACRE",
            current_crop_code="RICE",
            soil_type_code="BLACK_COTTON",
            local_name=f"{key.replace('_', ' ').title()} Parcel",
            ownership_type="OWNED",
            irrigation_source="RAIN_FED",
            crops_by_season={"KHARIF": ["RICE"]},
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

    soil = db.query(SoilProfile).filter(SoilProfile.id == persona["soil_id"], SoilProfile.tenant_id == TENANT_ID).first()
    if soil:
        result["soil_profiles"][key] = "EXISTS"
        if not dry_run:
            soil.farmer_id = persona["farmer_id"]
            soil.parcel_id = persona["parcel_id"]
            soil.test_date = date(2026, 8, 6)
            soil.ph = 6.8
            soil.boron_bo = 0.45
            soil.organic_carbon_oc = 0.72
            soil.soil_type_code = "BLACK_COTTON"
            soil.soil_texture = "Loamy"
            soil.data_source = "ANDROID_PERSONA_LIFECYCLE_SEED"
            soil.updated_at = now()
    elif not dry_run:
        db.add(SoilProfile(
            id=persona["soil_id"],
            tenant_id=TENANT_ID,
            farmer_id=persona["farmer_id"],
            parcel_id=persona["parcel_id"],
            test_date=date(2026, 8, 6),
            ph=6.8,
            boron_bo=0.45,
            organic_carbon_oc=0.72,
            soil_type_code="BLACK_COTTON",
            soil_texture="Loamy",
            data_source="ANDROID_PERSONA_LIFECYCLE_SEED",
            notes="Deterministic Android persona lifecycle soil profile.",
            created_at=now(),
            updated_at=now(),
        ))
        result["soil_profiles"][key] = "CREATED"
    else:
        result["soil_profiles"][key] = "WOULD_CREATE"

    if associated and "enrollment_id" in persona:
        enrollment = db.query(FarmerProjectEnrollment).filter(FarmerProjectEnrollment.id == persona["enrollment_id"], FarmerProjectEnrollment.tenant_id == TENANT_ID).first()
        assigned_user_ids = [str(PERSONAS["dual_agent"]["user_id"])] if assigned_agent else []
        if enrollment:
            result["enrollments"][key] = "EXISTS"
            if not dry_run:
                enrollment.farmer_id = persona["farmer_id"]
                enrollment.project_id = PROJECT_ID
                enrollment.enrollment_method = "PROJECT_INVITE"
                enrollment.enrollment_source = "ANDROID_PERSONA_LIFECYCLE_SEED"
                enrollment.status = "ACTIVE"
                enrollment.parcel_ids = [str(persona["parcel_id"])]
                enrollment.assigned_user_ids = assigned_user_ids
                enrollment.metadata_ = {"persona": key, "android_test": True}
                enrollment.updated_at = now()
        elif not dry_run:
            db.add(FarmerProjectEnrollment(
                id=persona["enrollment_id"],
                tenant_id=TENANT_ID,
                farmer_id=persona["farmer_id"],
                project_id=PROJECT_ID,
                enrollment_method="PROJECT_INVITE",
                enrollment_source="ANDROID_PERSONA_LIFECYCLE_SEED",
                status="ACTIVE",
                parcel_ids=[str(persona["parcel_id"])],
                assigned_user_ids=assigned_user_ids,
                metadata_={"persona": key, "android_test": True},
                notes="Deterministic Android persona lifecycle enrollment.",
                created_at=now(),
                updated_at=now(),
            ))
            result["enrollments"][key] = "CREATED"
        else:
            result["enrollments"][key] = "WOULD_CREATE"


def upsert_dual_agent(db, result: dict, dry_run: bool) -> None:
    persona = PERSONAS["dual_agent"]
    role = db.query(ProjectRole).filter(ProjectRole.id == persona["project_role_id"]).first()
    if role:
        result["project_roles"]["dual_agent"] = "EXISTS"
        if not dry_run:
            role.project_id = PROJECT_ID
            role.user_id = persona["user_id"]
            role.role = "FIELD_AGENT"
            role.territory_scope = {"village_names": ["Assisted Village", "Dual Agent Village"]}
            role.updated_at = now()
    elif not dry_run:
        db.add(ProjectRole(
            id=persona["project_role_id"],
            project_id=PROJECT_ID,
            user_id=persona["user_id"],
            role="FIELD_AGENT",
            territory_scope={"village_names": ["Assisted Village", "Dual Agent Village"]},
            created_at=now(),
            updated_at=now(),
        ))
        result["project_roles"]["dual_agent"] = "CREATED"
    else:
        result["project_roles"]["dual_agent"] = "WOULD_CREATE"

    profile = db.query(AgentProfile).filter(AgentProfile.id == persona["agent_profile_id"], AgentProfile.tenant_id == TENANT_ID).first()
    if profile:
        result["agent_profiles"]["dual_agent"] = "EXISTS"
        if not dry_run:
            profile.user_id = persona["user_id"]
            profile.farmer_id = persona["farmer_id"]
            profile.agent_code = "ANDROID-PERSONA-AGENT-001"
            profile.role_type = "FIELD_AGENT"
            profile.display_name = "Android Dual Agent Farmer"
            profile.mobile_number = persona["mobile"]
            profile.status = "ACTIVE"
            profile.skills = ["PROFILE_CAPTURE", "SOIL_SAMPLING"]
            profile.languages = ["hi", "en"]
            profile.territory_scope = {"village_names": ["Assisted Village", "Dual Agent Village"]}
            profile.metadata_ = {"can_also_act_as_farmer": True, "android_test": True}
            profile.updated_at = now()
    elif not dry_run:
        db.add(AgentProfile(
            id=persona["agent_profile_id"],
            tenant_id=TENANT_ID,
            user_id=persona["user_id"],
            farmer_id=persona["farmer_id"],
            agent_code="ANDROID-PERSONA-AGENT-001",
            role_type="FIELD_AGENT",
            display_name="Android Dual Agent Farmer",
            mobile_number=persona["mobile"],
            status="ACTIVE",
            skills=["PROFILE_CAPTURE", "SOIL_SAMPLING"],
            languages=["hi", "en"],
            territory_scope={"village_names": ["Assisted Village", "Dual Agent Village"]},
            availability={"mode": "FIELD_VISITS"},
            certification={"profile_capture": "ANDROID_TEST"},
            metadata_={"can_also_act_as_farmer": True, "android_test": True},
            created_at=now(),
            updated_at=now(),
        ))
        result["agent_profiles"]["dual_agent"] = "CREATED"
    else:
        result["agent_profiles"]["dual_agent"] = "WOULD_CREATE"


def apply_transition_state(db, state: str, result: dict, dry_run: bool) -> None:
    persona = PERSONAS["transition"]
    enrollment = db.query(FarmerProjectEnrollment).filter(FarmerProjectEnrollment.id == persona["enrollment_id"], FarmerProjectEnrollment.tenant_id == TENANT_ID).first()
    farmer = db.query(Farmer).filter(Farmer.id == persona["farmer_id"], Farmer.tenant_id == TENANT_ID).first()
    parcel = db.query(Parcel).filter(Parcel.id == persona["parcel_id"], Parcel.tenant_id == TENANT_ID).first()

    if state == "base":
        if enrollment:
            result["transition"]["enrollment_status"] = "WOULD_DELETE" if dry_run else "DELETED"
            if not dry_run:
                db.delete(enrollment)
        else:
            result["transition"]["enrollment_status"] = "ABSENT"
        if not dry_run:
            if farmer:
                farmer.project_id = None
            if parcel:
                parcel.project_id = None
        return

    status = "ACTIVE" if state == "transition-associated" else "CANCELLED"
    if not dry_run:
        if farmer:
            farmer.project_id = PROJECT_ID if status == "ACTIVE" else None
            farmer.updated_at = now()
        if parcel:
            parcel.project_id = PROJECT_ID if status == "ACTIVE" else None
            parcel.updated_at = now()
    if enrollment:
        result["transition"]["enrollment_status"] = "EXISTS"
        if not dry_run:
            enrollment.status = status
            enrollment.farmer_id = persona["farmer_id"]
            enrollment.project_id = PROJECT_ID
            enrollment.parcel_ids = [str(persona["parcel_id"])]
            enrollment.assigned_user_ids = []
            enrollment.enrollment_method = "PROJECT_INVITE"
            enrollment.enrollment_source = "ANDROID_PERSONA_LIFECYCLE_TRANSITION"
            enrollment.metadata_ = {
                "persona": "transition",
                "android_test": True,
                "lifecycle_events": [
                    {"at": now().isoformat(), "event": "ASSOCIATED" if status == "ACTIVE" else "DEACTIVATED", "source": "prepare_android_persona_lifecycle.py"}
                ],
            }
            enrollment.updated_at = now()
    elif not dry_run:
        db.add(FarmerProjectEnrollment(
            id=persona["enrollment_id"],
            tenant_id=TENANT_ID,
            farmer_id=persona["farmer_id"],
            project_id=PROJECT_ID,
            enrollment_method="PROJECT_INVITE",
            enrollment_source="ANDROID_PERSONA_LIFECYCLE_TRANSITION",
            status=status,
            parcel_ids=[str(persona["parcel_id"])],
            assigned_user_ids=[],
            metadata_={
                "persona": "transition",
                "android_test": True,
                "lifecycle_events": [
                    {"at": now().isoformat(), "event": "ASSOCIATED" if status == "ACTIVE" else "DEACTIVATED", "source": "prepare_android_persona_lifecycle.py"}
                ],
            },
            notes="Deterministic Android independent/project transition enrollment.",
            created_at=now(),
            updated_at=now(),
        ))
        result["transition"]["enrollment_status"] = "CREATED"
    else:
        result["transition"]["enrollment_status"] = "WOULD_CREATE"
    result["transition"]["target_status"] = status


def build_result(state: str, dry_run: bool, reset: bool) -> dict:
    return {
        "schema_version": "android_persona_lifecycle_prepare.v1",
        "mode": "DRY_RUN" if dry_run else "APPLY",
        "state": state,
        "reset_requested": reset,
        "tenant": {"tenant_id": TENANT_ID},
        "project": {"project_id": str(PROJECT_ID)},
        "users": {},
        "farmers": {},
        "parcels": {},
        "soil_profiles": {},
        "enrollments": {},
        "project_roles": {},
        "agent_profiles": {},
        "transition": {},
        "reset": {"deleted_counts": {}, "dry_run_delete_counts": {}, "skipped_missing_tables": []},
        "android_contract": {
            "headers": {"X-Tenant-ID": TENANT_ID},
            "project_id": str(PROJECT_ID),
            "mobiles": {key: persona["mobile"] for key, persona in PERSONAS.items()},
            "user_ids": {key: str(persona["user_id"]) for key, persona in PERSONAS.items()},
            "farmer_ids": {key: str(persona["farmer_id"]) for key, persona in PERSONAS.items()},
            "parcel_ids": {key: str(persona["parcel_id"]) for key, persona in PERSONAS.items()},
            "endpoints": {
                "profile_hydration_by_mobile": "/api/v1/farmers/by-mobile/{mobile}?include_form_contract=true",
                "farmer_launch_context": "/api/v1/farmers/{farmer_id}/launch-context",
                "mode_bootstrap": "/api/v1/auth/mode-bootstrap?user_id={user_id}&project_id={project_id}",
                "bootstrap": f"/api/v1/app-config/bootstrap?project_id={PROJECT_ID}",
                "agent_worklist": f"/api/v1/field-agent/worklist?project_id={PROJECT_ID}&assigned_only=true",
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write fixture rows. Omit for dry-run.")
    parser.add_argument("--reset", action="store_true", help="Delete deterministic fixture rows before preparing.")
    parser.add_argument("--state", choices=["base", "transition-associated", "transition-inactive"], default="base")
    args = parser.parse_args()

    dry_run = not args.apply
    result = build_result(args.state, dry_run, args.reset)

    db = SessionLocal()
    try:
        if args.reset:
            reset_fixture(db, result, dry_run)
            if dry_run:
                db.rollback()

        upsert_tenant_project(db, result, dry_run)
        if not dry_run:
            db.flush()
        for key in PERSONAS:
            upsert_user(db, key, "FIELD_AGENT" if key == "dual_agent" else "FARMER", result, dry_run)
        if not dry_run:
            db.flush()

        upsert_farmer_parcel_soil(db, "independent", associated=False, assigned_agent=False, result=result, dry_run=dry_run)
        upsert_farmer_parcel_soil(db, "associated", associated=True, assigned_agent=False, result=result, dry_run=dry_run)
        upsert_farmer_parcel_soil(db, "dual_agent", associated=True, assigned_agent=False, result=result, dry_run=dry_run)
        upsert_farmer_parcel_soil(db, "assisted", associated=True, assigned_agent=True, result=result, dry_run=dry_run)
        upsert_farmer_parcel_soil(db, "transition", associated=False, assigned_agent=False, result=result, dry_run=dry_run)
        if not dry_run:
            db.flush()
        upsert_dual_agent(db, result, dry_run)
        apply_transition_state(db, args.state, result, dry_run)

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

"""Verify Android persona/profile lifecycle fixture and endpoint contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from sqlalchemy import func

from app.core.database import SessionLocal
from app.main import app
from app.modules.auth.models import AgentProfile, User
from app.modules.farmer.models import Farmer, FarmerProjectEnrollment, Parcel, Project, ProjectRole, Tenant
from app.modules.farmer.soil_profile import SoilProfile
from app.modules.master_data.models import GeographyVillage  # noqa: F401 - load FK target metadata
from scripts.prepare_android_persona_lifecycle import PERSONAS, PROJECT_ID, TENANT_ID


def check(condition: bool, label: str, detail=None) -> None:
    print(f"{'PASS' if condition else 'FAIL'} {label}")
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str) if not isinstance(detail, str) else detail)
    if not condition:
        raise AssertionError(label)


def get_json(client: TestClient, path: str, headers: dict) -> dict:
    response = client.get(path, headers=headers)
    check(response.status_code == 200, f"GET {path} returns 200", response.text[:700])
    return response.json()


def hydration(client: TestClient, key: str, project_id: uuid.UUID | None = None) -> dict:
    mobile = PERSONAS[key]["mobile"]
    path = f"/api/v1/farmers/by-mobile/{mobile}?include_form_contract=true"
    if project_id:
        path += f"&project_id={project_id}"
    return get_json(client, path, {"X-Tenant-ID": TENANT_ID})


def launch_context(client: TestClient, key: str) -> dict:
    farmer_id = PERSONAS[key]["farmer_id"]
    return get_json(client, f"/api/v1/farmers/{farmer_id}/launch-context", {"X-Tenant-ID": TENANT_ID})


def mode_bootstrap(client: TestClient, key: str, with_project: bool = False) -> dict:
    user_id = PERSONAS[key]["user_id"]
    path = f"/api/v1/auth/mode-bootstrap?user_id={user_id}"
    if with_project:
        path += f"&project_id={PROJECT_ID}"
    return get_json(client, path, {"X-Tenant-ID": TENANT_ID})


def verify_independent(client: TestClient) -> dict:
    body = hydration(client, "independent")
    check(body["farmer"]["id"] == str(PERSONAS["independent"]["farmer_id"]), "Independent hydration uses deterministic farmer")
    check(body["project_enrollments"] == [], "Independent hydration has no project_enrollments")
    check(body["farmer_context"]["mode"] == "SELF_SERVICE", "Independent farmer context is SELF_SERVICE")
    check(body["farmer_context"]["active_project_count"] == 0, "Independent active project count is zero")
    check(body["farmer_context"]["project_selection_required"] is False, "Independent does not require project picker")
    check(body["summary"]["duplicate_farmer_count"] == 0, "Independent has no duplicate farmer rows")
    launch = launch_context(client, "independent")
    check(launch["recommended_navigation"] == "SHOW_HOME", "Independent complete profile goes home")
    check(launch["active_project_count"] == 0, "Independent launch active project count zero")
    check(launch["project_selection_required"] is False, "Independent launch does not require picker")
    bootstrap = mode_bootstrap(client, "independent")
    check(bootstrap["first_screen_hint"] == "FARMER_HOME", "Independent mode-bootstrap enters FARMER_HOME")
    check(bootstrap["modes"]["farmer"]["available"] is True, "Independent farmer mode available")
    check(bootstrap["modes"]["agent"]["available"] is False, "Independent agent mode unavailable")
    return {"hydration": body, "launch": launch, "mode_bootstrap": bootstrap}


def verify_associated(client: TestClient) -> dict:
    body = hydration(client, "associated", PROJECT_ID)
    check(body["farmer"]["id"] == str(PERSONAS["associated"]["farmer_id"]), "Associated hydration uses deterministic farmer")
    check(body["summary"]["active_project_enrollment_count"] == 1, "Associated has one active project enrollment")
    check(body["farmer_context"]["mode"] == "PROJECT", "Associated farmer context is PROJECT")
    check(body["farmer_context"]["active_project_candidate"]["project_id"] == str(PROJECT_ID), "Associated active project candidate selected")
    check(body["summary"]["duplicate_farmer_count"] == 0, "Associated has no duplicate farmer rows")
    launch = launch_context(client, "associated")
    check(launch["active_project_count"] == 1, "Associated launch active project count one")
    check(launch["active_project_candidate"]["project_id"] == str(PROJECT_ID), "Associated launch selects project candidate")
    check(launch["project_selection_required"] is False, "Associated launch does not require picker")
    app_bootstrap = get_json(client, f"/api/v1/app-config/bootstrap?project_id={PROJECT_ID}", {"X-Tenant-ID": TENANT_ID})
    check(app_bootstrap["project"]["id"] == str(PROJECT_ID), "Associated app bootstrap uses selected project_id")
    return {"hydration": body, "launch": launch, "app_bootstrap": app_bootstrap}


def verify_dual_agent(client: TestClient) -> dict:
    bootstrap = mode_bootstrap(client, "dual_agent", with_project=True)
    check(bootstrap["first_screen_hint"] == "MODE_CHOOSER", "Dual-capacity user gets MODE_CHOOSER")
    check(bootstrap["modes"]["farmer"]["available"] is True, "Dual farmer mode available")
    check(bootstrap["modes"]["agent"]["available"] is True, "Dual agent mode available")
    check(bootstrap["farmer_profile"]["id"] == str(PERSONAS["dual_agent"]["farmer_id"]), "Dual farmer profile linked")
    check(bootstrap["agent_profile"]["farmer_id"] == str(PERSONAS["dual_agent"]["farmer_id"]), "Dual agent profile links same farmer")
    check(bootstrap["endpoints"]["agent_worklist"] is not None, "Dual agent worklist endpoint provided")

    headers = {"X-Tenant-ID": TENANT_ID, "X-Actor-ID": str(PERSONAS["dual_agent"]["user_id"])}
    worklist = get_json(client, f"/api/v1/field-agent/worklist?project_id={PROJECT_ID}&assigned_only=true", headers)
    check(worklist["mode_switch"]["assigned_agent_mode"] is True, "Agent worklist reports assigned agent mode")
    check(worklist["mode_switch"]["personal_farmer_mode_available"] is True, "Agent worklist keeps personal farmer mode")
    check(worklist["mode_switch"]["personal_farmer_id"] == str(PERSONAS["dual_agent"]["farmer_id"]), "Agent worklist points to personal farmer")
    farmer_ids = {row["farmer"]["id"] for row in worklist["farmers"]}
    check(str(PERSONAS["assisted"]["farmer_id"]) in farmer_ids, "Assigned assisted farmer appears in worklist", sorted(farmer_ids))
    return {"mode_bootstrap": bootstrap, "worklist": worklist}


def verify_transition(client: TestClient, state: str) -> dict:
    body = hydration(client, "transition", PROJECT_ID)
    launch = launch_context(client, "transition")
    check(body["farmer"]["id"] == str(PERSONAS["transition"]["farmer_id"]), "Transition hydration preserves same farmer_id")
    check(body["summary"]["duplicate_farmer_count"] == 0, "Transition mobile has no duplicate farmer")
    if state == "transition-associated":
        check(body["summary"]["active_project_enrollment_count"] == 1, "Transition-associated has active enrollment")
        check(body["farmer_context"]["mode"] == "PROJECT", "Transition-associated context is PROJECT")
        check(launch["active_project_count"] == 1, "Transition-associated launch active project count one")
        check(launch["active_project_candidate"]["project_id"] == str(PROJECT_ID), "Transition-associated bootstrap candidate selected")
    elif state == "transition-inactive":
        check(body["summary"]["active_project_enrollment_count"] == 0, "Transition-inactive has no active enrollment")
        check(body["enrollment_lifecycle"]["cancelled_count"] == 1, "Transition-inactive records cancelled enrollment")
        check(body["farmer_context"]["mode"] == "SELF_SERVICE", "Transition-inactive returns to SELF_SERVICE")
        check(launch["active_project_count"] == 0, "Transition-inactive launch active project count zero")
        check(launch["active_project_candidate"] is None, "Transition-inactive has no active candidate")
    else:
        check(body["project_enrollments"] == [], "Transition-base starts without project enrollment")
        check(body["farmer_context"]["mode"] == "SELF_SERVICE", "Transition-base context is SELF_SERVICE")
        check(launch["active_project_count"] == 0, "Transition-base launch active project count zero")
    return {"hydration": body, "launch": launch}


def verify_db_integrity(state: str) -> dict:
    db = SessionLocal()
    try:
        check(db.query(Tenant).filter(Tenant.id == TENANT_ID).count() == 1, "Tenant exists exactly once")
        check(db.query(Project).filter(Project.id == PROJECT_ID, Project.tenant_id == TENANT_ID).count() == 1, "Project exists exactly once")
        result = {
            "duplicate_farmers_by_mobile": [],
            "orphan_parcels": [],
            "orphan_soil_profiles": [],
            "orphan_project_enrollments": [],
            "orphan_agent_profiles": [],
        }
        for key, persona in PERSONAS.items():
            count = db.query(Farmer).filter(Farmer.tenant_id == TENANT_ID, Farmer.mobile_number == persona["mobile"], Farmer.status != "INACTIVE").count()
            if count != 1:
                result["duplicate_farmers_by_mobile"].append({"persona": key, "mobile": persona["mobile"], "count": count})

        parcel_rows = db.query(Parcel).filter(Parcel.tenant_id == TENANT_ID).all()
        for parcel in parcel_rows:
            farmer = db.query(Farmer).filter(Farmer.id == parcel.farmer_id, Farmer.tenant_id == TENANT_ID).first()
            if not farmer:
                result["orphan_parcels"].append({"parcel_id": str(parcel.id), "farmer_id": str(parcel.farmer_id)})
            if parcel.project_id and not db.query(Project).filter(Project.id == parcel.project_id, Project.tenant_id == TENANT_ID).first():
                result["orphan_parcels"].append({"parcel_id": str(parcel.id), "project_id": str(parcel.project_id)})

        for soil in db.query(SoilProfile).filter(SoilProfile.tenant_id == TENANT_ID).all():
            farmer_ok = db.query(Farmer).filter(Farmer.id == soil.farmer_id, Farmer.tenant_id == TENANT_ID).first() is not None
            parcel = db.query(Parcel).filter(Parcel.id == soil.parcel_id, Parcel.tenant_id == TENANT_ID).first()
            if not farmer_ok or not parcel or parcel.farmer_id != soil.farmer_id:
                result["orphan_soil_profiles"].append({"soil_profile_id": str(soil.id), "farmer_id": str(soil.farmer_id), "parcel_id": str(soil.parcel_id)})

        for enrollment in db.query(FarmerProjectEnrollment).filter(FarmerProjectEnrollment.tenant_id == TENANT_ID).all():
            farmer_ok = db.query(Farmer).filter(Farmer.id == enrollment.farmer_id, Farmer.tenant_id == TENANT_ID).first() is not None
            project_ok = db.query(Project).filter(Project.id == enrollment.project_id, Project.tenant_id == TENANT_ID).first() is not None
            assigned_user_ids = [uuid.UUID(str(user_id)) for user_id in (enrollment.assigned_user_ids or [])]
            users_ok = all(db.query(User).filter(User.id == user_id, User.tenant_id == TENANT_ID).first() is not None for user_id in assigned_user_ids)
            if not farmer_ok or not project_ok or not users_ok:
                result["orphan_project_enrollments"].append({"enrollment_id": str(enrollment.id)})

        for agent in db.query(AgentProfile).filter(AgentProfile.tenant_id == TENANT_ID).all():
            user_ok = db.query(User).filter(User.id == agent.user_id, User.tenant_id == TENANT_ID).first() is not None
            farmer_ok = agent.farmer_id is None or db.query(Farmer).filter(Farmer.id == agent.farmer_id, Farmer.tenant_id == TENANT_ID).first() is not None
            role_ok = db.query(ProjectRole).filter(ProjectRole.project_id == PROJECT_ID, ProjectRole.user_id == agent.user_id).first() is not None
            if not user_ok or not farmer_ok or not role_ok:
                result["orphan_agent_profiles"].append({"agent_profile_id": str(agent.id)})

        for key, rows in result.items():
            check(rows == [], f"No {key.replace('_', ' ')}", rows)

        result["counts"] = {
            "users": db.query(User).filter(User.tenant_id == TENANT_ID).count(),
            "farmers": db.query(Farmer).filter(Farmer.tenant_id == TENANT_ID).count(),
            "parcels": db.query(Parcel).filter(Parcel.tenant_id == TENANT_ID).count(),
            "soil_profiles": db.query(SoilProfile).filter(SoilProfile.tenant_id == TENANT_ID).count(),
            "project_enrollments": db.query(FarmerProjectEnrollment).filter(FarmerProjectEnrollment.tenant_id == TENANT_ID).count(),
            "active_project_enrollments": db.query(FarmerProjectEnrollment).filter(FarmerProjectEnrollment.tenant_id == TENANT_ID, FarmerProjectEnrollment.status == "ACTIVE").count(),
            "agent_profiles": db.query(AgentProfile).filter(AgentProfile.tenant_id == TENANT_ID).count(),
        }
        result["farmer_mobile_counts"] = {
            mobile: count
            for mobile, count in db.query(Farmer.mobile_number, func.count(Farmer.id)).filter(Farmer.tenant_id == TENANT_ID).group_by(Farmer.mobile_number).all()
        }
        return result
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", choices=["base", "transition-associated", "transition-inactive"], default="base")
    args = parser.parse_args()

    print("=" * 72)
    print("ANDROID PERSONA LIFECYCLE VERIFIER")
    print("=" * 72)
    print(f"state={args.state}")

    client = TestClient(app)
    result = {
        "schema_version": "android_persona_lifecycle_verification.v1",
        "tenant_id": TENANT_ID,
        "project_id": str(PROJECT_ID),
        "state": args.state,
        "personas": {},
        "db_integrity": {},
        "android_visible_copy": {
            "mode_switch_title": "Choose how to continue",
            "farmer_mode_label": "My farm",
            "agent_mode_label": "Assigned farmers",
            "project_picker_title": "Choose project",
            "independent_context_label": "Continue independently",
        },
    }

    result["personas"]["independent"] = verify_independent(client)
    result["personas"]["associated"] = verify_associated(client)
    result["personas"]["dual_agent"] = verify_dual_agent(client)
    result["personas"]["transition"] = verify_transition(client, args.state)
    result["db_integrity"] = verify_db_integrity(args.state)

    print("=" * 72)
    print("ANDROID PERSONA LIFECYCLE VERIFIED")
    print("=" * 72)
    print(json.dumps({
        "schema_version": result["schema_version"],
        "tenant_id": result["tenant_id"],
        "project_id": result["project_id"],
        "state": result["state"],
        "db_integrity": result["db_integrity"],
        "android_visible_copy": result["android_visible_copy"],
    }, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

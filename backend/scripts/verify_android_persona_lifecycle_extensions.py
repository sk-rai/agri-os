"""Verify Android persona lifecycle extension contracts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.auth.models import AgentProfile, User
from app.modules.farmer.models import Farmer, FarmerProjectEnrollment, Parcel, Project
from app.modules.farmer.soil_profile import SoilProfile
from app.modules.master_data.models import GeographyVillage  # noqa: F401 - load FK target metadata
from scripts.prepare_android_persona_lifecycle import PERSONAS, PROJECT_ID, TENANT_ID
from scripts.prepare_android_persona_lifecycle_extensions import EXT, SECOND_PROJECT_ID


def check(condition: bool, label: str, detail=None) -> None:
    print(f"{'PASS' if condition else 'FAIL'} {label}")
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str) if not isinstance(detail, str) else detail)
    if not condition:
        raise AssertionError(label)


def get_json(client: TestClient, path: str, headers: dict) -> dict:
    response = client.get(path, headers=headers)
    check(response.status_code == 200, f"GET {path} returns 200", response.text[:800])
    return response.json()


def post_json(client: TestClient, path: str, headers: dict, body: dict) -> dict:
    response = client.post(path, headers=headers, json=body)
    check(response.status_code == 200, f"POST {path} returns 200", response.text[:800])
    return response.json()


def verify_project_picker(client: TestClient) -> dict:
    persona = EXT["project_picker"]
    headers = {"X-Tenant-ID": TENANT_ID}
    hydration = get_json(client, f"/api/v1/farmers/by-mobile/{persona['mobile']}?include_form_contract=true", headers)
    check(hydration["farmer"]["id"] == str(persona["farmer_id"]), "Project-picker hydration preserves farmer_id")
    check(hydration["summary"]["active_project_enrollment_count"] == 2, "Project-picker farmer has two active enrollments")
    check(hydration["farmer_context"]["mode"] == "PROJECT_PICKER", "Project-picker hydration mode is PROJECT_PICKER")
    check(hydration["farmer_context"]["project_selection_required"] is True, "Hydration requires project selection")
    project_ids = {row["project_id"] for row in hydration["project_enrollments"]}
    check(project_ids == {str(PROJECT_ID), str(SECOND_PROJECT_ID)}, "Hydration returns both project choices", sorted(project_ids))
    check(hydration["summary"]["duplicate_farmer_count"] == 0, "Project-picker mobile has no duplicate farmer")

    launch = get_json(client, f"/api/v1/farmers/{persona['farmer_id']}/launch-context", headers)
    check(launch["recommended_navigation"] == "SHOW_PROJECT_PICKER", "Launch context routes to project picker")
    check(launch["project_selection_required"] is True, "Launch context requires project picker")
    check(launch["active_project_count"] == 2, "Launch context reports two active projects")
    check(launch["active_project_candidate"] is None, "No accidental default active project candidate selected")
    check(launch["endpoints"]["bootstrap"] == "/api/v1/app-config/bootstrap", "Bootstrap endpoint stays unscoped until Android selects project")

    bootstrap_one = get_json(client, f"/api/v1/app-config/bootstrap?project_id={PROJECT_ID}", headers)
    bootstrap_two = get_json(client, f"/api/v1/app-config/bootstrap?project_id={SECOND_PROJECT_ID}", headers)
    check(bootstrap_one["project"]["id"] == str(PROJECT_ID), "Selected first project drives bootstrap")
    check(bootstrap_two["project"]["id"] == str(SECOND_PROJECT_ID), "Selected second project drives bootstrap")
    return {"hydration": hydration, "launch": launch, "bootstrap_project_ids": [bootstrap_one["project"]["id"], bootstrap_two["project"]["id"]]}


def worklist_farmer_ids(client: TestClient, actor_id, *, assigned_only: bool) -> set[str]:
    headers = {"X-Tenant-ID": TENANT_ID, "X-Actor-ID": str(actor_id)}
    body = get_json(client, f"/api/v1/field-agent/worklist?project_id={PROJECT_ID}&assigned_only={'true' if assigned_only else 'false'}", headers)
    return {row["farmer"]["id"] for row in body["farmers"]}


def verify_agent_reassignment(client: TestClient, *, perform_reassignment: bool) -> dict:
    assisted_farmer_id = PERSONAS["assisted"]["farmer_id"]
    primary_agent = PERSONAS["dual_agent"]["user_id"]
    second_agent = EXT["second_agent"]["user_id"]

    before_primary = worklist_farmer_ids(client, primary_agent, assigned_only=True)
    before_second = worklist_farmer_ids(client, second_agent, assigned_only=True)
    check(str(assisted_farmer_id) in before_primary, "Assisted farmer starts assigned to primary dual agent", sorted(before_primary))
    check(str(assisted_farmer_id) not in before_second, "Assisted farmer not initially assigned to second agent", sorted(before_second))

    result = {"before_primary": sorted(before_primary), "before_second": sorted(before_second)}
    if perform_reassignment:
        headers = {"X-Tenant-ID": TENANT_ID, "X-Actor-ID": str(primary_agent)}
        unassign = post_json(client, f"/api/v1/farmers/{assisted_farmer_id}/project-agent-assignment", headers, {
            "project_id": str(PROJECT_ID),
            "agent_user_id": str(primary_agent),
            "action": "UNASSIGN",
            "reason": "Android persona lifecycle reassignment verifier unassign primary",
        })
        check(str(primary_agent) not in unassign["assigned_user_ids"], "Primary agent removed from assigned_user_ids")
        assign = post_json(client, f"/api/v1/farmers/{assisted_farmer_id}/project-agent-assignment", headers, {
            "project_id": str(PROJECT_ID),
            "agent_user_id": str(second_agent),
            "action": "ASSIGN",
            "reason": "Android persona lifecycle reassignment verifier assign second",
        })
        check(str(second_agent) in assign["assigned_user_ids"], "Second agent added to assigned_user_ids")

        after_primary = worklist_farmer_ids(client, primary_agent, assigned_only=True)
        after_second = worklist_farmer_ids(client, second_agent, assigned_only=True)
        check(str(assisted_farmer_id) not in after_primary, "Assisted farmer disappears from primary assigned worklist")
        check(str(assisted_farmer_id) in after_second, "Assisted farmer appears in second agent assigned worklist")
        result.update({"after_primary": sorted(after_primary), "after_second": sorted(after_second), "assignment_payload": assign})
    return result


def verify_duplicate_cleanup(client: TestClient, *, archive_duplicate: bool) -> dict:
    primary = EXT["duplicate_primary"]
    duplicate = EXT["duplicate_empty"]
    headers = {"X-Tenant-ID": TENANT_ID}
    hydration = get_json(client, f"/api/v1/farmers/by-mobile/{primary['mobile']}?include_form_contract=true", headers)
    check(hydration["farmer"]["id"] == str(primary["farmer_id"]), "Duplicate hydration selects richer primary farmer")
    check(hydration["summary"]["duplicate_farmer_count"] == 1, "Duplicate hydration reports one duplicate")
    check(hydration["duplicates"][0]["id"] == str(duplicate["farmer_id"]), "Duplicate payload exposes empty duplicate id")

    listing = get_json(client, f"/api/v1/farmers/duplicates?mobile_number={primary['mobile']}", headers)
    check(listing["group_count"] == 1, "Duplicate list returns one group")
    check(listing["groups"][0]["recommended_primary_farmer_id"] == str(primary["farmer_id"]), "Duplicate list recommends richer profile")

    result = {"hydration": hydration, "listing": listing}
    if archive_duplicate:
        archive = post_json(client, f"/api/v1/farmers/{primary['farmer_id']}/duplicates/archive", {
            "X-Tenant-ID": TENANT_ID,
            "X-Actor-ID": str(primary["user_id"]),
        }, {
            "duplicate_farmer_ids": [str(duplicate["farmer_id"])],
            "reason": "Android persona lifecycle duplicate cleanup verifier",
        })
        check(archive["archived"][0]["id"] == str(duplicate["farmer_id"]), "Archive response includes duplicate farmer")
        after = get_json(client, f"/api/v1/farmers/by-mobile/{primary['mobile']}", headers)
        check(after["farmer"]["id"] == str(primary["farmer_id"]), "Hydration still returns primary after archive")
        check(after["summary"]["duplicate_farmer_count"] == 0, "Archived duplicate no longer counted")
        result.update({"archive": archive, "after_archive": after})
    return result


def verify_db_integrity(*, expect_duplicate: bool) -> dict:
    db = SessionLocal()
    try:
        result = {
            "orphan_parcels": [],
            "orphan_soil_profiles": [],
            "orphan_project_enrollments": [],
            "orphan_agent_profiles": [],
        }
        for parcel in db.query(Parcel).filter(Parcel.tenant_id == TENANT_ID).all():
            farmer = db.query(Farmer).filter(Farmer.id == parcel.farmer_id, Farmer.tenant_id == TENANT_ID).first()
            project_ok = parcel.project_id is None or db.query(Project).filter(Project.id == parcel.project_id, Project.tenant_id == TENANT_ID).first() is not None
            if not farmer or not project_ok:
                result["orphan_parcels"].append({"parcel_id": str(parcel.id)})
        for soil in db.query(SoilProfile).filter(SoilProfile.tenant_id == TENANT_ID).all():
            farmer_ok = db.query(Farmer).filter(Farmer.id == soil.farmer_id, Farmer.tenant_id == TENANT_ID).first() is not None
            parcel = db.query(Parcel).filter(Parcel.id == soil.parcel_id, Parcel.tenant_id == TENANT_ID).first()
            if not farmer_ok or not parcel or parcel.farmer_id != soil.farmer_id:
                result["orphan_soil_profiles"].append({"soil_profile_id": str(soil.id)})
        for enrollment in db.query(FarmerProjectEnrollment).filter(FarmerProjectEnrollment.tenant_id == TENANT_ID).all():
            farmer_ok = db.query(Farmer).filter(Farmer.id == enrollment.farmer_id, Farmer.tenant_id == TENANT_ID).first() is not None
            project_ok = db.query(Project).filter(Project.id == enrollment.project_id, Project.tenant_id == TENANT_ID).first() is not None
            assigned_ok = all(db.query(User).filter(User.id == value, User.tenant_id == TENANT_ID).first() is not None for value in [str(v) for v in (enrollment.assigned_user_ids or [])])
            if not farmer_ok or not project_ok or not assigned_ok:
                result["orphan_project_enrollments"].append({"enrollment_id": str(enrollment.id)})
        for profile in db.query(AgentProfile).filter(AgentProfile.tenant_id == TENANT_ID).all():
            user_ok = db.query(User).filter(User.id == profile.user_id, User.tenant_id == TENANT_ID).first() is not None
            farmer_ok = profile.farmer_id is None or db.query(Farmer).filter(Farmer.id == profile.farmer_id, Farmer.tenant_id == TENANT_ID).first() is not None
            if not user_ok or not farmer_ok:
                result["orphan_agent_profiles"].append({"agent_profile_id": str(profile.id)})
        for key, rows in result.items():
            check(rows == [], f"No {key.replace('_', ' ')}", rows)

        duplicate_count = db.query(Farmer).filter(
            Farmer.tenant_id == TENANT_ID,
            Farmer.mobile_number == EXT["duplicate_primary"]["mobile"],
            Farmer.status != "ARCHIVED",
        ).count()
        check(duplicate_count == (2 if expect_duplicate else 1), "Duplicate cleanup active farmer count matches expected state", {"count": duplicate_count, "expect_duplicate": expect_duplicate})
        result["duplicate_mobile_active_farmer_count"] = duplicate_count
        return result
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--perform-reassignment", action="store_true", help="Exercise unassign primary + assign second agent endpoint.")
    parser.add_argument("--archive-duplicate", action="store_true", help="Archive the controlled empty duplicate farmer.")
    args = parser.parse_args()

    print("=" * 72)
    print("ANDROID PERSONA LIFECYCLE EXTENSION VERIFIER")
    print("=" * 72)
    client = TestClient(app)
    result = {
        "schema_version": "android_persona_lifecycle_extensions_verification.v1",
        "tenant_id": TENANT_ID,
        "project_ids": [str(PROJECT_ID), str(SECOND_PROJECT_ID)],
        "project_picker": verify_project_picker(client),
        "agent_reassignment": verify_agent_reassignment(client, perform_reassignment=args.perform_reassignment),
        "duplicate_cleanup": verify_duplicate_cleanup(client, archive_duplicate=args.archive_duplicate),
        "db_integrity": verify_db_integrity(expect_duplicate=not args.archive_duplicate),
        "android_visible_copy": {
            "project_picker_title": "Choose project",
            "agent_reassignment_empty_state": "No assigned farmers",
            "duplicate_cleanup_action": "Use existing profile",
        },
    }
    print("=" * 72)
    print("ANDROID PERSONA LIFECYCLE EXTENSIONS VERIFIED")
    print("=" * 72)
    print(json.dumps({
        "schema_version": result["schema_version"],
        "tenant_id": result["tenant_id"],
        "project_ids": result["project_ids"],
        "db_integrity": result["db_integrity"],
        "android_visible_copy": result["android_visible_copy"],
    }, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

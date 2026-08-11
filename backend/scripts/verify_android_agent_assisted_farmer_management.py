#!/usr/bin/env python3
"""Verify assigned field-agent assisted farmer management.

Diagnostic contract:
- assigned field agent sees assisted farmer in assigned_only worklist;
- assigned field agent can update assisted farmer + parcel;
- unassigned field agent should be blocked from the same updates.

If unassigned updates return 200, script reports backend hardening gap.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import SessionLocal
from app.main import app
from scripts.prepare_android_persona_lifecycle import PERSONAS, PROJECT_ID, TENANT_ID
from scripts.prepare_android_persona_lifecycle_extensions import EXT


PRIMARY_AGENT_USER_ID = PERSONAS["dual_agent"]["user_id"]
SECOND_AGENT_USER_ID = EXT["second_agent"]["user_id"]
ASSISTED_FARMER_ID = PERSONAS["assisted"]["farmer_id"]
ASSISTED_PARCEL_ID = PERSONAS["assisted"]["parcel_id"]
MULTI_ASSIGNED_FARMER_ID = EXT["multi_assigned"]["farmer_id"]
MULTI_ASSIGNED_PARCEL_ID = EXT["multi_assigned"]["parcel_id"]
INDEPENDENT_FARMER_ID = PERSONAS["independent"]["farmer_id"]


def h(actor_id: UUID) -> dict[str, str]:
    return {"X-Tenant-ID": TENANT_ID, "X-Actor-ID": str(actor_id)}


def json_or_text(response):
    content_type = response.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        return response.json()
    return response.text


def get_worklist(client: TestClient, actor_id: UUID) -> dict:
    response = client.get(
        f"/api/v1/field-agent/worklist?project_id={PROJECT_ID}&assigned_only=true",
        headers=h(actor_id),
    )
    farmer_ids = []
    if response.status_code == 200:
        farmer_ids = [
            item.get("farmer", {}).get("id")
            for item in response.json().get("farmers", [])
            if item.get("farmer", {}).get("id")
        ]
    return {
        "status_code": response.status_code,
        "farmer_ids": farmer_ids,
        "body": json_or_text(response),
    }


def current_state(db) -> dict:
    farmer = db.execute(
        text("""
            select id::text, display_name, village_name_manual, language_preference
            from farmers
            where tenant_id = :tenant_id and id = cast(:farmer_id as uuid)
        """),
        {"tenant_id": TENANT_ID, "farmer_id": str(ASSISTED_FARMER_ID)},
    ).mappings().first()

    parcel = db.execute(
        text("""
            select id::text, local_name, reported_area, reported_area_unit, pin_code, location_scope
            from parcels
            where tenant_id = :tenant_id and id = cast(:parcel_id as uuid)
        """),
        {"tenant_id": TENANT_ID, "parcel_id": str(ASSISTED_PARCEL_ID)},
    ).mappings().first()

    enrollment = db.execute(
        text("""
            select id::text, assigned_user_ids, status
            from farmer_project_enrollments
            where tenant_id = :tenant_id
              and farmer_id = cast(:farmer_id as uuid)
              and project_id = cast(:project_id as uuid)
            order by created_at desc
            limit 1
        """),
        {
            "tenant_id": TENANT_ID,
            "farmer_id": str(ASSISTED_FARMER_ID),
            "project_id": str(PROJECT_ID),
        },
    ).mappings().first()

    return {
        "farmer": dict(farmer) if farmer else None,
        "parcel": dict(parcel) if parcel else None,
        "enrollment": dict(enrollment) if enrollment else None,
    }


def restore_state(db, before: dict) -> None:
    farmer = before.get("farmer")
    parcel = before.get("parcel")

    if farmer:
        db.execute(
            text("""
                update farmers
                set display_name = :display_name,
                    village_name_manual = :village_name_manual,
                    language_preference = :language_preference,
                    updated_at = now()
                where tenant_id = :tenant_id and id = cast(:farmer_id as uuid)
            """),
            {
                "tenant_id": TENANT_ID,
                "farmer_id": str(ASSISTED_FARMER_ID),
                "display_name": farmer["display_name"],
                "village_name_manual": farmer["village_name_manual"],
                "language_preference": farmer["language_preference"],
            },
        )

    if parcel:
        db.execute(
            text("""
                update parcels
                set local_name = :local_name,
                    reported_area = :reported_area,
                    reported_area_unit = :reported_area_unit,
                    pin_code = :pin_code,
                    location_scope = cast(:location_scope as jsonb),
                    updated_at = now()
                where tenant_id = :tenant_id and id = cast(:parcel_id as uuid)
            """),
            {
                "tenant_id": TENANT_ID,
                "parcel_id": str(ASSISTED_PARCEL_ID),
                "local_name": parcel["local_name"],
                "reported_area": parcel["reported_area"],
                "reported_area_unit": parcel["reported_area_unit"],
                "pin_code": parcel["pin_code"],
                "location_scope": json.dumps(parcel["location_scope"] or {}),
            },
        )

    db.commit()


def main() -> int:
    client = TestClient(app)
    db = SessionLocal()

    result = {
        "schema_version": "android_agent_assisted_farmer_management_verification.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tenant_id": TENANT_ID,
        "project_id": str(PROJECT_ID),
        "assigned_primary_agent_user_id": str(PRIMARY_AGENT_USER_ID),
        "unassigned_second_agent_user_id": str(SECOND_AGENT_USER_ID),
        "assisted_farmer_id": str(ASSISTED_FARMER_ID),
        "assisted_parcel_id": str(ASSISTED_PARCEL_ID),
        "multi_assigned_farmer_id": str(MULTI_ASSIGNED_FARMER_ID),
        "multi_assigned_parcel_id": str(MULTI_ASSIGNED_PARCEL_ID),
        "independent_farmer_id": str(INDEPENDENT_FARMER_ID),
        "mode": "MUTATING_VERIFIER_WITH_RESTORE",
        "external_calls_made": False,
        "db_writes_made": True,
        "restore_command": "cd ~/projects/farmint/backend && ../venv/bin/python scripts/prepare_android_persona_lifecycle_extensions.py --reset --apply",
    }

    try:
        before = current_state(db)
        result["before"] = before

        if not before["farmer"] or not before["parcel"] or not before["enrollment"]:
            result["readiness"] = {
                "baseline_present": False,
                "ready_for_android_agent_assisted_maestro": False,
                "reason": "Run prepare_android_persona_lifecycle_extensions.py --reset --apply first.",
            }
            print(json.dumps(result, indent=2, sort_keys=True, default=str))
            return 1

        primary_worklist = get_worklist(client, PRIMARY_AGENT_USER_ID)
        second_worklist = get_worklist(client, SECOND_AGENT_USER_ID)

        assigned_farmer_update = client.patch(
            f"/api/v1/farmers/{ASSISTED_FARMER_ID}",
            headers=h(PRIMARY_AGENT_USER_ID),
            json={
                "display_name": "Android Assisted Farmer Updated By Assigned Agent",
                "village_name_manual": "Assisted Village",
                "language_preference": "hi",
                "assistance_mode": "FIELD_AGENT_ASSISTED",
            },
        )

        assigned_parcel_update = client.patch(
            f"/api/v1/parcels/{ASSISTED_PARCEL_ID}",
            headers=h(PRIMARY_AGENT_USER_ID),
            json={
                "local_name": "Assigned Agent Updated Plot",
                "reported_area": 1.75,
                "reported_area_unit": "ACRE",
                "pin_code": "560001",
                "location_scope": {
                    "primary_village": "Assisted Village",
                    "source": "agent_assisted_management_verifier",
                },
            },
        )

        unassigned_farmer_probe = client.patch(
            f"/api/v1/farmers/{ASSISTED_FARMER_ID}",
            headers=h(SECOND_AGENT_USER_ID),
            json={
                "display_name": "UNASSIGNED AGENT UPDATE PROBE",
                "village_name_manual": "Assisted Village",
                "language_preference": "hi",
                "assistance_mode": "FIELD_AGENT_ASSISTED",
            },
        )

        unassigned_parcel_probe = client.patch(
            f"/api/v1/parcels/{ASSISTED_PARCEL_ID}",
            headers=h(SECOND_AGENT_USER_ID),
            json={
                "local_name": "UNASSIGNED AGENT PARCEL PROBE",
                "reported_area": 1.8,
                "reported_area_unit": "ACRE",
                "pin_code": "560001",
                "location_scope": {
                    "primary_village": "Assisted Village",
                    "source": "unassigned_agent_probe",
                },
            },
        )

        restore_state(db, before)

        result["worklists"] = {
            "primary_agent": {
                "status_code": primary_worklist["status_code"],
                "farmer_ids": primary_worklist["farmer_ids"],
                "assisted_farmer_visible": str(ASSISTED_FARMER_ID) in primary_worklist["farmer_ids"],
                "multi_assigned_farmer_visible": str(MULTI_ASSIGNED_FARMER_ID) in primary_worklist["farmer_ids"],
                "assigned_farmer_count": len(primary_worklist["farmer_ids"]),
                "independent_farmer_visible": str(INDEPENDENT_FARMER_ID) in primary_worklist["farmer_ids"],
            },
            "second_agent": {
                "status_code": second_worklist["status_code"],
                "farmer_ids": second_worklist["farmer_ids"],
                "assisted_farmer_visible": str(ASSISTED_FARMER_ID) in second_worklist["farmer_ids"],
            },
        }

        result["updates"] = {
            "assigned_agent_farmer_patch": {
                "status_code": assigned_farmer_update.status_code,
                "supported": assigned_farmer_update.status_code == 200,
            },
            "assigned_agent_parcel_patch": {
                "status_code": assigned_parcel_update.status_code,
                "supported": assigned_parcel_update.status_code == 200,
            },
            "unassigned_agent_farmer_patch_probe": {
                "status_code": unassigned_farmer_probe.status_code,
                "blocked": unassigned_farmer_probe.status_code in (401, 403, 404),
                "mutated_or_allowed": unassigned_farmer_probe.status_code == 200,
            },
            "unassigned_agent_parcel_patch_probe": {
                "status_code": unassigned_parcel_probe.status_code,
                "blocked": unassigned_parcel_probe.status_code in (401, 403, 404),
                "mutated_or_allowed": unassigned_parcel_probe.status_code == 200,
            },
        }

        assigned_visible = result["worklists"]["primary_agent"]["assisted_farmer_visible"]
        multi_assigned_visible = result["worklists"]["primary_agent"]["multi_assigned_farmer_visible"]
        primary_has_multiple_assigned = result["worklists"]["primary_agent"]["assigned_farmer_count"] >= 2
        independent_hidden = not result["worklists"]["primary_agent"]["independent_farmer_visible"]
        second_hidden = not result["worklists"]["second_agent"]["assisted_farmer_visible"]
        assigned_update_supported = (
            result["updates"]["assigned_agent_farmer_patch"]["supported"]
            and result["updates"]["assigned_agent_parcel_patch"]["supported"]
        )
        unassigned_blocked = (
            result["updates"]["unassigned_agent_farmer_patch_probe"]["blocked"]
            and result["updates"]["unassigned_agent_parcel_patch_probe"]["blocked"]
        )

        result["readiness"] = {
            "baseline_present": True,
            "assigned_agent_can_review_assisted_farmer": assigned_visible,
            "assigned_agent_can_update_assisted_farmer_profile": assigned_update_supported,
            "assigned_agent_can_review_multiple_assigned_farmers": primary_has_multiple_assigned,
            "multi_assigned_farmer_visible": multi_assigned_visible,
            "assigned_only_worklist_excludes_independent_farmer": independent_hidden,
            "unassigned_agent_hidden_from_assisted_farmer": second_hidden,
            "unassigned_agent_update_blocked": unassigned_blocked,
            "needs_assignment_authorization_hardening": not unassigned_blocked,
            "ready_for_android_agent_assisted_maestro": assigned_visible and multi_assigned_visible and primary_has_multiple_assigned and assigned_update_supported and independent_hidden and second_hidden and unassigned_blocked,
        }

        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

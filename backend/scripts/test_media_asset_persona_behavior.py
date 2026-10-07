#!/usr/bin/env python3
"""HTTP behavior contract for persona-scoped media asset mutations."""

import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.auth.models import AgentProfile
from app.modules.farmer.models import (
    Farmer,
    FarmerProjectEnrollment,
    Project,
    ProjectRole,
    Tenant,
)
from app.modules.media.models import MediaAsset
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin


def now():
    return datetime.now(timezone.utc)


def require(condition, label, detail=None):
    if not condition:
        if detail is not None:
            print(detail)
        raise AssertionError(label)
    print(f"PASS {label}")


def make_farmer(tenant_id, project_id, name, user_id=None):
    return Farmer(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        project_id=project_id,
        user_id=user_id,
        mobile_number=f"9{uuid.uuid4().int % 1000000000:09d}",
        display_name=name,
        village_name_manual="Media Persona Village",
        total_land_unit="ACRE",
        status="ACTIVE",
        created_at=now(),
        updated_at=now(),
    )


def make_profile(tenant_id, user, farmer_id, code, role_type):
    return AgentProfile(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user.id,
        farmer_id=farmer_id,
        agent_code=code,
        role_type=role_type,
        display_name=code,
        mobile_number=user.mobile_number,
        status="ACTIVE",
        skills=["CROP_HEALTH"],
        languages=["hi"],
        territory_scope={"village_names": ["Media Persona Village"]},
        availability={},
        certification={},
        metadata_={"regression": True},
        created_at=now(),
        updated_at=now(),
    )


def make_role(project_id, user_id, role):
    return ProjectRole(
        id=uuid.uuid4(),
        project_id=project_id,
        user_id=user_id,
        role=role,
        territory_scope={"village_names": ["Media Persona Village"]},
        created_at=now(),
        updated_at=now(),
    )


def asset_body(project_id, farmer_id, marker):
    return {
        "project_id": str(project_id),
        "farmer_id": str(farmer_id),
        "media_type": "PHOTO",
        "mime_type": "image/jpeg",
        "metadata": {"marker": marker},
    }


def main():
    tenant_id = f"media-persona-{uuid.uuid4().hex[:8]}"
    project_id = uuid.uuid4()
    created_user_ids = []
    created_asset_ids = []

    db = SessionLocal()
    db.expire_on_commit = False
    try:
        db.add(Tenant(
            id=tenant_id,
            name="Media Persona Tenant",
            type="ENTERPRISE",
            created_at=now(),
            updated_at=now(),
        ))
        db.commit()

        farmer_user, farmer_headers = create_test_admin(
            db,
            tenant_id=tenant_id,
            role="FARMER",
        )
        agent_user, agent_headers = create_test_admin(
            db,
            tenant_id=tenant_id,
            role="FIELD_AGENT",
        )
        dual_user, dual_headers = create_test_admin(
            db,
            tenant_id=tenant_id,
            role="AGRONOMIST",
        )
        unassigned_user, unassigned_headers = create_test_admin(
            db,
            tenant_id=tenant_id,
            role="FIELD_AGENT",
        )
        created_user_ids.extend([
            farmer_user.id,
            agent_user.id,
            dual_user.id,
            unassigned_user.id,
        ])

        project = Project(
            id=project_id,
            tenant_id=tenant_id,
            name="Media Persona Project",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=180),
            status="ACTIVE",
            geography_scope={},
            crop_scope=["RICE"],
            config={},
            created_at=now(),
            updated_at=now(),
        )
        db.add(project)
        db.flush()

        farmer_own = make_farmer(
            tenant_id,
            project_id,
            "Farmer Personal Farm",
            farmer_user.id,
        )
        dual_own = make_farmer(
            tenant_id,
            project_id,
            "Dual Personal Farm",
            dual_user.id,
        )
        assisted = make_farmer(
            tenant_id,
            project_id,
            "Assigned Assisted Farmer",
        )
        unassigned = make_farmer(
            tenant_id,
            project_id,
            "Unassigned Farmer",
        )
        db.add_all([farmer_own, dual_own, assisted, unassigned])
        db.flush()

        agent_profile = make_profile(
            tenant_id,
            agent_user,
            None,
            "MEDIA-AGENT",
            "FIELD_AGENT",
        )
        dual_profile = make_profile(
            tenant_id,
            dual_user,
            dual_own.id,
            "MEDIA-DUAL",
            "AGRONOMIST",
        )
        unassigned_profile = make_profile(
            tenant_id,
            unassigned_user,
            None,
            "MEDIA-UNASSIGNED",
            "FIELD_AGENT",
        )
        db.add_all([
            agent_profile,
            dual_profile,
            unassigned_profile,
        ])

        agent_role = make_role(project_id, agent_user.id, "FIELD_AGENT")
        dual_role = make_role(project_id, dual_user.id, "AGRONOMIST")
        unassigned_role = make_role(
            project_id,
            unassigned_user.id,
            "FIELD_AGENT",
        )
        db.add_all([agent_role, dual_role, unassigned_role])

        assigned_enrollment = FarmerProjectEnrollment(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            farmer_id=assisted.id,
            project_id=project_id,
            enrollment_method="ASSISTED",
            enrollment_source="MEDIA_PERSONA_REGRESSION",
            status="ACTIVE",
            parcel_ids=[],
            assigned_user_ids=[
                str(agent_user.id),
                str(dual_user.id),
            ],
            metadata_={"regression": True},
            created_at=now(),
            updated_at=now(),
        )
        unassigned_enrollment = FarmerProjectEnrollment(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            farmer_id=unassigned.id,
            project_id=project_id,
            enrollment_method="ASSISTED",
            enrollment_source="MEDIA_PERSONA_REGRESSION",
            status="ACTIVE",
            parcel_ids=[],
            assigned_user_ids=[],
            metadata_={"regression": True},
            created_at=now(),
            updated_at=now(),
        )
        db.add_all([assigned_enrollment, unassigned_enrollment])
        db.commit()
    finally:
        db.close()

    client = TestClient(app)

    try:
        farmer_create = client.post(
            "/api/v1/media/assets",
            headers=farmer_headers,
            json=asset_body(project_id, farmer_own.id, "farmer-own"),
        )
        require(
            farmer_create.status_code == 201,
            "Farmer uploads media for personal farmer profile",
            farmer_create.text,
        )
        farmer_asset = farmer_create.json()
        created_asset_ids.append(uuid.UUID(farmer_asset["id"]))
        require(
            farmer_asset["uploaded_by"] == str(farmer_user.id),
            "Farmer upload records authenticated user",
        )

        agent_create = client.post(
            "/api/v1/media/assets",
            headers=agent_headers,
            json=asset_body(project_id, assisted.id, "agent-assigned"),
        )
        require(
            agent_create.status_code == 201,
            "Assigned agent uploads media for assisted farmer",
            agent_create.text,
        )
        agent_asset = agent_create.json()
        created_asset_ids.append(uuid.UUID(agent_asset["id"]))
        require(
            agent_asset["uploaded_by"] == str(agent_user.id),
            "Agent upload records authenticated user",
        )

        dual_personal = client.post(
            "/api/v1/media/assets",
            headers=dual_headers,
            json=asset_body(project_id, dual_own.id, "dual-personal"),
        )
        require(
            dual_personal.status_code == 201,
            "Dual user uploads in personal farmer persona",
            dual_personal.text,
        )
        created_asset_ids.append(uuid.UUID(dual_personal.json()["id"]))

        dual_assigned = client.post(
            "/api/v1/media/assets",
            headers=dual_headers,
            json=asset_body(project_id, assisted.id, "dual-assigned"),
        )
        require(
            dual_assigned.status_code == 201,
            "Same dual user uploads in assigned agent persona",
            dual_assigned.text,
        )
        dual_assigned_asset = dual_assigned.json()
        created_asset_ids.append(uuid.UUID(dual_assigned_asset["id"]))

        unassigned_create = client.post(
            "/api/v1/media/assets",
            headers=unassigned_headers,
            json=asset_body(project_id, assisted.id, "unassigned-probe"),
        )
        require(
            unassigned_create.status_code == 403,
            "Unassigned agent cannot upload for assisted farmer",
            unassigned_create.text,
        )

        project_only_agronomist = client.post(
            "/api/v1/media/assets",
            headers=dual_headers,
            json={
                "project_id": str(project_id),
                "media_type": "DOCUMENT",
                "mime_type": "application/pdf",
            },
        )
        require(
            project_only_agronomist.status_code == 403,
            "Agronomist cannot use web-admin bypass",
            project_only_agronomist.text,
        )

        original_completion = client.post(
            f"/api/v1/media/assets/{farmer_asset['id']}/complete",
            headers=farmer_headers,
            json={
                "storage_key": "persona/farmer.jpg",
                "upload_status": "UPLOADED",
            },
        )
        require(
            original_completion.status_code == 200,
            "Original farmer uploader completes asset",
            original_completion.text,
        )

        assigned_completion = client.post(
            f"/api/v1/media/assets/{dual_assigned_asset['id']}/complete",
            headers=agent_headers,
            json={
                "storage_key": "persona/assigned.jpg",
                "upload_status": "UPLOADED",
            },
        )
        require(
            assigned_completion.status_code == 200,
            "Another assigned agent completes farmer-scoped asset",
            assigned_completion.text,
        )

        denied_completion = client.post(
            f"/api/v1/media/assets/{agent_asset['id']}/complete",
            headers=unassigned_headers,
            json={"upload_status": "UPLOADED"},
        )
        require(
            denied_completion.status_code == 403,
            "Unassigned agent cannot complete farmer-scoped asset",
            denied_completion.text,
        )

        db = SessionLocal()
        try:
            dual_role.is_active = False
            persisted_dual_role = (
                db.query(ProjectRole)
                .filter(ProjectRole.id == dual_role.id)
                .one()
            )
            persisted_dual_role.is_active = False
            db.commit()
        finally:
            db.close()

        revoked_create = client.post(
            "/api/v1/media/assets",
            headers=dual_headers,
            json=asset_body(project_id, assisted.id, "revoked-role"),
        )
        require(
            revoked_create.status_code == 403,
            "Revoked project role removes assigned-farmer media access",
            revoked_create.text,
        )

        print({
            "schema_version": "media_asset_persona_behavior.v1",
            "farmer_persona": True,
            "assigned_agent_persona": True,
            "dual_persona": True,
            "unassigned_denied": True,
            "agronomist_admin_bypass_denied": True,
            "revoked_project_role_denied": True,
        })
        print("MEDIA ASSET PERSONA BEHAVIOR PASSED")
    finally:
        cleanup_db = SessionLocal()
        try:
            cleanup_db.query(MediaAsset).filter(
                MediaAsset.tenant_id == tenant_id
            ).delete(synchronize_session=False)
            cleanup_db.query(FarmerProjectEnrollment).filter(
                FarmerProjectEnrollment.tenant_id == tenant_id
            ).delete(synchronize_session=False)
            cleanup_db.query(AgentProfile).filter(
                AgentProfile.tenant_id == tenant_id
            ).delete(synchronize_session=False)
            cleanup_db.query(ProjectRole).filter(
                ProjectRole.project_id == project_id
            ).delete(synchronize_session=False)
            cleanup_db.query(Farmer).filter(
                Farmer.tenant_id == tenant_id
            ).delete(synchronize_session=False)
            cleanup_db.query(Project).filter(
                Project.tenant_id == tenant_id
            ).delete(synchronize_session=False)
            for user_id in created_user_ids:
                delete_test_admin(cleanup_db, user_id)
            cleanup_db.query(Tenant).filter(
                Tenant.id == tenant_id
            ).delete(synchronize_session=False)
            cleanup_db.commit()
        finally:
            cleanup_db.close()

    verification_db = SessionLocal()
    try:
        counts = {
            "assets": verification_db.query(MediaAsset).filter(
                MediaAsset.tenant_id == tenant_id
            ).count(),
            "farmers": verification_db.query(Farmer).filter(
                Farmer.tenant_id == tenant_id
            ).count(),
            "profiles": verification_db.query(AgentProfile).filter(
                AgentProfile.tenant_id == tenant_id
            ).count(),
        }
        require(
            counts == {"assets": 0, "farmers": 0, "profiles": 0},
            "Media persona test rows are cleaned",
            counts,
        )
    finally:
        verification_db.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

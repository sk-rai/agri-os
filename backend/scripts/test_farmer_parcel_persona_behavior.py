#!/usr/bin/env python3
"""Direct persona behavior for authenticated farmer and parcel mutations."""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.auth.models import AgentProfile, User
from app.modules.farmer.models import (
    Farmer,
    FarmerProjectEnrollment,
    Parcel,
    Project,
    ProjectRole,
    Tenant,
)
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
        mobile_number=f"+9193{uuid.uuid4().int % 100000000:08d}",
        display_name=name,
        village_name_manual="Persona Village",
        pin_code="560001",
        total_land_unit="ACRE",
        language_preference="hi",
        status="ACTIVE",
        is_active=True,
        created_at=now(),
        updated_at=now(),
    )


def make_parcel(tenant_id, project_id, farmer_id, suffix):
    return Parcel(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        project_id=project_id,
        farmer_id=farmer_id,
        village_name_manual="Persona Village",
        pin_code="560001",
        location_scope={"primary_village": "Persona Village"},
        reported_area=1,
        reported_area_unit="ACRE",
        survey_number=f"PERSONA-{suffix}",
        ownership_type="OWNED",
        status="ACTIVE",
        is_active=True,
        created_at=now(),
        updated_at=now(),
    )


def parcel_body(farmer_id, suffix):
    return {
        "farmer_id": str(farmer_id),
        "village_name_manual": "Persona Village",
        "pin_code": "560001",
        "location_scope": {"primary_village": "Persona Village"},
        "reported_area": 1.25,
        "reported_area_unit": "ACRE",
        "survey_number": f"NEW-{suffix}",
        "ownership_type": "OWNED",
    }


def main():
    tenant_id = f"farmer-parcel-persona-{uuid.uuid4().hex[:8]}"
    project_id = uuid.uuid4()
    created_user_ids = []

    db = SessionLocal()
    db.expire_on_commit = False
    try:
        db.add(
            Tenant(
                id=tenant_id,
                name="Farmer Parcel Persona Tenant",
                type="ENTERPRISE",
                created_at=now(),
                updated_at=now(),
            )
        )
        db.commit()

        farmer_user, farmer_headers = create_test_admin(
            db, tenant_id=tenant_id, role="FARMER"
        )
        self_enroll_user, self_enroll_headers = create_test_admin(
            db, tenant_id=tenant_id, role="FARMER"
        )
        agent_user, agent_headers = create_test_admin(
            db, tenant_id=tenant_id, role="FIELD_AGENT"
        )
        unassigned_user, unassigned_headers = create_test_admin(
            db, tenant_id=tenant_id, role="FIELD_AGENT"
        )
        admin_user, admin_headers = create_test_admin(
            db, tenant_id=tenant_id, role="ENTERPRISE_ADMIN"
        )
        created_user_ids.extend(
            [
                farmer_user.id,
                self_enroll_user.id,
                agent_user.id,
                unassigned_user.id,
                admin_user.id,
            ]
        )

        project = Project(
            id=project_id,
            tenant_id=tenant_id,
            name="Farmer Parcel Persona Project",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=180),
            status="ACTIVE",
            geography_scope={},
            crop_scope=["RICE"],
            config={},
            is_active=True,
            created_at=now(),
            updated_at=now(),
        )
        db.add(project)
        db.flush()

        personal = make_farmer(
            tenant_id, project_id, "Personal Farmer", farmer_user.id
        )
        assisted = make_farmer(
            tenant_id, project_id, "Assisted Farmer"
        )
        unrelated = make_farmer(
            tenant_id, project_id, "Unrelated Farmer"
        )
        db.add_all([personal, assisted, unrelated])
        db.flush()

        personal_parcel = make_parcel(
            tenant_id, project_id, personal.id, "PERSONAL"
        )
        assisted_parcel = make_parcel(
            tenant_id, project_id, assisted.id, "ASSISTED"
        )
        unrelated_parcel = make_parcel(
            tenant_id, project_id, unrelated.id, "UNRELATED"
        )
        db.add_all([personal_parcel, assisted_parcel, unrelated_parcel])

        db.add_all(
            [
                AgentProfile(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    user_id=agent_user.id,
                    agent_code="FP-ASSIGNED",
                    role_type="FIELD_AGENT",
                    display_name="Assigned Agent",
                    status="ACTIVE",
                    is_active=True,
                    created_at=now(),
                    updated_at=now(),
                ),
                AgentProfile(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    user_id=unassigned_user.id,
                    agent_code="FP-UNASSIGNED",
                    role_type="FIELD_AGENT",
                    display_name="Unassigned Agent",
                    status="ACTIVE",
                    is_active=True,
                    created_at=now(),
                    updated_at=now(),
                ),
                ProjectRole(
                    id=uuid.uuid4(),
                    project_id=project_id,
                    user_id=agent_user.id,
                    role="FIELD_AGENT",
                    territory_scope={},
                    is_active=True,
                    created_at=now(),
                    updated_at=now(),
                ),
                ProjectRole(
                    id=uuid.uuid4(),
                    project_id=project_id,
                    user_id=unassigned_user.id,
                    role="FIELD_AGENT",
                    territory_scope={},
                    is_active=True,
                    created_at=now(),
                    updated_at=now(),
                ),
                FarmerProjectEnrollment(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    farmer_id=personal.id,
                    project_id=project_id,
                    enrollment_method="SELF",
                    enrollment_source="PERSONA_TEST",
                    enrolled_by=farmer_user.id,
                    status="ACTIVE",
                    parcel_ids=[str(personal_parcel.id)],
                    assigned_user_ids=[],
                    metadata_={},
                    is_active=True,
                    created_at=now(),
                    updated_at=now(),
                ),
                FarmerProjectEnrollment(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    farmer_id=assisted.id,
                    project_id=project_id,
                    enrollment_method="ASSISTED",
                    enrollment_source="PERSONA_TEST",
                    enrolled_by=agent_user.id,
                    status="ACTIVE",
                    parcel_ids=[str(assisted_parcel.id)],
                    assigned_user_ids=[str(agent_user.id)],
                    metadata_={},
                    is_active=True,
                    created_at=now(),
                    updated_at=now(),
                ),
                FarmerProjectEnrollment(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    farmer_id=unrelated.id,
                    project_id=project_id,
                    enrollment_method="ASSISTED",
                    enrollment_source="PERSONA_TEST",
                    enrolled_by=admin_user.id,
                    status="ACTIVE",
                    parcel_ids=[str(unrelated_parcel.id)],
                    assigned_user_ids=[],
                    metadata_={},
                    is_active=True,
                    created_at=now(),
                    updated_at=now(),
                ),
            ]
        )
        db.commit()

        client = TestClient(app)

        missing_farmer_list = client.get(
            "/api/v1/farmers",
            headers={"X-Tenant-ID": tenant_id},
        )
        require(
            missing_farmer_list.status_code == 401,
            "Farmer listing rejects missing bearer",
            missing_farmer_list.text,
        )

        missing_parcel_list = client.get(
            "/api/v1/parcels",
            headers={"X-Tenant-ID": tenant_id},
        )
        require(
            missing_parcel_list.status_code == 401,
            "Parcel listing rejects missing bearer",
            missing_parcel_list.text,
        )

        missing_readiness = client.get(
            "/api/v1/farmers/profile-readiness",
            headers={"X-Tenant-ID": tenant_id},
        )
        require(
            missing_readiness.status_code == 401,
            "Profile readiness rejects missing bearer",
            missing_readiness.text,
        )

        farmer_readiness = client.get(
            f"/api/v1/farmers/profile-readiness?project_id={project_id}",
            headers=farmer_headers,
        )
        require(
            farmer_readiness.status_code == 200,
            "Farmer reads personal profile readiness",
            farmer_readiness.text,
        )
        require(
            {
                row["farmer"]["id"]
                for row in farmer_readiness.json()["farmers"]
            }
            == {str(personal.id)},
            "Farmer readiness is restricted to personal farmer",
            farmer_readiness.text,
        )

        agent_readiness = client.get(
            f"/api/v1/farmers/profile-readiness?project_id={project_id}",
            headers=agent_headers,
        )
        require(
            agent_readiness.status_code == 200,
            "Assigned agent reads assisted-farmer readiness",
            agent_readiness.text,
        )
        require(
            {
                row["farmer"]["id"]
                for row in agent_readiness.json()["farmers"]
            }
            == {str(assisted.id)},
            "Agent readiness is restricted to assigned farmer",
            agent_readiness.text,
        )

        unassigned_readiness = client.get(
            f"/api/v1/farmers/profile-readiness?project_id={project_id}",
            headers=unassigned_headers,
        )
        require(
            unassigned_readiness.status_code == 200,
            "Unassigned agent reads an empty readiness collection",
            unassigned_readiness.text,
        )
        require(
            unassigned_readiness.json()["farmers"] == []
            and unassigned_readiness.json()["summary"]["farmer_count"] == 0,
            "Unassigned agent cannot discover farmer readiness",
            unassigned_readiness.text,
        )

        admin_readiness = client.get(
            f"/api/v1/farmers/profile-readiness?project_id={project_id}",
            headers=admin_headers,
        )
        require(
            admin_readiness.status_code == 200,
            "Web administrator reads tenant profile readiness",
            admin_readiness.text,
        )
        require(
            {
                row["farmer"]["id"]
                for row in admin_readiness.json()["farmers"]
            }
            == {
                str(personal.id),
                str(assisted.id),
                str(unrelated.id),
            },
            "Web administrator sees tenant farmer readiness",
            admin_readiness.text,
        )

        farmer_worklist = client.get(
            f"/api/v1/field-agent/worklist?project_id={project_id}",
            headers=farmer_headers,
        )
        require(
            farmer_worklist.status_code == 403,
            "Farmer persona cannot use field-agent worklist",
            farmer_worklist.text,
        )

        unassigned_worklist = client.get(
            f"/api/v1/field-agent/worklist?project_id={project_id}",
            headers=unassigned_headers,
        )
        require(
            unassigned_worklist.status_code == 200,
            "Unassigned active agent reads an empty worklist",
            unassigned_worklist.text,
        )
        require(
            unassigned_worklist.json()["farmers"] == []
            and unassigned_worklist.json()["summary"]["farmer_count"] == 0,
            "Unassigned active agent cannot discover worklist farmers",
            unassigned_worklist.text,
        )

        mismatch_readiness_headers = {
            **farmer_headers,
            "X-Tenant-ID": "default",
        }
        mismatch_readiness = client.get(
            "/api/v1/farmers/profile-readiness",
            headers=mismatch_readiness_headers,
        )
        require(
            mismatch_readiness.status_code == 403,
            "Profile readiness rejects token/header tenant mismatch",
            mismatch_readiness.text,
        )

        missing_enrollments = client.get(
            f"/api/v1/farmers/{personal.id}/project-enrollments",
            headers={"X-Tenant-ID": tenant_id},
        )
        require(
            missing_enrollments.status_code == 401,
            "Farmer project-enrollment read rejects missing bearer",
            missing_enrollments.text,
        )

        missing_launch = client.get(
            f"/api/v1/farmers/{personal.id}/launch-context",
            headers={"X-Tenant-ID": tenant_id},
        )
        require(
            missing_launch.status_code == 401,
            "Farmer launch-context read rejects missing bearer",
            missing_launch.text,
        )

        farmer_enrollments = client.get(
            f"/api/v1/farmers/{personal.id}/project-enrollments",
            headers=farmer_headers,
        )
        require(
            farmer_enrollments.status_code == 200
            and len(farmer_enrollments.json()) == 1,
            "Farmer reads personal project enrollment",
            farmer_enrollments.text,
        )

        farmer_launch = client.get(
            f"/api/v1/farmers/{personal.id}/launch-context",
            headers=farmer_headers,
        )
        require(
            farmer_launch.status_code == 200
            and farmer_launch.json()["farmer"]["id"] == str(personal.id),
            "Farmer reads personal launch context",
            farmer_launch.text,
        )

        farmer_cross_enrollments = client.get(
            f"/api/v1/farmers/{assisted.id}/project-enrollments",
            headers=farmer_headers,
        )
        require(
            farmer_cross_enrollments.status_code == 404,
            "Farmer cannot discover assisted-farmer enrollments",
            farmer_cross_enrollments.text,
        )

        farmer_cross_launch = client.get(
            f"/api/v1/farmers/{assisted.id}/launch-context",
            headers=farmer_headers,
        )
        require(
            farmer_cross_launch.status_code == 404,
            "Farmer cannot discover assisted-farmer launch context",
            farmer_cross_launch.text,
        )

        agent_enrollments = client.get(
            f"/api/v1/farmers/{assisted.id}/project-enrollments",
            headers=agent_headers,
        )
        require(
            agent_enrollments.status_code == 200
            and len(agent_enrollments.json()) == 1,
            "Assigned agent reads assisted-farmer enrollment",
            agent_enrollments.text,
        )

        agent_launch = client.get(
            f"/api/v1/farmers/{assisted.id}/launch-context",
            headers=agent_headers,
        )
        require(
            agent_launch.status_code == 200
            and agent_launch.json()["farmer"]["id"] == str(assisted.id),
            "Assigned agent reads assisted-farmer launch context",
            agent_launch.text,
        )

        agent_cross_enrollments = client.get(
            f"/api/v1/farmers/{unrelated.id}/project-enrollments",
            headers=agent_headers,
        )
        require(
            agent_cross_enrollments.status_code == 404,
            "Assigned agent cannot discover unrelated enrollments",
            agent_cross_enrollments.text,
        )

        agent_cross_launch = client.get(
            f"/api/v1/farmers/{unrelated.id}/launch-context",
            headers=agent_headers,
        )
        require(
            agent_cross_launch.status_code == 404,
            "Assigned agent cannot discover unrelated launch context",
            agent_cross_launch.text,
        )

        unassigned_enrollments = client.get(
            f"/api/v1/farmers/{assisted.id}/project-enrollments",
            headers=unassigned_headers,
        )
        require(
            unassigned_enrollments.status_code == 404,
            "Unassigned agent cannot discover farmer enrollments",
            unassigned_enrollments.text,
        )

        unassigned_launch = client.get(
            f"/api/v1/farmers/{assisted.id}/launch-context",
            headers=unassigned_headers,
        )
        require(
            unassigned_launch.status_code == 404,
            "Unassigned agent cannot discover farmer launch context",
            unassigned_launch.text,
        )

        admin_enrollments = client.get(
            f"/api/v1/farmers/{unrelated.id}/project-enrollments",
            headers=admin_headers,
        )
        require(
            admin_enrollments.status_code == 200
            and len(admin_enrollments.json()) == 1,
            "Web administrator reads tenant farmer enrollment",
            admin_enrollments.text,
        )

        admin_launch = client.get(
            f"/api/v1/farmers/{unrelated.id}/launch-context",
            headers=admin_headers,
        )
        require(
            admin_launch.status_code == 200
            and admin_launch.json()["farmer"]["id"] == str(unrelated.id),
            "Web administrator reads tenant farmer launch context",
            admin_launch.text,
        )

        mismatch_context_headers = {
            **farmer_headers,
            "X-Tenant-ID": "default",
        }
        mismatch_context = client.get(
            f"/api/v1/farmers/{personal.id}/launch-context",
            headers=mismatch_context_headers,
        )
        require(
            mismatch_context.status_code == 403,
            "Farmer launch context rejects token/header tenant mismatch",
            mismatch_context.text,
        )

        farmer_list = client.get(
            "/api/v1/farmers",
            headers=farmer_headers,
        )
        require(
            farmer_list.status_code == 200,
            "Farmer lists visible farmer profiles",
            farmer_list.text,
        )
        require(
            {row["id"] for row in farmer_list.json()} == {str(personal.id)},
            "Farmer list is restricted to personal farmer",
            farmer_list.text,
        )

        farmer_parcels = client.get(
            "/api/v1/parcels",
            headers=farmer_headers,
        )
        require(
            farmer_parcels.status_code == 200,
            "Farmer lists visible parcels",
            farmer_parcels.text,
        )
        require(
            {row["id"] for row in farmer_parcels.json()}
            == {str(personal_parcel.id)},
            "Farmer parcel list is restricted to personal farmer",
            farmer_parcels.text,
        )

        farmer_cross_parcels = client.get(
            f"/api/v1/parcels?farmer_id={assisted.id}",
            headers=farmer_headers,
        )
        require(
            farmer_cross_parcels.status_code == 200
            and farmer_cross_parcels.json() == [],
            "Farmer cannot discover assisted-farmer parcels",
            farmer_cross_parcels.text,
        )

        agent_list = client.get(
            "/api/v1/farmers",
            headers=agent_headers,
        )
        require(
            agent_list.status_code == 200,
            "Assigned agent lists visible farmers",
            agent_list.text,
        )
        require(
            {row["id"] for row in agent_list.json()} == {str(assisted.id)},
            "Agent farmer list is restricted to assignment",
            agent_list.text,
        )

        agent_parcels = client.get(
            "/api/v1/parcels",
            headers=agent_headers,
        )
        require(
            agent_parcels.status_code == 200,
            "Assigned agent lists assisted-farmer parcels",
            agent_parcels.text,
        )
        require(
            {row["id"] for row in agent_parcels.json()}
            == {str(assisted_parcel.id)},
            "Agent parcel list is restricted to assignment",
            agent_parcels.text,
        )

        agent_cross_parcels = client.get(
            f"/api/v1/parcels?farmer_id={unrelated.id}",
            headers=agent_headers,
        )
        require(
            agent_cross_parcels.status_code == 200
            and agent_cross_parcels.json() == [],
            "Assigned agent cannot discover unrelated parcels",
            agent_cross_parcels.text,
        )

        unassigned_list = client.get(
            "/api/v1/farmers",
            headers=unassigned_headers,
        )
        require(
            unassigned_list.status_code == 200
            and unassigned_list.json() == [],
            "Unassigned agent receives an empty farmer list",
            unassigned_list.text,
        )

        unassigned_parcels_read = client.get(
            "/api/v1/parcels",
            headers=unassigned_headers,
        )
        require(
            unassigned_parcels_read.status_code == 200
            and unassigned_parcels_read.json() == [],
            "Unassigned agent receives an empty parcel list",
            unassigned_parcels_read.text,
        )

        admin_list = client.get(
            "/api/v1/farmers",
            headers=admin_headers,
        )
        require(
            admin_list.status_code == 200,
            "Web administrator lists tenant farmers",
            admin_list.text,
        )
        require(
            {row["id"] for row in admin_list.json()}
            == {str(personal.id), str(assisted.id), str(unrelated.id)},
            "Web administrator sees all tenant farmers",
            admin_list.text,
        )

        admin_parcels = client.get(
            "/api/v1/parcels",
            headers=admin_headers,
        )
        require(
            admin_parcels.status_code == 200,
            "Web administrator lists tenant parcels",
            admin_parcels.text,
        )
        require(
            {row["id"] for row in admin_parcels.json()}
            == {
                str(personal_parcel.id),
                str(assisted_parcel.id),
                str(unrelated_parcel.id),
            },
            "Web administrator sees all tenant parcels",
            admin_parcels.text,
        )

        mismatch_read_headers = {
            **farmer_headers,
            "X-Tenant-ID": "default",
        }
        mismatch_farmer_list = client.get(
            "/api/v1/farmers",
            headers=mismatch_read_headers,
        )
        require(
            mismatch_farmer_list.status_code == 403,
            "Farmer listing rejects token/header tenant mismatch",
            mismatch_farmer_list.text,
        )

        mismatch_parcel_list = client.get(
            "/api/v1/parcels",
            headers=mismatch_read_headers,
        )
        require(
            mismatch_parcel_list.status_code == 403,
            "Parcel listing rejects token/header tenant mismatch",
            mismatch_parcel_list.text,
        )

        missing = client.patch(
            f"/api/v1/farmers/{personal.id}",
            headers={"X-Tenant-ID": tenant_id},
            json={"display_name": "Missing bearer"},
        )
        require(
            missing.status_code == 401,
            "Farmer mutation rejects missing bearer",
            missing.text,
        )

        personal_update = client.patch(
            f"/api/v1/farmers/{personal.id}",
            headers=farmer_headers,
            json={"display_name": "Personal Farmer Updated"},
        )
        require(
            personal_update.status_code == 200,
            "Farmer updates personal profile",
            personal_update.text,
        )

        personal_parcel_create = client.post(
            "/api/v1/parcels",
            headers=farmer_headers,
            json=parcel_body(personal.id, "PERSONAL"),
        )
        require(
            personal_parcel_create.status_code == 201,
            "Farmer creates parcel for personal profile",
            personal_parcel_create.text,
        )

        unrelated_farmer_update = client.patch(
            f"/api/v1/farmers/{unrelated.id}",
            headers=farmer_headers,
            json={"display_name": "Forbidden Farmer Update"},
        )
        require(
            unrelated_farmer_update.status_code == 403,
            "Farmer cannot update unrelated farmer",
            unrelated_farmer_update.text,
        )

        unrelated_parcel_update = client.patch(
            f"/api/v1/parcels/{unrelated_parcel.id}",
            headers=farmer_headers,
            json={"local_name": "Forbidden Parcel Update"},
        )
        require(
            unrelated_parcel_update.status_code == 403,
            "Farmer cannot update unrelated parcel",
            unrelated_parcel_update.text,
        )

        assisted_update = client.patch(
            f"/api/v1/farmers/{assisted.id}",
            headers=agent_headers,
            json={"display_name": "Assisted Farmer Updated"},
        )
        require(
            assisted_update.status_code == 200,
            "Assigned agent updates assisted farmer",
            assisted_update.text,
        )

        assisted_parcel_create = client.post(
            "/api/v1/parcels",
            headers=agent_headers,
            json=parcel_body(assisted.id, "ASSISTED"),
        )
        require(
            assisted_parcel_create.status_code == 201,
            "Assigned agent creates assisted-farmer parcel",
            assisted_parcel_create.text,
        )

        assisted_parcel_update = client.patch(
            f"/api/v1/parcels/{assisted_parcel.id}",
            headers=agent_headers,
            json={"local_name": "Assigned Agent Plot"},
        )
        require(
            assisted_parcel_update.status_code == 200,
            "Assigned agent updates assisted-farmer parcel",
            assisted_parcel_update.text,
        )

        unassigned_farmer = client.patch(
            f"/api/v1/farmers/{assisted.id}",
            headers=unassigned_headers,
            json={"display_name": "Unassigned Probe"},
        )
        require(
            unassigned_farmer.status_code == 403,
            "Unassigned agent cannot update assisted farmer",
            unassigned_farmer.text,
        )

        unassigned_parcel = client.patch(
            f"/api/v1/parcels/{assisted_parcel.id}",
            headers=unassigned_headers,
            json={"local_name": "Unassigned Probe"},
        )
        require(
            unassigned_parcel.status_code == 403,
            "Unassigned agent cannot update assisted parcel",
            unassigned_parcel.text,
        )

        assigned_cross_farmer = client.patch(
            f"/api/v1/farmers/{unrelated.id}",
            headers=agent_headers,
            json={"display_name": "Cross Farmer Probe"},
        )
        require(
            assigned_cross_farmer.status_code == 403,
            "Assigned agent cannot update unrelated farmer",
            assigned_cross_farmer.text,
        )

        geometry = client.patch(
            f"/api/v1/parcels/{assisted_parcel.id}/geometry",
            headers=agent_headers,
            json={
                "geometry_source": "PIN_DROP",
                "centroid_lat": 12.9716,
                "centroid_lng": 77.5946,
                "accuracy_meters": 8,
            },
        )
        require(
            geometry.status_code == 200,
            "Assigned agent records assisted-parcel geometry",
            geometry.text,
        )

        db.expire_all()
        stored_geometry = db.query(Parcel).filter(
            Parcel.id == assisted_parcel.id
        ).one()
        require(
            stored_geometry.geometry_captured_by == agent_user.id,
            "Geometry records authenticated agent",
        )

        admin_update = client.patch(
            f"/api/v1/farmers/{unrelated.id}",
            headers=admin_headers,
            json={"display_name": "Administrator Updated Farmer"},
        )
        require(
            admin_update.status_code == 200,
            "Web administrator updates tenant farmer",
            admin_update.text,
        )

        mismatch_headers = {
            **farmer_headers,
            "X-Tenant-ID": "default",
        }
        mismatch = client.patch(
            f"/api/v1/farmers/{personal.id}",
            headers=mismatch_headers,
            json={"display_name": "Tenant Mismatch Probe"},
        )
        require(
            mismatch.status_code == 403,
            "Farmer mutation rejects token/header tenant mismatch",
            mismatch.text,
        )

        self_enrollment = client.post(
            "/api/v1/farmers",
            headers=self_enroll_headers,
            json={
                "mobile_number": self_enroll_user.mobile_number,
                "display_name": "Self Enrolled Farmer",
                "village_name_manual": "Persona Village",
                "pin_code": "560001",
                "total_land_unit": "ACRE",
                "language_preference": "hi",
                "assistance_mode": "SELF_SERVICE",
            },
        )
        require(
            self_enrollment.status_code == 201,
            "Farmer self-enrolls using persisted mobile identity",
            self_enrollment.text,
        )
        self_farmer_id = uuid.UUID(self_enrollment.json()["id"])
        db.expire_all()
        stored_self = db.query(Farmer).filter(
            Farmer.id == self_farmer_id
        ).one()
        require(
            stored_self.user_id == self_enroll_user.id,
            "Self enrollment links authenticated user",
        )
        require(
            stored_self.enrolled_by == self_enroll_user.id,
            "Self enrollment records authenticated actor",
        )

        agent_enrollment_mobile = (
            f"+9192{uuid.uuid4().int % 100000000:08d}"
        )
        agent_enrollment = client.post(
            "/api/v1/farmers",
            headers=agent_headers,
            json={
                "mobile_number": agent_enrollment_mobile,
                "project_id": str(project_id),
                "display_name": "Agent Enrolled Farmer",
                "village_name_manual": "Persona Village",
                "pin_code": "560001",
                "total_land_unit": "ACRE",
                "language_preference": "hi",
                "assistance_mode": "FIELD_AGENT_ASSISTED",
            },
        )
        require(
            agent_enrollment.status_code == 201,
            "Project agent enrolls farmer",
            agent_enrollment.text,
        )
        agent_farmer_id = uuid.UUID(agent_enrollment.json()["id"])
        db.expire_all()
        stored_agent_farmer = db.query(Farmer).filter(
            Farmer.id == agent_farmer_id
        ).one()
        require(
            stored_agent_farmer.user_id is None,
            "Agent enrollment does not impersonate farmer identity",
        )
        require(
            stored_agent_farmer.enrolled_by == agent_user.id,
            "Agent enrollment records authenticated agent",
        )

        impostor_enrollment = client.post(
            "/api/v1/farmers",
            headers=farmer_headers,
            json={
                "mobile_number": f"+9191{uuid.uuid4().int % 100000000:08d}",
                "display_name": "Impersonated Enrollment",
                "village_name_manual": "Persona Village",
            },
        )
        require(
            impostor_enrollment.status_code == 403,
            "Farmer cannot enroll a different mobile identity",
            impostor_enrollment.text,
        )

        print(
            {
                "schema_version": "farmer_parcel_persona_behavior.v1",
                "farmer_self_enrollment": True,
                "farmer_read_scope": True,
                "parcel_read_scope": True,
                "profile_readiness_scope": True,
                "field_agent_worklist_scope": True,
                "farmer_enrollment_read_scope": True,
                "farmer_launch_context_scope": True,
                "assigned_agent_read_scope": True,
                "unassigned_read_empty": True,
                "admin_tenant_read": True,
                "farmer_personal_update": True,
                "farmer_personal_parcel_create": True,
                "assigned_agent_farmer_update": True,
                "assigned_agent_parcel_create": True,
                "assigned_agent_geometry": True,
                "unassigned_denied": True,
                "unrelated_denied": True,
                "admin_tenant_update": True,
                "tenant_mismatch_denied": True,
            }
        )
        print("FARMER PARCEL PERSONA BEHAVIOR PASSED")
    finally:
        db.close()
        cleanup = SessionLocal()
        try:
            cleanup.query(Parcel).filter(
                Parcel.tenant_id == tenant_id
            ).delete(synchronize_session=False)
            cleanup.query(FarmerProjectEnrollment).filter(
                FarmerProjectEnrollment.tenant_id == tenant_id
            ).delete(synchronize_session=False)
            cleanup.query(Farmer).filter(
                Farmer.tenant_id == tenant_id
            ).delete(synchronize_session=False)
            cleanup.query(ProjectRole).filter(
                ProjectRole.project_id == project_id
            ).delete(synchronize_session=False)
            cleanup.query(AgentProfile).filter(
                AgentProfile.tenant_id == tenant_id
            ).delete(synchronize_session=False)
            cleanup.query(Project).filter(
                Project.tenant_id == tenant_id
            ).delete(synchronize_session=False)
            cleanup.commit()

            for user_id in created_user_ids:
                delete_test_admin(cleanup, user_id)

            cleanup.query(Tenant).filter(
                Tenant.id == tenant_id
            ).delete(synchronize_session=False)
            cleanup.commit()
            print("PASS Farmer/parcel persona rows are cleaned")
        finally:
            cleanup.close()


if __name__ == "__main__":
    main()

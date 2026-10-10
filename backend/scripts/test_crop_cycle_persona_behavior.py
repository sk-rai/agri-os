#!/usr/bin/env python3
"""Direct persona behavior for authenticated crop-cycle mutations."""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import SessionLocal
from app.main import app
from app.modules.auth.models import AgentProfile
from app.modules.farmer.models import (
    Farmer,
    FarmerProjectEnrollment,
    Parcel,
    Project,
    ProjectRole,
    Tenant,
)
from app.modules.master_data.models import CropLifecycleTemplate
from app.modules.workflow.models import (
    CropActivity,
    CropCycle,
    CropStageInstance,
)
from scripts.admin_auth_test_utils import (
    create_test_admin,
    delete_test_admin,
)


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
        mobile_number=f"+9192{uuid.uuid4().int % 100000000:08d}",
        display_name=name,
        village_name_manual="Crop Persona Village",
        pin_code="560001",
        total_land_unit="ACRE",
        language_preference="en",
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
        village_name_manual="Crop Persona Village",
        pin_code="560001",
        location_scope={"primary_village": "Crop Persona Village"},
        reported_area=1,
        reported_area_unit="ACRE",
        survey_number=f"CROP-PERSONA-{suffix}",
        ownership_type="OWNED",
        status="ACTIVE",
        is_active=True,
        created_at=now(),
        updated_at=now(),
    )


def cycle_body(parcel, farmer, template, crop_code):
    return {
        "parcel_id": str(parcel.id),
        "farmer_id": str(farmer.id),
        "crop_code": crop_code,
        "season_code": "KHARIF",
        "lifecycle_template_id": str(template.id),
        "planned_sowing_date": (
            date.today() + timedelta(days=7)
        ).isoformat(),
    }


def main():
    tenant_id = f"crop-cycle-persona-{uuid.uuid4().hex[:8]}"
    project_id = uuid.uuid4()
    created_user_ids = []

    db = SessionLocal()
    db.expire_on_commit = False
    try:
        template = (
            db.query(CropLifecycleTemplate)
            .filter(CropLifecycleTemplate.crop_id.isnot(None))
            .first()
        )
        require(template is not None, "Lifecycle template fixture exists")
        crop_code = template.code.split("_")[0]

        db.add(
            Tenant(
                id=tenant_id,
                name="Crop Cycle Persona Tenant",
                type="ENTERPRISE",
                created_at=now(),
                updated_at=now(),
            )
        )
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
        unassigned_user, unassigned_headers = create_test_admin(
            db,
            tenant_id=tenant_id,
            role="FIELD_AGENT",
        )
        admin_user, admin_headers = create_test_admin(
            db,
            tenant_id=tenant_id,
            role="ENTERPRISE_ADMIN",
        )
        self_sync_user, self_sync_headers = create_test_admin(
            db,
            tenant_id=tenant_id,
            role="FARMER",
        )
        created_user_ids.extend([
            farmer_user.id,
            agent_user.id,
            unassigned_user.id,
            admin_user.id,
            self_sync_user.id,
        ])

        project = Project(
            id=project_id,
            tenant_id=tenant_id,
            name="Crop Cycle Persona Project",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=180),
            status="ACTIVE",
            geography_scope={},
            crop_scope=[crop_code],
            config={},
            is_active=True,
            created_at=now(),
            updated_at=now(),
        )
        db.add(project)
        db.flush()

        personal = make_farmer(
            tenant_id,
            project_id,
            "Personal Crop Farmer",
            farmer_user.id,
        )
        assisted = make_farmer(
            tenant_id,
            project_id,
            "Assisted Crop Farmer",
        )
        unrelated = make_farmer(
            tenant_id,
            project_id,
            "Unrelated Crop Farmer",
        )
        db.add_all([personal, assisted, unrelated])
        db.flush()

        personal_parcel = make_parcel(
            tenant_id,
            project_id,
            personal.id,
            "PERSONAL",
        )
        assisted_parcel = make_parcel(
            tenant_id,
            project_id,
            assisted.id,
            "ASSISTED",
        )
        unrelated_parcel = make_parcel(
            tenant_id,
            project_id,
            unrelated.id,
            "UNRELATED",
        )
        db.add_all([
            personal_parcel,
            assisted_parcel,
            unrelated_parcel,
        ])
        db.flush()

        db.add_all([
            AgentProfile(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                user_id=agent_user.id,
                agent_code="CROP-ASSIGNED",
                role_type="FIELD_AGENT",
                display_name="Assigned Crop Agent",
                status="ACTIVE",
                is_active=True,
                created_at=now(),
                updated_at=now(),
            ),
            AgentProfile(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                user_id=unassigned_user.id,
                agent_code="CROP-UNASSIGNED",
                role_type="FIELD_AGENT",
                display_name="Unassigned Crop Agent",
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
                enrollment_source="CROP_PERSONA_TEST",
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
                enrollment_source="CROP_PERSONA_TEST",
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
                enrollment_source="CROP_PERSONA_TEST",
                enrolled_by=admin_user.id,
                status="ACTIVE",
                parcel_ids=[str(unrelated_parcel.id)],
                assigned_user_ids=[],
                metadata_={},
                is_active=True,
                created_at=now(),
                updated_at=now(),
            ),
        ])
        db.commit()

        client = TestClient(app)

        personal_body = cycle_body(
            personal_parcel,
            personal,
            template,
            crop_code,
        )
        assisted_body = cycle_body(
            assisted_parcel,
            assisted,
            template,
            crop_code,
        )
        unrelated_body = cycle_body(
            unrelated_parcel,
            unrelated,
            template,
            crop_code,
        )

        missing = client.post(
            "/api/v1/crop-cycles",
            headers={"X-Tenant-ID": tenant_id},
            json=personal_body,
        )
        require(
            missing.status_code == 401,
            "Crop-cycle creation rejects missing bearer",
            missing.text,
        )

        impersonation = client.post(
            "/api/v1/crop-cycles",
            headers={
                **farmer_headers,
                "X-Actor-ID": str(uuid.uuid4()),
            },
            json=personal_body,
        )
        require(
            impersonation.status_code == 403,
            "Crop-cycle creation rejects actor impersonation",
            impersonation.text,
        )

        mismatch = client.post(
            "/api/v1/crop-cycles",
            headers={
                **farmer_headers,
                "X-Tenant-ID": "default",
            },
            json=personal_body,
        )
        require(
            mismatch.status_code == 403,
            "Crop-cycle creation rejects tenant mismatch",
            mismatch.text,
        )

        wrong_farmer_body = {
            **personal_body,
            "farmer_id": str(assisted.id),
        }
        wrong_farmer = client.post(
            "/api/v1/crop-cycles",
            headers=farmer_headers,
            json=wrong_farmer_body,
        )
        require(
            wrong_farmer.status_code == 400,
            "Crop-cycle creation rejects farmer/parcel mismatch",
            wrong_farmer.text,
        )

        farmer_cross = client.post(
            "/api/v1/crop-cycles",
            headers=farmer_headers,
            json=assisted_body,
        )
        require(
            farmer_cross.status_code == 403,
            "Farmer cannot create assisted farmer crop cycle",
            farmer_cross.text,
        )

        farmer_create = client.post(
            "/api/v1/crop-cycles",
            headers=farmer_headers,
            json=personal_body,
        )
        require(
            farmer_create.status_code == 201,
            "Farmer creates personal crop cycle",
            farmer_create.text,
        )
        personal_cycle = farmer_create.json()
        personal_cycle_id = personal_cycle["id"]
        personal_stage_id = personal_cycle["stages"][0]["id"]

        unassigned_create = client.post(
            "/api/v1/crop-cycles",
            headers=unassigned_headers,
            json=assisted_body,
        )
        require(
            unassigned_create.status_code == 403,
            "Unassigned agent cannot create farmer crop cycle",
            unassigned_create.text,
        )

        agent_create = client.post(
            "/api/v1/crop-cycles",
            headers=agent_headers,
            json=assisted_body,
        )
        require(
            agent_create.status_code == 201,
            "Assigned agent creates assisted farmer crop cycle",
            agent_create.text,
        )
        assisted_cycle = agent_create.json()
        assisted_cycle_id = assisted_cycle["id"]
        assisted_stage_id = assisted_cycle["stages"][0]["id"]

        admin_create = client.post(
            "/api/v1/crop-cycles",
            headers=admin_headers,
            json=unrelated_body,
        )
        require(
            admin_create.status_code == 201,
            "Web administrator creates tenant crop cycle",
            admin_create.text,
        )
        admin_cycle = admin_create.json()
        admin_cycle_id = admin_cycle["id"]

        missing_stage = client.patch(
            (
                f"/api/v1/crop-cycles/{personal_cycle_id}"
                f"/stages/{personal_stage_id}"
            ),
            headers={"X-Tenant-ID": tenant_id},
            json={"action": "START"},
        )
        require(
            missing_stage.status_code == 401,
            "Crop-stage transition rejects missing bearer",
            missing_stage.text,
        )

        agent_cross_stage = client.patch(
            (
                f"/api/v1/crop-cycles/{personal_cycle_id}"
                f"/stages/{personal_stage_id}"
            ),
            headers=agent_headers,
            json={"action": "START"},
        )
        require(
            agent_cross_stage.status_code == 403,
            "Assigned agent cannot transition unrelated crop stage",
            agent_cross_stage.text,
        )

        farmer_stage = client.patch(
            (
                f"/api/v1/crop-cycles/{personal_cycle_id}"
                f"/stages/{personal_stage_id}"
            ),
            headers=farmer_headers,
            json={"action": "START"},
        )
        require(
            farmer_stage.status_code == 200,
            "Farmer starts personal crop stage",
            farmer_stage.text,
        )

        activity = client.post(
            f"/api/v1/crop-cycles/{personal_cycle_id}/activities",
            headers=farmer_headers,
            json={
                "activity_type": "LABOR",
                "input_name": "Persona regression labor",
                "quantity": 1,
                "quantity_unit": "DAY",
                "cost_amount": 125,
                "activity_date": date.today().isoformat(),
            },
        )
        require(
            activity.status_code == 201,
            "Farmer logs personal crop activity",
            activity.text,
        )

        agent_stage = client.patch(
            (
                f"/api/v1/crop-cycles/{assisted_cycle_id}"
                f"/stages/{assisted_stage_id}"
            ),
            headers=agent_headers,
            json={"action": "START"},
        )
        require(
            agent_stage.status_code == 200,
            "Assigned agent starts assisted farmer crop stage",
            agent_stage.text,
        )

        unassigned_complete = client.post(
            f"/api/v1/crop-cycles/{assisted_cycle_id}/complete",
            headers=unassigned_headers,
            json={"notes": "must be denied"},
        )
        require(
            unassigned_complete.status_code == 403,
            "Unassigned agent cannot complete farmer crop cycle",
            unassigned_complete.text,
        )

        farmer_complete = client.post(
            f"/api/v1/crop-cycles/{personal_cycle_id}/complete",
            headers=farmer_headers,
            json={"notes": "personal completion"},
        )
        require(
            farmer_complete.status_code == 200,
            "Farmer completes personal crop cycle",
            farmer_complete.text,
        )

        admin_complete = client.post(
            f"/api/v1/crop-cycles/{admin_cycle_id}/complete",
            headers=admin_headers,
            json={"notes": "administrator completion"},
        )
        require(
            admin_complete.status_code == 200,
            "Web administrator completes tenant crop cycle",
            admin_complete.text,
        )

        db.expire_all()
        personal_stage = db.query(CropStageInstance).filter(
            CropStageInstance.id == uuid.UUID(personal_stage_id)
        ).one()
        personal_activity = db.query(CropActivity).filter(
            CropActivity.id == uuid.UUID(activity.json()["activity_id"])
        ).one()
        personal_cycle_row = db.query(CropCycle).filter(
            CropCycle.id == uuid.UUID(personal_cycle_id)
        ).one()

        require(
            personal_stage.started_by == farmer_user.id,
            "Stage transition records authenticated farmer",
        )
        require(
            personal_activity.logged_by == farmer_user.id,
            "Activity logging records authenticated farmer",
        )
        require(
            personal_cycle_row.status == "COMPLETED",
            "Personal crop cycle persists completion",
        )

        self_sync_farmer_id = uuid.uuid4()
        self_sync_event = {
            "event_id": str(uuid.uuid4()),
            "entity_type": "FARMER",
            "entity_id": str(self_sync_farmer_id),
            "operation": "CREATE",
            "payload": {
                "mobile_number": self_sync_user.mobile_number,
                "display_name": "Independent Sync Farmer",
                "village_name_manual": "Independent Sync Village",
                "status": "ACTIVE",
            },
            "version": 1,
            "dependency_ids": [],
            "metadata": {"source": "self_sync_enrollment_regression"},
        }
        self_sync_response = client.post(
            "/api/v1/sync/events",
            headers=self_sync_headers,
            json={"events": [self_sync_event]},
        )
        require(
            self_sync_response.status_code == 200
            and self_sync_response.json()["accepted"]
            == [self_sync_event["event_id"]],
            "Independent farmer self-enrolls through sync",
            self_sync_response.text,
        )

        db.expire_all()
        self_synced_farmer = db.query(Farmer).filter(
            Farmer.id == self_sync_farmer_id,
            Farmer.tenant_id == tenant_id,
        ).first()
        require(
            self_synced_farmer is not None,
            "Self-sync farmer is materialized",
        )
        require(
            self_synced_farmer.user_id == self_sync_user.id,
            "Self-sync farmer is linked to authenticated user",
        )
        require(
            self_synced_farmer.enrolled_by == self_sync_user.id,
            "Self-sync farmer records authenticated user",
        )

        agent_sync_farmer_id = uuid.uuid4()
        agent_sync_parcel_id = uuid.uuid4()
        agent_farmer_event = {
            "event_id": str(uuid.uuid4()),
            "entity_type": "FARMER",
            "entity_id": str(agent_sync_farmer_id),
            "operation": "CREATE",
            "payload": {
                "project_id": str(project_id),
                "mobile_number": (
                    f"+9192{uuid.uuid4().int % 100000000:08d}"
                ),
                "display_name": "Agent Sync Farmer",
                "village_name_manual": "Agent Sync Village",
                "status": "ACTIVE",
            },
            "version": 1,
            "dependency_ids": [],
            "metadata": {"source": "agent_sync_enrollment_regression"},
        }
        agent_parcel_event = {
            "event_id": str(uuid.uuid4()),
            "entity_type": "PARCEL",
            "entity_id": str(agent_sync_parcel_id),
            "operation": "CREATE",
            "payload": {
                "farmer_id": str(agent_sync_farmer_id),
                "project_id": str(project_id),
                "local_name": "AGENT-SYNC-PARCEL",
                "village_name_manual": "Agent Sync Village",
                "reported_area": 1,
                "reported_area_unit": "ACRE",
                "ownership_type": "OWNED",
                "status": "ACTIVE",
            },
            "version": 1,
            "dependency_ids": [agent_farmer_event["event_id"]],
            "metadata": {"source": "agent_sync_enrollment_regression"},
        }
        agent_enrollment_sync = client.post(
            "/api/v1/sync/events",
            headers=agent_headers,
            json={"events": [agent_farmer_event, agent_parcel_event]},
        )
        agent_enrollment_body = agent_enrollment_sync.json()
        require(
            agent_enrollment_sync.status_code == 200,
            "Project agent enrollment sync returns 200",
            agent_enrollment_body,
        )
        require(
            agent_enrollment_body["accepted"]
            == [
                agent_farmer_event["event_id"],
                agent_parcel_event["event_id"],
            ],
            "Project agent creates farmer and dependent parcel",
            agent_enrollment_body,
        )

        db.expire_all()
        agent_synced_farmer = db.query(Farmer).filter(
            Farmer.id == agent_sync_farmer_id,
            Farmer.tenant_id == tenant_id,
        ).first()
        agent_synced_enrollment = db.query(
            FarmerProjectEnrollment
        ).filter(
            FarmerProjectEnrollment.tenant_id == tenant_id,
            FarmerProjectEnrollment.farmer_id == agent_sync_farmer_id,
            FarmerProjectEnrollment.project_id == project_id,
        ).first()
        agent_synced_parcel = db.query(Parcel).filter(
            Parcel.id == agent_sync_parcel_id,
            Parcel.tenant_id == tenant_id,
        ).first()

        require(
            agent_synced_farmer is not None
            and agent_synced_farmer.enrolled_by == agent_user.id,
            "Agent-created farmer records authenticated agent",
        )
        require(
            agent_synced_farmer.user_id is None,
            "Agent enrollment does not impersonate farmer identity",
        )
        require(
            agent_synced_enrollment is not None
            and agent_synced_enrollment.assigned_user_ids
            == [str(agent_user.id)],
            "Agent enrollment persists authenticated assignment",
        )
        require(
            agent_synced_parcel is not None
            and agent_synced_parcel.farmer_id == agent_sync_farmer_id,
            "Dependent parcel is linked to agent-created farmer",
        )

        followup_agent_event = {
            "event_id": str(uuid.uuid4()),
            "entity_type": "PARCEL",
            "entity_id": str(agent_sync_parcel_id),
            "operation": "UPDATE",
            "payload": {
                "farmer_id": str(agent_sync_farmer_id),
                "local_name": "AGENT-SYNC-FOLLOWUP",
            },
            "version": 2,
            "dependency_ids": [],
            "metadata": {"source": "agent_sync_followup_regression"},
        }
        followup_agent_sync = client.post(
            "/api/v1/sync/events",
            headers=agent_headers,
            json={"events": [followup_agent_event]},
        )
        require(
            followup_agent_sync.status_code == 200
            and followup_agent_sync.json()["accepted"]
            == [followup_agent_event["event_id"]],
            "Persisted assignment authorizes later agent sync",
            followup_agent_sync.text,
        )

        def parcel_sync_event(parcel, farmer, label):
            return {
                "event_id": str(uuid.uuid4()),
                "entity_type": "PARCEL",
                "entity_id": str(parcel.id),
                "operation": "UPDATE",
                "payload": {
                    "farmer_id": str(farmer.id),
                    "local_name": label,
                },
                "version": 1,
                "dependency_ids": [],
                "metadata": {"source": "sync_persona_regression"},
            }

        personal_sync_event = parcel_sync_event(
            personal_parcel,
            personal,
            "PERSONAL-SYNC",
        )
        personal_sync = client.post(
            "/api/v1/sync/events",
            headers=farmer_headers,
            json={"events": [personal_sync_event]},
        )
        require(
            personal_sync.status_code == 200
            and personal_sync.json()["accepted"]
            == [personal_sync_event["event_id"]],
            "Farmer syncs personal parcel",
            personal_sync.text,
        )

        unrelated_sync_event = parcel_sync_event(
            unrelated_parcel,
            unrelated,
            "UNRELATED-FARMER-SYNC",
        )
        unrelated_sync = client.post(
            "/api/v1/sync/events",
            headers=farmer_headers,
            json={"events": [unrelated_sync_event]},
        )
        require(
            unrelated_sync.status_code == 200
            and unrelated_sync.json()["accepted"] == []
            and unrelated_sync.json()["failed"][0]["error_code"]
            == "SYNC_SCOPE_DENIED",
            "Farmer cannot sync unrelated parcel",
            unrelated_sync.text,
        )

        assisted_sync_event = parcel_sync_event(
            assisted_parcel,
            assisted,
            "ASSIGNED-AGENT-SYNC",
        )
        assisted_sync = client.post(
            "/api/v1/sync/events",
            headers=agent_headers,
            json={"events": [assisted_sync_event]},
        )
        require(
            assisted_sync.status_code == 200
            and assisted_sync.json()["accepted"]
            == [assisted_sync_event["event_id"]],
            "Assigned agent syncs assisted parcel",
            assisted_sync.text,
        )

        unassigned_sync_event = parcel_sync_event(
            assisted_parcel,
            assisted,
            "UNASSIGNED-AGENT-SYNC",
        )
        unassigned_sync = client.post(
            "/api/v1/sync/events",
            headers=unassigned_headers,
            json={"events": [unassigned_sync_event]},
        )
        require(
            unassigned_sync.status_code == 200
            and unassigned_sync.json()["accepted"] == []
            and unassigned_sync.json()["failed"][0]["error_code"]
            == "SYNC_SCOPE_DENIED",
            "Unassigned agent cannot sync assisted parcel",
            unassigned_sync.text,
        )

        admin_sync_event = parcel_sync_event(
            unrelated_parcel,
            unrelated,
            "ADMIN-SYNC",
        )
        admin_sync = client.post(
            "/api/v1/sync/events",
            headers=admin_headers,
            json={"events": [admin_sync_event]},
        )
        require(
            admin_sync.status_code == 200
            and admin_sync.json()["accepted"]
            == [admin_sync_event["event_id"]],
            "Web administrator syncs tenant parcel",
            admin_sync.text,
        )

        mixed_allowed_parcel_id = uuid.uuid4()
        mixed_allowed = {
            "event_id": str(uuid.uuid4()),
            "entity_type": "PARCEL",
            "entity_id": str(mixed_allowed_parcel_id),
            "operation": "CREATE",
            "payload": {
                "farmer_id": str(personal.id),
                "project_id": str(project_id),
                "local_name": "MIXED-ALLOWED",
                "village_name_manual": "Crop Persona Village",
                "reported_area": 1,
                "reported_area_unit": "ACRE",
                "ownership_type": "OWNED",
                "status": "ACTIVE",
            },
            "version": 1,
            "dependency_ids": [],
            "metadata": {"source": "sync_persona_mixed_regression"},
        }
        mixed_denied = parcel_sync_event(
            unrelated_parcel,
            unrelated,
            "MIXED-DENIED",
        )
        mixed_sync = client.post(
            "/api/v1/sync/events",
            headers=farmer_headers,
            json={"events": [mixed_allowed, mixed_denied]},
        )
        mixed_body = mixed_sync.json()
        require(
            mixed_sync.status_code == 200,
            "Mixed sync batch returns 200",
            mixed_sync.text,
        )
        require(
            mixed_body["accepted"] == [mixed_allowed["event_id"]],
            "Mixed sync batch commits authorized event",
            mixed_body,
        )
        require(
            len(mixed_body["failed"]) == 1
            and mixed_body["failed"][0]["event_id"]
            == mixed_denied["event_id"]
            and mixed_body["failed"][0]["error_code"]
            == "SYNC_SCOPE_DENIED",
            "Mixed sync batch rejects unauthorized event",
            mixed_body,
        )
        require(
            mixed_body["total_processed"] == 2,
            "Mixed sync batch counts both events",
            mixed_body,
        )

        db.expire_all()
        require(
            db.query(Parcel).filter(
                Parcel.id == mixed_allowed_parcel_id,
                Parcel.tenant_id == tenant_id,
            ).first().local_name == "MIXED-ALLOWED",
            "Authorized mixed event is materialized",
        )
        require(
            db.query(Parcel).filter(
                Parcel.id == unrelated_parcel.id,
                Parcel.tenant_id == tenant_id,
            ).first().local_name == "ADMIN-SYNC",
            "Denied mixed event is not materialized",
        )

        print({
            "schema_version": "crop_cycle_persona_behavior.v1",
            "personal_farmer": True,
            "assigned_agent": True,
            "unassigned_denied": True,
            "unrelated_denied": True,
            "admin_tenant_scope": True,
            "verified_actor_attribution": True,
        })
        print("CROP CYCLE PERSONA BEHAVIOR PASSED")
    finally:
        db.rollback()

        db.query(CropActivity).filter(
            CropActivity.tenant_id == tenant_id
        ).delete(synchronize_session=False)
        db.query(CropStageInstance).filter(
            CropStageInstance.tenant_id == tenant_id
        ).delete(synchronize_session=False)
        db.query(CropCycle).filter(
            CropCycle.tenant_id == tenant_id
        ).delete(synchronize_session=False)
        db.query(FarmerProjectEnrollment).filter(
            FarmerProjectEnrollment.tenant_id == tenant_id
        ).delete(synchronize_session=False)
        db.query(Parcel).filter(
            Parcel.tenant_id == tenant_id
        ).delete(synchronize_session=False)
        db.query(Farmer).filter(
            Farmer.tenant_id == tenant_id
        ).delete(synchronize_session=False)
        db.query(ProjectRole).filter(
            ProjectRole.project_id == project_id
        ).delete(synchronize_session=False)
        db.query(AgentProfile).filter(
            AgentProfile.tenant_id == tenant_id
        ).delete(synchronize_session=False)
        db.query(Project).filter(
            Project.tenant_id == tenant_id
        ).delete(synchronize_session=False)
        db.execute(
            text("DELETE FROM sync_conflicts WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_id},
        )
        db.execute(
            text("DELETE FROM sync_processed_events WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_id},
        )
        db.execute(
            text("DELETE FROM audit_chain WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_id},
        )
        db.commit()

        for user_id in created_user_ids:
            delete_test_admin(db, user_id)

        db.query(Tenant).filter(
            Tenant.id == tenant_id
        ).delete(synchronize_session=False)
        db.commit()
        db.close()

        print("PASS Crop-cycle persona rows are cleaned")


if __name__ == "__main__":
    main()

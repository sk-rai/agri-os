#!/usr/bin/env python3
"""HTTP behavior contract for persona-scoped field-event mutations."""

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
    Parcel,
    Project,
    ProjectRole,
    Tenant,
)
from app.modules.media.models import (
    FieldEventReport,
    MediaAsset,
    MediaAttachment,
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
        mobile_number=f"9{uuid.uuid4().int % 1000000000:09d}",
        display_name=name,
        village_name_manual="Attachment Village",
        total_land_unit="ACRE",
        status="ACTIVE",
        created_at=now(),
        updated_at=now(),
    )


def make_parcel(tenant_id, project_id, farmer_id, survey):
    return Parcel(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        project_id=project_id,
        farmer_id=farmer_id,
        village_name_manual="Attachment Village",
        reported_area=1,
        reported_area_unit="ACRE",
        survey_number=survey,
        ownership_type="OWNED",
        status="ACTIVE",
        created_at=now(),
        updated_at=now(),
    )


def make_asset(tenant_id, project_id, farmer_id, user_id, marker):
    return MediaAsset(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        project_id=project_id,
        farmer_id=farmer_id,
        uploaded_by=user_id,
        media_type="PHOTO",
        mime_type="image/jpeg",
        storage_key=f"attachment-persona/{marker}.jpg",
        upload_status="UPLOADED",
        metadata_={"marker": marker},
        created_at=now(),
        updated_at=now(),
    )


def attach(client, headers, asset_id, entity_type, entity_id, purpose="GENERAL"):
    return client.post(
        "/api/v1/media/attachments",
        headers=headers,
        json={
            "media_asset_id": str(asset_id),
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "purpose": purpose,
        },
    )



def create_event(client, headers, project_id, farmer_id, parcel_id, marker):
    return client.post(
        "/api/v1/field-events",
        headers=headers,
        json={
            "project_id": str(project_id),
            "farmer_id": str(farmer_id),
            "parcel_id": str(parcel_id),
            "event_type": "PEST",
            "severity": "HIGH",
            "description": marker,
            "source": "EXTERNAL_API",
            "external_source": "caller-spoof",
            "external_event_id": "caller-spoof-id",
            "metadata": {"marker": marker},
        },
    )


def patch_status(client, headers, event_id, status, reason):
    return client.patch(
        f"/api/v1/field-events/{event_id}/status",
        headers=headers,
        json={"status": status, "reason": reason},
    )

def main():
    tenant_id = f"media-attachment-persona-{uuid.uuid4().hex[:8]}"
    project_id = uuid.uuid4()
    other_project_id = uuid.uuid4()
    created_user_ids = []

    db = SessionLocal()
    db.expire_on_commit = False
    try:
        db.add(Tenant(
            id=tenant_id,
            name="Media Attachment Persona Tenant",
            type="ENTERPRISE",
            created_at=now(),
            updated_at=now(),
        ))
        db.commit()

        farmer_user, farmer_headers = create_test_admin(
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
        created_user_ids.extend([
            farmer_user.id,
            agent_user.id,
            unassigned_user.id,
            admin_user.id,
        ])

        project = Project(
            id=project_id,
            tenant_id=tenant_id,
            name="Attachment Project",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=180),
            status="ACTIVE",
            geography_scope={},
            crop_scope=["RICE"],
            config={},
            created_at=now(),
            updated_at=now(),
        )
        other_project = Project(
            id=other_project_id,
            tenant_id=tenant_id,
            name="Other Attachment Project",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=180),
            status="ACTIVE",
            geography_scope={},
            crop_scope=["MAIZE"],
            config={},
            created_at=now(),
            updated_at=now(),
        )
        db.add_all([project, other_project])
        db.flush()

        personal_farmer = make_farmer(
            tenant_id, project_id, "Personal Farmer", farmer_user.id
        )
        assisted_farmer = make_farmer(
            tenant_id, project_id, "Assisted Farmer"
        )
        unrelated_farmer = make_farmer(
            tenant_id, project_id, "Unrelated Farmer"
        )
        other_project_farmer = make_farmer(
            tenant_id, other_project_id, "Other Project Farmer"
        )
        db.add_all([
            personal_farmer,
            assisted_farmer,
            unrelated_farmer,
            other_project_farmer,
        ])
        db.flush()

        personal_parcel = make_parcel(
            tenant_id, project_id, personal_farmer.id, "PERSONAL-1"
        )
        assisted_parcel = make_parcel(
            tenant_id, project_id, assisted_farmer.id, "ASSISTED-1"
        )
        unrelated_parcel = make_parcel(
            tenant_id, project_id, unrelated_farmer.id, "UNRELATED-1"
        )
        other_project_parcel = make_parcel(
            tenant_id,
            other_project_id,
            other_project_farmer.id,
            "OTHER-PROJECT-1",
        )
        db.add_all([
            personal_parcel,
            assisted_parcel,
            unrelated_parcel,
            other_project_parcel,
        ])
        db.flush()

        event = FieldEventReport(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            project_id=project_id,
            farmer_id=assisted_farmer.id,
            parcel_id=assisted_parcel.id,
            event_type="PEST",
            severity="HIGH",
            event_date=now(),
            reported_at=now(),
            source="FIELD_AGENT_ANDROID",
            status="REPORTED",
            metadata_={"regression": True},
            created_at=now(),
            updated_at=now(),
        )
        db.add(event)

        agent_profile = AgentProfile(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=agent_user.id,
            agent_code="ATTACHMENT-AGENT",
            role_type="FIELD_AGENT",
            display_name="Attachment Agent",
            mobile_number=agent_user.mobile_number,
            status="ACTIVE",
            skills=["CROP_HEALTH"],
            languages=["en"],
            territory_scope={},
            availability={},
            certification={},
            metadata_={"regression": True},
            created_at=now(),
            updated_at=now(),
        )
        unassigned_profile = AgentProfile(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=unassigned_user.id,
            agent_code="ATTACHMENT-UNASSIGNED",
            role_type="FIELD_AGENT",
            display_name="Unassigned Attachment Agent",
            mobile_number=unassigned_user.mobile_number,
            status="ACTIVE",
            skills=[],
            languages=["en"],
            territory_scope={},
            availability={},
            certification={},
            metadata_={"regression": True},
            created_at=now(),
            updated_at=now(),
        )
        db.add_all([agent_profile, unassigned_profile])

        db.add_all([
            ProjectRole(
                id=uuid.uuid4(),
                project_id=project_id,
                user_id=agent_user.id,
                role="FIELD_AGENT",
                territory_scope={},
                created_at=now(),
                updated_at=now(),
            ),
            ProjectRole(
                id=uuid.uuid4(),
                project_id=project_id,
                user_id=unassigned_user.id,
                role="FIELD_AGENT",
                territory_scope={},
                created_at=now(),
                updated_at=now(),
            ),
        ])

        db.add(FarmerProjectEnrollment(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            farmer_id=assisted_farmer.id,
            project_id=project_id,
            enrollment_method="ASSISTED",
            enrollment_source="ATTACHMENT_PERSONA_REGRESSION",
            status="ACTIVE",
            parcel_ids=[str(assisted_parcel.id)],
            assigned_user_ids=[str(agent_user.id)],
            metadata_={"regression": True},
            created_at=now(),
            updated_at=now(),
        ))

        personal_asset = make_asset(
            tenant_id,
            project_id,
            personal_farmer.id,
            farmer_user.id,
            "personal",
        )
        assisted_asset = make_asset(
            tenant_id,
            project_id,
            assisted_farmer.id,
            agent_user.id,
            "assisted",
        )
        db.add_all([personal_asset, assisted_asset])
        db.commit()

        ids = {
            "personal_farmer": personal_farmer.id,
            "assisted_farmer": assisted_farmer.id,
            "unrelated_farmer": unrelated_farmer.id,
            "personal_parcel": personal_parcel.id,
            "assisted_parcel": assisted_parcel.id,
            "unrelated_parcel": unrelated_parcel.id,
            "other_project_parcel": other_project_parcel.id,
            "event": event.id,
            "personal_asset": personal_asset.id,
            "assisted_asset": assisted_asset.id,
        }
    finally:
        db.close()

    client = TestClient(app)

    try:
        personal = create_event(
            client,
            farmer_headers,
            project_id,
            ids["personal_farmer"],
            ids["personal_parcel"],
            "personal-farmer-report",
        )
        require(
            personal.status_code == 201,
            "Farmer reports an event for personal farmer profile",
            personal.text,
        )
        personal_body = personal.json()
        require(
            personal_body["source"] == "FARMER_ANDROID",
            "Farmer event source is server derived",
            personal.text,
        )
        require(
            personal_body["metadata"]["reported_by_user_id"]
                == str(farmer_user.id),
            "Farmer event records authenticated reporter",
            personal.text,
        )
        require(
            personal_body["external_source"] is None
                and personal_body["external_event_id"] is None,
            "Human reporter cannot impersonate external provider",
            personal.text,
        )

        assisted = create_event(
            client,
            agent_headers,
            project_id,
            ids["assisted_farmer"],
            ids["assisted_parcel"],
            "assigned-agent-report",
        )
        require(
            assisted.status_code == 201,
            "Assigned agent reports an assisted-farmer event",
            assisted.text,
        )
        assisted_body = assisted.json()
        assisted_event_id = assisted_body["id"]
        require(
            assisted_body["source"] == "FIELD_AGENT_ANDROID",
            "Assigned-agent event source is server derived",
            assisted.text,
        )
        require(
            assisted_body["metadata"]["reported_by_user_id"]
                == str(agent_user.id),
            "Agent event records authenticated reporter",
            assisted.text,
        )

        unrelated = create_event(
            client,
            farmer_headers,
            project_id,
            ids["assisted_farmer"],
            ids["assisted_parcel"],
            "unrelated-farmer-report",
        )
        require(
            unrelated.status_code == 403,
            "Farmer cannot report for unrelated assisted farmer",
            unrelated.text,
        )

        unassigned = create_event(
            client,
            unassigned_headers,
            project_id,
            ids["assisted_farmer"],
            ids["assisted_parcel"],
            "unassigned-agent-report",
        )
        require(
            unassigned.status_code == 403,
            "Unassigned agent cannot report for assisted farmer",
            unassigned.text,
        )

        farmer_review = patch_status(
            client,
            farmer_headers,
            personal_body["id"],
            "UNDER_REVIEW",
            "Farmer attempts review",
        )
        require(
            farmer_review.status_code == 403,
            "Farmer cannot perform review transition",
            farmer_review.text,
        )

        unassigned_review = patch_status(
            client,
            unassigned_headers,
            assisted_event_id,
            "UNDER_REVIEW",
            "Unassigned agent attempts review",
        )
        require(
            unassigned_review.status_code == 403,
            "Unassigned agent cannot review assisted-farmer event",
            unassigned_review.text,
        )

        assigned_review = patch_status(
            client,
            agent_headers,
            assisted_event_id,
            "UNDER_REVIEW",
            "Assigned agent reviews event",
        )
        require(
            assigned_review.status_code == 200,
            "Assigned agent moves event under review",
            assigned_review.text,
        )
        require(
            assigned_review.json()["metadata"]["status_history"][-1][
                "actor_user_id"
            ] == str(agent_user.id),
            "Review history records assigned agent",
            assigned_review.text,
        )

        agent_publish = patch_status(
            client,
            agent_headers,
            assisted_event_id,
            "ADVISORY_SENT",
            "Agent attempts publication",
        )
        require(
            agent_publish.status_code == 403,
            "Assigned agent cannot mark advisory sent",
            agent_publish.text,
        )

        admin_publish = patch_status(
            client,
            admin_headers,
            assisted_event_id,
            "ADVISORY_SENT",
            "Web admin confirms advisory publication",
        )
        require(
            admin_publish.status_code == 200,
            "Web administrator marks advisory sent",
            admin_publish.text,
        )
        require(
            admin_publish.json()["metadata"]["status_history"][-1][
                "actor_user_id"
            ] == str(admin_user.id),
            "Publication history records web administrator",
            admin_publish.text,
        )

        backwards = patch_status(
            client,
            admin_headers,
            assisted_event_id,
            "UNDER_REVIEW",
            "Invalid backwards transition",
        )
        require(
            backwards.status_code == 409,
            "Backwards field-event transition is rejected",
            backwards.text,
        )

        print({
            "schema_version": "field_event_persona_behavior.v1",
            "farmer_report": True,
            "assigned_agent_report": True,
            "unassigned_denied": True,
            "farmer_review_denied": True,
            "assigned_agent_review": True,
            "admin_advisory_sent": True,
            "backwards_transition_denied": True,
        })
        print("FIELD EVENT PERSONA BEHAVIOR PASSED")
    finally:
        cleanup = SessionLocal()
        try:
            cleanup.query(MediaAttachment).filter(
                MediaAttachment.tenant_id == tenant_id
            ).delete(synchronize_session=False)
            cleanup.query(FieldEventReport).filter(
                FieldEventReport.tenant_id == tenant_id
            ).delete(synchronize_session=False)
            cleanup.query(MediaAsset).filter(
                MediaAsset.tenant_id == tenant_id
            ).delete(synchronize_session=False)
            cleanup.query(Parcel).filter(
                Parcel.tenant_id == tenant_id
            ).delete(synchronize_session=False)
            cleanup.query(FarmerProjectEnrollment).filter(
                FarmerProjectEnrollment.tenant_id == tenant_id
            ).delete(synchronize_session=False)
            cleanup.query(AgentProfile).filter(
                AgentProfile.tenant_id == tenant_id
            ).delete(synchronize_session=False)
            cleanup.query(ProjectRole).filter(
                ProjectRole.project_id.in_([project_id, other_project_id])
            ).delete(synchronize_session=False)
            cleanup.query(Farmer).filter(
                Farmer.tenant_id == tenant_id
            ).delete(synchronize_session=False)
            cleanup.query(Project).filter(
                Project.tenant_id == tenant_id
            ).delete(synchronize_session=False)
            for user_id in created_user_ids:
                delete_test_admin(cleanup, user_id)
            cleanup.query(Tenant).filter(
                Tenant.id == tenant_id
            ).delete(synchronize_session=False)
            cleanup.commit()
        finally:
            cleanup.close()

    verify = SessionLocal()
    try:
        counts = {
            "attachments": verify.query(MediaAttachment).filter(
                MediaAttachment.tenant_id == tenant_id
            ).count(),
            "assets": verify.query(MediaAsset).filter(
                MediaAsset.tenant_id == tenant_id
            ).count(),
            "events": verify.query(FieldEventReport).filter(
                FieldEventReport.tenant_id == tenant_id
            ).count(),
            "farmers": verify.query(Farmer).filter(
                Farmer.tenant_id == tenant_id
            ).count(),
        }
        require(
            counts == {
                "attachments": 0,
                "assets": 0,
                "events": 0,
                "farmers": 0,
            },
            "Field-event persona rows are cleaned",
            counts,
        )
    finally:
        verify.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

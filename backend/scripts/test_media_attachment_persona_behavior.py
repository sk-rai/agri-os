#!/usr/bin/env python3
"""HTTP behavior contract for persona-scoped generic media attachments."""

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
        created_user_ids.extend([
            farmer_user.id,
            agent_user.id,
            unassigned_user.id,
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
        missing = attach(
            client,
            {"X-Tenant-ID": tenant_id},
            ids["personal_asset"],
            "FARMER",
            ids["personal_farmer"],
        )
        require(
            missing.status_code == 401,
            "Attachment creation rejects missing bearer",
            missing.text,
        )

        farmer_target = attach(
            client,
            farmer_headers,
            ids["personal_asset"],
            "FARMER",
            ids["personal_farmer"],
            "AUDIO_NOTE",
        )
        require(
            farmer_target.status_code == 201,
            "Farmer attaches own asset to personal farmer profile",
            farmer_target.text,
        )
        require(
            farmer_target.json()["metadata"]["created_by_user_id"]
                == str(farmer_user.id),
            "Attachment records authenticated farmer actor",
            farmer_target.text,
        )

        parcel_target = attach(
            client,
            farmer_headers,
            ids["personal_asset"],
            "PARCEL",
            ids["personal_parcel"],
            "PARCEL_BOUNDARY",
        )
        require(
            parcel_target.status_code == 201,
            "Farmer attaches own asset to personal parcel",
            parcel_target.text,
        )

        field_event_target = attach(
            client,
            agent_headers,
            ids["assisted_asset"],
            "FIELD_EVENT",
            ids["event"],
            "DISEASE_PHOTO",
        )
        require(
            field_event_target.status_code == 201,
            "Assigned agent attaches asset to assisted farmer field event",
            field_event_target.text,
        )
        require(
            field_event_target.json()["metadata"]["created_by_user_id"]
                == str(agent_user.id),
            "Attachment records authenticated agent actor",
            field_event_target.text,
        )

        unrelated_target = attach(
            client,
            farmer_headers,
            ids["personal_asset"],
            "FARMER",
            ids["unrelated_farmer"],
        )
        require(
            unrelated_target.status_code == 403,
            "Farmer cannot attach asset to unrelated farmer",
            unrelated_target.text,
        )

        cross_farmer = attach(
            client,
            agent_headers,
            ids["assisted_asset"],
            "PARCEL",
            ids["unrelated_parcel"],
        )
        require(
            cross_farmer.status_code == 403,
            "Cross-farmer asset and target mismatch is rejected",
            cross_farmer.text,
        )

        cross_project = attach(
            client,
            agent_headers,
            ids["assisted_asset"],
            "PARCEL",
            ids["other_project_parcel"],
        )
        require(
            cross_project.status_code == 403,
            "Cross-project attachment is rejected",
            cross_project.text,
        )

        unassigned = attach(
            client,
            unassigned_headers,
            ids["assisted_asset"],
            "FIELD_EVENT",
            ids["event"],
        )
        require(
            unassigned.status_code == 403,
            "Unassigned agent cannot attach assisted-farmer media",
            unassigned.text,
        )

        unsupported = attach(
            client,
            farmer_headers,
            ids["personal_asset"],
            "SOIL_PROFILE",
            uuid.uuid4(),
            "SOIL_CARD",
        )
        require(
            unsupported.status_code == 403,
            "Unmapped generic attachment target fails closed",
            unsupported.text,
        )
        require(
            unsupported.json()["detail"]["error"]
                == "MEDIA_ATTACHMENT_TARGET_UNSUPPORTED",
            "Unsupported target returns stable error code",
            unsupported.text,
        )

        tenant_mismatch = attach(
            client,
            {**farmer_headers, "X-Tenant-ID": "default"},
            ids["personal_asset"],
            "FARMER",
            ids["personal_farmer"],
        )
        require(
            tenant_mismatch.status_code == 403,
            "Attachment creation rejects token/header tenant mismatch",
            tenant_mismatch.text,
        )

        print({
            "schema_version": "media_attachment_persona_behavior.v1",
            "farmer_target": True,
            "parcel_target": True,
            "assigned_field_event_target": True,
            "unrelated_denied": True,
            "cross_farmer_denied": True,
            "cross_project_denied": True,
            "unassigned_denied": True,
            "unsupported_failed_closed": True,
        })
        print("MEDIA ATTACHMENT PERSONA BEHAVIOR PASSED")
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
            "Attachment persona rows are cleaned",
            counts,
        )
    finally:
        verify.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
